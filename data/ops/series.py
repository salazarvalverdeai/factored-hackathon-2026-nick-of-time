"""The three series of ops_kpis.json (spec 14 §7.4 and §11): Bank today `[data]`, With Nick of Time `[simulated]` and
Live, over 2026-01..2026-05, per month and a 5-month total. Live (T5, key `live`, named "Public demo traffic") is
the deployed app's public demo traffic in both modes, per day since its first case, read from Postgres by
`make ops-live`; pending while there is none (the lead's reading of 2026-10-06, spec 14 §8).

Only two pairs are side by side (`COMPARE`): the lead's goal metric, the bank's FCR against the system's complete
intake at first contact (spec 10 §4.1 `complete_intake_rate`), which measure different things and say so; and the
days to a receipt with a legal deadline (the bank's through a proxy). Every other figure is context of its own series,
with its own definition: the bank's `escalated`, `outside_sla_at_intake` and `resolution_days` (a person decides the
final resolution: not simulated); the system's `handed_to_analyst`, `opened_without_deadline`,
`safe_automated_resolution` and the no-merchant `sensitivity`.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

import duckdb
import polars as pl

from data.ops import gold
from nick_of_time.policy.clock import DEMO_TODAY

ROOT = Path(__file__).resolve().parents[2]
ASIS_SQL = ROOT / "queries" / "ops" / "asis_monthly.sql"
FCR_CSV = ROOT / "queries" / "pitch" / "p02_fcr_complaint_vs_bank.csv"
WINDOW = ["2026-01", "2026-05"]
COMPARE = [{"bank_today": "first_contact_resolution", "replay": "complete_intake"},
           {"bank_today": "days_to_receipt", "replay": "days_to_receipt"}]
LIVE = {"key": "live", "name": "Public demo traffic", "status": "pending",
        "message": "Pending: no public demo traffic yet",
        "reason": "spec 14 T5 (the Postgres source) has not run on the deployed app's demo traffic"}
MODES = ("live", "replay")


def rate(num: int, den: int, **extra: Any) -> dict[str, Any]:
    return {"value": num / den if den else None, "numerator": num, "denominator": den, **extra}


def asis(gold: Path) -> pl.DataFrame:
    """queries/ops/asis_monthly.sql over gold `complaints` (named columns only; never gold_eval)."""
    if "gold_eval" in Path(gold).resolve().parts:
        raise ValueError("the as-is query reads data/gold only, never gold_eval")
    con = duckdb.connect(":memory:")
    source = con.read_parquet(str(Path(gold) / "complaints.parquet")).select(
        "creation_date, first_response_date, category, case_type, status, sla_breached, resolution_days")
    con.register("complaints", source)
    return con.execute(ASIS_SQL.read_text()).pl()


def quota(frame: pl.DataFrame) -> dict[str, int]:
    """Contacts per month of the replay: the bank's W3 complaints of that month."""
    return {r["month"]: r["n_complaints"] for r in frame.iter_rows(named=True) if r["month"] != "total"}


def bank_today(frame: pl.DataFrame) -> dict[str, Any]:
    with FCR_CSV.open(encoding="utf-8") as handle:
        fcr = next(r for r in csv.DictReader(handle) if r["group_name"].startswith("Queja"))
    first = rate(int(fcr["n_resolved"]), int(fcr["denominator"]), constant=True)

    def row(r: dict[str, Any]) -> dict[str, Any]:
        n = r["n_complaints"]
        return {"month": r["month"], "contacts": n,
                "days_to_receipt": {"p50": r["days_to_first_response_p50"], "mean": r["days_to_first_response_mean"],
                                    "n": r["n_first_response"], "missing": r["n_no_first_response"]},
                "first_contact_resolution": first, "escalated": rate(r["n_escalated"], n),
                "outside_sla_at_intake": rate(r["n_sla_breached"], n),
                "resolution_days": {"p50": r["resolution_days_p50"], "n": r["n_resolved"]}}

    rows = [row(r) for r in frame.iter_rows(named=True)]
    return {"key": "bank_today", "name": "Bank today", "label": "[data]", "window": WINDOW,
            "source": "queries/ops/asis_monthly.sql on gold complaints; FCR from queries/pitch/p02_fcr_complaint_vs_bank.csv",
            "months": rows[:-1], "total": rows[-1],
            "notes": {
                "first_contact_resolution": "The bank's FCR means a complaint contact resolved at first contact. It is "
                                            "the 'Queja' call-center value over the whole dataset (43.6%); the contacts "
                                            "table is not in this repo's gold, so the same value repeats each month.",
                "days_to_receipt": "First response date minus creation date, in days: the closest proxy the dataset "
                                   "has, since it records no receipt or legal deadline. Complaints with no first "
                                   "response are left out.",
                "escalated": "Complaints whose status is Escalated at the dataset's snapshot: moved up a level "
                             "inside the bank. Context only; the system has no such status.",
                "outside_sla_at_intake": "The dataset's own sla_breached flag, by intake month. The dataset does not "
                                         "say which SLA it measures. Context only.",
                "resolution_days": "Bank only: a person decides the final resolution, so it is not simulated."}}


def replay(tables: dict[str, pl.DataFrame], contacts: pl.DataFrame) -> dict[str, Any]:
    kpis = (tables["ops_kpis"].filter(pl.col("mode") == "replay")
            .with_columns(pl.col("day").dt.strftime("%Y-%m").alias("month")))
    cases = kpis.group_by("month").agg(pl.col("cases").sum(), pl.col("receipt_rate_numerator").sum().alias("dated"))
    seen = contacts.group_by("month").agg(
        pl.len().alias("contacts"), pl.col("complete_intake").sum().alias("complete"),
        ((pl.col("outcome") == "handoff") & pl.col("complete_intake")).sum().alias("handed"),
        pl.col("expected_block").sum().alias("expected_block"),
        (pl.col("expected_block") & (pl.col("outcome") == "automated") & pl.col("complete_intake")).sum()
        .alias("automated"),
        (pl.col("outcome") == "asked_several").sum().alias("asked_several"),
        (pl.col("outcome") == "asked_none").sum().alias("asked_none"), pl.col("confirmed").sum().alias("confirmed"))
    joined = seen.join(cases, on="month", how="left").fill_null(0).sort("month")
    total = joined.drop("month").sum().with_columns(pl.lit("total").alias("month"))

    def row(r: dict[str, Any]) -> dict[str, Any]:
        n, opened = r["contacts"], r["cases"]
        return {"month": r["month"], "contacts": n, "cases_opened": opened,
                "complete_intake": rate(r["complete"], n),
                "days_to_receipt": {"p50": 0.0 if r["dated"] else None, "mean": 0.0 if r["dated"] else None,
                                    "n": r["dated"], "missing": n - r["dated"]},
                "handed_to_analyst": rate(r["handed"], n), "opened_without_deadline": rate(opened - r["dated"], opened),
                "safe_automated_resolution": rate(r["automated"], r["expected_block"]),
                "asked_several": rate(r["asked_several"], n), "asked_none": rate(r["asked_none"], n),
                "confirmations_assumed": r["confirmed"]}

    return {"key": "replay", "name": "With Nick of Time (simulated)", "label": "[simulated]", "window": WINDOW,
            "source": "make ops-replay: real card charges (queries/ops/replay_sample.sql) through B0, "
                      "search_transaction and PolicyEngine.decide, then the spec 14 job (mode replay)",
            "months": [row(r) for r in joined.iter_rows(named=True)], "total": row(total.row(0, named=True)),
            "notes": {
                "complete_intake": "Complete intake means a case open on the charge the customer named, in the "
                                   "expected queue, with a receipt that carries its legal deadline, all in the first "
                                   "contact; a person then decides. It is not the bank's resolved-at-first-contact. "
                                   "It is an upper bound: the message names the charge exactly as the statement "
                                   "shows it, and real customers misremember amounts and dates.",
                "days_to_receipt": "0 days: the receipt with its legal deadline comes in the same conversation. "
                                   "Contacts that end with a question have no receipt yet and are left out.",
                "handed_to_analyst": "Cases handed to an analyst at first contact with the evidence and the legal "
                                     "deadline, over all contacts. Charges with a medium or low bank score always go "
                                     "to a person, who decides the block or the credit: by design, not a failure.",
                "opened_without_deadline": "Cases opened at first contact with no legal deadline, over cases "
                                           "opened.",
                "safe_automated_resolution": "High-zone charges the system blocked and verified with no person, over "
                                             "the contacts whose charge is in the high zone. Few charges are, so it is "
                                             "a small secondary figure, not the value claim.",
                "asked": "The engine asks when the search finds several candidate charges, or none; the replay "
                         "ends the contact there."}}


def sensitivity(base: pl.DataFrame, variant: pl.DataFrame) -> dict[str, Any]:
    """The same contacts with a message that names only the amount and the date (no merchant)."""
    def figures(frame: pl.DataFrame) -> dict[str, Any]:
        n = frame.height
        return {"complete_intake": rate(int(frame["complete_intake"].sum()), n),
                "asked": rate(int(frame["outcome"].str.starts_with("asked").sum()), n)}

    return {"variant": "the message names the amount and the date, no merchant", "named": figures(base),
            "amount_and_date": figures(variant)}


def build(tables: dict[str, pl.DataFrame], contacts: Optional[pl.DataFrame], asis_frame: Optional[pl.DataFrame],
          variant: Optional[pl.DataFrame] = None) -> dict[str, Any]:
    sim = None if contacts is None else replay(tables, contacts)
    if sim is not None and variant is not None:
        sim["sensitivity"] = sensitivity(contacts, variant)
    return {"window": WINDOW, "compare": COMPARE,
            "bank_today": None if asis_frame is None else bank_today(asis_frame), "replay": sim, "live": LIVE}


def _mode_row(r: Optional[dict[str, Any]], cases: pl.DataFrame) -> dict[str, Any]:
    """One mode of the Live total: its cases, rates and unsafe outcomes over the window (zeros when it has none)."""
    if r is None:
        empty = {"value": None, "numerator": 0, "denominator": 0}
        return {"cases": 0, "receipt_rate": empty, "escalation_rate": empty, "automated_rate": empty,
                "unsafe_outcomes": 0, "demo_sessions": 0, "synthetic_charges": 0}
    return {"cases": r["cases"], "receipt_rate": gold.rate(r, "receipt_rate"),
            "escalation_rate": gold.rate(r, "escalation_rate"), "automated_rate": gold.rate(r, "automated_rate"),
            "unsafe_outcomes": r["unsafe_outcomes"], "demo_sessions": cases["run_id"].drop_nulls().n_unique(),
            "synthetic_charges": int(cases["synthetic"].sum())}


def live(silver: dict[str, pl.DataFrame], as_of: Optional[str]) -> dict[str, Any]:
    """T5: the Live series, "Public demo traffic", from the silver rows of one Postgres snapshot (the lead's reading
    of 2026-10-06, spec 14 §8). It counts the cases of the public demo sessions (`demo-` runs, ADR 0026) and of
    operation (`run_id` null) in both modes, never an evaluation run (AC-07), per day since the first one, with the
    definitions of `ops_kpis` and a breakdown by mode. The day is the UTC date the case row was written: a
    replay-mode case's own date is always the demo date (ADR 0020). Replay-mode demos run over the historical gold
    state and live-mode charges are synthetic, so the series is `[simulated]` demo traffic, not the bank's operation;
    `LIVE` (pending) while there is no such case. Counts and rates only: no id, name or text (AC-08)."""
    cases = silver["cases"].filter(gold.DEMO_TRAFFIC)
    if cases.height == 0:
        return LIVE
    dated = cases.with_columns(pl.col("created_at").dt.date().alias("opened_on"), pl.lit("public").alias("_all"))
    first, last = dated["opened_on"].min(), dated["opened_on"].max()
    scoped = {**silver, "cases": dated}
    kpis = gold.ops_kpis(scoped, gold.DEMO_TRAFFIC, by="_all")
    # the whole window as one day: the same definitions, and the p95 over every call of the window
    window = {**silver, "cases": dated.with_columns(pl.lit(first).alias("opened_on"))}
    total = gold.ops_kpis(window, gold.DEMO_TRAFFIC, by="_all").row(0, named=True)
    per_mode = {r["mode"]: r for r in gold.ops_kpis(window, gold.DEMO_TRAFFIC).iter_rows(named=True)}
    daily = {(r["opened_on"], r["mode"]): r["len"]
             for r in dated.group_by("opened_on", "mode").len().iter_rows(named=True)}
    feedback = gold.feedback_cases(scoped, gold.DEMO_TRAFFIC)
    demo = cases["run_id"].drop_nulls()
    demo_date = DEMO_TODAY.isoformat()
    return {"key": "live", "name": "Public demo traffic", "status": "ready", "label": "[simulated]",
            "message": f"Public demo traffic on the deployed app since {first.isoformat()}",
            "reason": f"Replay-mode demos run over the historical gold state with the fixed demo date {demo_date}, and "
                      "live-mode charges are synthetic (ADR 0020), so every figure is [simulated], not the bank's "
                      "operation. Evaluation runs never count.",
            "source": "make ops-live: the spec 14 job over one read-only Postgres snapshot (public demo sessions and "
                      "operation, both modes; evaluation runs left out)",
            "window": [first.isoformat(), last.isoformat()], "as_of": as_of,
            "days": [{**gold.day_row(r), "automated_rate": gold.rate(r, "automated_rate"),
                      "cases_by_mode": {m: daily.get((r["day"], m), 0) for m in MODES}}
                     for r in kpis.iter_rows(named=True)],
            "total": {**gold.day_row(total), "day": "total", "automated_rate": gold.rate(total, "automated_rate"),
                      "cost_usd": total["cost_usd"], "demo_sessions": demo.n_unique(),
                      "cases_without_demo_session": cases.height - demo.len(),
                      "synthetic_charges": int(cases["synthetic"].sum()),
                      "by_mode": {m: _mode_row(per_mode.get(m), cases.filter(pl.col("mode") == m)) for m in MODES}},
            "feedback": {"decided": feedback.height, "agreed": int(feedback["agreed"].sum())},
            "notes": {
                "cases": "Cases opened on the deployed app by its public demo sessions (each isolated in its own run) "
                         "and by any production session, in both modes. Evaluation runs never count. A handful of "
                         "demo cases a day is an illustration, not a measurement.",
                "day": f"The UTC date the case was written. A replay-mode case's own date is always the demo date "
                       f"{demo_date}, so it is not used.",
                "by_mode": f"Replay mode runs over the dataset's historical state with the fixed demo date {demo_date}; "
                           "live mode uses today's date and synthetic charges, which gold does not hold (ADR 0020).",
                "receipt_rate": "Cases with a receipt that carries its legal deadline, over cases.",
                "escalation_rate": "Cases handed to an analyst (a handoff), over cases. Charges with a medium or low "
                                   "bank score always go to a person, by design.",
                "automated_rate": "Cases with a verified block and no handoff, over cases: the safe automated path.",
                "unsafe_outcomes": "Cases with a critical lifecycle finding of the auditor (A7), checked per mode and "
                                   "session.",
                "cost_per_case": "Model cost of the calls reached through a case, over cases.",
                "latency_p95_ms": "p95 of single model calls, not of a whole turn [assumption].",
                "synthetic_charges": "Cases on a visitor's synthetic charge, which gold does not hold (ADR 0020).",
                "feedback": "Cases an analyst decided, and how many kept the system's proposal; a synthetic charge "
                            "is never a label."}}
