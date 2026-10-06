"""Replay of real card charges through the S0 intake (spec 14 §11.2, lead 2026-10-05). Deterministic, offline, no LLM.

"Synthetic message over real state" (spec 09): queries/ops/replay_sample.sql draws real approved card charges per
month of 2026-01..2026-05, as many as the bank's W3 complaints that month. The customer reports each one the next day
in a templated Spanish message that names it (amount, currency, date, merchant when there is one). The B0 rules read
it; the MCP read handlers search the customer's own card transactions and read the score, the profile and the
deadline; `PolicyEngine.decide` decides. Several candidates or none → the engine asks and the contact ends. A zone
medium confirmation is answered yes [assumption]. Opened cases go to an in-memory store with mode `replay`, as the
MCP write tools leave them, for the spec 14 job; each contact is then checked against the store (complete intake,
spec 10 §4.1: a case on the reported charge, the expected queue status, a receipt with its legal deadline).

[assumption] "Today" is the contact date: replay pins `clock.today` to DEMO_TODAY, so the read handlers run with
their `utc_now` hook at noon of the contact date in the customer's country. Gold is read by column name only; never
`is_fraud` or gold_eval. The bank's `fraud_score` serves only the expected queue status (a policy lookup, as spec 09
derives expected states) and, at runtime, `get_fraud_score`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import duckdb
import polars as pl

from contracts import tools as t
from nick_of_time import ids
from nick_of_time.nlu import NLU
from nick_of_time.policy import DecisionInput, PolicyEngine, load_policies
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
from mcp_server.gate import Call, SessionRow  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402
from mcp_server.reads import read_handlers  # noqa: E402

SAMPLE_SQL = ROOT / "queries" / "ops" / "replay_sample.sql"
TZ = {"México": "America/Mexico_City", "Colombia": "America/Bogota", "Argentina": "America/Argentina/Buenos_Aires"}
SESSION = "S-replay0000000000"
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")


def sample(gold: Path, quota: dict[str, int]) -> pl.DataFrame:
    """queries/ops/replay_sample.sql over gold, `quota` = contacts per month (the bank's W3 complaints)."""
    if "gold_eval" in Path(gold).resolve().parts:                       # constitution #7
        raise ValueError("the replay reads data/gold only, never gold_eval")
    con = duckdb.connect(":memory:")
    con.register("card", con.read_parquet(str(Path(gold) / "transactions_enriched.parquet")).select(
        "transaction_id, customer_id, transaction_date, amount, currency, merchant_name, fraud_score, product_type, "
        "transaction_status"))
    con.register("customers", con.read_parquet(str(Path(gold) / "customers.parquet")).select("customer_id, country"))
    con.register("quota", pl.DataFrame({"month": list(quota), "n": list(quota.values())}))
    rows = con.execute(SAMPLE_SQL.read_text()).pl()
    return rows.join(pl.read_parquet(Path(gold) / "customers.parquet", columns=["customer_id", "country"]),
                     on="customer_id", how="left")


def message(row: dict[str, Any], merchant: bool = True) -> str:
    """The customer names the charge as their statement shows it; half the contacts read as a wrongful charge.
    `merchant=False` is the sensitivity variant: amount and date only."""
    day, shop = row["charged_on"], row["merchant_name"] if merchant else None
    said = f"de {row['amount']:.2f} {row['currency']}" + (f" en {shop}" if shop else "")
    when = f"del {day.day} de {MONTHS[day.month - 1]} de {day.year}"
    if int(hashlib.md5(row["transaction_id"].encode()).hexdigest(), 16) % 2:
        return f"Hola, me cobraron de más: el cargo {said} {when} es un cobro indebido."
    return f"Hola, no reconozco un cargo {said} {when}."


class Replay:
    def __init__(self, gold: Path, store: MemoryStore, now: list[dt.datetime], merchant: bool = True):
        self.store, self.now, self.nlu, self.merchant = store, now, NLU(), merchant
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

    def expected_status(self, row: dict[str, Any], country: Optional[str]) -> str:
        """Spec 09's expected state from the policy file: zone high blocks (verification) unless the amount tier
        needs a person; every other zone hands off (review)."""
        score, high = row["fraud_score"], self.policies.zones["high"].score_min
        tier = self.engine.amount_tier(row["amount"], row["currency"], country)
        return "verification" if score is not None and score >= high and tier != "human_required" else "review"

    def contact(self, n: int, row: dict[str, Any]) -> dict[str, Any]:
        today, customer = row["contact_on"], row["customer_id"]
        self.now[0] = dt.datetime.combine(today, dt.time(12), ZoneInfo(TZ.get(row["country"], "UTC"))).astimezone(dt.UTC)
        read = self.nlu.parse(message(row, self.merchant), "es", today=today)
        slots = read.slots
        query = {"amount": float(slots.amount) if slots.amount else None, "currency": slots.currency,
                 "approx_date": slots.date, "merchant": slots.merchant}
        found = self.call("search_transaction", customer, **{k: v for k, v in query.items() if v is not None})
        candidates = getattr(found, "candidates", [])
        country = getattr(self.call("get_customer_profile", customer), "country", None)
        facts: dict[str, Any] = {"candidates": len(candidates)}
        trx = candidates[0] if len(candidates) == 1 else None
        if trx is not None:
            score = self.call("get_fraud_score", customer, transaction_id=trx.transaction_id)
            card = self.gold.transaction(customer, trx.transaction_id)
            facts |= {"score": getattr(score, "score", None), "score_source": getattr(score, "source", None),
                      "amount": trx.amount, "currency": trx.currency, "product_type": card.product_type}
        base = dict(session_state="verified", intent=read.intent, intent_confidence=read.confidence,
                    dispute_detected=read.dispute_detected, injection_flagged=read.injection_flagged,
                    cross_customer=False, supervised_mode=False, country=country, **facts)
        decision = self.engine.decide(DecisionInput(**base))
        confirmed = decision.decision == "confirm"                      # zone medium: the customer says yes
        if confirmed:
            decision = self.engine.decide(DecisionInput(**base, customer_confirmed=True))
        expected = self.expected_status(row, country)
        out = {"month": row["month"], "country": row["country"], "candidates": min(len(candidates), 2),
               "zone": decision.zone, "confirmed": confirmed, "expected_block": expected == "verification"}
        if decision.decision == "ask":
            outcome = "asked_several" if len(candidates) > 1 else "asked_none"
        elif "open_case" not in decision.allowed_actions:
            outcome = "other"
        else:
            self.open(n, customer, today, country, trx, card, decision, read.intent)
            outcome = "automated" if decision.decision == "block_and_open_case" else "handoff"
        return out | {"outcome": outcome, "complete_intake": self.complete(customer, row["transaction_id"], expected)}

    def complete(self, customer: str, transaction_id: str, expected: str) -> bool:
        """Spec 10 §4.1, read back from the store: a case on the reported charge, in the expected queue status, with
        a receipt that carries its legal deadline."""
        for case in self.store.list_cases(customer, run_id=None):
            if case.transaction_id == transaction_id and self.store.queue_status(case.case_id) == expected:
                receipts = [e.payload["receipt"] for e in self.store.events(case.case_id) if e.type == "receipt_issued"]
                return any(r.get("deadline") for r in receipts)
        return False

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


def run(gold: Path, quota: dict[str, int], limit: Optional[int] = None,
        merchant: bool = True) -> tuple[MemoryStore, pl.DataFrame]:
    """The store holding the replay's writes and one outcome row per contact (no id, name or text)."""
    now = [dt.datetime(2026, 1, 1, tzinfo=dt.UTC)]
    store = MemoryStore(now=lambda: now[0])
    replay, rows = Replay(gold, store, now, merchant), sample(gold, quota)
    rows = rows if limit is None else rows.head(limit)
    outcomes = [replay.contact(n, row) for n, row in enumerate(rows.iter_rows(named=True), 1)]
    schema = {"month": pl.Utf8, "country": pl.Utf8, "candidates": pl.Int64, "zone": pl.Utf8, "confirmed": pl.Boolean,
              "expected_block": pl.Boolean, "outcome": pl.Utf8, "complete_intake": pl.Boolean}
    return store, pl.DataFrame(outcomes, schema=schema)
