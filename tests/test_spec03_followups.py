"""Spec 03 T6: `add_case_info`, `request_call` and `request_reevaluation` through the real gate over the case store
(AC-17, AC-18, AC-19; D-008, D-025, D-026, D-042, D-052). Every test runs on MemoryStore and, with TEST_DATABASE_URL
(`-m postgres`), on PostgresStore in a fresh schema. No network, no LLM; gold is a stub or #123's tiny fixture."""
from __future__ import annotations

import datetime as dt
import itertools
import secrets
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from contracts import tools
from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn
from nick_of_time.policy import load_policies
from nick_of_time.store import StoreError
from tests.test_spec01_store import RUN, at_once, backend, new_store, open_case, postgres_only, types  # noqa: F401
from tests.test_spec03_case_and_block import write_gold

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/mcp"))
from mcp_server import followups, gate, writes  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402

NOW = dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC)
ANA, BRUNO = "CLI-000001", "CLI-000002"
POLICIES = load_policies()
# Gold as the T8 entry point passes it (by name): Ana is a México customer whose charge is dated 2026-05-30.
GOLD = SimpleNamespace(customer=lambda c: SimpleNamespace(country="México") if c == ANA else None,
                       transaction=lambda c, _: SimpleNamespace(transaction_date=dt.date(2026, 5, 30)) if c == ANA
                       else None)


class Sessions:
    def __init__(self, store):
        self.store = store

    def get(self, session_id):
        row = self.store.get_session(session_id)
        return gate.SessionRow.model_validate(row.model_dump()) if row else None


class Run:
    def __init__(self, policies=POLICIES, extra=None, **kwargs):
        self.store, self.denials = new_store(), []
        guardrails = {rule_id: rule.guardrail for rule_id, rule in policies.rules.items() if rule.guardrail}
        handlers = {**followups.followups_handlers(self.store, policies, **kwargs), **(extra(self) if extra else {})}
        self.gate = gate.Gate(Sessions(self.store), handlers,
                              denials=self.denials.append, audit=lambda _: None, now=lambda: NOW,
                              guardrails=guardrails, limiter=gate.RateLimiter(clock=itertools.count(0, 1000).__next__))
        self.ana, self.bruno = self.session(ANA), self.session(BRUNO)

    def session(self, customer, mode="replay"):
        return self.store.create_session(customer_id=customer, otp_hash="h", verified_at=NOW, language="es",
                                         expires_at=NOW + dt.timedelta(hours=1), mode=mode).session_id

    def __call__(self, tool, session=None, key=None, **args):
        arguments = {"session_id": session or self.ana, "idempotency_key": key or secrets.token_hex(4), **args}
        return self.gate.call(tool, arguments, "trace-t6")

    def case(self, status="new", customer=ANA, resolved_on=dt.date(2026, 5, 20), **facts):
        case_id = open_case(self.store, customer_id=customer, **facts).case_id
        steps = [("take", "review", resolved_on), ("resolve", "resolved", resolved_on),
                 ("close_case", "closed", resolved_on)][:{"new": 0, "review": 1, "resolved": 2, "closed": 3}[status]]
        for action, to, on in steps:
            self.analyst(case_id, action, to, on)
        return case_id

    def analyst(self, case_id, action, to=None, on=dt.date(2026, 5, 20)):
        request = AnalystActionIn(case_id=case_id, actor_id="sub-1", action=action, reason="x", idempotency_key="k")
        self.store.record_analyst_action(request, new_status=to, on=on, trace_id="t")


def test_ac_17_add_case_info_stores_the_text_as_customer_data_once_and_get_case_can_verify_it():
    run = Run()
    case_id = run.case()
    out = run("add_case_info", key="k1", case_id=case_id, text="Nunca estuve en esa tienda.")
    assert isinstance(out, tools.AddCaseInfoOut) and (out.state, out.case_id) == ("requested", case_id)
    event = run.store.events(case_id)[-1]
    assert (event.type, event.event_id, event.actor) == ("customer_info_added", out.event_id, "agent")
    assert event.payload == {"action_id": out.action_id, "text": "Nunca estuve en esa tienda.", "origin": "customer"}
    again = run("add_case_info", key="k1", case_id=case_id, text="Nunca estuve en esa tienda.")
    assert again == out and types(run.store, case_id).count("customer_info_added") == 1      # replayed, not rewritten
    run.store.record_verification(case_id, out.action_id, read="get_case", run_id=None, customer_id=ANA,
                                  actor="agent", trace_id="t")                                  # D-025: verifiable


@pytest.mark.parametrize("text", ["Mi tarjeta es 4111 1111 1111 1111", "el CVV 123", "CVC: 9876",
                                  "mi contraseña es hunter2", "minha senha: abc123", "password=Secreta1"])
def test_ac_17_add_case_info_rejects_card_numbers_cvv_and_passwords_with_g_in_04(text):
    run = Run()
    case_id = run.case()
    out = run("add_case_info", case_id=case_id, text=text)
    assert (out.code, out.policy_id) == ("DENY", "POL-PII") and text not in out.message
    assert [(d.policy_id, d.guardrail_id) for d in run.denials] == [("POL-PII", "G-IN-04")]   # D-062 [assumption]
    assert types(run.store, case_id) == ["case_opened"]


@pytest.mark.parametrize("tool, field, case", [("request_call", "preferred_time", "new"),
                                               ("request_call", "preferred_time", None),
                                               ("request_reevaluation", "reason", "resolved")])
def test_ac_17_the_other_free_texts_refuse_card_data_too_and_store_nothing(tool, field, case):
    """G-IN-04 on every customer text a follow-up stores: the call's preferred time (with or without a case) and the
    re-evaluation reason."""
    run = Run(gold=GOLD, transaction_country=lambda *_: None)
    case_id = run.case(case) if case else None
    before = types(run.store, case_id) if case_id else []
    out = run(tool, **({"case_id": case_id} if case_id else {}), **{field: "tarde, mi tarjeta 4111 1111 1111 1111"})
    assert (out.code, out.policy_id) == ("DENY", "POL-PII")
    assert (types(run.store, case_id) if case_id else []) == before and run.store.call_requests(ANA, run_id=None) == []


def test_ac_17_add_case_info_takes_plain_text_up_to_1000_characters_on_a_case_that_is_not_closed():
    run = Run()
    resolved, closed = run.case("resolved"), run.case("closed")
    for text in ("Nunca di mi contraseña a nadie.", "Fue el 2026-05-30 por 1,250.00 MXN, caso " + resolved):
        assert isinstance(run("add_case_info", case_id=resolved, text=text), tools.AddCaseInfoOut)
    too_long = run("add_case_info", case_id=resolved, text="x" * 1001)
    assert (too_long.code, too_long.policy_id) == ("DENY", "POL-DEFAULT-DENY")             # schema (G-TOOL-01)
    before = types(run.store, closed)
    assert run("add_case_info", case_id=closed, text="Hola").policy_id == "POL-DEFAULT-DENY"
    assert types(run.store, closed) == before


@pytest.mark.parametrize("tool, args", [("add_case_info", {"text": "hola"}), ("request_call", {}),
                                        ("request_reevaluation", {"reason": "No estoy de acuerdo"})])
def test_d052_another_customers_case_is_not_found_like_an_unknown_one_and_logged_as_a_probe(tool, args):
    run = Run()
    theirs = run.case("resolved", customer=BRUNO)
    before = types(run.store, theirs)
    probe, unknown = run(tool, case_id=theirs, **args), run(tool, case_id="K-999999", **args)
    assert probe == unknown and (probe.code, probe.policy_id) == ("NOT_FOUND", None)
    assert [(d.policy_id, d.guardrail_id) for d in run.denials] == [("POL-CROSS-CUSTOMER", "G-SES-02")]
    assert types(run.store, theirs) == before


def test_ac_18_one_open_call_per_case_with_the_stored_expected_contact_by_until_the_analyst_ends_it():
    run = Run()
    case_id = run.case()
    first = run("request_call", case_id=case_id, preferred_time="por la tarde")
    assert isinstance(first, tools.RequestCallOut) and first.expected_contact_by == dt.date(2026, 6, 2)   # D-008
    event = next(e for e in run.store.events(case_id) if e.event_id == first.event_id)
    assert event.type == "call_requested"
    assert event.payload == {"action_id": first.action_id, "expected_contact_by": "2026-06-02",
                             "preferred_time": "por la tarde", "origin": "customer"}
    run.analyst(case_id, "take", "review")                                # take keeps the call open (D-042)
    assert run("request_call", case_id=case_id) == first and types(run.store, case_id).count("call_requested") == 1
    run.analyst(case_id, "approve_block")                                 # ends it: a new request is a new write
    second = run("request_call", case_id=case_id)
    assert second.event_id != first.event_id and types(run.store, case_id).count("call_requested") == 2


def test_ac_18_no_callback_term_in_the_policy_promises_no_date():
    run = Run(policies=POLICIES.model_copy(update={"contact": None}))
    case_id = run.case()
    out = run("request_call", case_id=case_id)
    event = next(e for e in run.store.events(case_id) if e.event_id == out.event_id)
    assert out.expected_contact_by is None and event.payload["expected_contact_by"] is None


@pytest.mark.parametrize("country, expected", [(None, None), ("MX", dt.date(2026, 6, 2))])
def test_d026_a_call_with_no_case_is_a_call_requests_row_and_no_case_event(country, expected):
    run = Run(**({"gold": GOLD, "transaction_country": lambda *_: None} if country else {}))
    out = run("request_call", preferred_time="mañana")
    assert (out.case_id, out.expected_contact_by, out.state) == (None, expected, "requested")
    [row] = run.store.call_requests(ANA, run_id=None)
    assert (row.event_id, row.action_id, row.expected_contact_by, row.preferred_time) == (
        out.event_id, out.action_id, expected, "mañana")
    assert run.store.list_cases(ANA, run_id=None) == [] and run.store.call_requests(BRUNO, run_id=None) == []
    with pytest.raises(StoreError):                                       # an action id is used once
        run.store.add_call_request(customer_id=ANA, session_id=run.ana, action_id=out.action_id, trace_id="t")


def test_ac_19_a_resolved_case_in_the_window_goes_back_to_review_with_the_reason():
    run = Run()
    case_id = run.case("resolved", resolved_on=dt.date(2026, 5, 20))
    out = run("request_reevaluation", case_id=case_id, reason="No reconozco el cargo")
    assert (out.outcome, out.case_id, out.related_case_id) == ("back_to_review", case_id, None)
    *_, asked, moved = run.store.events(case_id)
    assert (asked.type, asked.event_id, asked.payload["action_id"]) == ("reevaluation_requested", out.event_id,
                                                                         out.action_id)
    assert asked.payload["reason"] == "No reconozco el cargo" and moved.payload["to"] == "review"
    assert run.store.queue_status(case_id) == "review"
    again = run("request_reevaluation", case_id=case_id, reason="Otra vez")          # now active: nothing written
    assert (again.outcome, again.action_id, again.event_id) == ("already_in_progress", out.action_id, out.event_id)


@pytest.mark.parametrize("days, allowed", [(30, True), (31, False)])
def test_ac_19_the_window_is_policies_reevaluation_window_days_and_day_31_is_denied(days, allowed):
    """policies.yaml `reevaluation.window_days` (30 [assumption] D-062): day 30 after the resolution goes back to
    review, day 31 gets POL-REEVAL-WINDOW and nothing is written."""
    assert POLICIES.reevaluation.window_days["MX"] == 30
    run = Run()
    case_id = run.case("resolved", resolved_on=dt.date(2026, 6, 1) - dt.timedelta(days=days))
    before = types(run.store, case_id)
    out = run("request_reevaluation", case_id=case_id, reason="No estoy de acuerdo")
    if allowed:
        assert out.outcome == "back_to_review" and run.store.queue_status(case_id) == "review"
    else:
        assert (out.code, out.policy_id) == ("DENY", "POL-REEVAL-WINDOW") and types(run.store, case_id) == before
        assert [(d.policy_id, d.guardrail_id) for d in run.denials] == [("POL-REEVAL-WINDOW", "G-POL-01")]


def test_ac_19_an_active_case_comes_back_unchanged_with_its_opening_write():
    run = Run()
    case_id = run.case("review")
    opened, before = run.store.events(case_id)[0], types(run.store, case_id)
    out = run("request_reevaluation", case_id=case_id, reason="¿Cómo va?")
    assert (out.outcome, out.action_id, out.event_id) == ("already_in_progress", opened.payload["action_id"],
                                                          opened.event_id)
    assert types(run.store, case_id) == before


@pytest.mark.parametrize("with_clock", [False, True])
def test_ac_19_a_closed_case_opens_a_related_case_in_review_from_the_new_notice(with_clock):
    run = Run(**({"gold": GOLD, "transaction_country": lambda *_: "México"} if with_clock else {}))
    closed = run.case("closed")
    out = run("request_reevaluation", case_id=closed, reason="Sigo sin reconocerlo")
    assert (out.outcome, out.related_case_id) == ("related_case_opened", closed) and out.case_id != closed
    new = run.store.get_case(out.case_id, run_id=None, customer_id=ANA)
    assert (new.related_case_id, new.opened_on, new.action_id) == (closed, dt.date(2026, 6, 1), out.action_id)
    assert new.credit_deadline == (dt.date(2026, 6, 3) if with_clock else None)   # no gold: no invented deadline
    assert types(run.store, out.case_id) == ["case_opened", "reevaluation_requested", "status_changed"]
    assert run.store.events(out.case_id)[0].event_id == out.event_id and run.store.queue_status(out.case_id) == "review"
    assert types(run.store, closed)[-1] == "related_case_opened" and run.store.queue_status(closed) == "closed"
    assert ids.is_valid("case", out.case_id)
    again = run("request_reevaluation", case_id=closed, reason="Otra vez")       # AC-15: no second active case
    assert (again.outcome, again.case_id, again.action_id, again.event_id, again.related_case_id) == (
        "already_in_progress", out.case_id, out.action_id, out.event_id, closed)
    assert run("request_reevaluation", case_id=out.case_id, reason="Y?") == again     # the related case: same holder
    assert len([c for c in run.store.list_cases(ANA, run_id=None) if c.related_case_id == closed]) == 1


def test_ac_15_a_closed_case_whose_charge_already_has_an_active_case_opens_no_other():
    """An active case of the same transaction, e.g. one open_case opened with related_case_id, is the answer."""
    run = Run()
    closed = run.case("closed")
    active = open_case(run.store, customer_id=ANA, related_case_id=closed)
    out = run("request_reevaluation", case_id=closed, reason="Sigo sin reconocerlo")
    assert (out.outcome, out.case_id, out.action_id) == ("already_in_progress", active.case_id, active.action_id)
    assert len(run.store.list_cases(ANA, run_id=None)) == 2


@pytest.mark.parametrize("where, ruling", [("México", dt.date(2026, 7, 16)), ("Estados Unidos", dt.date(2026, 11, 28))])
def test_ac_19_a_related_case_deadline_is_abroad_when_the_charge_was_abroad(where, ruling):
    """The same `abroad` rule as open_case: the charge's gold transaction_country against the customer's country."""
    run = Run(gold=GOLD, transaction_country=lambda *_: where)
    out = run("request_reevaluation", case_id=run.case("closed"), reason="Sigo sin reconocerlo")
    assert run.store.get_case(out.case_id, run_id=None, customer_id=ANA).ruling_deadline == ruling


def test_d008_a_later_duplicate_request_keeps_the_stored_expected_contact_by():
    """Live mode: asked on 2026-06-01 (-> 2026-06-02); asked again on 2026-06-03, the open request keeps 2026-06-02."""
    clock = [NOW]
    run = Run(now=lambda: clock[0])
    live, case_id = run.session(ANA, mode="live"), run.case()
    first = run("request_call", session=live, case_id=case_id)
    clock[0] = NOW + dt.timedelta(days=2)
    again = run("request_call", session=live, case_id=case_id)
    assert first.expected_contact_by == again.expected_contact_by == dt.date(2026, 6, 2) and again == first


def test_ac_19_a_country_with_no_window_sends_nothing_back():
    """Spec 02 FR-09: the window is per country; a country not in `reevaluation.window_days` is denied."""
    run = Run()
    case_id = run.case("resolved", resolved_on=dt.date(2026, 5, 31), country="US")
    out = run("request_reevaluation", case_id=case_id, reason="No estoy de acuerdo")
    assert (out.code, out.policy_id) == ("DENY", "POL-DEFAULT-DENY")       # no window, so none "passed" (D-062)


# ---------- with #123's gold fixture: the card index and open_case ----------
GOLD_ANA, CREDIT, ABROAD_TRX = "CLI-ANA000000001", "PRD-ANACREDIT001", "TRX-" + "0" * 19 + "4"   # charged in "USA"


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    return write_gold(tmp_path_factory.mktemp("data"))


def closed_abroad(run: Run, session_run=None) -> str:
    return run.case("closed", customer=GOLD_ANA, transaction_id=ABROAD_TRX, product_id=CREDIT, product_type="credit",
                    run_id=session_run)


def test_ac_19_the_entry_points_wiring_reads_the_card_index_and_gives_the_abroad_ruling_term(gold_dir):
    """`followups_handlers(store, policies, gold)` exactly as the entry point calls it, with no transaction_country
    injected: the card index (`cards_of(gold)`) says the charge was abroad, so the MX 180-day ruling term applies."""
    run = Run(gold=Gold(gold_dir))
    out = run("request_reevaluation", session=run.session(GOLD_ANA), case_id=closed_abroad(run), reason="Sigo")
    case = run.store.get_case(out.case_id, run_id=None, customer_id=GOLD_ANA)
    assert (out.outcome, case.ruling_deadline) == ("related_case_opened", dt.date(2026, 11, 28))


def _sessions(run: Run) -> list[str]:
    return [run.store.create_session(customer_id=GOLD_ANA, otp_hash="h", verified_at=NOW, language="es", run_id=RUN,
                                     expires_at=NOW + dt.timedelta(hours=1), mode="replay").session_id]


@pytest.mark.parametrize("second", ["request_reevaluation", "open_case"])
def test_ac_15_concurrent_reevaluations_and_open_case_on_a_closed_case_open_one_case(gold_dir, backend,  # noqa: F811
                                                                                     second):
    """Two connections, different keys: `request_reevaluation` takes `open_case`'s lock on the same key, so two
    re-evaluations, or a re-evaluation and `open_case(related_case_id)`, leave one active case for the charge. Each
    pair runs in its own scratch schema (one test per pair), so neither sees the other's case."""
    postgres_only(backend)
    gold = Gold(gold_dir)

    def wired(run):
        return writes.writes_handlers(gold, POLICIES, run.store, now=lambda: NOW)
    runs = [Run(gold=gold, extra=wired) for _ in range(2)]
    closed = closed_abroad(runs[0], session_run=RUN)
    assert [c.case_id for c in runs[0].store.list_cases(GOLD_ANA, run_id=RUN)] == [closed]   # a fresh schema
    sessions = [_sessions(r)[0] for r in runs]
    calls = [lambda: runs[0]("request_reevaluation", session=sessions[0], case_id=closed, reason="Sigo")]
    if second == "open_case":
        calls.append(lambda: runs[1]("open_case", session=sessions[1], transaction_id=ABROAD_TRX, zone="high",
                                     dispute_type="unrecognized_charge", related_case_id=closed))
    else:
        calls.append(lambda: runs[1]("request_reevaluation", session=sessions[1], case_id=closed, reason="Sigo"))
    outs = at_once(calls)
    assert all(not isinstance(o, (tools.ToolError, StoreError)) for o in outs), outs
    active = [c for c in runs[0].store.list_cases(GOLD_ANA, run_id=RUN)
              if c.transaction_id == ABROAD_TRX and runs[0].store.queue_status(c.case_id) != "closed"]
    assert len(active) == 1 and {o.case_id for o in outs} == {active[0].case_id}
    assert any(getattr(o, "outcome", None) == "related_case_opened" or getattr(o, "duplicate_of", 1) is None
               for o in outs)                                              # one of the pair wrote the case


@pytest.mark.parametrize("status, after", [("new", "review"), ("verification", "verification"),
                                           ("review", "review")])
def test_d063_a_call_on_a_new_case_moves_it_to_review_once(status, after):
    """[assumption] D-063: the held case (D-029) gets the review SLA as spec 02 `_open()` expects; a case already in
    verification or review is left as is, and a repeated call moves nothing."""
    run = Run()
    case_id = run.case("new" if status == "verification" else status)
    if status == "verification":
        run.store.change_status(case_id, "verification", on=dt.date(2026, 6, 1), actor="agent", trace_id="t")
    moves = types(run.store, case_id).count("status_changed")
    run("request_call", case_id=case_id)
    run("request_call", case_id=case_id)                                    # the open request: nothing written
    assert run.store.queue_status(case_id) == after
    changes = [e for e in run.store.events(case_id) if e.type == "status_changed"][moves:]
    assert [(e.payload["to"], e.payload.get("reason")) for e in changes] == (
        [("review", "call_requested")] if status == "new" else [])


def test_d063_the_move_to_review_rolls_back_with_the_call_request():
    """One `once`: a failing status change leaves no call_requested either, and the retry with its key writes both."""
    run = Run()
    case_id = run.case()

    def broken(*args, **kwargs):
        raise StoreError("down")
    run.store.change_status = broken                                      # this instance only
    assert run("request_call", key="k1", case_id=case_id) == gate.UNAVAILABLE
    assert types(run.store, case_id) == ["case_opened"]
    del run.store.change_status
    out = run("request_call", key="k1", case_id=case_id)
    assert isinstance(out, tools.RequestCallOut) and types(run.store, case_id) == [
        "case_opened", "call_requested", "status_changed"]
