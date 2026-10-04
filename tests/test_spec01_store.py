"""Spec 01 — the store: case ids (T9), append-only events, status as the last event, run isolation (AC-01, §6.5,
§6.8). Runs against the in-memory backend, which keeps the same rules as Postgres."""
from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn
from nick_of_time.store import CUSTOMER_VISIBLE, NewCase, Store, StoreError
from nick_of_time.store.memory import MemoryStore

FACTS = dict(customer_id="CLI-000001", transaction_id="TRX-" + "A" * 20, product_id="PRD-" + "B" * 12, country="MX",
             product_type="debit", zone="high", dispute_type="unrecognized_charge",
             credit_deadline=dt.date(2026, 6, 3), deadline_source="Banxico Circular 3/2012",
             deadline_source_url="https://www.banxico.org.mx/", deadline_verified_on=dt.date(2026, 10, 4),
             mode="replay", trace_id="trace-1")


def new_case(**changes) -> NewCase:
    return NewCase(**{**FACTS, **changes})


def analyst(case_id: str, action: str, reason: str | None = None) -> AnalystActionIn:
    return AnalystActionIn(case_id=case_id, actor_id="sub-1", action=action, reason=reason, idempotency_key="k")


def forced_case_ids(monkeypatch, *values: str) -> None:
    real, queue = ids.new_id, list(values)
    monkeypatch.setattr(ids, "new_id", lambda kind: queue.pop(0) if kind == "case" and queue else real(kind))


def test_ac_01_memory_store_implements_the_store_interface():
    assert isinstance(MemoryStore(), Store)


def test_t9_case_insert_retries_with_a_fresh_id_on_a_forced_primary_key_collision(monkeypatch):
    store = MemoryStore()
    first = store.create_case(new_case(), actor="agent")
    forced_case_ids(monkeypatch, first.case_id, "K-123456")
    second = store.create_case(new_case(transaction_id="TRX-" + "C" * 20), actor="agent")
    assert second.case_id == "K-123456"
    assert store.get_case(first.case_id, run_id=None) == first            # the existing row is untouched
    assert [e.type for e in store.events(first.case_id)] == ["case_opened"]
    assert [e.type for e in store.events(second.case_id)] == ["case_opened"]


def test_t9_case_insert_gives_up_and_writes_nothing_when_every_id_collides(monkeypatch):
    store = MemoryStore()
    taken = store.create_case(new_case(), actor="agent").case_id
    monkeypatch.setattr(ids, "new_id", lambda kind: taken)
    with pytest.raises(StoreError, match="no free case id"):
        store.create_case(new_case(customer_id="CLI-000002"), actor="agent")
    assert store.list_cases("CLI-000002", run_id=None) == []


def test_ac_01_status_is_the_last_status_changed_event_and_events_are_numbered():
    """FR-02: `new` until the first status_changed; seq 1..n; customer_visible follows the ✓ list of §6.5."""
    store = MemoryStore()
    case_id = store.create_case(new_case(), actor="agent").case_id
    assert store.queue_status(case_id) == "new"
    store.append_event(case_id, "card_blocked", actor="agent", trace_id="t")
    store.change_status(case_id, "verification", actor="agent", trace_id="t")
    store.append_event(case_id, "handoff_emitted", actor="agent", trace_id="t")
    store.change_status(case_id, "review", actor="agent", trace_id="t", reason="customer disagrees")
    events = store.events(case_id)
    assert store.queue_status(case_id) == "review"
    assert [e.seq for e in events] == [1, 2, 3, 4, 5]
    assert events[-1].payload == {"from": "verification", "to": "review", "reason": "customer disagrees"}
    assert [e.customer_visible for e in events] == [True, True, True, False, True]
    assert CUSTOMER_VISIBLE.isdisjoint({"handoff_emitted", "analyst_action"})


def test_ac_01_events_are_append_only():
    """§6.5 AO: no update or delete in the interface, reserved types only through the store, copies on read."""
    assert not [n for n in dir(Store) if n.split("_")[0] in {"update", "delete", "remove", "set", "clear", "reset"}]
    store = MemoryStore()
    case_id = store.create_case(new_case(), actor="agent").case_id
    for reserved in ("case_opened", "status_changed", "analyst_action", "assigned"):
        with pytest.raises(StoreError):
            store.append_event(case_id, reserved, actor="agent", trace_id="t")
    sent = {"detail": {"text": "Compra que no hice"}}
    store.append_event(case_id, "customer_info_added", actor="customer", trace_id="t", payload=sent)
    sent["detail"]["text"] = "edited"                                       # neither the written payload…
    store.events(case_id)[0].payload["to"] = "closed"                       # …nor a read changes what is stored
    assert store.events(case_id)[-1].payload == {"detail": {"text": "Compra que no hice"}}
    assert store.events(case_id)[0].payload == {} and store.queue_status(case_id) == "new"
    with pytest.raises(StoreError):
        store.append_event("K-999999", "card_blocked", actor="agent", trace_id="t")


def test_ac_01_the_store_never_closes_a_case_on_its_own():
    """Constitution #6: `closed` comes only from an analyst action, and a closed case never changes status."""
    store = MemoryStore()
    case_id = store.create_case(new_case(), actor="agent").case_id
    with pytest.raises(StoreError, match="analyst action"):
        store.change_status(case_id, "closed", actor="agent", trace_id="t")
    with pytest.raises(StoreError, match="unknown queue status"):
        store.record_analyst_action(analyst(case_id, "take"), new_status="archived", trace_id="t")
    assert len(store.events(case_id)) == 1                                  # refused = nothing written
    taken = store.record_analyst_action(analyst(case_id, "take"), new_status="review", trace_id="t")
    assert (taken.previous_status, taken.new_status) == ("new", "review")
    store.record_analyst_action(analyst(case_id, "resolve", "refund"), new_status="resolved", trace_id="t")
    closed = store.record_analyst_action(analyst(case_id, "close_case", "done"), new_status="closed", trace_id="t")
    assert (closed.previous_status, closed.new_status, store.queue_status(case_id)) == ("resolved", "closed", "closed")
    by_analyst = [e for e in store.events(case_id) if e.type in {"analyst_action", "assigned", "status_changed"}]
    assert {e.actor for e in by_analyst} == {"analyst:sub-1"} and "assigned" in {e.type for e in by_analyst}
    written = len(store.events(case_id))
    for attempt in (lambda: store.change_status(case_id, "review", actor="agent", trace_id="t"),
                    lambda: store.record_analyst_action(analyst(case_id, "reopen_case", "x"), new_status="review",
                                                        trace_id="t")):
        with pytest.raises(StoreError, match="closed case"):
            attempt()
    assert store.queue_status(case_id) == "closed" and len(store.events(case_id)) == written   # refused = no write


def test_ac_01_eval_runs_get_fresh_case_ids_and_never_see_each_other():
    """§6.8: the same fixture seeded in four runs gives four case ids, each visible only in its run."""
    store = MemoryStore()
    runs = [f"EV-0001:S1:{k}" for k in range(1, 5)]
    seeded = {run: store.create_case(new_case(run_id=run), actor="system").case_id for run in runs}
    assert len(set(seeded.values())) == 4
    for run, case_id in seeded.items():
        assert [c.case_id for c in store.list_cases("CLI-000001", run_id=run)] == [case_id]
        assert all(store.get_case(other, run_id=run) is None for other in seeded.values() if other != case_id)
    assert store.list_cases("CLI-000001", run_id=None) == []                   # production sees no eval rows
    assert store.list_cases("CLI-000002", run_id=runs[0]) == []                # nor another customer


def test_ac_01_active_cases_come_first_then_newest():
    ticks = iter(dt.datetime(2026, 6, 1, 15, minute, tzinfo=dt.UTC) for minute in range(60))
    store = MemoryStore(now=lambda: next(ticks))
    old = store.create_case(new_case(), actor="agent").case_id
    for action, status in (("resolve", "resolved"), ("close_case", "closed")):
        store.record_analyst_action(analyst(old, action, "x"), new_status=status, trace_id="t")
    related = store.create_case(new_case(related_case_id=old), actor="customer").case_id
    newest = store.create_case(new_case(transaction_id="TRX-" + "D" * 20), actor="agent").case_id
    assert [c.case_id for c in store.list_cases("CLI-000001", run_id=None)] == [newest, related, old]


def test_d014_stored_deadlines_and_payloads_come_back_unchanged():
    """Spec 03 AC-16 and D-014: deadlines with source, URL and verified_on are stored once and read back as stored;
    a call_requested payload keeps expected_contact_by as written (D-008)."""
    store = MemoryStore()
    case = store.create_case(new_case(), actor="agent")
    assert store.get_case(case.case_id, run_id=None).model_dump(include=set(FACTS)) == FACTS
    store.append_event(case.case_id, "call_requested", actor="agent", trace_id="t",
                       payload={"expected_contact_by": "2026-06-02"})
    assert store.events(case.case_id)[-1].payload == {"expected_contact_by": "2026-06-02"}
    with pytest.raises(ValidationError, match="ADR 0019"):
        new_case(deadline_source=None)
    with pytest.raises(ValidationError):
        new_case(deadline_source_url="http://insecure.example")


def test_ac_01_notifications_belong_to_the_case_customer_and_show_the_latest_delivery():
    store = MemoryStore()
    case_id = store.create_case(new_case(run_id="EV-0001:S1:1"), actor="agent").case_id
    sent = store.add_notification(case_id, event="case_opened", channel="telegram", masked_address="@ju***",
                                  text="Abrimos tu caso.", trigger="auto", actor="system", trace_id="t")
    assert sent.customer_id == "CLI-000001" and ids.is_valid("notification", sent.notification_id)
    assert store.events(case_id)[-1].payload == {"notification_id": sent.notification_id, "event": "case_opened",
                                                 "channel": "telegram"}
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id="EV-0001:S1:1")] == ["queued"]
    store.add_delivery(sent.notification_id, "sent")
    store.add_delivery(sent.notification_id, "delivered", {"type": "email.delivered"})
    assert [n.delivery_status for n in store.list_notifications("CLI-000001", run_id="EV-0001:S1:1")] == ["delivered"]
    assert store.list_notifications("CLI-000001", run_id=None) == []
    with pytest.raises(StoreError):
        store.add_delivery("N-000000000000", "sent")
