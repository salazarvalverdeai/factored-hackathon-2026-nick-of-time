"""Case state and audit store (spec 01 §6.5, §6.8; ADR 0010).

`Store` is the interface the MCP tools and the api use; `store.memory.MemoryStore` backs tests and the fake MCP; a
Postgres backend over the §6.5 tables lands with the api (spec 05) [assumption]. Every backend keeps these rules:
- events are append-only (no update or delete) and a case's status is its last `status_changed` event (FR-02);
- the store generates every case id, retrying on a primary-key conflict (T9), so no eval run reuses one (§6.8);
- only `record_analyst_action` writes `closed` (constitution #6);
- reads are scoped by the caller's `run_id`; `customer_id` comes from the session row, never from text (#3).
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Literal, Optional, Protocol, get_args, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nick_of_time import ids
from nick_of_time.contracts import HTTPS_URL, AnalystActionIn, AnalystActionOut, Mode, ProductType, QueueStatus, Zone

EventType = Literal["case_opened", "card_blocked", "block_verified", "status_changed", "handoff_emitted", "assigned",
                    "analyst_action", "customer_info_added", "call_requested", "reevaluation_requested",
                    "related_case_opened", "notification_sent", "receipt_issued", "telegram_linked", "email_confirmed"]
CUSTOMER_VISIBLE: frozenset[str] = frozenset(get_args(EventType)) - {"handoff_emitted", "analyst_action"}   # §6.5 ✓
# Written only by the store's own methods, so their invariants hold: one opening, checked status changes, analysts.
RESERVED_EVENTS: frozenset[str] = frozenset({"case_opened", "status_changed", "analyst_action", "assigned"})
Channel = Literal["log", "telegram", "email"]
DeliveryStatus = Literal["queued", "sent", "delivered", "bounced", "failed"]
MAX_CASE_ID_ATTEMPTS = 8      # 10^6 case ids; at 1% occupancy, 8 straight conflicts happen once in 10^16 inserts


class StoreError(Exception):
    """A write the store refuses or a row it cannot find; nothing was written."""


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NewCase(_Row):
    """A case's static facts. `customer_id` and `run_id` come from the session row; deadlines are stored once and
    never recomputed (spec 03 AC-16)."""
    customer_id: str
    transaction_id: str
    product_id: str
    country: str
    product_type: ProductType
    zone: Zone
    dispute_type: Literal["unrecognized_charge", "wrongful_charge"]
    credit_deadline: Optional[dt.date] = None
    ruling_deadline: Optional[dt.date] = None
    deadline_source: Optional[str] = None
    deadline_source_url: Optional[str] = Field(None, pattern=HTTPS_URL)
    deadline_verified_on: Optional[dt.date] = None          # [assumption] D-014
    related_case_id: Optional[str] = Field(None, pattern=ids.PATTERN["case"])
    mode: Mode
    run_id: Optional[str] = None
    trace_id: str

    @model_validator(mode="after")
    def _a_legal_date_has_its_source(self) -> NewCase:
        if (self.credit_deadline or self.ruling_deadline) and not (self.deadline_source and self.deadline_source_url):
            raise ValueError("a legal deadline travels with deadline_source and deadline_source_url (ADR 0019)")
        return self


class CaseRecord(NewCase):
    case_id: str = Field(pattern=ids.PATTERN["case"])
    created_at: AwareDatetime


class CaseEvent(_Row):
    event_id: str = Field(pattern=ids.PATTERN["event"])
    case_id: str
    seq: int = Field(ge=1)
    type: EventType
    actor: str                                              # agent | customer | system | analyst:<sub>
    payload: dict[str, Any]
    customer_visible: bool
    trace_id: str
    created_at: AwareDatetime


class Notification(_Row):
    notification_id: str = Field(pattern=ids.PATTERN["notification"])
    case_id: str
    customer_id: str                                        # always the case's customer
    event: str
    channel: Channel
    masked_address: Optional[str] = None
    text: str
    trigger: Literal["auto", "on_request"]
    provider_message_id: Optional[str] = None
    created_at: AwareDatetime
    delivery_status: DeliveryStatus = "queued"              # read from its latest notification_deliveries row


def insert_with_fresh_case_id(try_insert: Callable[[str], bool]) -> str:
    """T9: draw a fresh `ids.new_id("case")` while the insert hits a `case_id` primary-key conflict (`try_insert`
    returns False, e.g. Postgres `insert … on conflict (case_id) do nothing` that returns no row)."""
    for _ in range(MAX_CASE_ID_ATTEMPTS):
        case_id = ids.new_id("case")
        if try_insert(case_id):
            return case_id
    raise StoreError(f"no free case id after {MAX_CASE_ID_ATTEMPTS} attempts")


@runtime_checkable
class Store(Protocol):
    """Cases, their append-only events, analyst actions and notifications (spec 01 §6.5). Accessors for the other
    §6.5 tables land with the tasks that use them."""

    def create_case(self, case: NewCase, *, actor: str) -> CaseRecord:
        """Insert the case under a fresh case id (T9) together with its `case_opened` event."""

    def get_case(self, case_id: str, *, run_id: Optional[str]) -> Optional[CaseRecord]:
        """The case if it belongs to `run_id` (None = production), else None."""

    def list_cases(self, customer_id: str, *, run_id: Optional[str]) -> list[CaseRecord]:
        """The customer's cases in `run_id`: active (not closed) first, newest first within each group."""

    def append_event(self, case_id: str, type: EventType, *, actor: str, trace_id: str,
                     payload: Optional[dict[str, Any]] = None) -> CaseEvent:
        """Append one event with the next `seq`; reserved types (RESERVED_EVENTS) are refused."""

    def events(self, case_id: str) -> list[CaseEvent]:
        """Every event of the case in `seq` order."""

    def queue_status(self, case_id: str) -> QueueStatus:
        """The `to` of the last `status_changed` event, `new` before the first one."""

    def change_status(self, case_id: str, to: QueueStatus, *, actor: str, trace_id: str,
                      reason: Optional[str] = None) -> CaseEvent:
        """Append `status_changed`; refuses `closed` (an analyst action) and any change of a closed case."""

    def record_analyst_action(self, action: AnalystActionIn, *, new_status: Optional[QueueStatus],
                              trace_id: str) -> AnalystActionOut:
        """Append `analyst_action` (and `assigned` for `take`) with actor `analyst:<actor_id>`, then the
        `status_changed` the policy engine allowed (`new_status`; None keeps the status). The only way to close."""

    def add_notification(self, case_id: str, *, event: str, channel: Channel, masked_address: Optional[str],
                         text: str, trigger: Literal["auto", "on_request"], actor: str, trace_id: str,
                         provider_message_id: Optional[str] = None) -> Notification:
        """Store a notification for the case's customer, its first `queued` delivery and a `notification_sent`
        event (every send is a case event, policies.yaml `notifications`)."""

    def add_delivery(self, notification_id: str, status: DeliveryStatus,
                     provider_event: Optional[dict[str, Any]] = None) -> None:
        """Append a delivery row; the notification's delivery status becomes `status`."""

    def list_notifications(self, customer_id: str, *, run_id: Optional[str]) -> list[Notification]:
        """The customer's notifications whose case is in `run_id`, newest first, with their delivery status."""
