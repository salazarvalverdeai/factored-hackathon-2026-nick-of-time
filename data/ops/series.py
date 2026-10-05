"""The three series of ops_kpis.json (spec 14 §7.4 and §11): Bank today `[data]`, With Nick of Time `[simulated]` and
Live (pending until T5). Both measured series share four metrics per month and a 12-month total:
`days_to_receipt`, `first_contact_resolution`, `escalated` and `outside_sla_at_intake`; `resolution_days` exists for
the bank only, since a person decides the final resolution and it is not simulated.
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
WINDOW = ["2025-06", "2026-05"]
REPLAY_DOC = "specs/14-ops-lakehouse.md#11-amendment-bank-today-and-replay-over-the-dataset-lead-2026-10-05"
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
                "days_to_receipt": "First response date minus creation date, in days: the closest proxy the dataset "
                                   "has; it records no receipt or legal deadline. Complaints with no first response "
                                   "are left out (missing).",
                "first_contact_resolution": "FCR of the bank's 'Queja' call-center contacts over the whole dataset "
                                            "window (43.6%). The interactions table is not in this repo's gold, so "
                                            "it cannot be split per month: the same value repeats.",
                "escalated": "Complaints with status Escalated at the dataset's snapshot.",
                "outside_sla_at_intake": "The dataset's own sla_breached flag, counted by intake month.",
                "resolution_days": "Bank only: a person decides the final resolution, so it is not simulated."}}


def replay(tables: dict[str, pl.DataFrame], contacts: pl.DataFrame) -> dict[str, Any]:
    kpis = (tables["ops_kpis"].filter(pl.col("mode") == "replay")
            .with_columns(pl.col("day").dt.strftime("%Y-%m").alias("month")))
    cases = kpis.group_by("month").agg(pl.col("cases").sum(), pl.col("receipt_rate_numerator").sum().alias("dated"),
                                       pl.col("escalation_rate_numerator").sum().alias("handoffs"),
                                       pl.col("automated_rate_numerator").sum().alias("automated"))
    seen = contacts.group_by("month").agg(
        pl.len().alias("contacts"), (pl.col("outcome") == "asked_several").sum().alias("asked_several"),
        (pl.col("outcome") == "asked_none").sum().alias("asked_none"), pl.col("confirmed").sum().alias("confirmed"),
        (pl.col("outcome") == "duplicate").sum().alias("duplicates"))
    joined = seen.join(cases, on="month", how="left").fill_null(0).sort("month")
    total = joined.drop("month").sum().with_columns(pl.lit("total").alias("month"))

    def row(r: dict[str, Any]) -> dict[str, Any]:
        n, opened = r["contacts"], r["cases"]
        return {"month": r["month"], "contacts": n, "cases_opened": opened,
                "days_to_receipt": {"p50": 0.0 if r["dated"] else None, "mean": 0.0 if r["dated"] else None,
                                    "n": r["dated"], "missing": n - r["dated"]},
                "first_contact_resolution": rate(r["automated"], n), "escalated": rate(r["handoffs"], n),
                "outside_sla_at_intake": rate(opened - r["dated"], opened),
                "asked_several": rate(r["asked_several"], n), "asked_none": rate(r["asked_none"], n),
                "confirmations_assumed": r["confirmed"], "duplicates": r["duplicates"]}

    return {"key": "replay", "name": "With Nick of Time (simulated)", "label": "[simulated]", "window": WINDOW,
            "source": "python -m data.ops replay: B0 + search_transaction + PolicyEngine.decide over gold complaints, "
                      "then the spec 14 job (ops_kpis, mode replay)",
            "method": REPLAY_DOC, "months": [row(r) for r in joined.iter_rows(named=True)],
            "total": row(total.row(0, named=True)),
            "notes": {
                "days_to_receipt": "0 days: the receipt with its legal deadline is given in the same conversation. "
                                   "Contacts with no such receipt (asked, or opened with no deadline) are missing.",
                "first_contact_resolution": "The safe automated path: card blocked and verified, case opened, no "
                                            "person, over all contacts.",
                "escalated": "Cases handed to a person at intake (zone medium or human), over all contacts.",
                "outside_sla_at_intake": "Cases opened at first contact with no legal deadline (the clock is unknown "
                                         "for that date), over cases opened.",
                "asked": "The engine asks when the search finds several candidate charges, or none; the contact ends "
                         "there in the replay, since the dataset does not say which charge the customer meant."}}


def build(tables: dict[str, pl.DataFrame], contacts: Optional[pl.DataFrame],
          asis_frame: Optional[pl.DataFrame]) -> dict[str, Any]:
    return {"window": WINDOW, "bank_today": None if asis_frame is None else bank_today(asis_frame),
            "replay": None if contacts is None else replay(tables, contacts), "live": LIVE}
