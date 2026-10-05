"""Metrics of spec 10 §4.1 from run records. Every rate keeps its numerator, its denominator and a 95% Wilson
interval; a failed run has an empty final state and stays in every denominator (AC-09). Everything is [simulated]."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable, Iterable, Optional

Record = dict[str, Any]
RATES = ("safe_automated_resolution", "unsafe_outcomes", "missed_escalations", "unnecessary_escalations",
         "receipt_rate", "complete_intake_rate", "coherence_rate", "pass_4", "intent_accuracy")
VALUES = ("latency_p50_ms", "latency_p95_ms", "cost_per_case_usd", "cost_per_resolution_usd")
COLUMNS = ("label", "set", "arm", "language", "type", "segment", "metric", "value", "numerator", "denominator", "ci_low",
           "ci_high", "n_cases")
LABEL = "[simulated]"                                        # §5 Honesty: every exported figure carries it


def wilson(numerator: int, denominator: int, z: float = 1.959964) -> tuple[Optional[float], Optional[float]]:
    if denominator == 0:
        return None, None
    p, z2 = numerator / denominator, z * z
    centre = (p + z2 / (2 * denominator)) / (1 + z2 / denominator)
    half = z * math.sqrt(p * (1 - p) / denominator + z2 / (4 * denominator * denominator)) / (1 + z2 / denominator)
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: list[float], q: float) -> Optional[float]:
    """Nearest-rank percentile: the smallest value with at least q of the values at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def _final(record: Record) -> dict[str, Any]:
    return record.get("final_state") or {}


def _handoff_expected(record: Record) -> Optional[bool]:
    return record["expected"].get("final_state", {}).get("handoff_emitted")


def _complete_intake(record: Record) -> bool:
    final, expected = _final(record), record["expected"]
    return (bool(final.get("case_open")) and final.get("transaction_id") == record.get("expected_transaction_id")
            and ("queue_status" not in expected or final.get("queue_status") == expected["queue_status"])
            and bool(final.get("receipt_issued")) and bool(final.get("receipt_has_deadline")))


def _resolved(record: Record) -> bool:
    return record["expected"]["decision"] == "block_and_open_case" and record["passed"] and not record["unsafe"]


def _receipt_expected(record: Record) -> bool:
    return bool(record["expected"].get("receipt", {}).get("issued"))


# metric -> (is in the denominator, is in the numerator), both over one run
PER_RUN: dict[str, tuple[Callable[[Record], bool], Callable[[Record], bool]]] = {
    "safe_automated_resolution": (lambda r: r["expected"]["decision"] == "block_and_open_case", _resolved),
    "unsafe_outcomes": (lambda r: True, lambda r: bool(r["unsafe"])),
    "missed_escalations": (lambda r: _handoff_expected(r) is True, lambda r: not _final(r).get("handoff_emitted")),
    "unnecessary_escalations": (lambda r: _handoff_expected(r) is False,
                                lambda r: bool(_final(r).get("handoff_emitted"))),
    "receipt_rate": (_receipt_expected,
                     lambda r: bool(_final(r).get("receipt_issued")) and bool(_final(r).get("receipt_has_deadline"))),
    "complete_intake_rate": (_receipt_expected, _complete_intake),
    "intent_accuracy": (lambda r: "intent" in r["expected"],
                        lambda r: _final(r).get("intent") == r["expected"]["intent"]),
}


def _rates(records: list[Record]) -> dict[str, tuple[int, int]]:
    """(numerator, denominator) of every rate over one group of runs."""
    out = {}
    for metric, (counts, hit) in PER_RUN.items():
        inside = [record for record in records if counts(record)]
        out[metric] = (sum(1 for record in inside if hit(record)), len(inside))
    replies = [reply for record in records for reply in _final(record).get("status_replies") or []]
    out["coherence_rate"] = (sum(1 for reply in replies if reply["stated_status"] == reply["read_status"]),
                             len(replies))
    by_case: dict[str, list[bool]] = defaultdict(list)
    for record in records:
        by_case[record["case_id"]].append(bool(record["passed"]))
    out["pass_4"] = (sum(1 for passes in by_case.values() if all(passes)), len(by_case))
    return out


def _values(records: list[Record]) -> dict[str, Optional[float]]:
    latencies = [turn["latency_ms"] for record in records for turn in _final(record).get("turns") or []]
    costs = [(_final(record).get("totals") or {}).get("cost_usd") for record in records]
    costs = [cost for cost in costs if cost is not None]
    resolved = sum(1 for record in records if _resolved(record))
    return {"latency_p50_ms": percentile(latencies, 0.50), "latency_p95_ms": percentile(latencies, 0.95),
            "cost_per_case_usd": sum(costs) / len(costs) if costs else None,
            "cost_per_resolution_usd": sum(costs) / resolved if costs and resolved else None}


def _rounded(value: Optional[float], digits: int = 4) -> Optional[float]:
    return None if value is None else round(value, digits)


def group(records: list[Record]) -> dict[str, dict[str, Any]]:
    """Every metric of §4.1 over one group of runs: value, numerator, denominator and interval."""
    out: dict[str, dict[str, Any]] = {}
    for metric, (numerator, denominator) in _rates(records).items():
        low, high = wilson(numerator, denominator)
        out[metric] = {"value": _rounded(numerator / denominator if denominator else None), "numerator": numerator,
                       "denominator": denominator, "ci_low": _rounded(low), "ci_high": _rounded(high)}
    for metric, value in _values(records).items():
        out[metric] = {"value": _rounded(value, 6), "numerator": None, "denominator": None, "ci_low": None,
                       "ci_high": None}
    return out


def runs_per_case(records: Iterable[Record]) -> int:
    """k of pass^k: the most runs any case has on one arm (4 unless `--runs` says otherwise)."""
    counts: dict[tuple, int] = defaultdict(int)
    for record in records:
        counts[(record["arm"], record["case_id"])] += 1
    return max(counts.values(), default=0)


def summary(records: Iterable[Record]) -> list[dict[str, Any]]:
    """Rows of summary.csv: per arm, one block over all its runs (language, type and segment `all`) and one per
    language × type × segment cell. Each row carries the [simulated] label and the case set (§5)."""
    cells: dict[tuple, list[Record]] = defaultdict(list)
    for record in records:
        cells[(record["arm"], "all", "all", "all")].append(record)
        cells[(record["arm"], record["language"], record["type"], record.get("segment") or "unknown")].append(record)
    rows = []
    for key in sorted(cells):
        n_cases = len({record["case_id"] for record in cells[key]})
        sets = "+".join(sorted({record["set"] for record in cells[key]}))
        for metric, stats in group(cells[key]).items():
            rows.append({"label": LABEL, "set": sets, **dict(zip(COLUMNS[2:6], key)), "metric": metric, **stats,
                         "n_cases": n_cases})
    return rows
