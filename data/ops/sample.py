"""A small seeded in-memory store for the ops job (spec 14 §8: developed on the in-memory store until spec 05 is
deployed). Its figures are `[simulated]` illustrations, never operation: the CLI writes them under data/ops/, not to
the public page. Covers every zone, a verified block, receipts with and without a deadline, a handoff, analyst
decisions, LLM calls, a denial, one evaluation case (`run_id`) and one live case on a synthetic transaction.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import polars as pl

from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore

REPLAY_DAY = dt.date(2026, 6, 1)                      # DEMO_TODAY (ADR 0020)
COUNTRY = {"México": "MX", "Colombia": "CO", "Argentina": "AR"}
PRODUCT = {"Tarjeta Débito": "debit", "Tarjeta Crédito": "credit"}
DEADLINE = {"credit_deadline": "2026-06-03", "deadline_source": "Banxico 3/2012"}


def gold_transactions(gold: Path, n: int = 4) -> list[dict[str, Any]]:
    """The first `n` card transactions of gold (by id) with a resolved customer, as the seeder takes them."""
    customers = pl.scan_parquet(Path(gold) / "customers.parquet").select("customer_id", "country")
    rows = (pl.scan_parquet(Path(gold) / "transactions_enriched.parquet")
            .select("transaction_id", "customer_id", "product_id", "product_type")
            .filter(pl.col("product_type").is_in(list(PRODUCT)) & pl.col("customer_id").is_not_null())
            .sort("transaction_id").head(n).join(customers, on="customer_id").collect())
    return [{**r, "country": COUNTRY.get(r["country"], "XX"), "product_type": PRODUCT[r["product_type"]]}
            for r in rows.iter_rows(named=True)]


def _analyst(store: MemoryStore, case_id: str, action: str, to: Any, reason: Any = None) -> None:
    store.record_analyst_action(AnalystActionIn(case_id=case_id, actor_id="sample-analyst", action=action,
                                                reason=reason, idempotency_key=ids.new_id("action")),
                                new_status=to, on=REPLAY_DAY, trace_id="T-analyst")


def seed(store: MemoryStore, txns: list[dict[str, Any]], live_day: dt.date = dt.date(2026, 10, 5)) -> MemoryStore:
    """Replay cases on `txns` (zones high, medium, human in turn), plus one eval and one synthetic live case."""
    zones = ("high", "medium", "human")
    plan = [(t, zones[i % 3], "replay", None, REPLAY_DAY) for i, t in enumerate(txns)]
    plan += [(txns[0], "high", "replay", "eval-sample:S0:1", REPLAY_DAY)]
    plan += [({**txns[0], "transaction_id": "TRX-SYNTHETIC000000000001"}, "high", "live", None, live_day)]
    for n, (t, zone, mode, run_id, day) in enumerate(plan):
        trace = f"T-{n}"
        case = store.create_case(NewCase(
            customer_id=t["customer_id"], transaction_id=t["transaction_id"], product_id=t["product_id"],
            country=t["country"], product_type=t["product_type"], zone=zone, dispute_type="unrecognized_charge",
            opened_on=day, mode=mode, run_id=run_id, trace_id=trace), actor="agent", action_id=ids.new_id("action"))
        store.add_llm_call(trace_id=trace, provider="fake", model="fake-graph", tokens_in=900 + n, tokens_out=120,
                           latency_ms=1500 + 250 * n, cost_usd="0.0042", run_id=run_id)
        if zone == "high":
            block = ids.new_id("action")
            store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id=trace)
            store.record_verification(case.case_id, block, read="get_product_status", run_id=run_id,
                                      customer_id=case.customer_id, actor="agent", trace_id=trace)
            store.change_status(case.case_id, "verification", on=day, actor="agent", trace_id=trace)
        if zone != "human":
            deadline = DEADLINE if zone == "high" else None
            store.append_event(case.case_id, "receipt_issued", actor="agent", trace_id=trace,
                               payload={"receipt": {"receipt_id": ids.new_id("receipt"), "deadline": deadline}})
        if zone != "high":
            store.change_status(case.case_id, "review", on=day, actor="agent", trace_id=trace)
            store.append_event(case.case_id, "handoff_emitted", actor="agent", trace_id=trace, payload={})
        if zone == "human":
            store.add_denial(trace_id=trace, session_id=None, actor="agent", policy_id="POL-CROSS-CUSTOMER")
        if mode == "replay" and run_id is None and zone == "high":
            _analyst(store, case.case_id, "take", "review")
            _analyst(store, case.case_id, "approve_block", None)
            _analyst(store, case.case_id, "resolve", "resolved", "block kept after review")
            _analyst(store, case.case_id, "close_case", "closed", "customer informed")
        elif mode == "replay" and run_id is None and zone == "medium":
            _analyst(store, case.case_id, "take", "review")
            _analyst(store, case.case_id, "approve_block", None)
    return store
