"""Run loop of the harness (spec 10 FR-01, FR-02, FR-06): one record per case × arm × repetition."""
from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

from eval.harness import metrics, report
from eval.harness.client import Api, HarnessError
from eval.harness.compare import findings, mismatches, unsafe_outcomes


def _expected_transaction(case: dict[str, Any]) -> Any:
    fixtures = case["initial_state"].get("fixtures") or []
    return fixtures[0]["transaction_id"] if len(fixtures) == 1 else None


def run_one(api: Api, case: dict[str, Any], arm: str, k: int) -> dict[str, Any]:
    """One run. A failure of the system under test is a failed run that stays in every denominator (AC-09); a
    HarnessError stops the whole set instead."""
    record = {"run_id": f"{case['id']}:{arm}:{k}", "case_id": case["id"], "arm": arm, "k": k, "set": case["set"],
              "language": case["language"], "type": case["type"], "segment": case.get("segment"),
              "country": case.get("country"), "status": "ok", "error": None, "passed": False, "unsafe": [],
              "mismatches": {}, "findings": [], "final_state": None, "expected": case["expected"],
              "expected_transaction_id": _expected_transaction(case)}
    try:
        final = api.run(case, record["run_id"], arm)
    except HarnessError:
        raise
    except Exception as error:                               # timeout, HTTP error, no FinalState, bad JSON
        return {**record, "status": "failed", "error": f"{type(error).__name__}: {error}"}
    found = findings(final)
    differences = mismatches(case["expected"], final)
    return {**record, "final_state": final, "findings": found, "mismatches": differences,
            "passed": not differences, "unsafe": unsafe_outcomes(case["expected"], final, found)}


def run_set(cases: Iterable[dict[str, Any]], arms: Iterable[str], runs: int = 4, *, api: Api | None = None,
            api_url: str | None = None, workers: int = 4) -> list[dict[str, Any]]:
    """Every case on every arm, `runs` times each (pass^4 needs four). Give `api` or `api_url`. Records come back
    in a fixed order whatever the concurrency. A held-out case runs only after the seal and only as sealed (AC-07):
    the guard lives here, not in the command line, because spec 15 calls this function directly (FR-06)."""
    cases = list(cases)
    report.check_heldout_cases(cases)
    owned = api is None
    if owned:
        if not api_url:
            raise HarnessError("run_set needs api or api_url")
        api = Api.at(api_url)
    jobs = [(case, arm, k) for arm in arms for case in cases for k in range(1, runs + 1)]
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            return list(pool.map(lambda job: run_one(api, *job), jobs))
    finally:
        if owned:
            api.close()


def write_outputs(records: list[dict[str, Any]], out: Path) -> None:
    """runs.jsonl (the full FinalState of every run) and summary.csv (§7.1)."""
    out.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    (out / "runs.jsonl").write_text(lines, encoding="utf-8", newline="\n")
    with (out / "summary.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=metrics.COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(metrics.summary(records))
