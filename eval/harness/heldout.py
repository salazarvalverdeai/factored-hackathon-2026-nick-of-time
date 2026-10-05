"""Spec 10 T7: the held-out agent run, once (ADR 0007, eval/PROTOCOL.md §0.2 and §2.1).

    make eval-heldout          # = python -m eval.harness run --set heldout --arms S0,S1,S2 --runs 4 --api URL

Order, so that nothing consumes the one run before the stack is known to be right:
1. the arms and runs are the protocol's (S0, S1, S2 × 4); `--cases`, `--out` and `--web` are refused;
2. `seal_guard.check_seal(inputs={"agent_heldout": None})`: the tag, the protocol bytes and the held-out sha256;
3. the S1 model map (MODEL_MAP if spec 15 B2 wrote it, else the default Haiku map, labeled `[assumption]`);
4. the out folder `eval/results/<date>-heldout/` is empty;
5. the projected cost is printed;
6. a preflight on one DEV case per arm, which does not consume the run: api health, replay with DEMO_TODAY, and each
   arm's `run_meta` shows the expected provider and model (the fake provider is refused);
7. `seal_guard.claim_run("heldout", ...)`, the run-once marker; only then is the held-out case file read.
Each run is appended to runs.jsonl as it finishes. If the set stops after the claim, meta.json says
`run_status: "aborted"` and the partial runs stay (lead decision D-079 pending; this is the default). If every run
failed, the command exits non-zero and the web summary is not written.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from eval.harness import report, seal_guard
from eval.harness.client import Api, HarnessError
from eval.harness.run import run_set, write_outputs

ROOT = Path(__file__).resolve().parents[2]
ARMS = ("S0", "S1", "S2")                         # spec 10 AC-03, ADR 0007, PROTOCOL §2.1: S0 is the reference
RUNS = 4                                          # pass^4 (spec 10 §4.1)
RUN_NAME = "heldout"
DEV_CASES = "eval/cases/dev.jsonl"
# The S1 model map chosen on dev by spec 15 B2 (§4.2: "it becomes arm S1"); spec 15 T6 writes it. Shape:
# {"label", "source", "arms": {"S1": {"provider", "model_fast"}, "S2": {"provider", "model_graph"}}}.
MODEL_MAP = "eval/results/model_map.json"
DEMO_TODAY = "2026-06-01"                         # ADR 0020: the replay "today" every evaluation runs on
# Projected cost of the full held-out (80 cases × 4 runs per arm) `[projected]`: the dev run spent 0.037 USD on S1
# for 20 cases × 4 runs `[simulated]` (spec 10 T6), so S1 ≈ 4 × 0.037; S2 (Sonnet 4.6) costs 3× Haiku 4.5 per token
# (eval/bench/prices.yaml `[external]`). The G-OPS-01 cap of 0.02 USD per conversation bounds it at 12.8 USD.
PROJECTED_COST_USD = {"S0": 0.0, "S1": 0.15, "S2": 0.45}


def default_model_map() -> dict[str, Any]:
    from nick_of_time.config import HAIKU, SONNET
    return {"label": "[assumption]",
            "source": f"default map: spec 15 B2 has not written {MODEL_MAP}, so S1 is Haiku 4.5 for every task "
                      "(lead decision D-080 pending)",
            "arms": {"S1": {"provider": "bedrock", "model_fast": HAIKU},
                     "S2": {"provider": "bedrock", "model_graph": SONNET}}}


def load_model_map(root: Path = ROOT) -> dict[str, Any]:
    """The map the held-out confirms against S0: spec 15's chosen map when its file exists, else the default."""
    path = root / MODEL_MAP
    if not path.is_file():
        return default_model_map()
    chosen = json.loads(path.read_text(encoding="utf-8"))
    arms = chosen.get("arms") or {}
    for arm in ("S1", "S2"):
        expected = arms.get(arm) or {}
        if expected.get("provider") in (None, "fake") or not any(expected.get(k) for k in ("model_fast", "model_graph")):
            raise HarnessError(f"{MODEL_MAP} has no real provider and model for {arm}")
    return {"label": chosen.get("label", "[data]"), "source": chosen.get("source", MODEL_MAP), "arms": arms}


def projected_cost() -> dict[str, Any]:
    return {"label": "[projected]", "usd": dict(PROJECTED_COST_USD),
            "total_usd": round(sum(PROJECTED_COST_USD.values()), 2),
            "basis": "dev run S1 0.037 USD for 20 cases x 4 runs [simulated], scaled to 80 cases; S2 at 3x the "
                     "Haiku 4.5 token price (eval/bench/prices.yaml [external])"}


def _expected(arm: str, model_map: dict[str, Any]) -> dict[str, Any]:
    if arm == "S0":
        return {"provider": "none", "model_fast": None, "model_graph": None}
    return dict(model_map["arms"][arm])


def preflight(api: Api, model_map: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """Checks the stack on one dev case per arm; never touches a held-out case and claims nothing."""
    try:
        health = api.http.get("/api/health")
        health.raise_for_status()
        body = health.json()
    except Exception as error:                       # dead port, HTTP error, not JSON
        raise HarnessError(f"preflight: the api health check failed ({type(error).__name__}: {error})") from error
    if body.get("status") != "ok":
        raise HarnessError(f"preflight: the api health is {body.get('status')!r}, not 'ok'")
    replay_today = (body.get("today") or {}).get("replay")
    if replay_today != DEMO_TODAY:
        raise HarnessError(f"preflight: the api's replay today is {replay_today!r}, not DEMO_TODAY {DEMO_TODAY}")
    dev = [json.loads(line) for line in (root / DEV_CASES).read_text(encoding="utf-8").splitlines() if line.strip()]
    case = next((c for c in dev if c.get("set") == "dev"), None)
    if case is None:
        raise HarnessError(f"preflight: {DEV_CASES} has no dev case")
    seen: dict[str, Any] = {}
    for arm in ARMS:
        run_id = f"{case['id']}:{arm}:preflight"
        try:
            final = api.run(case, run_id, arm)          # raises HarnessError if the seeded session is not replay
        except HarnessError:
            raise
        except Exception as error:
            raise HarnessError(f"preflight: the dev case {case['id']} failed on {arm} "
                               f"({type(error).__name__}: {error})") from error
        meta = final.get("run_meta") or {}
        if final.get("mode") != "replay":
            raise HarnessError(f"preflight: {arm} ran in mode {final.get('mode')!r}, not replay")
        if meta.get("provider") == "fake":
            raise HarnessError(f"preflight: {arm} runs on the fake provider; the held-out needs the real models")
        for key, want in _expected(arm, model_map).items():
            if meta.get(key) != want:
                raise HarnessError(f"preflight: {arm} run_meta {key} is {meta.get(key)!r}, expected {want!r}")
        seen[arm] = {"case_id": case["id"], "run_meta": meta}
    return {"health": {k: body.get(k) for k in ("status", "version", "git_sha", "policies_version", "today")},
            "arms": seen}


def _order(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = {case["id"]: i for i, case in enumerate(cases)}
    return sorted(records, key=lambda r: (ARMS.index(r["arm"]), index.get(r["case_id"], len(index)), r["k"]))


def run(args, api: Optional[Api] = None, root: Optional[Path] = None, web: Optional[Path] = None) -> int:
    """`python -m eval.harness run --set heldout` (spec 10 T7). Exit 0 done, 1 every run failed, 2 refused before
    the claim, 3 aborted after the claim (partial results kept)."""
    root = root or ROOT
    web = web or report.WEB_SUMMARY
    arms = tuple(arm for arm in args.arms.split(",") if arm)
    try:
        if arms != ARMS or args.runs != RUNS:
            raise HarnessError(f"the held-out runs only as pre-registered: --arms {','.join(ARMS)} --runs {RUNS} "
                               f"(got --arms {args.arms} --runs {args.runs})")
        if args.cases or args.out or args.web:
            raise HarnessError("the held-out takes no --cases, --out or --web: it reads the sealed case file and "
                               "writes eval/results/<date>-heldout/ and the web summary")
        guard = seal_guard.check_seal(inputs={"agent_heldout": None}, root=root)
        model_map = load_model_map(root)
        out = root / seal_guard.RESULTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}-{RUN_NAME}"
        if out.exists() and any(out.iterdir()):
            raise HarnessError(f"{out} is not empty; the held-out runs once")
        cost = projected_cost()
        print(f"{cost['label']} projected cost of the held-out run: "
              + ", ".join(f"{arm} ~{usd} USD" for arm, usd in cost["usd"].items()) + f", total ~{cost['total_usd']} USD")
        print(f"S1 model map {model_map['label']}: {model_map['source']}")
        owned = api is None
        api = api or Api.at(args.api)
        try:
            checked = preflight(api, model_map, root)
            seal_guard.claim_run(RUN_NAME, out, guard, root=root)
        finally:
            if owned:
                api.close()
                api = None
    except (HarnessError, seal_guard.SealError) as error:
        print(f"harness stopped: {error}", file=sys.stderr)
        return 2

    # The run is claimed: from here on everything that was seen is kept.
    cases_path = root / seal_guard.HELDOUT_CASES
    started = report.now()
    runs_path = out / "runs.jsonl"
    status, error_text, cases = "complete", None, []
    with runs_path.open("a", encoding="utf-8", newline="\n") as sink:
        def keep(record: dict[str, Any]) -> None:
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            sink.flush()
            os.fsync(sink.fileno())
        try:
            cases = [c for c in map(json.loads, filter(str.strip, cases_path.read_text(encoding="utf-8").splitlines()))
                     if c.get("set") == RUN_NAME]
            records = run_set(cases, ARMS, RUNS, api=api, api_url=args.api, workers=args.workers, on_record=keep)
        except BaseException as error:               # HarnessError, a crash, Ctrl-C: keep the partial set
            status, error_text = "aborted", f"{type(error).__name__}: {error}"
            records = None
    if records is None:
        lines = runs_path.read_text(encoding="utf-8").splitlines()
        records = _order([json.loads(line) for line in lines if line.strip()], cases)
    write_outputs(records, out)
    run_meta = {**report.meta(records, cases_path, started, guard=guard), "run_status": status, "error": error_text,
                "arms_pinned": list(ARMS), "runs_per_case": RUNS, "model_map": model_map, "projected_cost": cost,
                "preflight": checked}
    all_failed = not records or all(r["status"] == "failed" for r in records)
    publish = status == "complete" and not all_failed
    if records:
        report.write_reports(records, out, run_meta, web if publish else None)
    else:
        (out / "meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                                       newline="\n")
    if status == "aborted":
        print(f"harness stopped after the claim: {error_text}; {len(records)} runs kept in {out} "
              "(run_status aborted; the web summary was not written)", file=sys.stderr)
        return 3
    if all_failed:
        print(f"every held-out run failed; results kept in {out}, the web summary was not written", file=sys.stderr)
        return 1
    print(f"wrote runs.jsonl, summary.csv, meta.json and evaluation_summary.json in {out} and {web}")
    return 0
