"""In-memory `Store` for tests and the fake MCP (spec 01 §6.5, FR-06): the same rules as Postgres, no persistence.

Not thread-safe; each write checks everything it needs before it writes, so a refused call writes nothing.
"""
from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Callable
from typing import Any, Literal, Optional

from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn, AnalystActionOut, QueueStatus
from nick_of_time.store import (CUSTOMER_VISIBLE, RESERVED_EVENTS, CaseEvent, CaseRecord, Channel, DeliveryStatus,
                                EventType, NewCase, Notification, ProductOverride, StoreError, check_transition,
                                insert_with_fresh_case_id)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _check_action_id(action_id: str) -> None:
    if not ids.is_valid("action", action_id):
        raise StoreError(f"not an action id: {action_id!r}")


class MemoryStore:
    def __init__(self, now: Callable[[], dt.datetime] = _utc_now) -> None:
        self._now = now
        self._cases: dict[str, CaseRecord] = {}
        self._events: dict[str, list[CaseEvent]] = {}
        self._overrides: dict[str, ProductOverride] = {}    # override_id (the write's action id) -> row
        self._notifications: list[Notification] = []
        self._deliveries: dict[str, list[tuple[DeliveryStatus, Optional[dict[str, Any]]]]] = {}

    # ---------- cases ----------
    def create_case(self, case: NewCase, *, actor: str, action_id: str) -> CaseRecord:
        related = case.related_case_id
        if related is not None and self.get_case(related, run_id=case.run_id, customer_id=case.customer_id) is None:
            raise StoreError(f"related case {related} is not a case of this customer in this run")

        def try_insert(case_id: str) -> bool:
            if case_id in self._cases:                      # primary-key conflict: the caller draws a new id
                return False
            self._cases[case_id] = CaseRecord(**case.model_dump(), case_id=case_id, action_id=action_id,
                                              created_at=self._now())
            self._events[case_id] = []
            return True

        _check_action_id(action_id)
        case_id = insert_with_fresh_case_id(try_insert)
        self._append(case_id, "case_opened", actor, case.trace_id, {"action_id": action_id})
        if related is not None:
            self._append(related, "related_case_opened", actor, case.trace_id, {"case_id": case_id})
        return self._cases[case_id]

    def get_case(self, case_id: str, *, run_id: Optional[str], customer_id: Optional[str]) -> Optional[CaseRecord]:
        case = self._cases.get(case_id)
        if case is None or case.run_id != run_id or customer_id not in (None, case.customer_id):
            return None
        return self._read(case)

    def list_cases(self, customer_id: str, *, run_id: Optional[str]) -> list[CaseRecord]:
        mine = [c for c in self._cases.values() if c.customer_id == customer_id and c.run_id == run_id]
        mine.sort(key=lambda c: (self.queue_status(c.case_id) == "closed", -c.created_at.timestamp()))
        return [self._read(c) for c in mine]

    # ---------- events ----------
    def append_event(self, case_id: str, type: EventType, *, actor: str, trace_id: str,
                     payload: Optional[dict[str, Any]] = None) -> CaseEvent:
        if type in RESERVED_EVENTS:
            raise StoreError(f"{type} is written only by the store's own methods")
        return self._append(case_id, type, actor, trace_id, payload or {})

    def events(self, case_id: str) -> list[CaseEvent]:
        return [e.model_copy(deep=True) for e in self._case_events(case_id)]

    def queue_status(self, case_id: str) -> QueueStatus:
        changes = [e for e in self._case_events(case_id) if e.type == "status_changed"]
        return changes[-1].payload["to"] if changes else "new"

    def change_status(self, case_id: str, to: QueueStatus, *, on: dt.date, actor: str, trace_id: str,
                      reason: Optional[str] = None) -> CaseEvent:
        current = self.queue_status(case_id)
        check_transition(current, to, actor=actor)
        return self._change(case_id, current, to, on, actor, trace_id, reason)

    def record_analyst_action(self, action: AnalystActionIn, *, new_status: Optional[QueueStatus], on: dt.date,
                              trace_id: str) -> AnalystActionOut:
        previous = self.queue_status(action.case_id)
        actor = f"analyst:{action.actor_id}"
        if new_status is not None:
            check_transition(previous, new_status, actor=actor, analyst_action=action.action)   # before any write
        event = self._append(action.case_id, "analyst_action", actor, trace_id,
                             {"action": action.action, "reason": action.reason})
        if action.action == "take":
            self._append(action.case_id, "assigned", actor, trace_id, {})
        if new_status is not None:
            self._change(action.case_id, previous, new_status, on, actor, trace_id, action.reason)
        return AnalystActionOut(event_id=event.event_id, previous_status=previous,
                                new_status=new_status or previous, notification_id=None)

    # ---------- products and verification (D-025) ----------
    def block_product(self, case_id: str, product_id: str, *, action_id: str, actor: str,
                      trace_id: str) -> CaseEvent:
        case = self._case(case_id)
        _check_action_id(action_id)
        if product_id != case.product_id:
            raise StoreError(f"{product_id} is not the product of case {case_id}")
        if action_id in self._overrides:                    # override_id primary key
            raise StoreError(f"action {action_id} already wrote an override")
        self._overrides[action_id] = ProductOverride(product_id=product_id, status="Blocked", case_id=case_id,
                                                     action_id=action_id, run_id=case.run_id, created_at=self._now())
        payload = {"action_id": action_id, "product_id": product_id}
        return self._append(case_id, "card_blocked", actor, trace_id, payload)

    def product_status(self, product_id: str, *, run_id: Optional[str]) -> Optional[ProductOverride]:
        rows = [o for o in self._overrides.values() if o.product_id == product_id and o.run_id == run_id]
        if not rows:
            return None
        latest = rows[-1]                                   # insertion order = created_at order
        return latest.model_copy(update={"verification_id": self._verified(latest.case_id, latest.action_id)})

    def record_verification(self, case_id: str, action_id: str, *, run_id: Optional[str], actor: str,
                            trace_id: str) -> CaseEvent:
        if self.get_case(case_id, run_id=run_id, customer_id=None) is None:
            raise StoreError(f"unknown case {case_id} in this run")
        writes = {"case_opened", "card_blocked"}
        if action_id not in {e.payload.get("action_id") for e in self._events[case_id] if e.type in writes}:
            raise StoreError(f"action {action_id} was never written for case {case_id}")
        payload = {"action_id": action_id, "verification_id": ids.new_id("verification"),
                   "read_at": self._now().isoformat()}
        return self._append(case_id, "action_verified", actor, trace_id, payload)

    # ---------- notifications ----------
    def add_notification(self, case_id: str, *, event: str, channel: Channel, masked_address: Optional[str],
                         text: str, trigger: Literal["auto", "on_request"], actor: str, trace_id: str,
                         provider_message_id: Optional[str] = None) -> Notification:
        case = self._case(case_id)
        sent = Notification(notification_id=ids.new_id("notification"), case_id=case_id, customer_id=case.customer_id,
                            event=event, channel=channel, masked_address=masked_address, text=text, trigger=trigger,
                            provider_message_id=provider_message_id, created_at=self._now())
        self._notifications.append(sent)
        self._deliveries[sent.notification_id] = [("queued", None)]
        self._append(case_id, "notification_sent", actor, trace_id,
                     {"notification_id": sent.notification_id, "event": event, "channel": channel})
        return sent

    def add_delivery(self, notification_id: str, status: DeliveryStatus,
                     provider_event: Optional[dict[str, Any]] = None) -> None:
        if notification_id not in self._deliveries:
            raise StoreError(f"unknown notification {notification_id}")
        self._deliveries[notification_id].append((status, copy.deepcopy(provider_event)))

    def list_notifications(self, customer_id: str, *, run_id: Optional[str]) -> list[Notification]:
        return [n.model_copy(update={"delivery_status": self._deliveries[n.notification_id][-1][0]})
                for n in reversed(self._notifications)
                if n.customer_id == customer_id and self._cases[n.case_id].run_id == run_id]

    # ---------- internals ----------
    def _case(self, case_id: str) -> CaseRecord:
        if case_id not in self._cases:
            raise StoreError(f"unknown case {case_id}")
        return self._cases[case_id]

    def _case_events(self, case_id: str) -> list[CaseEvent]:
        self._case(case_id)
        return self._events[case_id]

    def _verified(self, case_id: str, action_id: str) -> Optional[str]:
        reads = [e.payload["verification_id"] for e in self._events[case_id]
                 if e.type == "action_verified" and e.payload["action_id"] == action_id]
        return reads[-1] if reads else None

    def _read(self, case: CaseRecord) -> CaseRecord:
        return case.model_copy(update={"verification_id": self._verified(case.case_id, case.action_id)})

    def _change(self, case_id: str, current: QueueStatus, to: QueueStatus, on: dt.date, actor: str, trace_id: str,
                reason: Optional[str]) -> CaseEvent:
        payload = {"from": current, "to": to, "on": on.isoformat(), **({"reason": reason} if reason else {})}
        return self._append(case_id, "status_changed", actor, trace_id, payload)

    def _append(self, case_id: str, type: EventType, actor: str, trace_id: str, payload: dict[str, Any]) -> CaseEvent:
        events = self._case_events(case_id)
        event = CaseEvent(event_id=ids.new_id("event"), case_id=case_id, seq=len(events) + 1, type=type, actor=actor,
                          payload=copy.deepcopy(payload), customer_visible=type in CUSTOMER_VISIBLE,
                          trace_id=trace_id, created_at=self._now())
        events.append(event)
        return event.model_copy(deep=True)
