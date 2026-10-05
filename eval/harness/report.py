"""What a run set leaves behind (spec 10 §7): meta.json, the web summary, and the guard of the sealed held-out."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from eval.harness import labels as label_module
from eval.harness import metrics, seal_guard
from eval.harness.client import HarnessError

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "eval/PROTOCOL.md"
HELDOUT_HASH = ROOT / "eval/heldout.sha256"
HELDOUT_CASES = ROOT / "eval/cases/heldout.jsonl"
WEB_SUMMARY = ROOT / "apps/web/public/data/evaluation_summary.json"
SMALL_CELL = 5                                               # §4.1: a cell with fewer cases is flagged


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol_seal(path: Path = PROTOCOL) -> dict[str, Optional[str]]:
    """Status and protocol hash from the seal block of eval/PROTOCOL.md; the harness reads nothing else of it."""
    fields = seal_guard.seal_fields(path.read_text(encoding="utf-8"))
    sha = fields.get("Protocol sha256", "")
    return {"status": fields.get("Status", "UNSEALED"), "sha256": sha if seal_guard.HEX64.fullmatch(sha) else None}


def check_heldout(cases: Path, protocol: Path = PROTOCOL, hash_file: Path = HELDOUT_HASH) -> None:
    """AC-07: the held-out runs only when the protocol is SEALED and the case file is the hashed one."""
    status = protocol_seal(protocol)["status"]
    if status != "SEALED":
        raise HarnessError(f"the held-out is not available: eval/PROTOCOL.md is {status}, not SEALED (use --set dev)")
    if not hash_file.exists():
        raise HarnessError("the held-out is not available: eval/heldout.sha256 is missing")
    if not cases.is_file():
        raise HarnessError(f"the held-out is not available: the case file {cases} is missing")
    if sha256_of(cases) != hash_file.read_text(encoding="ascii").strip():
        raise HarnessError(f"{cases.name} is not the sealed held-out: its sha256 differs from eval/heldout.sha256")


def check_heldout_cases(cases: list[dict[str, Any]], protocol: Optional[Path] = None,
                        hash_file: Optional[Path] = None, sealed_cases: Optional[Path] = None) -> None:
    """AC-07 for callers of run_set (spec 15 FR-06): a case of the held-out set runs only under check_heldout, and
    only as it is in the sealed file, so an edited copy of a held-out case is refused too."""
    heldout = [case for case in cases if case.get("set") == "heldout"]
    if not heldout:
        return
    sealed_cases = sealed_cases or HELDOUT_CASES
    check_heldout(sealed_cases, protocol or PROTOCOL, hash_file or HELDOUT_HASH)
    lines = sealed_cases.read_text(encoding="utf-8").splitlines()
    sealed = {case["id"]: case for case in map(json.loads, filter(str.strip, lines))}
    changed = sorted(case.get("id", "?") for case in heldout if sealed.get(case.get("id")) != case)
    if changed:
        raise HarnessError(f"{len(changed)} held-out case(s) differ from the sealed file: {', '.join(changed[:5])}")


def _run_meta(records: list[dict[str, Any]]) -> dict[str, Any]:
    """What the system under test reported about itself (git SHA, models, prompt hash, policies version; AC-05).
    The first ok run's meta, plus `drift` with every field that changed between runs of the same arm (a redeploy
    or a config change mid-run), so the run set is not reported as one configuration when it was not."""
    metas = [(record["final_state"] or {}).get("run_meta") or {} for record in records if record["status"] == "ok"]
    if not metas:
        return {}
    drift = {key: values for key in sorted({key for meta in metas for key in meta})
             if len(values := list(dict.fromkeys(json.dumps(meta.get(key), sort_keys=True) for meta in metas))) > 1}
    return {**metas[0], **({"drift": {key: [json.loads(v) for v in values] for key, values in drift.items()}}
                           if drift else {})}


def _arms(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {arm: [record for record in records if record["arm"] == arm]
            for arm in dict.fromkeys(record["arm"] for record in records)}


def meta(records: list[dict[str, Any]], cases: Path, started_at: str, protocol: Path = PROTOCOL) -> dict[str, Any]:
    return {"label": "[simulated]", "harness_git_sha": git_sha(), "cases_file": cases.name,
            "cases_sha256": sha256_of(cases), "protocol": protocol_seal(protocol), "started_at": started_at,
            "ended_at": now(), "runs": len(records),
            "failed_runs": sum(1 for record in records if record["status"] == "failed"),
            "arms": {arm: _run_meta(mine) for arm, mine in _arms(records).items()}}


def web_summary(records: list[dict[str, Any]], run_meta: dict[str, Any],
                fraud_labels: Optional[dict[str, bool]] = None) -> dict[str, Any]:
    """`{generated_at, git_sha, source, data}` of spec 01 §6.2 with the `data` of spec 10 §7.2."""
    arms = []
    for arm, mine in _arms(records).items():
        cells: dict[tuple, list] = {}
        for record in mine:
            cells.setdefault((record["language"], record["type"], record.get("segment") or "unknown"), []).append(record)
        stats = metrics.group(mine)
        arms.append({
            "arm": arm, "run_meta": run_meta["arms"].get(arm, {}),
            "overall": {name: stats[name] for name in metrics.RATES},
            "cells": [{"language": language, "type": type_, "segment": segment,
                       "n_cases": len({record["case_id"] for record in runs}),
                       "small": len({record["case_id"] for record in runs}) < SMALL_CELL,
                       "metrics": {name: value for name, value in metrics.group(runs).items() if name in metrics.RATES}}
                      for (language, type_, segment), runs in sorted(cells.items())],
            "latency_ms": {"p50": stats["latency_p50_ms"]["value"], "p95": stats["latency_p95_ms"]["value"]},
            "cost_usd": {"per_case": stats["cost_per_case_usd"]["value"],
                         "per_resolution": stats["cost_per_resolution_usd"]["value"]},
            "blocks_vs_label": None if fraud_labels is None else label_module.blocks_vs_label(mine, fraud_labels)})
    cases = {record["case_id"] for record in records}
    per_case = max((sum(1 for record in mine if record["case_id"] == case_id) for mine in _arms(records).values()
                    for case_id in cases), default=0)
    return {"generated_at": run_meta["ended_at"], "git_sha": run_meta["harness_git_sha"],
            "source": "eval/harness [simulated] — final state of scripted cases, see eval/PROTOCOL.md",
            "data": {"label": "[simulated]", "set": next(iter({record["set"] for record in records}), None),
                     "cases": len(cases), "runs_per_case": per_case, "cases_sha256": run_meta["cases_sha256"],
                     "protocol": run_meta["protocol"], "arms": arms}}


def write_reports(records: list[dict[str, Any]], out: Path, run_meta: dict[str, Any],
                  web: Optional[Path] = None, labels_path: Optional[Path] = None) -> dict[str, Any]:
    """meta.json and evaluation_summary.json in the run folder, and the web copy when `web` is given (AC-11)."""
    labels_path = labels_path or label_module.LABELS
    wanted = {record["expected_transaction_id"] for record in records if record.get("expected_transaction_id")}
    wanted |= {(record.get("final_state") or {}).get("transaction_id") for record in records} - {None}
    summary = web_summary(records, run_meta, label_module.load_labels(wanted, labels_path))
    for path, payload in ((out / "meta.json", run_meta), (out / "evaluation_summary.json", summary),
                          *(((web, summary),) if web else ())):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary
