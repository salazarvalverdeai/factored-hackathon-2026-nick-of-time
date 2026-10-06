"""Silver (spec 14 §7.2, T2): bronze typed, checked against pandera contracts and joined with gold.

A row that breaks a contract stays in bronze, goes to silver/_quarantine/<table>.parquet with its reason and is
counted; the job goes on (AC-11). Cases are checked first, so an event, call or denial is checked against the cases
that passed. Gold is read by column name only (`transactions_enriched`: id, amount, currency, date; `customers`: id,
segment): never `is_fraud`, `fraud_score` or `gold_eval/`. In live mode a transaction missing from gold is a
synthetic demo transaction (ADR 0020) and is flagged `synthetic`; any other miss raises `qc_gold_missing`.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, get_args

import pandera.polars as pa
import polars as pl
from pandera.errors import SchemaErrors

from nick_of_time.store import ACTOR, EventType
from nick_of_time.store.accounts import DENIAL_ACTOR

TS = pl.Datetime("us", "UTC")
STATUS_TO = ["verification", "review", "resolved", "closed"]                    # spec 01 §6.5 status_changed
# AC-08: `reason` is read from the analyst's and the status change's payloads only; a customer's
# `reevaluation_requested` reason and `customer_info_added` text are the customer's own words and stay in bronze.
REASON_FROM = ("analyst_action", "status_changed")


def _c(dtype: Any, *checks: pa.Check, required: bool = True, unique: bool = False) -> pa.Column:
    return pa.Column(dtype, list(checks), nullable=not required, unique=unique)


def schemas(now: dt.datetime) -> dict[str, pa.DataFrameSchema]:
    """The silver contracts; `now` is the job's run time ("timestamps not in the future")."""
    past = pa.Check.le(now)
    return {
        "cases": pa.DataFrameSchema({
            "case_id": _c(pl.Utf8, pa.Check.str_matches(r"^K-[0-9]{6}$"), unique=True),
            "customer_id": _c(pl.Utf8), "transaction_id": _c(pl.Utf8), "country": _c(pl.Utf8),
            "product_type": _c(pl.Utf8, pa.Check.isin(["debit", "credit"])),
            "zone": _c(pl.Utf8, pa.Check.isin(["high", "medium", "human"])),
            "mode": _c(pl.Utf8, pa.Check.isin(["replay", "live"])), "opened_on": _c(pl.Date),
            "created_at": _c(TS, past)}),
        "case_events": pa.DataFrameSchema({
            "event_id": _c(pl.Utf8, unique=True), "case_id": _c(pl.Utf8), "seq": _c(pl.Int64, pa.Check.ge(1)),
            "type": _c(pl.Utf8, pa.Check.isin(list(get_args(EventType)))),
            "actor": _c(pl.Utf8, pa.Check.str_matches(ACTOR)),
            "status_to": _c(pl.Utf8, pa.Check.isin(STATUS_TO), required=False), "created_at": _c(TS, past)}),
        "llm_calls": pa.DataFrameSchema({
            "call_id": _c(pl.Utf8, unique=True), "trace_id": _c(pl.Utf8),
            "latency_ms": _c(pl.Int64, pa.Check.ge(0)), "cost_usd": _c(pl.Float64, pa.Check.ge(0)),
            "created_at": _c(TS, past)}),
        "policy_denials": pa.DataFrameSchema({
            "denial_id": _c(pl.Utf8, unique=True), "trace_id": _c(pl.Utf8),
            "actor": _c(pl.Utf8, pa.Check.str_matches(DENIAL_ACTOR)), "policy_id": _c(pl.Utf8),
            "created_at": _c(TS, past)}),
    }


def _ts(col: str) -> pl.Expr:
    return pl.col(col).str.to_datetime(time_zone="UTC", strict=False).dt.cast_time_unit("us")


def _load(text: Any) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _payload(frame: pl.DataFrame) -> pl.DataFrame:
    """Typed columns from `payload`; the payload itself (receipt, handoff and customer text) does not reach silver. A
    payload that is not a JSON object is flagged in `_payload_ok` and quarantined."""
    parsed = [_load(p) for p in frame["payload"].to_list()]
    loaded = [p if isinstance(p, dict) else {} for p in parsed]
    receipt = [p.get("receipt") if t == "receipt_issued" else None for p, t in zip(loaded, frame["type"])]
    return frame.drop("payload").with_columns(
        pl.Series("_payload_ok", [isinstance(p, dict) for p in parsed], pl.Boolean),
        pl.Series("status_to", [p.get("to") if t == "status_changed" else None
                                for p, t in zip(loaded, frame["type"])], pl.Utf8),
        pl.Series("action", [p.get("action") if t == "analyst_action" else None
                             for p, t in zip(loaded, frame["type"])], pl.Utf8),
        pl.Series("reason", [p.get("reason") if t in REASON_FROM else None
                             for p, t in zip(loaded, frame["type"])], pl.Utf8),
        pl.Series("receipt_has_deadline", [isinstance(r, dict) and isinstance(r.get("deadline"), dict)
                                           if r is not None else None for r in receipt], pl.Boolean))


def split(frame: pl.DataFrame, schema: pa.DataFrameSchema,
          extra: dict[str, pl.Expr] | None = None) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, int]]:
    """(rows that pass, quarantined rows with `_quarantine_reason`, failures per column:check). `extra` holds
    cross-row rules as boolean expressions that are true when the row passes."""
    frame = frame.with_row_index("_idx").with_columns(pl.col("_idx").cast(pl.Int64))
    reasons: dict[int, set[str]] = {}
    try:
        schema.validate(frame.select(list(schema.columns)), lazy=True)
    except SchemaErrors as error:
        for row in error.failure_cases.filter(pl.col("index").is_not_null()).iter_rows(named=True):
            check = str(row["check"]).split("(")[0]                     # isin([...]) → isin
            reasons.setdefault(int(row["index"]), set()).add(f"{row['column']}:{check}")
    for name, ok in (extra or {}).items():
        for idx in frame.filter(~ok.fill_null(False))["_idx"].to_list():
            reasons.setdefault(idx, set()).add(name)
    counts: dict[str, int] = {}
    for rs in reasons.values():
        for r in rs:
            counts[r] = counts.get(r, 0) + 1
    bad = pl.DataFrame({"_idx": list(reasons), "_quarantine_reason": ["; ".join(sorted(r)) for r in reasons.values()]},
                       schema={"_idx": pl.Int64, "_quarantine_reason": pl.Utf8})
    return (frame.filter(~pl.col("_idx").is_in(list(reasons))).drop("_idx"),
            frame.join(bad, on="_idx").drop("_idx"), dict(sorted(counts.items())))


def read_gold(gold: Path, transaction_ids: list[str], customer_ids: list[str]) -> tuple[pl.DataFrame, pl.DataFrame]:
    if "gold_eval" in Path(gold).resolve().parts:                       # constitution #7
        raise ValueError("the ops job reads data/gold only, never gold_eval")
    txn = (pl.scan_parquet(Path(gold) / "transactions_enriched.parquet")
           .select("transaction_id", "amount", "currency", pl.col("transaction_date").cast(pl.Date))
           .filter(pl.col("transaction_id").is_in(transaction_ids)).collect())
    customers = (pl.scan_parquet(Path(gold) / "customers.parquet").select("customer_id", "segment")
                 .filter(pl.col("customer_id").is_in(customer_ids)).collect())
    return txn, customers


def build(bronze: Path, out: Path, gold: Path, now: dt.datetime) -> dict[str, Any]:
    """Write silver/<table>.parquet and silver/_quarantine/; returns per-table rows and check counts."""
    contract, stats, quarantine = schemas(now), {}, out / "_quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    raw = {t: pl.read_parquet(bronze / f"{t}.parquet").drop("_loaded_at", "_source")
           for t in ("cases", "case_events", "llm_calls", "policy_denials")}

    def keep(table: str, frame: pl.DataFrame, extra: dict[str, pl.Expr] | None = None) -> pl.DataFrame:
        good, bad, failures = split(frame, contract[table], extra)
        (bad.write_parquet(quarantine / f"{table}.parquet") if bad.height
         else (quarantine / f"{table}.parquet").unlink(missing_ok=True))
        stats[table] = {"rows_bronze": frame.height, "quarantined": bad.height, "contract_failures": failures}
        return good

    cases = keep("cases", raw["cases"].with_columns(
        pl.col("opened_on").str.to_date(strict=False), _ts("created_at")).select(
        "case_id", "customer_id", "transaction_id", "product_id", "country", "product_type", "zone", "dispute_type",
        "opened_on", "mode", "run_id", "trace_id", "created_at"))
    events = _payload(raw["case_events"].with_columns(pl.col("seq").cast(pl.Int64, strict=False), _ts("created_at"))
                      .drop("customer_visible"))
    events = keep("case_events", events, {
        "case_id:case_exists": pl.col("case_id").is_in(cases["case_id"].implode()),
        "seq:continuous": pl.col("seq") == pl.col("seq").rank("ordinal").over("case_id").cast(pl.Int64),
        "payload:json_object": pl.col("_payload_ok")})
    events = events.drop("_payload_ok").sort("case_id", "seq")

    txn, customers = read_gold(gold, cases["transaction_id"].unique().to_list(), cases["customer_id"].unique().to_list())
    per_case = events.group_by("case_id", maintain_order=True).agg(
        pl.col("status_to").filter(pl.col("type") == "status_changed").last().fill_null("new").alias("queue_status"),
        pl.col("created_at").filter(pl.col("status_to") == "closed").last().alias("closed_at"),
        (pl.col("type") == "block_verified").any().alias("block_verified"),
        (pl.col("type") == "receipt_issued").any().alias("receipt_issued"),
        pl.col("receipt_has_deadline").fill_null(False).any().alias("receipt_has_deadline"),
        (pl.col("type") == "handoff_emitted").any().alias("handoff_emitted"))
    cases = (cases.join(per_case, on="case_id", how="left")
             .with_columns(pl.col("queue_status").fill_null("new"),
                           *(pl.col(c).fill_null(False) for c in ("block_verified", "receipt_issued",
                                                                   "receipt_has_deadline", "handoff_emitted")))
             .join(txn, on="transaction_id", how="left").join(customers, on="customer_id", how="left")
             .with_columns(synthetic=(pl.col("mode") == "live") & pl.col("amount").is_null())
             .with_columns(qc_gold_missing=pl.col("segment").is_null() | (pl.col("amount").is_null()
                                                                          & ~pl.col("synthetic")))
             .sort("case_id"))
    context = cases.select("case_id", "country", "product_type", "zone", "mode", "run_id", "segment", "amount",
                           "currency", "transaction_date", "synthetic", "qc_gold_missing")
    events = events.join(context, on="case_id", how="left")

    first = (pl.concat([events.select("trace_id", "case_id", "created_at"),
                        cases.select("trace_id", "case_id", "created_at")])
             .sort("created_at", "case_id").unique("trace_id", keep="first", maintain_order=True)
             .select("trace_id", "case_id"))
    calls = keep("llm_calls", raw["llm_calls"].with_columns(
        *(pl.col(c).cast(pl.Int64, strict=False) for c in ("tokens_in", "tokens_out", "latency_ms")),
        pl.col("cost_usd").cast(pl.Float64, strict=False), _ts("created_at")))
    denials = keep("policy_denials", raw["policy_denials"].drop("detail").with_columns(_ts("created_at")))
    tables = {"cases": cases, "case_events": events,
              "llm_calls": calls.join(first, on="trace_id", how="left").sort("call_id"),
              "policy_denials": denials.join(first, on="trace_id", how="left").sort("denial_id")}
    for name, frame in tables.items():
        frame.write_parquet(out / f"{name}.parquet")
        stats[name]["rows_silver"] = frame.height
    stats["cases"]["qc_gold_missing"] = int(cases["qc_gold_missing"].sum())
    stats["cases"]["synthetic"] = int(cases["synthetic"].sum())
    for name in ("llm_calls", "policy_denials"):
        stats[name]["without_case"] = int(tables[name]["case_id"].null_count())
    return {"tables": tables, "stats": stats}
