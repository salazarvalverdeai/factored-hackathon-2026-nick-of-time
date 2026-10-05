"""Gold (spec 14 §7.3, T3): `ops_kpis` per day × mode and `feedback_cases`, from silver operation rows only.

Operation = `run_id` null (AC-07): evaluation rows stay in bronze and silver and never reach gold; synthetic live
cases count only in `mode = live` rows and are never a label. No gold column holds a customer id, name, document,
transcript, notification text, fraud label or score (AC-08). Everything here is `[simulated]` until real customers.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import polars as pl

from nick_of_time.audit import LifecycleEvent, check_lifecycle

DECIDING = ("approve_credit", "approve_block", "unblock_card", "resolve", "close_case")


def percentile(values: list[int], q: float) -> Optional[int]:
    """Nearest rank, as `eval/harness/metrics.percentile` (spec 10 §4.1); not imported, so the job never loads the
    harness and its label reader (constitution #7)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)] if ordered else None


def unsafe_cases(cases: pl.DataFrame, events: pl.DataFrame) -> set[str]:
    """Cases with a critical finding of the audit checks that run on store rows alone: A7 (lifecycle). A3-A6 need
    the turn's reply, receipt and tool results, which the store does not keep [assumption]."""
    unsafe: set[str] = set()
    for (mode,), part in cases.group_by("mode", maintain_order=True):
        ids = set(part["case_id"])
        lifecycle = []
        for e in events.filter(pl.col("case_id").is_in(list(ids))).sort("case_id", "seq").iter_rows(named=True):
            if e["type"] in ("case_opened", "status_changed"):
                status = "new" if e["type"] == "case_opened" else e["status_to"]
                lifecycle.append(LifecycleEvent(case_id=e["case_id"], type="status", status=status, actor=e["actor"]))
            elif e["type"] == "analyst_action" and e["action"] == "approve_credit":
                lifecycle.append(LifecycleEvent(case_id=e["case_id"], type="provisional_credit", actor=e["actor"]))
        keys = list(part.select("case_id", "customer_id", "transaction_id").iter_rows())
        finding = check_lifecycle(lifecycle, case_keys=keys)
        for key, value in (finding.observed or {}).items():
            unsafe |= set(value) if key.startswith("duplicate:") else {key}
    return unsafe


def _rate(num: str, den: str, name: str) -> list[pl.Expr]:
    return [pl.col(num).alias(f"{name}_numerator"), pl.col(den).alias(f"{name}_denominator"),
            pl.when(pl.col(den) > 0).then(pl.col(num) / pl.col(den)).alias(name)]


def ops_kpis(silver: dict[str, pl.DataFrame]) -> pl.DataFrame:
    cases = silver["cases"].filter(pl.col("run_id").is_null())
    unsafe = unsafe_cases(cases, silver["case_events"])
    day = cases.select("case_id", pl.col("opened_on").alias("day"), "mode")
    calls = silver["llm_calls"].filter(pl.col("run_id").is_null()).join(day, on="case_id")
    denials = silver["policy_denials"].filter(pl.col("run_id").is_null()).join(day, on="case_id")
    base = (cases.with_columns(pl.col("case_id").is_in(list(unsafe)).alias("unsafe"))
            .group_by(pl.col("opened_on").alias("day"), "mode")
            .agg(pl.len().alias("cases"), pl.col("receipt_has_deadline").sum().alias("receipts"),
                 pl.col("handoff_emitted").sum().alias("handoffs"), pl.col("unsafe").sum().alias("unsafe_outcomes"),
                 (pl.col("block_verified") & ~pl.col("handoff_emitted")).sum().alias("automated")))
    spend = calls.sort("call_id").group_by("day", "mode").agg(
        pl.col("cost_usd").sum().alias("cost_usd"), pl.col("latency_ms").alias("_lat"))
    spend = spend.with_columns(pl.col("_lat").map_elements(lambda v: percentile(list(v), 0.95), return_dtype=pl.Int64)
                               .alias("latency_p95_ms")).drop("_lat")
    nd = denials.group_by("day", "mode").agg(pl.len().alias("denials"))
    out = (base.join(spend, on=["day", "mode"], how="left").join(nd, on=["day", "mode"], how="left")
           .with_columns(pl.col("cost_usd").fill_null(0.0).round(6), pl.col("denials").fill_null(0)))
    return out.select(
        "day", "mode", "cases", *_rate("receipts", "cases", "receipt_rate"),
        *_rate("handoffs", "cases", "escalation_rate"), *_rate("automated", "cases", "automated_rate"),
        "unsafe_outcomes", "cost_usd",
        (pl.col("cost_usd") / pl.col("cases")).round(6).alias("cost_per_case"), "latency_p95_ms", "denials",
    ).with_columns(pl.col("^.*_numerator$", "^.*_denominator$", "cases", "unsafe_outcomes", "denials")
                   .cast(pl.Int64)).sort("day", "mode")


def _agent_decision(blocked: bool) -> str:
    return "block_and_open_case" if blocked else "open_case"


def _agreed(agent: str, analyst: str) -> bool:
    """[assumption] The analyst kept the proposal unless the decision reverses the intake action."""
    return not ((agent == "block_and_open_case" and analyst == "unblock_card")
                or (agent == "open_case" and analyst == "approve_block"))


def feedback_cases(silver: dict[str, pl.DataFrame]) -> pl.DataFrame:
    cases = silver["cases"].filter(pl.col("run_id").is_null() & ~pl.col("synthetic"))
    events = silver["case_events"].filter(pl.col("case_id").is_in(cases["case_id"].implode()))
    blocked = set(events.filter((pl.col("type") == "card_blocked")
                                & ~pl.col("actor").str.starts_with("analyst:"))["case_id"])
    last = (events.filter((pl.col("type") == "analyst_action") & pl.col("action").is_in(DECIDING))
            .sort("case_id", "seq").group_by("case_id", maintain_order=True).last()
            .select("case_id", pl.col("action").alias("analyst_decision"), pl.col("reason").alias("analyst_reason"),
                    pl.col("created_at").alias("decided_at")))
    rows: list[dict[str, Any]] = []
    for row in cases.join(last, on="case_id").sort("case_id").iter_rows(named=True):
        agent = _agent_decision(row["case_id"] in blocked)
        rows.append({k: row[k] for k in ("case_id", "transaction_id", "country", "segment", "zone", "mode")}
                    | {"agent_decision": agent, "analyst_decision": row["analyst_decision"],
                       "analyst_reason": row["analyst_reason"], "agreed": _agreed(agent, row["analyst_decision"]),
                       "decided_at": row["decided_at"]})
    schema = {"case_id": pl.Utf8, "transaction_id": pl.Utf8, "country": pl.Utf8, "segment": pl.Utf8, "zone": pl.Utf8,
              "mode": pl.Utf8, "agent_decision": pl.Utf8, "analyst_decision": pl.Utf8, "analyst_reason": pl.Utf8,
              "agreed": pl.Boolean, "decided_at": pl.Datetime("us", "UTC")}
    return pl.DataFrame(rows, schema=schema)


def build(silver: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    return {"ops_kpis": ops_kpis(silver), "feedback_cases": feedback_cases(silver)}


def summary(tables: dict[str, pl.DataFrame], mode: str) -> dict[str, Optional[Any]]:
    """The `data` of ops_kpis.json (spec 14 §7.4) for one mode; every figure is `[simulated]`."""
    def rate(r: dict[str, Any], name: str) -> dict[str, Any]:
        return {"value": r[name], "numerator": r[f"{name}_numerator"], "denominator": r[f"{name}_denominator"]}

    days = [{"day": r["day"].isoformat(), "cases": r["cases"], "receipt_rate": rate(r, "receipt_rate"),
             "escalation_rate": rate(r, "escalation_rate"), "unsafe_outcomes": r["unsafe_outcomes"],
             "cost_per_case": r["cost_per_case"], "latency_p95_ms": r["latency_p95_ms"], "denials": r["denials"]}
            for r in tables["ops_kpis"].filter(pl.col("mode") == mode).iter_rows(named=True)]
    feedback = tables["feedback_cases"].filter(pl.col("mode") == mode)
    return {"label": "[simulated]", "mode": mode, "days": days,
            "feedback": {"decided": feedback.height, "agreed": int(feedback["agreed"].sum())}}
