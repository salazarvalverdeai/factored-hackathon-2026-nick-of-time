"""Case state and audit store (spec 01 §6.5, §6.8; ADR 0010).

`Store` is the interface the MCP tools and the api use; `store.memory.MemoryStore` backs tests and the fake MCP; the
Postgres backend over the §6.5 tables is built by C1 in task 03a [assumption] (D-023). Every backend keeps these rules:
- events are append-only (no update or delete) and a case's status is its last `status_changed` event (FR-02);
- the store generates every case id, retrying on a primary-key conflict (T9), so no eval run reuses one (§6.8);
- a status change follows `case_queue.transitions`, and only an analyst `close_case` closes (constitution #6);
- reads are scoped by the caller's `run_id` and customer; `customer_id` comes from the session row, never from text.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Literal, Optional, Protocol, get_args, runtime_checkable

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nick_of_time import ids
from nick_of_time.contracts import (CONTRACTS_DIR, HTTPS_URL, AnalystActionIn, AnalystActionOut, Mode, ProductType,
                                    QueueStatus, Zone)

EventType = Literal["case_opened", "card_blocked", "block_verified", "action_verified", "status_changed",
                    "handoff_emitted", "assigned", "analyst_action", "customer_info_added", "call_requested",
                    "reevaluation_requested", "related_case_opened", "notification_sent", "receipt_issued",
                    "telegram_linked", "email_confirmed"]
CUSTOMER_VISIBLE: frozenset[str] = frozenset(get_args(EventType)) - {"action_verified", "handoff_emitted",
                                                                     "analyst_action"}               # §6.5 ✓
# Written only by the store's own methods, so their invariants hold: one opening, checked status changes, analysts,
# a related case that exists, a block with its override row, a V- id only from a read, a send with its row.
RESERVED_EVENTS: frozenset[str] = frozenset({"case_opened", "status_changed", "analyst_action", "assigned",
                                             "related_case_opened", "card_blocked", "action_verified",
                                             "notification_sent"})
# policies.yaml case_queue.transitions; switch to `engine.transition` (spec 02) when task 02a merges.
TRANSITIONS: dict[str, list[str]] = yaml.safe_load((CONTRACTS_DIR / "policies.yaml").read_text())["case_queue"][
    "transitions"]
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
    opened_on: dt.date                                      # business date: clock.today(mode, country) (D-023)
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
        provenance = (self.deadline_source, self.deadline_source_url, self.deadline_verified_on)
        if (self.credit_deadline or self.ruling_deadline) and not all(provenance):
            raise ValueError("a legal deadline travels with deadline_source, deadline_source_url and "
                             "deadline_verified_on (ADR 0019, D-014)")
        return self


class CaseRecord(NewCase):
    case_id: str = Field(pattern=ids.PATTERN["case"])
    action_id: str = Field(pattern=ids.PATTERN["action"])                       # in the case_opened payload
    verification_id: Optional[str] = Field(None, pattern=ids.PATTERN["verification"])   # latest read (D-025)
    created_at: AwareDatetime                               # audit time in every mode


class ProductOverride(_Row):
    """A product_overrides row; its `override_id` is the action id of the write, also in `card_blocked`."""
    product_id: str
    status: Literal["Active", "Blocked", "Closed", "Suspended"]
    case_id: str
    action_id: str = Field(pattern=ids.PATTERN["action"])
    verification_id: Optional[str] = Field(None, pattern=ids.PATTERN["verification"])   # latest read (D-025)
    run_id: Optional[str] = None
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


def check_transition(current: str, to: str, *, actor: str, analyst_action: Optional[str] = None) -> None:
    """Refuse a status change outside `TRANSITIONS[current]` (a closed case has none), `resolved` unless a person
    (`analyst:<sub>`) resolves it (spec 18 A7), and `closed` unless an analyst `close_case` asks for it (constitution
    #6). Every backend calls it before it writes anything."""
    if to == "closed" and analyst_action != "close_case":
        raise StoreError("only an analyst close_case action closes a case (constitution #6)")
    if to == "resolved" and not actor.startswith("analyst:"):
        raise StoreError("only a person (analyst:<sub>) resolves a case")
    if to not in TRANSITIONS.get(current, []):
        raise StoreError(f"{current} -> {to} is not in case_queue.transitions")


@runtime_checkable
class Store(Protocol):
    """Cases, their append-only events, analyst actions, product blocks, verifications and notifications (spec 01
    §6.5). Accessors for the other §6.5 tables land with the tasks that use them."""

    def create_case(self, case: NewCase, *, actor: str, action_id: str) -> CaseRecord:
        """Insert the case under a fresh case id (T9) with `case_opened` `{action_id}` and, when `related_case_id` is
        set (a case of the same customer and run), `related_case_opened` on that case, all in one operation. A write
        has no V- id: only `record_verification` mints one (D-025)."""

    def get_case(self, case_id: str, *, run_id: Optional[str], customer_id: Optional[str]) -> Optional[CaseRecord]:
        """The case if it belongs to `run_id` (None = production) and to `customer_id` (None = analyst console),
        with the V- id of the latest `action_verified` of its `case_opened` action."""

    def list_cases(self, customer_id: str, *, run_id: Optional[str]) -> list[CaseRecord]:
        """The customer's cases in `run_id`: active (not closed) first, newest first within each group."""

    def append_event(self, case_id: str, type: EventType, *, actor: str, trace_id: str,
                     payload: Optional[dict[str, Any]] = None) -> CaseEvent:
        """Append one event with the next `seq`; reserved types (RESERVED_EVENTS) are refused."""

    def events(self, case_id: str) -> list[CaseEvent]:
        """Every event of the case in `seq` order."""

    def queue_status(self, case_id: str) -> QueueStatus:
        """The `to` of the last `status_changed` event, `new` before the first one."""

    def change_status(self, case_id: str, to: QueueStatus, *, on: dt.date, actor: str, trace_id: str,
                      reason: Optional[str] = None) -> CaseEvent:
        """Append `status_changed` `{from, to, on, reason?}` (`on` = business date) if `check_transition` allows it;
        never `closed`."""

    def record_analyst_action(self, action: AnalystActionIn, *, new_status: Optional[QueueStatus], on: dt.date,
                              trace_id: str) -> AnalystActionOut:
        """Append `analyst_action` (and `assigned` for `take`) with actor `analyst:<actor_id>`, then the
        `status_changed` to `new_status` (None keeps the status). The only way to close. The api checks
        `action.idempotency_key` before calling (spec 01 §10 T9)."""

    def block_product(self, case_id: str, product_id: str, *, action_id: str, actor: str,
                      trace_id: str) -> CaseEvent:
        """Block the case's own product in the case's run: a `product_overrides(Blocked)` row whose `override_id` is
        `action_id`, and `card_blocked` `{action_id, product_id}`. Gold is never written; no V- id is minted."""

    def product_status(self, product_id: str, *, run_id: Optional[str]) -> Optional[ProductOverride]:
        """The latest override of the product in `run_id`, with the V- id of the latest `action_verified` of its
        action (None until a read verified it); None = read gold."""

    def record_verification(self, case_id: str, action_id: str, *, run_id: Optional[str], actor: str,
                            trace_id: str) -> CaseEvent:
        """Called by the verifying read after it read the post-condition: mint a V- id and append `action_verified`
        `{action_id, verification_id, read_at}` (D-025). Every read adds one; earlier ones stay as the audit trail."""

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
