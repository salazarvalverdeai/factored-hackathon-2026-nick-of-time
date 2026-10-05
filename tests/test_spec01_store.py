"""Spec 01 — the store: case ids (T9), append-only events, status as the last event, transitions, customer and run
scoping, verification ids (AC-01, §6.5, §6.8, D-014, D-023, D-025, D-034). Every test runs on both backends (T9):
MemoryStore, and PostgresStore in a fresh schema when TEST_DATABASE_URL is set (`-m postgres`; offline it skips)."""
from __future__ import annotations

import datetime as dt
import itertools
import os
import secrets
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from contracts import tools as contract_tools
from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn
from nick_of_time.store import (CUSTOMER_VISIBLE, RESERVED_EVENTS, VERIFIED_WITH, WRITE_EVENTS, WRITE_TOOL, NewCase,
                                NotVerified, ProductOverride, Store, StoreError, VerifyingRead)
from nick_of_time.store.memory import MemoryStore

FACTS = dict(customer_id="CLI-000001", transaction_id="TRX-" + "A" * 20, product_id="PRD-" + "B" * 12, country="MX",
             product_type="debit", zone="high", dispute_type="unrecognized_charge", opened_on=dt.date(2026, 6, 1),
             credit_deadline=dt.date(2026, 6, 3), deadline_source="Banxico Circular 3/2012",
             deadline_source_url="https://www.banxico.org.mx/", deadline_verified_on=dt.date(2026, 10, 4),
             mode="replay", trace_id="trace-1")
ON = dt.date(2026, 6, 2)
RUN = "EV-0001:S1:1"
STATUSES = ["new", "verification", "review", "resolved", "closed"]
ANALYST_ACTIONS = get_args(AnalystActionIn.model_fields["action"].annotation)
PG_URL = os.environ.get("TEST_DATABASE_URL")
SCHEMA_SQL = (Path(__file__).resolve().parents[1] / "packages/nick_of_time/store/schema.sql").read_text()
BACKENDS = ["memory", pytest.param("postgres", marks=[pytest.mark.postgres, pytest.mark.skipif(
    not PG_URL, reason="needs a PostgreSQL server at TEST_DATABASE_URL")])]
_backend: list[Callable[..., Store]] = []


@contextmanager
def scratch_schema() -> Iterator[Callable[..., Store]]:
    """T9: a PostgresStore factory over the whole schema.sql in a fresh schema, dropped (with its rows) afterwards."""
    import psycopg

    from nick_of_time.store.postgres import PostgresStore
    schema, opened = "t01g_" + secrets.token_hex(4), []

    def build(**kwargs) -> PostgresStore:
        opened.append(PostgresStore(PG_URL, options=f"-c search_path={schema}", **kwargs))
        return opened[-1]

    with psycopg.connect(PG_URL, autocommit=True) as admin:
        admin.execute(f"create schema {schema}")
        try:
            admin.execute(f"set search_path to {schema}")
            admin.execute(SCHEMA_SQL)
            yield build
        finally:
            for store in opened:
                store.close()
            admin.execute(f"drop schema {schema} cascade")


@pytest.fixture(autouse=True, params=BACKENDS)
def backend(request) -> Iterator[str]:
    """T9: the same suite on MemoryStore and PostgresStore; `new_store()` builds the current one."""
    if request.param == "memory":
        _backend[:] = [MemoryStore]
        yield request.param
    else:
        with scratch_schema() as build:
            _backend[:] = [build]
            yield request.param


def new_store(**kwargs) -> Store:
    return _backend[0](**kwargs)


def new_case(**changes) -> NewCase:
    return NewCase(**{**FACTS, **changes})


def open_case(store: Store, actor: str = "agent", **changes):
    return store.create_case(new_case(**changes), actor=actor, action_id=ids.new_id("action"))


def act(store: Store, case_id: str, action: str, new_status: str | None, reason: str | None = "x",
        actor_id: str = "sub-1"):
    request = AnalystActionIn(case_id=case_id, actor_id=actor_id, action=action, reason=reason, idempotency_key="k")
    return store.record_analyst_action(request, new_status=new_status, on=ON, trace_id="t")


def verify(store: Store, case_id: str, action_id: str, read: str = "get_case", run_id: str | None = None,
           customer_id: str | None = None):
    return store.record_verification(case_id, action_id, read=read, run_id=run_id, customer_id=customer_id,
                                     actor="agent", trace_id="t")


def at(store: Store, status: str, **changes) -> str:
    """A case moved to `status` along the queue."""
    case_id = open_case(store, **changes).case_id
    if status == "verification":
        store.change_status(case_id, "verification", on=ON, actor="agent", trace_id="t")
    steps = {"review": 1, "resolved": 2, "closed": 3}.get(status, 0)
    for action, to in [("take", "review"), ("resolve", "resolved"), ("close_case", "closed")][:steps]:
        act(store, case_id, action, to)
    assert store.queue_status(case_id) == status
    return case_id


def ticking_store() -> Store:
    ticks = iter(dt.datetime(2026, 6, 1, 15, minute, tzinfo=dt.UTC) for minute in range(60))
    return new_store(now=lambda: next(ticks))


FIXED = dt.datetime(2026, 6, 1, 15, tzinfo=dt.UTC)


def clock_store(clock: str) -> Store:
    """A store whose clock repeats one instant ("fixed") or steps a minute back on every call ("backward")."""
    ticks, step = itertools.count(), {"fixed": 0, "backward": -1}[clock]
    return new_store(now=lambda: FIXED + dt.timedelta(minutes=step * next(ticks)))


def types(store: Store, case_id: str) -> list[str]:
    return [e.type for e in store.events(case_id)]


def test_ac_01_each_backend_implements_the_store_interface():
    assert isinstance(new_store(), Store)


def test_t9_case_insert_retries_with_a_fresh_id_on_a_forced_primary_key_collision(monkeypatch):
    store = new_store()
    first = open_case(store)
    real, queue = ids.new_id, [first.case_id, "K-123456"]
    monkeypatch.setattr(ids, "new_id", lambda kind: queue.pop(0) if kind == "case" and queue else real(kind))
    second = open_case(store, transaction_id="TRX-" + "C" * 20)
    assert second.case_id == "K-123456"
    assert store.get_case(first.case_id, run_id=None, customer_id=None) == first     # the existing row is untouched
    assert types(store, first.case_id) == ["case_opened"] == types(store, second.case_id)


def test_t9_case_insert_gives_up_and_writes_nothing_when_every_id_collides(monkeypatch):
    store = new_store()
    taken, real = open_case(store).case_id, ids.new_id
    monkeypatch.setattr(ids, "new_id", lambda kind: taken if kind == "case" else real(kind))
    with pytest.raises(StoreError, match="no free case id"):
        open_case(store, customer_id="CLI-000002")
    assert store.list_cases("CLI-000002", run_id=None) == []


def test_ac_01_status_is_the_last_status_changed_event_and_events_are_numbered():
    """FR-02: `new` until the first status_changed; payload {from, to, on, reason?} with the business date (D-023);
    seq 1..n; customer_visible follows the ✓ list of §6.5."""
    store = new_store()
    case_id = open_case(store).case_id
    assert store.queue_status(case_id) == "new"
    store.change_status(case_id, "verification", on=ON, actor="agent", trace_id="t")
    store.append_event(case_id, "handoff_emitted", actor="agent", trace_id="t")
    store.change_status(case_id, "review", on=ON, actor="agent", trace_id="t", reason="customer disagrees")
    events = store.events(case_id)
    assert store.queue_status(case_id) == "review" and [e.seq for e in events] == [1, 2, 3, 4]
    assert events[-1].payload == {"from": "verification", "to": "review", "on": "2026-06-02",
                                  "reason": "customer disagrees"}
    assert [e.customer_visible for e in events] == [True, True, False, True]
    assert CUSTOMER_VISIBLE.isdisjoint({"handoff_emitted", "analyst_action", "action_verified"})


def test_ac_01_events_are_append_only():
    """§6.5 AO: no update or delete in the interface, reserved types only through the store, copies on read."""
    assert not [n for n in dir(Store) if n.split("_")[0] in {"update", "delete", "remove", "set", "clear", "reset"}]
    store = new_store()
    case_id = open_case(store).case_id
    assert RESERVED_EVENTS == {"case_opened", "status_changed", "analyst_action", "assigned", "related_case_opened",
                               "card_blocked", "action_verified", "block_verified", "notification_sent",
                               "telegram_linked", "email_confirmed"}
    for reserved in sorted(RESERVED_EVENTS):
        with pytest.raises(StoreError, match="written only by the store"):
            store.append_event(case_id, reserved, actor="agent", trace_id="t")
    sent = {"action_id": ids.new_id("action"), "detail": {"text": "Compra que no hice"}}
    store.append_event(case_id, "customer_info_added", actor="customer", trace_id="t", payload=sent)
    sent["detail"]["text"] = "edited"                                       # neither the written payload…
    store.events(case_id)[0].payload["to"] = "closed"                       # …nor a read changes what is stored
    assert store.events(case_id)[-1].payload["detail"] == {"text": "Compra que no hice"}
    assert "to" not in store.events(case_id)[0].payload and store.queue_status(case_id) == "new"
    with pytest.raises(StoreError, match="unknown case"):
        store.append_event("K-999999", "handoff_emitted", actor="agent", trace_id="t")


def test_ac_01_payloads_are_json_as_in_jsonb():
    """A payload or provider_event comes back as JSON gives it (a tuple as a list); a date or NaN is refused."""
    store = new_store()
    case_id = open_case(store).case_id
    event = store.append_event(case_id, "handoff_emitted", actor="agent", trace_id="t", payload={"ids": ("a", "b")})
    assert event.payload == {"ids": ["a", "b"]} == store.events(case_id)[-1].payload
    written = len(store.events(case_id))
    for bad in ({"on": dt.date(2026, 6, 2)}, {"score": float("nan")}):
        with pytest.raises(StoreError, match="not JSON"):
            store.append_event(case_id, "handoff_emitted", actor="agent", trace_id="t", payload=bad)
    assert len(store.events(case_id)) == written
    sent = store.add_notification(case_id, event="case_opened", channel="log", masked_address=None, text="Abrimos.",
                                  trigger="auto", actor="system", trace_id="t")
    with pytest.raises(StoreError, match="not JSON"):
        store.add_delivery(sent.notification_id, "delivered", {"at": dt.date(2026, 6, 2)})
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id=None)] == ["queued"]


def test_ac_01_only_a_person_resolves_and_closes_and_closed_is_final():
    """Constitution #6 and spec 18 A7: `resolved` and `closed` come only from analysts; a closed case never moves."""
    store = new_store()
    case_id = open_case(store).case_id
    taken = act(store, case_id, "take", "review", reason=None)
    assert (taken.previous_status, taken.new_status) == ("new", "review")
    act(store, case_id, "resolve", "resolved")
    closed = act(store, case_id, "close_case", "closed")
    assert (closed.previous_status, closed.new_status, store.queue_status(case_id)) == ("resolved", "closed", "closed")
    by_analyst = [e for e in store.events(case_id) if e.type in {"analyst_action", "assigned", "status_changed"}]
    assert {e.actor for e in by_analyst} == {"analyst:sub-1"} and "assigned" in {e.type for e in by_analyst}
    assert [e.payload for e in by_analyst if e.type == "analyst_action"] == [
        {"action": "take", "reason": None}, {"action": "resolve", "reason": "x"},
        {"action": "close_case", "reason": "x"}]
    written = len(store.events(case_id))
    with pytest.raises(StoreError, match="closed -> review is not in case_queue.transitions"):
        store.change_status(case_id, "review", on=ON, actor="agent", trace_id="t")
    assert store.queue_status(case_id) == "closed" and len(store.events(case_id)) == written   # refused = no write
    other = open_case(store, transaction_id="TRX-" + "E" * 20).case_id
    assert act(store, other, "take", "verification").new_status == "verification"
    kept = act(store, other, "request_customer_info", None)                     # None keeps the status
    assert (kept.previous_status, kept.new_status) == ("verification", "verification")
    assert types(store, other)[-1] == "analyst_action" and store.queue_status(other) == "verification"
    act(store, other, "resolve", "resolved")
    assert act(store, other, "reopen_case", "review").new_status == "review"     # resolved -> review


@pytest.mark.parametrize("actor", ["agent", "customer", "system", "analyst:x"])
def test_ac_01_change_status_never_resolves_whatever_the_actor(actor):
    """Spec 18 A7: like `closed`, `resolved` comes only through record_analyst_action, even where the queue allows it
    and even from an actor that looks like an analyst."""
    store = new_store()
    case_id = at(store, "verification")
    written = len(store.events(case_id))
    with pytest.raises(StoreError, match="only an analyst resolve resolves"):
        store.change_status(case_id, "resolved", on=ON, actor=actor, trace_id="t")
    assert store.queue_status(case_id) == "verification" and len(store.events(case_id)) == written
    assert act(store, case_id, "resolve", "resolved").new_status == "resolved"


@pytest.mark.parametrize("start", STATUSES)
@pytest.mark.parametrize("to, error", [(None, "needs a status"), ("archived", "-> archived is not in")])
def test_ac_01_change_status_needs_a_known_status_from_every_start(start, to, error):
    """A `status_changed {to: null}` would leave the case with no status and no way to close it."""
    store = new_store()
    case_id = at(store, start)
    written = len(store.events(case_id))
    with pytest.raises(StoreError, match=error):
        store.change_status(case_id, to, on=ON, actor="agent", trace_id="t")
    assert store.queue_status(case_id) == start and len(store.events(case_id)) == written


@pytest.mark.parametrize("action", ANALYST_ACTIONS)
def test_d034_a_closed_case_takes_no_analyst_action(action):
    store = new_store()
    case_id = at(store, "closed")
    written = len(store.events(case_id))
    for new_status in (None, "review"):
        with pytest.raises(StoreError, match="a closed case takes no analyst action"):
            act(store, case_id, action, new_status)
    assert store.queue_status(case_id) == "closed" and len(store.events(case_id)) == written


@pytest.mark.parametrize("actor_id", ["", " "])
def test_ac_01_an_analyst_action_needs_a_person(actor_id):
    """Spec 18 A7: `analyst:` with a blank sub is no person; nothing is written."""
    store = new_store()
    case_id = open_case(store).case_id
    with pytest.raises(StoreError, match="not a store actor"):
        act(store, case_id, "take", "review", actor_id=actor_id)
    assert types(store, case_id) == ["case_opened"]


@pytest.mark.parametrize("actor", ["", "bot", "analyst:", "analyst: "])
def test_ac_01_every_write_names_a_store_actor(actor):
    store = new_store()
    case = open_case(store)
    for write in (lambda: store.create_case(new_case(transaction_id="TRX-" + "H" * 20), actor=actor,
                                            action_id=ids.new_id("action")),
                  lambda: store.append_event(case.case_id, "handoff_emitted", actor=actor, trace_id="t"),
                  lambda: store.change_status(case.case_id, "review", on=ON, actor=actor, trace_id="t"),
                  lambda: store.block_product(case.case_id, case.product_id, action_id=ids.new_id("action"),
                                              actor=actor, trace_id="t"),
                  lambda: store.record_verification(case.case_id, case.action_id, read="get_case", run_id=None,
                                                    customer_id=None, actor=actor, trace_id="t"),
                  lambda: store.add_notification(case.case_id, event="case_opened", channel="log",
                                                 masked_address=None, text="Abrimos.", trigger="auto", actor=actor,
                                                 trace_id="t")):
        with pytest.raises(StoreError, match="not a store actor"):
            write()
    assert types(store, case.case_id) == ["case_opened"] and len(store.list_cases("CLI-000001", run_id=None)) == 1


def nothing_written(store: Store, case) -> bool:
    return (types(store, case.case_id) == ["case_opened"] and store.product_status(case.product_id, run_id=None) is None
            and store.list_notifications(case.customer_id, run_id=None) == []
            and len(store.list_cases(case.customer_id, run_id=None)) == 1)


@pytest.mark.parametrize("trace_id", [None, "", 7])
def test_ac_01_every_write_checks_its_trace_id_before_writing(trace_id):
    """A bad trace id is refused before the first write: no override without its card_blocked, no notification
    without its notification_sent, no analyst_action without its status change; the action id stays free."""
    store = new_store()
    case = open_case(store)
    block, summary = ids.new_id("action"), ids.new_id("action")
    request = AnalystActionIn(case_id=case.case_id, actor_id="sub-1", action="take", idempotency_key="k")
    writes = [lambda: store.append_event(case.case_id, "handoff_emitted", actor="agent", trace_id=trace_id),
              lambda: store.change_status(case.case_id, "review", on=ON, actor="agent", trace_id=trace_id),
              lambda: store.record_analyst_action(request, new_status="review", on=ON, trace_id=trace_id),
              lambda: store.block_product(case.case_id, case.product_id, action_id=block, actor="agent",
                                          trace_id=trace_id),
              lambda: store.record_verification(case.case_id, case.action_id, read="get_case", run_id=None,
                                                customer_id=None, actor="agent", trace_id=trace_id),
              lambda: store.add_notification(case.case_id, event="receipt", channel="log", masked_address=None,
                                             text="Resumen", trigger="on_request", actor="customer",
                                             trace_id=trace_id, action_id=summary)]
    if trace_id == "":                                     # NewCase itself refuses a trace id that is not a str
        writes.append(lambda: store.create_case(new_case(transaction_id="TRX-" + "H" * 20, trace_id=""),
                                                actor="agent", action_id=ids.new_id("action")))
    for write in writes:
        with pytest.raises(StoreError, match="not a trace id"):
            write()
    assert nothing_written(store, case)
    store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")


@pytest.mark.parametrize("on", ["2026-06-02", dt.datetime(2026, 6, 3, 2, 0, tzinfo=dt.UTC), None])
def test_ac_01_a_status_change_needs_a_business_date_before_writing(on):
    """D-023: `on` is a date; a datetime is refused, since its UTC day may not be the country's business day."""
    store = new_store()
    case = open_case(store)
    request = AnalystActionIn(case_id=case.case_id, actor_id="sub-1", action="take", idempotency_key="k")
    for write in (lambda: store.record_analyst_action(request, new_status="review", on=on, trace_id="t"),
                  lambda: store.change_status(case.case_id, "review", on=on, actor="agent", trace_id="t")):
        with pytest.raises(StoreError, match="not a business date"):
            write()
    assert nothing_written(store, case) and store.queue_status(case.case_id) == "new"


@pytest.mark.parametrize("start, attempt, error", [
    # the queue table alone refuses these
    ("resolved", lambda s, c: s.change_status(c, "new", on=ON, actor="agent", trace_id="t"), "resolved -> new"),
    ("resolved", lambda s, c: act(s, c, "resolve", "resolved"), "resolved -> resolved"),
    ("new", lambda s, c: act(s, c, "close_case", "closed"), "new -> closed"),
    ("verification", lambda s, c: act(s, c, "take", "verification"), "verification -> verification"),
    # only an analyst resolve or close_case resolves or closes
    ("resolved", lambda s, c: s.change_status(c, "closed", on=ON, actor="agent", trace_id="t"), "close_case closes"),
    # an analyst action and its statuses are tied (ANALYST_SOURCES, ANALYST_TARGETS; D-034)
    ("review", lambda s, c: act(s, c, "take", "resolved"), "take moves a case only to review or verification"),
    ("review", lambda s, c: act(s, c, "take", None), "take moves"),
    ("resolved", lambda s, c: act(s, c, "take", "review"), "take starts only from new or review or verification"),
    ("resolved", lambda s, c: act(s, c, "close_case", "review"), "close_case moves a case only to closed"),
    ("resolved", lambda s, c: act(s, c, "close_case", None), "close_case moves"),
    ("review", lambda s, c: act(s, c, "close_case", "resolved"), "close_case moves"),
    ("review", lambda s, c: act(s, c, "resolve", "review"), "resolve moves a case only to resolved"),
    ("review", lambda s, c: act(s, c, "resolve", None), "resolve moves"),
    ("resolved", lambda s, c: act(s, c, "reopen_case", "closed"), "reopen_case moves a case only to review"),
    ("review", lambda s, c: act(s, c, "reopen_case", "review"), "reopen_case starts only from resolved"),
    ("resolved", lambda s, c: act(s, c, "approve_credit", "review"), "approve_credit keeps the status"),
    ("review", lambda s, c: act(s, c, "request_customer_info", "review"), "request_customer_info keeps the status"),
])
def test_ac_01_status_changes_follow_case_queue_transitions(start, attempt, error):
    """policies.yaml case_queue.transitions and the analyst action's own statuses (engine.transition once 02a merges);
    each case is refused by one rule only, and a refused change writes nothing."""
    store = new_store()
    case_id = at(store, start)
    written = len(store.events(case_id))
    with pytest.raises(StoreError, match=error):
        attempt(store, case_id)
    assert store.queue_status(case_id) == start and len(store.events(case_id)) == written


def test_ac_01_eval_runs_get_fresh_case_ids_and_never_see_each_other():
    """§6.8: the same fixture seeded in four runs gives four case ids, each visible only in its run."""
    store = new_store()
    runs = [f"EV-0001:S1:{k}" for k in range(1, 5)]
    seeded = {run: open_case(store, actor="system", run_id=run).case_id for run in runs}
    assert len(set(seeded.values())) == 4
    for run, case_id in seeded.items():
        assert [c.case_id for c in store.list_cases("CLI-000001", run_id=run)] == [case_id]
        assert all(store.get_case(other, run_id=run, customer_id=None) is None
                   for other in seeded.values() if other != case_id)
    assert store.list_cases("CLI-000001", run_id=None) == []                   # production sees no eval rows
    assert store.list_cases("CLI-000002", run_id=runs[0]) == []                # nor another customer


def test_ac_01_reads_and_related_cases_are_scoped_to_the_session_customer():
    """Constitution #3: another customer's case reads as missing; customer_id=None is the analyst console; a related
    case must be a closed case of the same customer, in the same run."""
    store = new_store()
    mine, theirs = at(store, "closed"), at(store, "closed", customer_id="CLI-000002")
    assert store.get_case(theirs, run_id=None, customer_id="CLI-000001") is None
    assert store.get_case(theirs, run_id=None, customer_id=None).customer_id == "CLI-000002"
    assert store.get_case(mine, run_id=None, customer_id="CLI-000001").case_id == mine
    seeded, active = at(store, "closed", run_id=RUN), open_case(store, transaction_id="TRX-" + "J" * 20).case_id
    for related in (theirs, seeded, active):
        with pytest.raises(StoreError, match="related case"):
            open_case(store, related_case_id=related)
    assert len(store.list_cases("CLI-000001", run_id=None)) == 2                # refused = nothing written
    assert open_case(store, related_case_id=mine).related_case_id == mine


def test_ac_01_a_related_case_is_written_on_both_cases_and_active_cases_come_first():
    """A closed case newer than two active ones still sorts after them."""
    store = ticking_store()
    old = at(store, "closed")
    related = open_case(store, actor="customer", related_case_id=old).case_id
    assert (store.events(old)[-1].type, store.events(old)[-1].actor) == ("related_case_opened", "customer")
    assert store.events(old)[-1].payload == {"case_id": related}
    active = open_case(store, transaction_id="TRX-" + "D" * 20).case_id
    closed_newer = at(store, "closed", transaction_id="TRX-" + "F" * 20)
    assert [c.case_id for c in store.list_cases("CLI-000001", run_id=None)] == [active, related, closed_newer, old]


@pytest.mark.parametrize("status", ["verification", "review", "resolved"])
def test_ac_01_an_open_case_takes_customer_writes_past_new(status):
    """The closed-case refusal stops at closed: an analyst's review takes information (request_customer_info), a
    resolved case takes a re-evaluation (spec 03 AC-19), and every open case takes a block and a call request."""
    store = new_store()
    case = store.get_case(at(store, status), run_id=None, customer_id=None)
    for write in ("customer_info_added", "call_requested", "reevaluation_requested"):
        event = store.append_event(case.case_id, write, actor="customer", trace_id="t",
                                   payload={"action_id": ids.new_id("action")})
        assert (event.type, store.events(case.case_id)[-1].event_id) == (write, event.event_id)
    block = ids.new_id("action")
    assert store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t").type == \
        "card_blocked"
    assert store.product_status(case.product_id, run_id=None).action_id == block
    assert store.queue_status(case.case_id) == status


def test_ac_01_a_closed_case_takes_no_customer_write():
    """§6.5: block, information, call and re-evaluation on a closed case are refused (the tool opens a related case);
    a summary send (N) and automatic notifications stay allowed."""
    store = new_store()
    case = store.get_case(at(store, "closed"), run_id=None, customer_id=None)
    written = len(store.events(case.case_id))
    for write in ("customer_info_added", "call_requested", "reevaluation_requested"):
        with pytest.raises(StoreError, match="is closed"):
            store.append_event(case.case_id, write, actor="customer", trace_id="t",
                               payload={"action_id": ids.new_id("action")})
    with pytest.raises(StoreError, match="is closed"):
        store.block_product(case.case_id, case.product_id, action_id=ids.new_id("action"), actor="agent", trace_id="t")
    assert len(store.events(case.case_id)) == written and store.product_status(case.product_id, run_id=None) is None
    store.add_notification(case.case_id, event="receipt", channel="log", masked_address=None, text="Resumen",
                           trigger="on_request", actor="customer", trace_id="t", action_id=ids.new_id("action"))
    store.append_event(case.case_id, "receipt_issued", actor="agent", trace_id="t")
    assert types(store, case.case_id)[-2:] == ["notification_sent", "receipt_issued"]


def test_d014_stored_deadlines_and_payloads_come_back_unchanged():
    """Spec 03 AC-16 and D-014: deadlines with source, URL and verified_on are stored once and read back as stored;
    a call_requested payload keeps expected_contact_by as written (D-008)."""
    store = new_store()
    case = open_case(store)
    assert store.get_case(case.case_id, run_id=None, customer_id=None).model_dump(include=set(FACTS)) == FACTS
    request = {"action_id": ids.new_id("action"), "expected_contact_by": "2026-06-02"}
    store.append_event(case.case_id, "call_requested", actor="agent", trace_id="t", payload=request)
    assert store.events(case.case_id)[-1].payload == request


@pytest.mark.parametrize("change", [{"deadline_verified_on": None}, {"deadline_source": None},
                                    {"deadline_source_url": None}, {"credit_deadline": None,
                                                                    "ruling_deadline": dt.date(2026, 7, 1),
                                                                    "deadline_verified_on": None}])
def test_d014_a_deadline_date_needs_its_source_url_and_verified_on(change):
    with pytest.raises(ValidationError, match="deadline_verified_on"):
        new_case(**change)
    assert new_case(credit_deadline=None, deadline_source=None, deadline_source_url=None, deadline_verified_on=None)
    for bad in ({"deadline_source_url": "http://insecure.example"}, {"credit_deadline": None, "deadline_source": ""}):
        with pytest.raises(ValidationError):
            new_case(**bad)


def test_d023_a_case_needs_its_business_date():
    with pytest.raises(ValidationError, match="opened_on"):
        NewCase(**{k: v for k, v in FACTS.items() if k != "opened_on"})


def test_d025_a_write_has_no_verification_id_and_each_read_mints_one():
    """The verifying read mints the V- id (`action_verified`); case_opened and card_blocked carry only the action.
    The read must be of the case's own run and customer, and of an action written on that case."""
    store = ticking_store()
    case = open_case(store)
    assert case.verification_id is None and store.events(case.case_id)[0].payload == {"action_id": case.action_id}
    assert store.get_case(case.case_id, run_id=None, customer_id=None).verification_id is None
    first = verify(store, case.case_id, case.action_id, customer_id="CLI-000001")
    second = verify(store, case.case_id, case.action_id)
    assert set(first.payload) == {"action_id", "verification_id", "read_at", "read"} and not first.customer_visible
    assert ids.is_valid("verification", first.payload["verification_id"])
    assert first.payload["verification_id"] != second.payload["verification_id"]
    assert first.payload["read_at"] < second.payload["read_at"]
    assert store.get_case(case.case_id, run_id=None, customer_id=None).verification_id == \
        second.payload["verification_id"]
    assert types(store, case.case_id).count("action_verified") == 2                    # the audit trail stays
    cited = ids.new_id("action")                                     # an action id outside a write does not count
    store.append_event(case.case_id, "handoff_emitted", actor="agent", trace_id="t", payload={"action_id": cited})
    seeded, theirs = open_case(store, run_id=RUN), open_case(store, customer_id="CLI-000002")
    other = open_case(store, transaction_id="TRX-" + "K" * 20)
    written = {c: len(store.events(c)) for c in (case.case_id, seeded.case_id, theirs.case_id, other.case_id)}
    for bad in (lambda: verify(store, case.case_id, ids.new_id("action")),
                lambda: verify(store, case.case_id, cited),
                lambda: verify(store, case.case_id, case.action_id, run_id=RUN),
                lambda: verify(store, seeded.case_id, seeded.action_id, run_id=None),        # a run case, read live
                lambda: verify(store, other.case_id, case.action_id),                       # case B, action of A
                lambda: verify(store, theirs.case_id, theirs.action_id, customer_id="CLI-000001")):
        with pytest.raises(StoreError):
            bad()
    assert {c: len(store.events(c)) for c in written} == written


@pytest.mark.parametrize("write", sorted(WRITE_EVENTS))
def test_d025_each_write_is_verified_only_by_its_read(write):
    """VERIFIED_WITH (§6.3): a read verifies only the writes it can see; the reads without a case id find the case by
    the action id (`action_write`); any other read is refused and writes nothing."""
    store = new_store()
    case = open_case(store, run_id=RUN)
    action_id = case.action_id if write == "case_opened" else ids.new_id("action")
    if write == "card_blocked":
        store.block_product(case.case_id, case.product_id, action_id=action_id, actor="agent", trace_id="t")
    elif write == "notification_sent":
        store.add_notification(case.case_id, event="receipt", channel="log", masked_address=None, text="Resumen",
                               trigger="on_request", actor="customer", trace_id="t", action_id=action_id)
    elif write != "case_opened":
        store.append_event(case.case_id, write, actor="customer", trace_id="t", payload={"action_id": action_id})
    found = store.action_write(action_id, run_id=RUN, customer_id="CLI-000001")
    assert (found.type, found.case_id, found.payload["action_id"]) == (write, case.case_id, action_id)
    found.payload["action_id"] = "A-000000000000"                                      # a copy, not the row
    assert store.action_write(action_id, run_id=RUN, customer_id=None).payload["action_id"] == action_id
    assert store.action_write(action_id, run_id=None, customer_id=None) is None
    assert store.action_write(action_id, run_id=RUN, customer_id="CLI-000002") is None
    right = VERIFIED_WITH[WRITE_TOOL[write]]
    written = len(store.events(case.case_id))
    for read in sorted(set(get_args(VerifyingRead)) - {right}):
        with pytest.raises(StoreError, match=f"verified with {right}, not {read}"):
            verify(store, found.case_id, action_id, read=read, run_id=RUN, customer_id="CLI-000001")
    assert len(store.events(case.case_id)) == written
    read = verify(store, found.case_id, action_id, read=right, run_id=RUN, customer_id="CLI-000001")
    assert (read.type, read.payload["action_id"]) == ("action_verified", action_id)
    assert set(WRITE_TOOL.values()) == set(VERIFIED_WITH)
    assert set(VERIFIED_WITH.values()) == set(get_args(VerifyingRead))


def test_d025_verifications_lists_every_read_of_one_action_in_read_order():
    """get_case shows the latest V- id; `verifications` returns all of them, so the auditor accepts any V- id a turn
    showed (read_at at or after the request)."""
    store = ticking_store()
    case = open_case(store, run_id=RUN)
    block = ids.new_id("action")
    store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    reads = [verify(store, case.case_id, action, read=read, run_id=RUN).payload
             for action, read in ((case.action_id, "get_case"), (block, "get_product_status"),
                                  (case.action_id, "get_case"))]
    listed = store.verifications(case.case_id, case.action_id, run_id=RUN)
    assert [e.payload for e in listed] == [reads[0], reads[2]] and {e.type for e in listed} == {"action_verified"}
    assert [e.payload for e in store.verifications(case.case_id, block, run_id=RUN)] == [reads[1]]
    assert store.get_case(case.case_id, run_id=RUN, customer_id=None).verification_id == reads[2]["verification_id"]
    assert store.verifications(case.case_id, case.action_id, run_id=None) == []        # another run reads nothing
    listed[0].payload["verification_id"] = "V-000000000000"                            # a copy, not the row
    assert store.verifications(case.case_id, case.action_id, run_id=RUN)[0].payload == reads[0]


def test_d025_the_first_read_of_a_block_writes_block_verified_once():
    """`block_verified` ✓ is the customer milestone: written by the store on the first read of each card_blocked
    action, never by append_event, never on a repeated read, never for another write."""
    store = new_store()
    case = open_case(store)
    verify(store, case.case_id, case.action_id)
    block = ids.new_id("action")
    store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    assert "block_verified" not in types(store, case.case_id)
    verify(store, case.case_id, block, read="get_product_status")
    assert types(store, case.case_id)[-2:] == ["action_verified", "block_verified"]
    verify(store, case.case_id, block, read="get_product_status")
    again = ids.new_id("action")
    store.block_product(case.case_id, case.product_id, action_id=again, actor="agent", trace_id="t")
    verify(store, case.case_id, again, read="get_product_status")
    verified = [e for e in store.events(case.case_id) if e.type == "block_verified"]
    assert [(e.payload, e.customer_visible) for e in verified] == [
        ({"action_id": block, "product_id": case.product_id}, True),
        ({"action_id": again, "product_id": case.product_id}, True)]


def test_d025_a_stale_block_read_verifies_nothing():
    """The post-condition is the card's current status: a block is verified only while its override is the latest of
    the product in the run and Blocked. Until the unblock writer lands (03/05), the test writes the Active row."""
    store = new_store()
    case = open_case(store, run_id=RUN)
    first, second = ids.new_id("action"), ids.new_id("action")
    for block in (first, second):
        store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    written = len(store.events(case.case_id))
    with pytest.raises(NotVerified, match="no longer the card's current status"):
        verify(store, case.case_id, first, read="get_product_status", run_id=RUN)
    assert len(store.events(case.case_id)) == written
    unblock = ids.new_id("action")
    write_override(store, ProductOverride(product_id=case.product_id, status="Active", case_id=case.case_id,
                                          action_id=unblock, actor="analyst:sub-1", run_id=RUN,
                                          created_at=dt.datetime.now(dt.UTC)))
    with pytest.raises(NotVerified, match="no longer the card's current status"):
        verify(store, case.case_id, second, read="get_product_status", run_id=RUN)
    assert len(store.events(case.case_id)) == written and "block_verified" not in types(store, case.case_id)


def write_override(store: Store, row: ProductOverride) -> None:
    """A product_overrides row written as the unblock writer (03/05) will, until it lands."""
    if isinstance(store, MemoryStore):
        store._overrides[row.action_id] = row
    else:
        store._rows("insert into product_overrides (override_id, product_id, status, case_id, actor, run_id, "
                    "created_at) values (%(action_id)s, %(product_id)s, %(status)s, %(case_id)s, %(actor)s, "
                    "%(run_id)s, %(created_at)s)", row.model_dump())


@pytest.mark.parametrize("clock", ["fixed", "backward"])
def test_d025_the_latest_override_is_the_last_one_written_whatever_the_clock(clock):
    """§6.5 "latest" is the row inserted last (Postgres `row_no`), not the latest `created_at`: with a repeated or
    backward clock the newer block is the card's status, and a block overridden to Active verifies nothing."""
    store = clock_store(clock)
    case = open_case(store, run_id=RUN)
    first, second = ids.new_id("action"), ids.new_id("action")
    for block in (first, second):
        store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    assert store.product_status(case.product_id, run_id=RUN).action_id == second
    with pytest.raises(NotVerified, match="no longer the card's current status"):
        verify(store, case.case_id, first, read="get_product_status", run_id=RUN)
    verify(store, case.case_id, second, read="get_product_status", run_id=RUN)
    write_override(store, ProductOverride(product_id=case.product_id, status="Active", case_id=case.case_id,
                                          action_id=ids.new_id("action"), actor="analyst:sub-1", run_id=RUN,
                                          created_at=FIXED - dt.timedelta(hours=clock == "backward")))
    written = len(store.events(case.case_id))
    assert store.product_status(case.product_id, run_id=RUN).status == "Active"
    with pytest.raises(NotVerified, match="no longer the card's current status"):
        verify(store, case.case_id, second, read="get_product_status", run_id=RUN)
    assert len(store.events(case.case_id)) == written


@pytest.mark.parametrize("clock", ["fixed", "backward"])
def test_d035_the_latest_delivery_is_the_last_one_written_whatever_the_clock(clock):
    """D-035 with a repeated or backward clock: a summary whose last delivery failed is not verified and is listed
    as failed; the next delivery verifies it again (§6.5 "latest" = inserted last)."""
    store = clock_store(clock)
    case_id = open_case(store).case_id
    summary = ids.new_id("action")
    sent = store.add_notification(case_id, event="receipt", channel="email", masked_address="j***@example.com",
                                  text="Resumen", trigger="on_request", actor="customer", trace_id="t",
                                  action_id=summary)
    store.add_delivery(sent.notification_id, "failed")
    written = len(store.events(case_id))
    with pytest.raises(NotVerified, match=f"summary {summary} failed"):
        verify(store, case_id, summary, read="list_my_notifications")
    assert len(store.events(case_id)) == written
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id=None)] == ["failed"]
    store.add_delivery(sent.notification_id, "delivered")
    verify(store, case_id, summary, read="list_my_notifications")
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id=None)] == ["delivered"]


def test_ac_01_list_order_breaks_a_created_at_tie_by_id_on_both_backends():
    """§6.5: with one instant for every row, active cases still come first, then each list is by id descending."""
    store = clock_store("fixed")
    active = [open_case(store, transaction_id="TRX-" + c * 20).case_id for c in "HJMQ"]
    closed = at(store, "closed", transaction_id="TRX-" + "N" * 20)
    assert [c.case_id for c in store.list_cases("CLI-000001", run_id=None)] == sorted(active, reverse=True) + [closed]
    sent = [store.add_notification(active[0], event="case_opened", channel="log", masked_address=None, text=text,
                                   trigger="auto", actor="system", trace_id="t").notification_id for text in "abcdef"]
    assert [n.notification_id for n in store.list_notifications("CLI-000001", run_id=None)] == sorted(sent,
                                                                                                       reverse=True)


def test_ac_01_both_backends_refuse_a_bad_action_id_nul_and_lone_surrogates_alike():
    """§6.5: any `payload.action_id` is an A- id, and no payload or notification text holds NUL or a lone surrogate;
    both backends raise StoreError (Postgres cannot store them) and write nothing."""
    store = new_store()
    case_id = open_case(store).case_id
    written, nul, surrogate = len(store.events(case_id)), chr(0), chr(0xD800)
    for type, payload in [("handoff_emitted", {"action_id": "bogus"}), ("receipt_issued", {"action_id": None}),
                          ("handoff_emitted", {"text": "a" + nul}), ("handoff_emitted", {"text": surrogate}),
                          ("handoff_emitted", {"key" + nul: 1}),
                          ("customer_info_added", {"action_id": ids.new_id("action"), "text": "Nunca" + nul})]:
        with pytest.raises(StoreError, match="not an action id|not storable text"):
            store.append_event(case_id, type, actor="customer", trace_id="t", payload=payload)
    for text in ("Abrimos" + nul, surrogate):
        with pytest.raises(StoreError, match="not storable text"):
            store.add_notification(case_id, event="case_opened", channel="log", masked_address=None, text=text,
                                   trigger="auto", actor="system", trace_id="t")
    for writer in (lambda: store.create_case(new_case(trace_id="t" + nul), actor="agent",
                                             action_id=ids.new_id("action")),
                   lambda: store.create_case(new_case(transaction_id="TRX-" + nul), actor="agent",
                                             action_id=ids.new_id("action")),
                   lambda: store.append_event(case_id, "handoff_emitted", actor="agent", trace_id="t" + nul),
                   lambda: store.append_event(case_id, "handoff_emitted", actor="analyst:x" + nul, trace_id="t")):
        with pytest.raises(StoreError, match="not storable text"):
            writer()
    with pytest.raises(StoreError):                         # Postgres: before the advisory-lock query, not raw
        store.append_event("K-" + surrogate, "handoff_emitted", actor="agent", trace_id="t")
    assert len(store.events(case_id)) == written and store.list_notifications("CLI-000001", run_id=None) == []
    assert [c.case_id for c in store.list_cases("CLI-000001", run_id=None)] == [case_id]


def test_d035_a_summary_send_is_verified_only_while_its_latest_delivery_is_not_lost():
    """[assumption] D-035: the post-condition of send_case_summary is its latest delivery; after `bounced` or
    `failed` the read stays plain (NotVerified, nothing written), and a later delivery verifies it again."""
    store = new_store()
    case_id = open_case(store).case_id
    summary = ids.new_id("action")
    sent = store.add_notification(case_id, event="receipt", channel="email", masked_address="j***@example.com",
                                  text="Resumen", trigger="on_request", actor="customer", trace_id="t",
                                  action_id=summary)
    verified = [verify(store, case_id, summary, read="list_my_notifications")]           # queued
    for lost in ("bounced", "failed"):
        store.add_delivery(sent.notification_id, lost)
        written = len(store.events(case_id))
        with pytest.raises(NotVerified, match=f"summary {summary} {lost}"):
            verify(store, case_id, summary, read="list_my_notifications")
        assert len(store.events(case_id)) == written
        store.add_delivery(sent.notification_id, "delivered")
        verified.append(verify(store, case_id, summary, read="list_my_notifications"))
    assert [e.payload for e in store.verifications(case_id, summary, run_id=None)] == [e.payload for e in verified]
    with pytest.raises(StoreError, match="not a delivery status"):
        store.add_delivery(sent.notification_id, "exploded")
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id=None)] == ["delivered"]


def test_d025_the_store_import_of_verified_with_matches_the_contract():
    """The store imports VERIFIED_WITH from contracts.tools (spec 01 §6.3)."""
    assert VERIFIED_WITH is contract_tools.VERIFIED_WITH


@pytest.mark.parametrize("write, payload", [("customer_info_added", {"text": "Nunca estuve en Monterrey"}),
                                            ("call_requested", {"preferred_time": "tarde"})])
def test_d025_add_case_info_and_request_call_are_verified_by_a_read_of_their_action(write, payload):
    """Every customer write carries its own action id; the read that finds the event mints its V- id."""
    store = new_store()
    case = open_case(store, run_id=RUN)
    action_id = ids.new_id("action")
    store.append_event(case.case_id, write, actor="customer", trace_id="t", payload={"action_id": action_id, **payload})
    read = verify(store, case.case_id, action_id, run_id=RUN, customer_id="CLI-000001")
    assert (read.type, read.payload["action_id"]) == ("action_verified", action_id)
    assert store.verifications(case.case_id, action_id, run_id=RUN)[0].payload == read.payload
    assert store.get_case(case.case_id, run_id=RUN, customer_id=None).verification_id is None   # opening unread
    assert "block_verified" not in types(store, case.case_id)


def test_d025_a_write_event_needs_a_fresh_action_id():
    store = new_store()
    case_id = open_case(store).case_id
    for write in ("customer_info_added", "call_requested", "reevaluation_requested"):
        for payload in (None, {"text": "x"}, {"action_id": "A-1"}):
            with pytest.raises(StoreError, match="not an action id"):
                store.append_event(case_id, write, actor="customer", trace_id="t", payload=payload)
    assert types(store, case_id) == ["case_opened"]


def test_d025_an_action_id_is_written_once():
    """One write per action id over the six write events, so one read can never verify two actions (Postgres: a
    unique index, T10)."""
    store = new_store()
    case = open_case(store)
    block, info, summary = ids.new_id("action"), ids.new_id("action"), ids.new_id("action")
    store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    store.append_event(case.case_id, "customer_info_added", actor="customer", trace_id="t", payload={"action_id": info})
    store.add_notification(case.case_id, event="receipt", channel="log", masked_address=None, text="Resumen",
                           trigger="on_request", actor="customer", trace_id="t", action_id=summary)
    written = len(store.events(case.case_id))
    for reuse in (lambda: store.block_product(case.case_id, case.product_id, action_id=case.action_id, actor="agent",
                                              trace_id="t"),
                  lambda: store.block_product(case.case_id, case.product_id, action_id=block, actor="agent",
                                              trace_id="t"),
                  lambda: store.block_product(case.case_id, case.product_id, action_id=info, actor="agent",
                                              trace_id="t"),
                  lambda: store.create_case(new_case(transaction_id="TRX-" + "G" * 20), actor="agent",
                                            action_id=case.action_id),
                  lambda: store.create_case(new_case(transaction_id="TRX-" + "G" * 20), actor="agent",
                                            action_id=summary),
                  lambda: store.append_event(case.case_id, "call_requested", actor="customer", trace_id="t",
                                             payload={"action_id": block}),
                  lambda: store.append_event(case.case_id, "call_requested", actor="customer", trace_id="t",
                                             payload={"action_id": summary}),
                  lambda: store.add_notification(case.case_id, event="receipt", channel="log", masked_address=None,
                                                 text="Resumen", trigger="on_request", actor="customer",
                                                 trace_id="t", action_id=info)):
        with pytest.raises(StoreError, match="already written; a write takes a fresh action id"):
            reuse()
    assert len(store.events(case.case_id)) == written and len(store.list_cases("CLI-000001", run_id=None)) == 1
    assert store.product_status(case.product_id, run_id=None).action_id == block


def test_d025_a_block_is_an_override_in_its_run_verified_only_by_a_read():
    store = ticking_store()
    case = open_case(store, run_id=RUN)
    block = ids.new_id("action")
    event = store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    assert (event.type, event.payload) == ("card_blocked", {"action_id": block, "product_id": case.product_id})
    status = store.product_status(case.product_id, run_id=RUN)
    assert (status.status, status.action_id, status.verification_id, status.actor) == ("Blocked", block, None, "agent")
    reads = [verify(store, case.case_id, block, read="get_product_status", run_id=RUN) for _ in range(2)]
    assert store.product_status(case.product_id, run_id=RUN).verification_id == reads[1].payload["verification_id"]
    assert store.product_status(case.product_id, run_id=None) is None           # another run reads gold
    again = ids.new_id("action")
    store.block_product(case.case_id, case.product_id, action_id=again, actor="agent", trace_id="t")
    latest = store.product_status(case.product_id, run_id=RUN)
    assert (latest.action_id, latest.verification_id) == (again, None)         # the latest write, not yet read
    written = len(store.events(case.case_id))
    for bad in (lambda: store.block_product(case.case_id, "PRD-" + "Z" * 12, action_id=ids.new_id("action"),
                                            actor="agent", trace_id="t"),
                lambda: store.block_product(case.case_id, case.product_id, action_id="A-1", actor="agent",
                                            trace_id="t"),
                lambda: store.create_case(new_case(), actor="agent", action_id="not-an-action")):
        with pytest.raises(StoreError):
            bad()
    assert len(store.events(case.case_id)) == written and len(store.list_cases("CLI-000001", run_id=None)) == 0


def test_ac_01_notifications_belong_to_the_case_customer_and_show_the_latest_delivery():
    store = new_store()
    case_id = open_case(store, run_id=RUN).case_id
    sent = store.add_notification(case_id, event="case_opened", channel="telegram", masked_address="@ju***",
                                  text="Abrimos tu caso.", trigger="auto", actor="system", trace_id="t")
    other = open_case(store, run_id=RUN, customer_id="CLI-000002").case_id
    store.add_notification(other, event="case_opened", channel="log", masked_address=None, text="Abrimos tu caso.",
                           trigger="auto", actor="system", trace_id="t")
    assert sent.customer_id == "CLI-000001" and ids.is_valid("notification", sent.notification_id)
    assert store.events(case_id)[-1].payload == {"notification_id": sent.notification_id, "event": "case_opened",
                                                 "channel": "telegram"}
    assert [n.notification_id for n in store.list_notifications("CLI-000001", run_id=RUN)] == [sent.notification_id]
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id=RUN)] == ["queued"]
    store.add_delivery(sent.notification_id, "sent")
    store.add_delivery(sent.notification_id, "delivered", {"type": "email.delivered"})
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id=RUN)] == ["delivered"]
    newer = store.add_notification(case_id, event="in_review", channel="log", masked_address=None, text="Revisando.",
                                   trigger="auto", actor="system", trace_id="t")
    assert [n.notification_id for n in store.list_notifications("CLI-000001", run_id=RUN)] == [
        newer.notification_id, sent.notification_id]                               # newest first
    assert store.list_notifications("CLI-000001", run_id=None) == []
    with pytest.raises(StoreError):
        store.add_delivery("N-000000000000", "sent")


def test_d025_a_case_summary_send_carries_its_action_and_an_auto_send_has_none():
    """send_case_summary (`on_request`) is a customer write with its own action id; an `auto` send is not."""
    store = new_store()
    case_id = open_case(store).case_id
    summary = ids.new_id("action")
    store.add_notification(case_id, event="receipt", channel="email", masked_address="j***@example.com",
                           text="Resumen", trigger="on_request", actor="customer", trace_id="t", action_id=summary)
    assert store.events(case_id)[-1].payload["action_id"] == summary
    read = verify(store, case_id, summary, read="list_my_notifications")
    assert read.payload["action_id"] == summary
    written = len(store.events(case_id))
    for bad in ({"trigger": "auto", "action_id": ids.new_id("action")}, {"trigger": "on_request", "action_id": None}):
        with pytest.raises(StoreError, match="action id"):
            store.add_notification(case_id, event="receipt", channel="log", masked_address=None, text="Resumen",
                                   actor="customer", trace_id="t", **bad)
    assert len(store.events(case_id)) == written and len(store.list_notifications("CLI-000001", run_id=None)) == 1


def test_d025_action_verified_names_the_read_that_minted_its_id():
    """18x X1-3: `action_verified` carries `read`, the VERIFIED_WITH tool that minted the V- id, as stored and as
    returned, so the auditor (A3) can check it against the write's tool; on both backends."""
    store = new_store()
    case = open_case(store, run_id=RUN)
    block = ids.new_id("action")
    store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    reads = [verify(store, case.case_id, case.action_id, run_id=RUN),
             verify(store, case.case_id, block, read="get_product_status", run_id=RUN)]
    assert [r.payload["read"] for r in reads] == ["get_case", "get_product_status"]
    stored = [e.payload["read"] for e in store.events(case.case_id) if e.type == "action_verified"]
    assert stored == [VERIFIED_WITH[WRITE_TOOL[w]] for w in ("case_opened", "card_blocked")]


# ---------- [postgres] only: the per-case advisory lock and the one transaction behind each write (T9) ----------
def postgres_only(backend: str) -> None:
    if backend != "postgres":
        pytest.skip("T9: the advisory lock and the transaction exist only in PostgresStore")


def at_once(calls: list[Callable[[], object]]) -> list[object]:
    """Each call on its own thread and connection, all released together; a StoreError is returned, not raised."""
    start = threading.Barrier(len(calls))

    def run(call: Callable[[], object]) -> object:
        start.wait()
        try:
            return call()
        except StoreError as error:
            return error
    with ThreadPoolExecutor(len(calls)) as pool:
        return list(pool.map(run, calls))


def test_t9_concurrent_writers_on_one_case_use_an_action_id_once_with_gap_free_seq(backend):
    """[postgres] 8 connections append to one case at once, 4 with one shared action id and 4 with fresh ones: the
    shared id is written once, every fresh one is written, and seq has no gap (without the lock they collide)."""
    postgres_only(backend)
    stores = [new_store() for _ in range(8)]
    case_id = open_case(stores[0]).case_id
    for _ in range(3):
        actions = [ids.new_id("action")] * 4 + [ids.new_id("action") for _ in range(4)]
        results = at_once([lambda s=s, a=a: s.append_event(case_id, "call_requested", actor="customer", trace_id="t",
                                                           payload={"action_id": a})
                           for s, a in zip(stores, actions)])
        assert sum(not isinstance(r, StoreError) for r in results[:4]) == 1
        assert [r for r in results[4:] if isinstance(r, StoreError)] == []
    events = stores[0].events(case_id)
    assert [e.seq for e in events] == list(range(1, 17)) and types(stores[0], case_id).count("call_requested") == 15


def test_t9_concurrent_first_reads_of_one_block_write_block_verified_once(backend):
    """[postgres] 8 connections make the first read of one block at once: 8 action_verified, exactly one
    block_verified, gap-free seq (the post-condition read and the inserts are one locked transaction)."""
    postgres_only(backend)
    stores = [new_store() for _ in range(8)]
    case = open_case(stores[0], run_id=RUN)
    for _ in range(3):
        block = ids.new_id("action")
        stores[0].block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
        results = at_once([lambda s=s: verify(s, case.case_id, block, read="get_product_status", run_id=RUN)
                           for s in stores])
        assert [r for r in results if isinstance(r, StoreError)] == []
    names = types(stores[0], case.case_id)
    assert names.count("action_verified") == 24 and names.count("block_verified") == 3
    assert [e.seq for e in stores[0].events(case.case_id)] == list(range(1, len(names) + 1))


def test_t9_the_unique_index_backstop_rolls_back_the_whole_write(backend, monkeypatch):
    """[postgres] With the action-id pre-check stubbed out, a reused id reaches the unique index mid-write; the one
    transaction rolls the write back: no override, no case row, no notification or delivery."""
    postgres_only(backend)
    store = new_store()
    case = open_case(store)
    block = ids.new_id("action")
    store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    monkeypatch.setattr(store, "_check_new_action", lambda action_id: None)
    tables = ("cases", "case_events", "product_overrides", "notifications", "notification_deliveries")

    def rows() -> list[int]:
        return [store._rows(f"select count(*) as n from {table}")[0]["n"] for table in tables]
    before = rows()
    for reuse in (lambda: store.block_product(case.case_id, case.product_id, action_id=case.action_id, actor="agent",
                                              trace_id="t"),
                  lambda: store.create_case(new_case(transaction_id="TRX-" + "P" * 20), actor="agent",
                                            action_id=block),
                  lambda: store.add_notification(case.case_id, event="receipt", channel="log", masked_address=None,
                                                 text="Resumen", trigger="on_request", actor="customer",
                                                 trace_id="t", action_id=block)):
        with pytest.raises(StoreError, match=r"already written \(case_events_action_id_once\)"):
            reuse()
    assert rows() == before and store.product_status(case.product_id, run_id=None).action_id == block


def test_t9_a_server_data_error_becomes_a_store_error(backend):
    """[postgres] The backstop behind check_text: a psycopg DataError inside a store transaction is a StoreError."""
    postgres_only(backend)
    store = new_store()
    with pytest.raises(StoreError, match="refused by the server"):
        with store._tx():
            store._rows("select %s::text", ("a" + chr(0),))
