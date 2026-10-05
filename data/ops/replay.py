"""Replay of the dataset's W3 complaints through the S0 intake (spec 14 §11, lead 2026-10-05). Deterministic, offline.

Each W3 complaint (queries/pitch/p01 definition) created in the window becomes one templated Spanish message, read by
the B0 rules; the MCP read handlers search the customer's own card transactions, read the score and the deadline;
`PolicyEngine.decide` decides. Several candidates or none → the engine asks, and the contact ends there. One candidate
the customer must confirm (D-067, zone medium) → the customer is assumed to confirm it [assumption]. The writes go to
an in-memory store with mode `replay`, as the MCP write tools would leave them, for the spec 14 job to read.

[assumption] "Today" is the complaint's creation date: replay pins `clock.today` to DEMO_TODAY, so the read tools run
with their `utc_now` hook at the complaint's creation instant (the same date arithmetic, another today). Gold is read
by column name: complaints and customers here, card transactions in `mcp_server.gold`; never `is_fraud` or gold_eval.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import polars as pl

from contracts import tools as t
from nick_of_time import ids
from nick_of_time.nlu import NLU
from nick_of_time.policy import DecisionInput, PolicyEngine, load_policies
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "mcp"))
from mcp_server.gate import Call, SessionRow  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402
from mcp_server.reads import read_handlers  # noqa: E402

WINDOW = (dt.date(2025, 6, 1), dt.date(2026, 6, 1))          # 12 months, 2025-06..2026-05 [half-open]
TZ = {"México": "America/Mexico_City", "Colombia": "America/Bogota", "Argentina": "America/Argentina/Buenos_Aires"}
SESSION = "S-replay0000000000"


def w3(frame: pl.LazyFrame) -> pl.LazyFrame:
    """The W3 rules CMP-01..03 of queries/pitch/p01_w3_share_complaints.sql."""
    tx = (pl.col("category") == "Transactions") & pl.col("case_type").is_in(["Claim", "Complaint", "Request"])
    return frame.filter(tx | ((pl.col("category") == "Fees") & pl.col("case_type").is_in(["Claim", "Complaint"])))


def complaints(gold: Path, window: tuple[dt.date, dt.date] = WINDOW) -> pl.DataFrame:
    if "gold_eval" in Path(gold).resolve().parts:                       # constitution #7
        raise ValueError("the replay reads data/gold only, never gold_eval")
    cols = ("complaint_id", "creation_date", "customer_id", "category", "case_type", "subcategory", "claimed_amount",
            "currency")
    start, end = (dt.datetime.combine(d, dt.time()) for d in window)
    country = pl.scan_parquet(Path(gold) / "customers.parquet").select("customer_id", "country")
    return (w3(pl.scan_parquet(Path(gold) / "complaints.parquet").select(cols))
            .filter((pl.col("creation_date") >= start) & (pl.col("creation_date") < end))
            .join(country, on="customer_id", how="left").sort("complaint_id").collect())


def message(row: dict[str, Any]) -> str:
    """The customer's first message, from the category or subcategory and the claimed amount (ES; MX, CO, AR)."""
    amount = row["claimed_amount"]
    said = "" if amount is None else f" de {amount:.2f}" + (f" {row['currency']}" if row["currency"] else "")
    if row["subcategory"] == "Cargo no reconocido":
        return f"Hola, no reconozco un cargo{said} en mi tarjeta."
    if row["subcategory"] == "Cobro indebido":
        return f"Hola, me cobraron de más{said} en mi tarjeta, es un cobro indebido."
    return f"Hola, quiero reclamar un {'cargo' if row['category'] == 'Transactions' else 'cobro'}{said} de mi tarjeta."


class Replay:
    def __init__(self, gold: Path, store: MemoryStore, now: list[dt.datetime]):
        self.store, self.now, self.nlu = store, now, NLU()
        self.policies = load_policies()
        self.engine = PolicyEngine(self.policies)
        self.gold = Gold(gold)
        self.tools = read_handlers(self.gold, self.policies, utc_now=lambda: self.now[0])

    def call(self, tool: str, customer: str, **args: Any) -> Any:
        at = self.now[0]
        session = SessionRow(session_id=SESSION, customer_id=customer, verified_at=at, language="es", mode="live",
                             expires_at=at + dt.timedelta(minutes=15))
        model = {"search_transaction": t.SearchTransactionIn, "get_fraud_score": t.GetFraudScoreIn,
                 "compute_deadline": t.ComputeDeadlineIn, "get_customer_profile": t.GetCustomerProfileIn}[tool]
        return self.tools[tool](Call(tool, session, "T-replay"), model(session_id=SESSION, **args))

    def contact(self, n: int, row: dict[str, Any]) -> dict[str, Any]:
        local = row["creation_date"].replace(tzinfo=ZoneInfo(TZ.get(row["country"], "UTC")))
        self.now[0], customer, today = local.astimezone(dt.UTC), row["customer_id"], local.date()
        read = self.nlu.parse(message(row), "es", today=today)
        slots = read.slots
        query = {"amount": float(slots.amount) if slots.amount else None, "currency": slots.currency,
                 "approx_date": slots.date, "merchant": slots.merchant}
        found = self.call("search_transaction", customer, **{k: v for k, v in query.items() if v is not None})
        candidates = getattr(found, "candidates", [])
        profile = self.call("get_customer_profile", customer)
        facts: dict[str, Any] = {"candidates": len(candidates)}
        trx = candidates[0] if len(candidates) == 1 else None
        if trx is not None:
            score = self.call("get_fraud_score", customer, transaction_id=trx.transaction_id)
            card = self.gold.transaction(customer, trx.transaction_id)
            facts |= {"score": getattr(score, "score", None), "score_source": getattr(score, "source", None),
                      "amount": trx.amount, "currency": trx.currency, "product_type": card.product_type}
        base = dict(session_state="verified", intent=read.intent, intent_confidence=read.confidence,
                    dispute_detected=read.dispute_detected, injection_flagged=read.injection_flagged,
                    cross_customer=False, supervised_mode=False, country=getattr(profile, "country", None), **facts)
        decision = self.engine.decide(DecisionInput(**base))
        confirmed = decision.decision == "confirm"                      # zone medium: the customer says yes
        if confirmed:
            decision = self.engine.decide(DecisionInput(**base, customer_confirmed=True))
        out = {"month": today.strftime("%Y-%m"), "country": row["country"], "candidates": min(len(candidates), 2),
               "zone": decision.zone, "confirmed": confirmed or (trx is not None and not (slots.amount or slots.date))}
        if decision.decision == "ask":
            return out | {"outcome": "asked_several" if len(candidates) > 1 else "asked_none"}
        if "open_case" not in decision.allowed_actions:
            return out | {"outcome": "other"}
        if any(c.transaction_id == trx.transaction_id and self.store.queue_status(c.case_id) != "closed"
               for c in self.store.list_cases(customer, run_id=None)):
            return out | {"outcome": "duplicate"}                       # AC-23: the active case answers, nothing opens
        self.open(n, customer, today, base["country"], trx, card, decision, read.intent)
        return out | {"outcome": "automated" if decision.decision == "block_and_open_case" else "handoff"}

    def open(self, n: int, customer: str, day: dt.date, country: str, trx: Any, card: Any, decision: Any,
             intent: str) -> None:
        trace, store = f"T-replay-{n:06d}", self.store
        clock = self.call("compute_deadline", customer, transaction_id=trx.transaction_id)
        dated = isinstance(clock, t.ComputeDeadlineOut)
        legal = {"credit_deadline": clock.credit_deadline, "ruling_deadline": clock.ruling_deadline,
                 "deadline_source": clock.deadline_source, "deadline_source_url": clock.source_url,
                 "deadline_verified_on": clock.verified_on} if dated else {}
        opened = ids.new_id("action")
        case = store.create_case(NewCase(
            customer_id=customer, transaction_id=trx.transaction_id, product_id=trx.product_id,
            country=country, product_type="debit" if "Débito" in card.product_type else "credit",
            zone=decision.zone, dispute_type=intent if intent == "wrongful_charge" else "unrecognized_charge",
            opened_on=day, mode="replay", trace_id=trace, **legal), actor="agent", action_id=opened)
        store.record_verification(case.case_id, opened, read="get_case", run_id=None, customer_id=customer,
                                  actor="agent", trace_id=trace)
        if decision.decision == "block_and_open_case":
            block = ids.new_id("action")
            store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id=trace)
            store.record_verification(case.case_id, block, read="get_product_status", run_id=None,
                                      customer_id=customer, actor="agent", trace_id=trace)
            store.change_status(case.case_id, "verification", on=day, actor="agent", trace_id=trace)
        else:
            store.change_status(case.case_id, "review", on=day, actor="agent", trace_id=trace)
            store.append_event(case.case_id, "handoff_emitted", actor="agent", trace_id=trace, payload={})
        deadline = {k: str(legal[k]) for k in ("credit_deadline", "ruling_deadline") if legal.get(k)} or None
        store.append_event(case.case_id, "receipt_issued", actor="agent", trace_id=trace,
                           payload={"receipt": {"receipt_id": ids.new_id("receipt"), "deadline": deadline}})


def run(gold: Path, window: tuple[dt.date, dt.date] = WINDOW,
        limit: Optional[int] = None) -> tuple[MemoryStore, pl.DataFrame]:
    """The store holding the replay's writes and one outcome row per contact (no id, name or text)."""
    now = [dt.datetime(2025, 6, 1, tzinfo=dt.UTC)]
    store = MemoryStore(now=lambda: now[0])
    replay, rows = Replay(gold, store, now), complaints(gold, window)
    rows = rows if limit is None else rows.head(limit)
    outcomes = [replay.contact(n, row) for n, row in enumerate(rows.iter_rows(named=True), 1)]
    schema = {"month": pl.Utf8, "country": pl.Utf8, "candidates": pl.Int64, "zone": pl.Utf8, "confirmed": pl.Boolean,
              "outcome": pl.Utf8}
    return store, pl.DataFrame(outcomes, schema=schema)
