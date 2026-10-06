"""The three series of ops_kpis.json (spec 14 §7.4 and §11): Bank today `[data]`, With Nick of Time `[simulated]` and
Live (pending until T5), over 2026-01..2026-05, per month and a 5-month total.

The headline pair is the lead's goal metric: the bank's FCR (resolved at first contact) against the system's complete
intake at first contact (spec 10 §4.1 `complete_intake_rate`: a case on the reported charge, the expected queue
status, a receipt with its legal deadline). Both also carry `days_to_receipt`, `escalated` and
`outside_sla_at_intake`; `resolution_days` exists for the bank only, since a person decides it (not simulated).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

import duckdb
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ASIS_SQL = ROOT / "queries" / "ops" / "asis_monthly.sql"
FCR_CSV = ROOT / "queries" / "pitch" / "p02_fcr_complaint_vs_bank.csv"
WINDOW = ["2026-01", "2026-05"]
LIVE = {"key": "live", "name": "Live", "status": "pending", "message": "Pending: no live traffic yet",
        "reason": "spec 14 T5 (the Postgres source) has not run on live traffic"}


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
                "escalated": "Complaints with status Escalated at the dataset's snapshot.",
                "outside_sla_at_intake": "The dataset's own sla_breached flag, counted by intake month.",
                "resolution_days": "Bank only: a person decides the final resolution, so it is not simulated."}}


def replay(tables: dict[str, pl.DataFrame], contacts: pl.DataFrame) -> dict[str, Any]:
    kpis = (tables["ops_kpis"].filter(pl.col("mode") == "replay")
            .with_columns(pl.col("day").dt.strftime("%Y-%m").alias("month")))
    cases = kpis.group_by("month").agg(pl.col("cases").sum(), pl.col("receipt_rate_numerator").sum().alias("dated"),
                                       pl.col("escalation_rate_numerator").sum().alias("handoffs"))
    seen = contacts.group_by("month").agg(
        pl.len().alias("contacts"), pl.col("complete_intake").sum().alias("complete"),
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
                "escalated": rate(r["handoffs"], n), "outside_sla_at_intake": rate(opened - r["dated"], opened),
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
                                   "contact; a person then decides. It is not the bank's resolved-at-first-contact.",
                "days_to_receipt": "0 days: the receipt with its legal deadline comes in the same conversation. "
                                   "Contacts that end with a question have no receipt yet and are left out.",
                "escalated": "Cases handed to a person at intake (medium or human zone), over all contacts. Most "
                             "charges carry a low bank score, so a person decides them by design.",
                "outside_sla_at_intake": "Cases opened at first contact with no legal deadline, over cases opened.",
                "safe_automated_resolution": "High-zone charges the system blocked and verified with no person, over "
                                             "the contacts whose charge is in the high zone. Few charges are, so it is "
                                             "a small secondary figure, not the value claim.",
                "asked": "The engine asks when the search finds several candidate charges, or none; the replay "
                         "ends the contact there."}}


def build(tables: dict[str, pl.DataFrame], contacts: Optional[pl.DataFrame],
          asis_frame: Optional[pl.DataFrame]) -> dict[str, Any]:
    return {"window": WINDOW, "bank_today": None if asis_frame is None else bank_today(asis_frame),
            "replay": None if contacts is None else replay(tables, contacts), "live": LIVE}
