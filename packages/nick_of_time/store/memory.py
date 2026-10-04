"""In-memory `Store` for tests and the fake MCP (spec 01 §6.5, FR-06): the same rules as Postgres, no persistence.

Not thread-safe; each write checks everything it needs before it writes, so a refused call writes nothing.
"""
from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Callable
from typing import Any, Literal, Optional, get_args

from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn, AnalystActionOut, QueueStatus
from nick_of_time.store import (CUSTOMER_VISIBLE, RESERVED_EVENTS, CaseEvent, CaseRecord, Channel, DeliveryStatus,
                                EventType, NewCase, Notification, StoreError, insert_with_fresh_case_id)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _check_change(current: QueueStatus, to: str) -> None:
    if to not in get_args(QueueStatus):
        raise StoreError(f"unknown queue status {to!r}")
    if current == "closed":
        raise StoreError("a closed case never changes status; a new case gets related_case_id")


class MemoryStore:
    def __init__(self, now: Callable[[], dt.datetime] = _utc_now) -> None:
        self._now = now
        self._cases: dict[str, CaseRecord] = {}
        self._events: dict[str, list[CaseEvent]] = {}
        self._notifications: list[Notification] = []
        self._deliveries: dict[str, list[tuple[DeliveryStatus, Optional[dict[str, Any]]]]] = {}

    # ---------- cases ----------
    def create_case(self, case: NewCase, *, actor: str) -> CaseRecord:
        def try_insert(case_id: str) -> bool:
            if case_id in self._cases:                      # primary-key conflict: the caller draws a new id
                return False
            self._cases[case_id] = CaseRecord(**case.model_dump(), case_id=case_id, created_at=self._now())
            self._events[case_id] = []
            return True

        case_id = insert_with_fresh_case_id(try_insert)
        self._append(case_id, "case_opened", actor, case.trace_id, {})
        return self._cases[case_id]

    def get_case(self, case_id: str, *, run_id: Optional[str]) -> Optional[CaseRecord]:
        case = self._cases.get(case_id)
        return case if case is not None and case.run_id == run_id else None

    def list_cases(self, customer_id: str, *, run_id: Optional[str]) -> list[CaseRecord]:
        mine = [c for c in self._cases.values() if c.customer_id == customer_id and c.run_id == run_id]
        return sorted(mine, key=lambda c: (self.queue_status(c.case_id) == "closed", -c.created_at.timestamp()))

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

    def change_status(self, case_id: str, to: QueueStatus, *, actor: str, trace_id: str,
                      reason: Optional[str] = None) -> CaseEvent:
        if to == "closed":
            raise StoreError("closing a case is an analyst action; a person closes (constitution #6)")
        return self._change(case_id, to, actor, trace_id, reason)

    def record_analyst_action(self, action: AnalystActionIn, *, new_status: Optional[QueueStatus],
                              trace_id: str) -> AnalystActionOut:
        previous = self.queue_status(action.case_id)
        if new_status is not None:
            _check_change(previous, new_status)             # before any write: a refused call writes nothing
        actor = f"analyst:{action.actor_id}"
        event = self._append(action.case_id, "analyst_action", actor, trace_id,
                             {"action": action.action, "reason": action.reason})
        if action.action == "take":
            self._append(action.case_id, "assigned", actor, trace_id, {})
        if new_status is not None:
            self._change(action.case_id, new_status, actor, trace_id, action.reason)
        return AnalystActionOut(event_id=event.event_id, previous_status=previous,
                                new_status=new_status or previous, notification_id=None)

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

    def _change(self, case_id: str, to: QueueStatus, actor: str, trace_id: str, reason: Optional[str]) -> CaseEvent:
        current = self.queue_status(case_id)
        _check_change(current, to)
        payload = {"from": current, "to": to, **({"reason": reason} if reason else {})}
        return self._append(case_id, "status_changed", actor, trace_id, payload)

    def _append(self, case_id: str, type: EventType, actor: str, trace_id: str, payload: dict[str, Any]) -> CaseEvent:
        events = self._case_events(case_id)
        event = CaseEvent(event_id=ids.new_id("event"), case_id=case_id, seq=len(events) + 1, type=type, actor=actor,
                          payload=copy.deepcopy(payload), customer_visible=type in CUSTOMER_VISIBLE,
                          trace_id=trace_id, created_at=self._now())
        events.append(event)
        return event.model_copy(deep=True)
