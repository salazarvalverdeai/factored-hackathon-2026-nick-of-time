"""Spec 01 — the store: case ids (T9), append-only events, status as the last event, transitions, customer and run
scoping, verification ids (AC-01, §6.5, §6.8, D-014, D-023, D-025). Runs against the in-memory backend, which keeps
the same rules as Postgres."""
from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn
from nick_of_time.store import CUSTOMER_VISIBLE, RESERVED_EVENTS, NewCase, Store, StoreError
from nick_of_time.store.memory import MemoryStore

FACTS = dict(customer_id="CLI-000001", transaction_id="TRX-" + "A" * 20, product_id="PRD-" + "B" * 12, country="MX",
             product_type="debit", zone="high", dispute_type="unrecognized_charge", opened_on=dt.date(2026, 6, 1),
             credit_deadline=dt.date(2026, 6, 3), deadline_source="Banxico Circular 3/2012",
             deadline_source_url="https://www.banxico.org.mx/", deadline_verified_on=dt.date(2026, 10, 4),
             mode="replay", trace_id="trace-1")
ON = dt.date(2026, 6, 2)


def new_case(**changes) -> NewCase:
    return NewCase(**{**FACTS, **changes})


def open_case(store: MemoryStore, actor: str = "agent", **changes):
    return store.create_case(new_case(**changes), actor=actor, action_id=ids.new_id("action"))


def act(store: MemoryStore, case_id: str, action: str, new_status: str | None, reason: str | None = "x"):
    request = AnalystActionIn(case_id=case_id, actor_id="sub-1", action=action, reason=reason, idempotency_key="k")
    return store.record_analyst_action(request, new_status=new_status, on=ON, trace_id="t")


def ticking_store() -> MemoryStore:
    ticks = iter(dt.datetime(2026, 6, 1, 15, minute, tzinfo=dt.UTC) for minute in range(60))
    return MemoryStore(now=lambda: next(ticks))


def test_ac_01_memory_store_implements_the_store_interface():
    assert isinstance(MemoryStore(), Store)


def test_t9_case_insert_retries_with_a_fresh_id_on_a_forced_primary_key_collision(monkeypatch):
    store = MemoryStore()
    first = open_case(store)
    real, queue = ids.new_id, [first.case_id, "K-123456"]
    monkeypatch.setattr(ids, "new_id", lambda kind: queue.pop(0) if kind == "case" and queue else real(kind))
    second = open_case(store, transaction_id="TRX-" + "C" * 20)
    assert second.case_id == "K-123456"
    assert store.get_case(first.case_id, run_id=None, customer_id=None) == first     # the existing row is untouched
    assert [e.type for e in store.events(first.case_id)] == ["case_opened"]
    assert [e.type for e in store.events(second.case_id)] == ["case_opened"]


def test_t9_case_insert_gives_up_and_writes_nothing_when_every_id_collides(monkeypatch):
    store = MemoryStore()
    taken, real = open_case(store).case_id, ids.new_id
    monkeypatch.setattr(ids, "new_id", lambda kind: taken if kind == "case" else real(kind))
    with pytest.raises(StoreError, match="no free case id"):
        open_case(store, customer_id="CLI-000002")
    assert store.list_cases("CLI-000002", run_id=None) == []


def test_ac_01_status_is_the_last_status_changed_event_and_events_are_numbered():
    """FR-02: `new` until the first status_changed; payload {from, to, on, reason?} with the business date (D-023);
    seq 1..n; customer_visible follows the ✓ list of §6.5."""
    store = MemoryStore()
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
    store = MemoryStore()
    case_id = open_case(store).case_id
    assert RESERVED_EVENTS == {"case_opened", "status_changed", "analyst_action", "assigned", "related_case_opened",
                               "card_blocked", "action_verified", "notification_sent"}
    for reserved in sorted(RESERVED_EVENTS):
        with pytest.raises(StoreError, match="written only by the store"):
            store.append_event(case_id, reserved, actor="agent", trace_id="t")
    sent = {"detail": {"text": "Compra que no hice"}}
    store.append_event(case_id, "customer_info_added", actor="customer", trace_id="t", payload=sent)
    sent["detail"]["text"] = "edited"                                       # neither the written payload…
    store.events(case_id)[0].payload["to"] = "closed"                       # …nor a read changes what is stored
    assert store.events(case_id)[-1].payload == {"detail": {"text": "Compra que no hice"}}
    assert "to" not in store.events(case_id)[0].payload and store.queue_status(case_id) == "new"
    with pytest.raises(StoreError):
        store.append_event("K-999999", "customer_info_added", actor="agent", trace_id="t")


def test_ac_01_only_a_person_resolves_and_closes_and_closed_is_final():
    """Constitution #6 and spec 18 A7: `resolved` and `closed` come only from analysts; a closed case never moves."""
    store = MemoryStore()
    case_id = open_case(store).case_id
    taken = act(store, case_id, "take", "review", reason=None)
    assert (taken.previous_status, taken.new_status) == ("new", "review")
    act(store, case_id, "resolve", "resolved")
    closed = act(store, case_id, "close_case", "closed")
    assert (closed.previous_status, closed.new_status, store.queue_status(case_id)) == ("resolved", "closed", "closed")
    by_analyst = [e for e in store.events(case_id) if e.type in {"analyst_action", "assigned", "status_changed"}]
    assert {e.actor for e in by_analyst} == {"analyst:sub-1"} and "assigned" in {e.type for e in by_analyst}
    written = len(store.events(case_id))
    for attempt in (lambda: store.change_status(case_id, "review", on=ON, actor="agent", trace_id="t"),
                    lambda: act(store, case_id, "reopen_case", "review")):
        with pytest.raises(StoreError, match="closed -> review is not in case_queue.transitions"):
            attempt()
    assert store.queue_status(case_id) == "closed" and len(store.events(case_id)) == written   # refused = no write


@pytest.mark.parametrize("start, attempt, error", [
    ("new", lambda s, c: s.change_status(c, "resolved", on=ON, actor="agent", trace_id="t"), "person"),
    ("verification", lambda s, c: s.change_status(c, "resolved", on=ON, actor="agent", trace_id="t"), "person"),
    ("resolved", lambda s, c: s.change_status(c, "new", on=ON, actor="agent", trace_id="t"), "resolved -> new"),
    ("new", lambda s, c: s.change_status(c, "closed", on=ON, actor="agent", trace_id="t"), "close_case"),
    ("new", lambda s, c: act(s, c, "take", "closed"), "close_case"),
    ("resolved", lambda s, c: act(s, c, "take", "closed"), "close_case"),
    ("resolved", lambda s, c: act(s, c, "resolve", "resolved"), "resolved -> resolved"),
    ("new", lambda s, c: act(s, c, "close_case", "closed"), "new -> closed"),
    ("new", lambda s, c: act(s, c, "take", "archived"), "new -> archived"),
])
def test_ac_01_status_changes_follow_case_queue_transitions(start, attempt, error):
    """policies.yaml case_queue.transitions (engine.transition once 02a merges); a refused change writes nothing."""
    store = MemoryStore()
    case_id = open_case(store).case_id
    if start == "verification":
        store.change_status(case_id, "verification", on=ON, actor="agent", trace_id="t")
    if start == "resolved":
        act(store, case_id, "take", "review")
        act(store, case_id, "resolve", "resolved")
    written = len(store.events(case_id))
    with pytest.raises(StoreError, match=error):
        attempt(store, case_id)
    assert store.queue_status(case_id) == start and len(store.events(case_id)) == written


def test_ac_01_eval_runs_get_fresh_case_ids_and_never_see_each_other():
    """§6.8: the same fixture seeded in four runs gives four case ids, each visible only in its run."""
    store = MemoryStore()
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
    case must be the same customer's, in the same run."""
    store = MemoryStore()
    mine, theirs = open_case(store).case_id, open_case(store, customer_id="CLI-000002").case_id
    assert store.get_case(theirs, run_id=None, customer_id="CLI-000001") is None
    assert store.get_case(theirs, run_id=None, customer_id=None).customer_id == "CLI-000002"
    assert store.get_case(mine, run_id=None, customer_id="CLI-000001").case_id == mine
    with pytest.raises(StoreError, match="related case"):
        open_case(store, related_case_id=theirs)
    seeded = open_case(store, run_id="EV-0001:S1:1").case_id
    with pytest.raises(StoreError, match="related case"):
        open_case(store, related_case_id=seeded)
    assert len(store.list_cases("CLI-000001", run_id=None)) == 1                # refused = nothing written


def test_ac_01_a_related_case_is_written_on_both_cases_and_active_cases_come_first():
    store = ticking_store()
    old = open_case(store).case_id
    for action, status in (("take", "review"), ("resolve", "resolved"), ("close_case", "closed")):
        act(store, old, action, status)
    related = open_case(store, actor="customer", related_case_id=old).case_id
    assert store.events(old)[-1].type == "related_case_opened"
    assert store.events(old)[-1].payload == {"case_id": related}
    newest = open_case(store, transaction_id="TRX-" + "D" * 20).case_id
    assert [c.case_id for c in store.list_cases("CLI-000001", run_id=None)] == [newest, related, old]


def test_d014_stored_deadlines_and_payloads_come_back_unchanged():
    """Spec 03 AC-16 and D-014: deadlines with source, URL and verified_on are stored once and read back as stored;
    a call_requested payload keeps expected_contact_by as written (D-008)."""
    store = MemoryStore()
    case = open_case(store)
    assert store.get_case(case.case_id, run_id=None, customer_id=None).model_dump(include=set(FACTS)) == FACTS
    store.append_event(case.case_id, "call_requested", actor="agent", trace_id="t",
                       payload={"expected_contact_by": "2026-06-02"})
    assert store.events(case.case_id)[-1].payload == {"expected_contact_by": "2026-06-02"}


@pytest.mark.parametrize("change", [{"deadline_verified_on": None}, {"deadline_source": None},
                                    {"deadline_source_url": None}, {"credit_deadline": None,
                                                                    "ruling_deadline": dt.date(2026, 7, 1),
                                                                    "deadline_verified_on": None}])
def test_d014_a_deadline_date_needs_its_source_url_and_verified_on(change):
    with pytest.raises(ValidationError, match="deadline_verified_on"):
        new_case(**change)
    assert new_case(credit_deadline=None, deadline_source=None, deadline_source_url=None, deadline_verified_on=None)
    with pytest.raises(ValidationError):
        new_case(deadline_source_url="http://insecure.example")


def test_d025_a_write_has_no_verification_id_and_each_read_mints_one():
    """The verifying read mints the V- id (`action_verified`); case_opened and card_blocked carry only the action."""
    store = ticking_store()
    case = open_case(store)
    assert case.verification_id is None and store.events(case.case_id)[0].payload == {"action_id": case.action_id}
    assert store.get_case(case.case_id, run_id=None, customer_id=None).verification_id is None
    first = store.record_verification(case.case_id, case.action_id, run_id=None, actor="agent", trace_id="t")
    second = store.record_verification(case.case_id, case.action_id, run_id=None, actor="agent", trace_id="t")
    assert set(first.payload) == {"action_id", "verification_id", "read_at"} and not first.customer_visible
    assert ids.is_valid("verification", first.payload["verification_id"])
    assert first.payload["verification_id"] != second.payload["verification_id"]
    assert first.payload["read_at"] < second.payload["read_at"]
    assert store.get_case(case.case_id, run_id=None, customer_id=None).verification_id == \
        second.payload["verification_id"]
    assert [e.type for e in store.events(case.case_id)].count("action_verified") == 2    # the audit trail stays
    for bad in (lambda: store.record_verification(case.case_id, ids.new_id("action"), run_id=None, actor="agent",
                                                  trace_id="t"),
                lambda: store.record_verification(case.case_id, case.action_id, run_id="EV-0001:S1:1",
                                                  actor="agent", trace_id="t")):
        with pytest.raises(StoreError):
            bad()


def test_d025_a_block_is_an_override_in_its_run_verified_only_by_a_read():
    store = MemoryStore()
    case = open_case(store, run_id="EV-0001:S1:1")
    block = ids.new_id("action")
    event = store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id="t")
    assert (event.type, event.payload) == ("card_blocked", {"action_id": block, "product_id": case.product_id})
    status = store.product_status(case.product_id, run_id="EV-0001:S1:1")
    assert (status.status, status.action_id, status.verification_id) == ("Blocked", block, None)
    read = store.record_verification(case.case_id, block, run_id="EV-0001:S1:1", actor="agent", trace_id="t")
    assert store.product_status(case.product_id, run_id="EV-0001:S1:1").verification_id == \
        read.payload["verification_id"]
    assert store.product_status(case.product_id, run_id=None) is None           # another run reads gold
    again = ids.new_id("action")
    store.block_product(case.case_id, case.product_id, action_id=again, actor="agent", trace_id="t")
    latest = store.product_status(case.product_id, run_id="EV-0001:S1:1")
    assert (latest.action_id, latest.verification_id) == (again, None)         # the latest write, not yet read
    written = len(store.events(case.case_id))
    for bad in (lambda: store.block_product(case.case_id, "PRD-" + "Z" * 12, action_id=ids.new_id("action"),
                                            actor="agent", trace_id="t"),
                lambda: store.block_product(case.case_id, case.product_id, action_id=block, actor="agent",
                                            trace_id="t"),
                lambda: store.block_product(case.case_id, case.product_id, action_id="A-1", actor="agent",
                                            trace_id="t"),
                lambda: store.create_case(new_case(), actor="agent", action_id="not-an-action")):
        with pytest.raises(StoreError):
            bad()
    assert len(store.events(case.case_id)) == written and len(store.list_cases("CLI-000001", run_id=None)) == 0


def test_ac_01_notifications_belong_to_the_case_customer_and_show_the_latest_delivery():
    store = MemoryStore()
    run = "EV-0001:S1:1"
    case_id = open_case(store, run_id=run).case_id
    sent = store.add_notification(case_id, event="case_opened", channel="telegram", masked_address="@ju***",
                                  text="Abrimos tu caso.", trigger="auto", actor="system", trace_id="t")
    other = open_case(store, run_id=run, customer_id="CLI-000002").case_id
    store.add_notification(other, event="case_opened", channel="log", masked_address=None, text="Abrimos tu caso.",
                           trigger="auto", actor="system", trace_id="t")
    assert sent.customer_id == "CLI-000001" and ids.is_valid("notification", sent.notification_id)
    assert store.events(case_id)[-1].payload == {"notification_id": sent.notification_id, "event": "case_opened",
                                                 "channel": "telegram"}
    assert [n.notification_id for n in store.list_notifications("CLI-000001", run_id=run)] == [sent.notification_id]
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id=run)] == ["queued"]
    store.add_delivery(sent.notification_id, "sent")
    store.add_delivery(sent.notification_id, "delivered", {"type": "email.delivered"})
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id=run)] == ["delivered"]
    assert store.list_notifications("CLI-000001", run_id=None) == []
    with pytest.raises(StoreError):
        store.add_delivery("N-000000000000", "sent")
