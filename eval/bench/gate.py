"""Third-party gate per arm (spec 15 section 4.5, AC-10): a verdict for "benchmark" and for "production"."""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).parent
# criterion -> (needed to benchmark, needed for production), from the table of section 4.5
CRITERIA = {
    "synthetic_only": (True, False),
    "no_training": (True, True),
    "retention": (False, True),
    "region": (False, True),
    "certification": (False, True),
    "credentials": (True, True),
    "version_pinning": (True, True),
    "availability": (False, True),
    "es_pt_quality": (False, True),  # the benchmark measures it, so it cannot gate benchmarking (D-012)
}
NOT_DOCUMENTED = "not documented"
FIELDS = ["arm", "criterion", "needed_benchmark", "needed_production", "verdict", "evidence_url", "checked_on"]


def load_evidence(path: Path = HERE / "gate_evidence.yaml") -> dict:
    return yaml.safe_load(path.read_text())


def _provider(arm: dict) -> str | None:
    return arm["provider"] if arm.get("llm") or arm["provider"] == "typesafe" else None


_PINNED = re.compile(r"(\d{8}|-v\d+(:\d+)?$|-\d+:\d+$|\d+\.\d+\.\d+$)")


def version_pinned(model_id: str | None) -> bool:
    """Fallback only, for a provider without lifecycle evidence: the id carries a date, -vN[:M] or x.y.z."""
    return bool(model_id and _PINNED.search(model_id))


def gate_rows(arms: list[dict], evidence: dict, checked_on: str | None = None) -> list[dict]:
    """One row per arm and criterion; no evidence means "not documented", stamped with the evaluation date.
    version_pinning comes from the provider's lifecycle evidence; only without it does the id format decide, and an
    id without a version is then "not documented", never "fail"."""
    today = checked_on or date.today().isoformat()
    rows = []
    for arm in arms:
        prov = _provider(arm)
        if prov is None:  # B0 / B1 call no third party
            continue
        for crit, (b, p) in CRITERIA.items():
            ev = (evidence.get("arms", {}).get(arm["id"], {}).get(crit)
                  or evidence.get("providers", {}).get(prov, {}).get(crit) or {})
            if crit == "version_pinning" and not ev and version_pinned(arm.get("model_id")):
                ev = {"verdict": "pass", "evidence_url": f'model id {arm["model_id"]} (fallback: version in the id)'}
            rows.append({"arm": arm["id"], "criterion": crit, "needed_benchmark": b, "needed_production": p,
                         "verdict": ev.get("verdict", NOT_DOCUMENTED), "evidence_url": ev.get("evidence_url", ""),
                         "checked_on": ev.get("checked_on") or today})
    return rows


def summary(rows: list[dict]) -> dict[str, dict[str, bool]]:
    """Per arm: may it be used to benchmark / in production? Every needed criterion must be a pass."""
    out: dict[str, dict[str, bool]] = {}
    for r in rows:
        a = out.setdefault(r["arm"], {"benchmark": True, "production": True})
        ok = r["verdict"] == "pass"
        if r["needed_benchmark"] and not ok:
            a["benchmark"] = False
        if r["needed_production"] and not ok:
            a["production"] = False
    return out


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
