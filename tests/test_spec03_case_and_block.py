"""Spec 03 T4: `open_case` and `block_card` through the real gate over a tiny gold fixture and the store (MemoryStore,
and PostgresStore when TEST_DATABASE_URL is set). Idempotency (AC-03), the overlay block (AC-04), the zone check
(AC-09), the block preconditions and the call hold (AC-10, D-042, D-043), denials as rows (AC-12), duplicates and the
related case (AC-15), cross-customer probes (D-052). No network, no LLM; data/gold_eval is never opened."""
from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from contracts import tools
from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn
from nick_of_time.policy import load_policies
from tests.test_spec01_store import RUN, backend, new_store, postgres_only, types  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server import cards, gate, writes  # noqa: E402
from mcp_server.cards import GoldCards  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402

NOW = dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC)
ON = dt.date(2026, 6, 1)
ANA, BRUNO = "CLI-ANA000000001", "CLI-BRUNO0000001"                       # both MX
DEBIT, CREDIT, BRUNO_CARD = "PRD-ANADEBIT0001", "PRD-ANACREDIT001", "PRD-BRUNOCARD001"
S_ANA, S_BRUNO, S_OTHER_RUN = "S-anareplay0000001", "S-brunoreplay00001", "S-anaotherrun00001"


def trx(n: int) -> str:
    return f"TRX-{n:020d}"


def _trx(n, customer, product, ptype, score, amount=100.0, country="México", day=31):
    return {"transaction_id": trx(n), "product_id": product, "customer_id": customer,
            "transaction_date": dt.datetime(2026, 5, day, 12, 30), "amount": amount, "currency": "USD",
            "amount_usd": amount, "merchant_name": "Tienda", "transaction_status": "Approved", "product_type": ptype,
            "transaction_country": country, "fraud_score": score, "is_fraud": True}   # is_fraud: never selected


TRX = [_trx(1, ANA, DEBIT, "Tarjeta Débito", 72.0), _trx(2, ANA, DEBIT, "Tarjeta Débito", 40.0),
       _trx(3, ANA, DEBIT, "Tarjeta Débito", None), _trx(4, ANA, CREDIT, "Tarjeta Crédito", 80.0, country="USA"),
       _trx(5, BRUNO, BRUNO_CARD, "Tarjeta Débito", 70.0), _trx(6, ANA, DEBIT, "Tarjeta Débito", 90.0, day=30),
       _trx(7, ANA, DEBIT, "Tarjeta Débito", 95.0, amount=6000.0)]   # 108,000 MXN: above the MX high gate


def write_gold(root: Path) -> Path:
    gold = root / "gold"
    gold.mkdir()
    pl.DataFrame(TRX).write_parquet(gold / "transactions_enriched.parquet")
    pl.DataFrame([{"customer_id": c, "first_name": f, "country": "México", "email": "secret@example.com"}
                  for c, f in ((ANA, "Ana"), (BRUNO, "Bruno"))]).write_parquet(gold / "customers.parquet")
    pl.DataFrame([{"product_id": p, "customer_id": c, "product_type": k, "product_number": n, "product_status": s}
                  for p, c, k, n, s in ((DEBIT, ANA, "Tarjeta Débito", "4111111111114417", "Active"),
                                        (CREDIT, ANA, "Tarjeta Crédito", "5500000000000004", "Active"),
                                        (BRUNO_CARD, BRUNO, "Tarjeta Débito", "4000000000009999", "Active"),
                                        ("PRD-ANASAVINGS01", ANA, "Cuenta Ahorro", "000123", "Active"))]).write_parquet(
        gold / "products.parquet")
    return gold


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory) -> Path:
    return write_gold(tmp_path_factory.mktemp("data"))


def session(sid: str, customer: str, run_id=RUN, **extra) -> gate.SessionRow:
    return gate.SessionRow(session_id=sid, customer_id=customer, verified_at=NOW, language="es", mode="replay",
                           expires_at=NOW + dt.timedelta(minutes=15), run_id=run_id, **extra)


class Run:
    """The gate with the write handlers (and any extra ones) over one store; `denials` keeps every DENY row."""

    def __init__(self, gold_dir: Path, store=None, extra=None):
        self.store, self.denials, policies = store or new_store(), [], load_policies()
        self.sessions = {S_ANA: session(S_ANA, ANA), S_BRUNO: session(S_BRUNO, BRUNO),
                         S_OTHER_RUN: session(S_OTHER_RUN, ANA, run_id="EV-0002:S1:1")}
        self.gold, self.cards = Gold(gold_dir), GoldCards(gold_dir)
        handlers = {**writes.writes_handlers(self.gold, policies, self.store, cards=self.cards,
                                                now=lambda: NOW),
                    **(extra(self) if extra else {})}
        guardrails = {rule_id: rule.guardrail for rule_id, rule in policies.rules.items() if rule.guardrail}
        self.gate = gate.Gate(self.sessions, handlers, denials=self.denials.append, audit=lambda _: None,
                              limiter=_NoLimit(), now=lambda: NOW,
                              guardrails=guardrails)

    def __call__(self, tool, session_id=S_ANA, trace_id="trace-1", **args):
        if tool in tools.VERIFIED_WITH:
            args.setdefault("idempotency_key", ids.new_id("action"))
        return self.gate.call(tool, {"session_id": session_id, **args}, trace_id)

    def open(self, n=1, zone="high", session_id=S_ANA, **args) -> tools.OpenCaseOut:
        out = self("open_case", session_id, transaction_id=trx(n), dispute_type="unrecognized_charge", zone=zone, **args)
        assert isinstance(out, tools.OpenCaseOut), out
        return out

    def block(self, product=DEBIT, session_id=S_ANA, **args):
        return self("block_card", session_id, product_id=product, reason="high_zone_dispute", **args)

    def analyst(self, case_id, action, new_status=None):
        request = AnalystActionIn(case_id=case_id, actor_id="sub-1", action=action, reason="x", idempotency_key="k")
        self.store.record_analyst_action(request, new_status=new_status, on=ON, trace_id="t")

    def call_requested(self, case_id):          # what request_call (T6) writes on the case
        self.store.append_event(case_id, "call_requested", actor="agent", trace_id="t",
                                payload={"action_id": ids.new_id("action"), "expected_contact_by": "2026-06-02"})

    def person_requested(self, case_id):        # the opening turn's handoff (spec 03 §8, D-055 [assumption])
        self.store.append_event(case_id, "handoff_emitted", actor="agent", trace_id="trace-1",
                                payload={"handoff_reason": "person_requested"})


class _NoLimit(gate.RateLimiter):
    def admit(self, session_id, tool):          # the rate limits are T1's (tests/test_spec03_server.py)
        return None


def denied(out, policy_id):
    return isinstance(out, tools.ToolError) and (out.code, out.policy_id) == ("DENY", policy_id)


def nothing_written(run: Run, before: dict) -> bool:
    return {c.case_id: types(run.store, c.case_id) for c in run.store.list_cases(ANA, run_id=RUN)} == before


def snapshot(run: Run) -> dict:
    return {c.case_id: types(run.store, c.case_id) for c in run.store.list_cases(ANA, run_id=RUN)}


# ---------- open_case ----------
def test_ac_09_open_case_stores_the_case_with_its_deadline_and_reports_it_only_as_requested(gold_dir):
    run = Run(gold_dir)
    out = run.open(1)
    case = run.store.get_case(out.case_id, run_id=RUN, customer_id=ANA)
    assert (out.state, out.duplicate_of, out.country, out.credit_deadline) == ("requested", None, "MX", dt.date(2026, 6, 3))
    assert out.action_id == case.action_id and out.deadline_source_url.startswith("https://")
    assert (case.zone, case.product_type, case.product_id, case.opened_on, case.mode, case.trace_id) == (
        "high", "debit", DEBIT, ON, "replay", "trace-1")
    assert types(run.store, out.case_id) == ["case_opened"] and case.verification_id is None   # D-025


def test_ac_09_an_operation_abroad_gets_the_abroad_ruling_term(gold_dir):
    out = Run(gold_dir).open(4)                                  # credit card, transaction in the USA
    assert out.ruling_deadline == ON + dt.timedelta(days=180)   # MX ruling_abroad: 180 calendar days


@pytest.mark.parametrize("n, zone", [(1, "medium"), (1, "human"), (2, "high"), (3, "medium"), (3, "high")])
def test_ac_09_a_zone_other_than_the_scores_is_denied_with_g_in_02_and_writes_nothing(gold_dir, n, zone):
    run = Run(gold_dir)
    out = run("open_case", transaction_id=trx(n), dispute_type="unrecognized_charge", zone=zone, trace_id="trace-9")
    assert denied(out, "POL-ZONE-MISMATCH") and snapshot(run) == {}
    [row] = run.denials
    assert (row.policy_id, row.guardrail_id, row.trace_id, row.run_id) == ("POL-ZONE-MISMATCH", "G-IN-02", "trace-9", RUN)


@pytest.mark.parametrize("n, zone", [(1, "high"), (2, "medium"), (3, "human")])
def test_ac_09_the_zone_of_the_score_opens_the_case_null_score_is_human(gold_dir, n, zone):
    assert Run(gold_dir).open(n, zone).duplicate_of is None


def test_ac_15_an_active_case_of_the_same_transaction_is_returned_with_duplicate_of_and_nothing_is_written(gold_dir):
    run = Run(gold_dir)
    first = run.open(1)
    before = snapshot(run)
    again = run.open(1, zone="medium")                            # duplicate check first: before the zone check
    assert (again.case_id, again.duplicate_of, again.action_id) == (first.case_id, first.case_id, first.action_id)
    assert again.credit_deadline == first.credit_deadline and nothing_written(run, before) and run.denials == []


def test_ac_15_a_closed_case_opens_a_new_one_linked_by_related_case_id(gold_dir):
    run = Run(gold_dir)
    first = run.open(1)
    for action, to in (("take", "review"), ("resolve", "resolved"), ("close_case", "closed")):
        run.analyst(first.case_id, action, to)
    second = run.open(1, related_case_id=first.case_id)
    assert second.case_id != first.case_id and (second.duplicate_of, second.related_case_id) == (None, first.case_id)
    assert types(run.store, first.case_id)[-1] == "related_case_opened"


def test_ac_15_d052_the_related_case_must_be_a_closed_case_of_the_customer(gold_dir):
    run = Run(gold_dir)
    open_one, bruno = run.open(1), run.open(5, session_id=S_BRUNO)
    before = snapshot(run)
    assert denied(run("open_case", transaction_id=trx(2), dispute_type="wrongful_charge", zone="medium",
                      related_case_id=open_one.case_id), "POL-DEFAULT-DENY")
    probe = run("open_case", transaction_id=trx(2), dispute_type="wrongful_charge", zone="medium",
                related_case_id=bruno.case_id)
    unknown = run("open_case", transaction_id=trx(2), dispute_type="wrongful_charge", zone="medium",
                  related_case_id="K-999999")
    assert probe == unknown == tools.ToolError(code="NOT_FOUND", message=writes.NO_CASE.message)
    assert nothing_written(run, before)
    assert [(d.policy_id, d.guardrail_id) for d in run.denials] == [("POL-DEFAULT-DENY", "G-POL-01"),
                                                                    ("POL-CROSS-CUSTOMER", "G-SES-02")]


def test_ac_15_d052_another_customers_transaction_is_not_found_and_logged(gold_dir):
    run = Run(gold_dir)
    probe = run("open_case", transaction_id=trx(5), dispute_type="unrecognized_charge", zone="high")
    unknown = run("open_case", transaction_id="TRX-" + "9" * 20, dispute_type="unrecognized_charge", zone="high")
    assert probe == unknown and probe.code == "NOT_FOUND" and probe.policy_id is None and snapshot(run) == {}
    assert [(d.policy_id, d.guardrail_id) for d in run.denials] == [("POL-CROSS-CUSTOMER", "G-SES-02")]


def test_ac_03_open_case_retried_with_its_key_replays_the_first_result_and_writes_once(gold_dir):
    run = Run(gold_dir)
    first = run.open(1, idempotency_key="turn-1:open")
    again = run.open(1, idempotency_key="turn-1:open")
    assert again == first and again.duplicate_of is None and len(run.store.list_cases(ANA, run_id=RUN)) == 1


def test_ac_03_a_key_reused_with_other_arguments_is_denied_and_writes_nothing(gold_dir):
    run = Run(gold_dir)
    run.open(1, idempotency_key="k")
    before = snapshot(run)
    assert denied(run("open_case", transaction_id=trx(2), dispute_type="unrecognized_charge", zone="medium",
                      idempotency_key="k"), "POL-DEFAULT-DENY")
    assert denied(run.block(idempotency_key="k"), "POL-DEFAULT-DENY") and nothing_written(run, before)


# ---------- block_card ----------
def test_ac_03_block_card_twice_with_the_same_key_blocks_once(gold_dir):
    run = Run(gold_dir)
    case = run.open(1)
    first, again = run.block(idempotency_key="turn-1:block"), run.block(idempotency_key="turn-1:block")
    assert isinstance(first, tools.BlockCardOut) and again == first and first.state == "requested"
    assert types(run.store, case.case_id).count("card_blocked") == 1


def test_ac_04_a_block_is_an_overlay_row_of_the_run_and_gold_is_never_written(gold_dir):
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in gold_dir.iterdir()}
    run = Run(gold_dir)
    case = run.open(1)
    out = run.block()
    row = run.store.product_status(DEBIT, run_id=RUN)
    assert (row.status, row.action_id, row.case_id, row.verification_id) == ("Blocked", out.action_id, case.case_id, None)
    assert run.store.product_status(DEBIT, run_id=None) is None and run.cards.card(ANA, DEBIT).status == "Active"
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in gold_dir.iterdir()} == digest


def test_ac_10_a_block_without_an_open_case_of_that_card_in_the_run_is_denied_and_writes_nothing(gold_dir):
    run = Run(gold_dir)
    assert denied(run.block(), "POL-DEFAULT-DENY")
    run.open(4)                                                   # a case on the credit card only
    assert denied(run.block(DEBIT), "POL-DEFAULT-DENY")
    assert denied(run.block(CREDIT, S_OTHER_RUN), "POL-DEFAULT-DENY")    # same customer, another run
    assert run.store.product_status(DEBIT, run_id=RUN) is None and run.store.product_status(CREDIT, run_id=RUN) is None
    assert [d.policy_id for d in run.denials] == ["POL-DEFAULT-DENY"] * 3


def test_ac_10_a_closed_case_allows_no_block(gold_dir):
    run = Run(gold_dir)
    case = run.open(1)
    for action, to in (("take", "review"), ("resolve", "resolved"), ("close_case", "closed")):
        run.analyst(case.case_id, action, to)
    assert denied(run.block(), "POL-DEFAULT-DENY") and run.store.product_status(DEBIT, run_id=RUN) is None


@pytest.mark.parametrize("n, zone, policy_id", [(2, "medium", "POL-DEFAULT-DENY"), (3, "human", "POL-DEFAULT-DENY"),
                                                (7, "high", "POL-AMOUNT-GATE")])
def test_ac_10_the_engine_re_check_denies_with_its_policy_id_and_writes_nothing(gold_dir, n, zone, policy_id):
    run = Run(gold_dir)
    case = run.open(n, zone)
    assert denied(run.block(), policy_id) and types(run.store, case.case_id) == ["case_opened"]


def test_ac_10_d052_another_customers_card_is_not_found_and_logged(gold_dir):
    run = Run(gold_dir)
    run.open(5, session_id=S_BRUNO)                               # Bruno's card has an open case
    probe, unknown = run.block(BRUNO_CARD), run.block("PRD-UNKNOWN00001")
    assert probe == unknown == writes.NO_CARD and run.store.product_status(BRUNO_CARD, run_id=RUN) is None
    assert [(d.policy_id, d.guardrail_id, d.session_id) for d in run.denials] == [
        ("POL-CROSS-CUSTOMER", "G-SES-02", S_ANA)]


def test_ac_12_every_deny_of_the_write_tools_is_a_row_with_trace_policy_and_guardrail(gold_dir):
    run = Run(gold_dir)
    outs = [run("open_case", trace_id="t-1", transaction_id=trx(1), dispute_type="unrecognized_charge", zone="human"),
            run.block(trace_id="t-2")]
    case = run.open(1)
    run.call_requested(case.case_id)
    outs.append(run.block(trace_id="t-3"))
    assert [o.policy_id for o in outs] == ["POL-ZONE-MISMATCH", "POL-DEFAULT-DENY", "POL-HUMAN-REQUEST"]
    assert [(d.trace_id, d.policy_id, d.guardrail_id, d.session_id) for d in run.denials] == [
        ("t-1", "POL-ZONE-MISMATCH", "G-IN-02", S_ANA), ("t-2", "POL-DEFAULT-DENY", "G-POL-01", S_ANA),
        ("t-3", "POL-HUMAN-REQUEST", "G-POL-01", S_ANA)]


# ---------- the call hold (spec 03 §8, D-042, D-043) ----------
def test_ac_10_d042_an_open_call_on_the_case_denies_the_block_with_pol_human_request(gold_dir):
    run = Run(gold_dir)
    case = run.open(1)
    run.call_requested(case.case_id)
    before = snapshot(run)
    assert denied(run.block(), "POL-HUMAN-REQUEST") and nothing_written(run, before)


@pytest.mark.parametrize("keep", [("take", "review"), ("request_customer_info", None), ("mark_ambiguous", None)])
def test_ac_10_d042_take_request_customer_info_and_mark_ambiguous_keep_the_hold(gold_dir, keep):
    run = Run(gold_dir)
    case = run.open(1)
    run.call_requested(case.case_id)
    run.analyst(case.case_id, *keep)
    assert denied(run.block(), "POL-HUMAN-REQUEST") and run.store.product_status(DEBIT, run_id=RUN) is None


@pytest.mark.parametrize("end", ["approve_block", "resolve"])
def test_ac_10_d042_approve_block_and_resolve_each_lift_the_hold(gold_dir, end):
    run = Run(gold_dir)
    case = run.open(1)
    run.call_requested(case.case_id)
    run.analyst(case.case_id, "take", "review")
    run.analyst(case.case_id, end, "resolved" if end == "resolve" else None)
    assert isinstance(run.block(), tools.BlockCardOut)
    assert run.store.product_status(DEBIT, run_id=RUN).status == "Blocked"


def test_ac_10_d042_close_case_lifts_the_hold(gold_dir):
    run = Run(gold_dir)
    case = run.open(1)
    run.call_requested(case.case_id)
    assert writes.call_open(run.store.events(case.case_id))
    for action, to in (("take", "review"), ("resolve", "resolved")):
        run.analyst(case.case_id, action, to)
    run.call_requested(case.case_id)                              # a new call after the resolve holds again
    assert writes.call_open(run.store.events(case.case_id))
    run.analyst(case.case_id, "close_case", "closed")
    assert not writes.call_open(run.store.events(case.case_id))
    assert denied(run.block(), "POL-DEFAULT-DENY")                # no open case left, no longer the call hold


def test_ac_10_d042_a_person_requested_case_without_a_call_event_is_held(gold_dir):
    """Spec 04 `connect` fallback: the call went out as a general request, so the case has no call_requested event."""
    run = Run(gold_dir)
    case = run.open(1)
    run.person_requested(case.case_id)
    assert "call_requested" not in types(run.store, case.case_id)
    assert denied(run.block(), "POL-HUMAN-REQUEST")
    run.analyst(case.case_id, "approve_block")
    assert isinstance(run.block(), tools.BlockCardOut)


def test_ac_10_d042_another_handoff_reason_holds_nothing(gold_dir):
    run = Run(gold_dir)
    case = run.open(1)
    run.store.append_event(case.case_id, "handoff_emitted", actor="agent", trace_id="t",
                           payload={"handoff_reason": "zone_medium"})
    assert isinstance(run.block(), tools.BlockCardOut)


def test_ac_10_d042_the_hold_is_per_case(gold_dir):
    run = Run(gold_dir)
    held = run.open(1)
    run.call_requested(held.case_id)
    run.open(4)                                                   # another charge, on the credit card
    assert isinstance(run.block(CREDIT), tools.BlockCardOut)
    assert denied(run.block(DEBIT), "POL-HUMAN-REQUEST")
    newer = run.open(6)                                           # another charge on the held card: its own case
    out = run.block(DEBIT)
    assert isinstance(out, tools.BlockCardOut) and run.store.product_status(DEBIT, run_id=RUN).case_id == newer.case_id
    assert writes.call_open(run.store.events(held.case_id))      # the first case is still held


def test_ac_10_d042_the_hold_reads_the_latest_request_against_the_latest_end():
    assert not writes.call_open([])
    assert writes.call_open([_ev(1, "case_opened"), _ev(2, "call_requested")])
    assert not writes.call_open([_ev(2, "call_requested"), _ev(3, "analyst_action", action="approve_block")])
    assert writes.call_open([_ev(2, "call_requested"), _ev(3, "analyst_action", action="approve_block"),
                             _ev(4, "call_requested")])
    assert writes.call_open([_ev(2, "handoff_emitted", handoff_reason="person_requested"),
                             _ev(3, "analyst_action", action="unblock_card")])


def _ev(seq, type, **payload):
    return SimpleNamespace(seq=seq, type=type, payload=payload)


def test_ac_10_writes_handlers_is_wired_from_the_entry_points_dependencies(gold_dir, monkeypatch):
    """Spec 03 T8 wiring: `writes_handlers` needs only gold, policies and store; the cards come from GOLD_PATH."""
    monkeypatch.setenv("GOLD_PATH", str(gold_dir))
    handlers = writes.writes_handlers(Gold(gold_dir), load_policies(), new_store())
    assert set(handlers) == {"open_case", "block_card"} and cards.shared_cards() is cards.shared_cards()
    monkeypatch.delenv("GOLD_PATH")
    with pytest.raises(RuntimeError):
        cards.shared_cards()
