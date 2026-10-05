"""Case state and audit store (spec 01 §6.5, §6.8; ADR 0010).

`Store` is the interface the MCP tools and the api use; `store.memory.MemoryStore` backs tests and the fake MCP; the
Postgres backend over the §6.5 tables is built by C1 in task 03a [assumption] (D-023). Every backend keeps these rules:
- events are append-only (no update or delete) and a case's status is its last `status_changed` event (FR-02);
- the store generates every case id, retrying on a primary-key conflict (T9), so no eval run reuses one (§6.8);
- a status change follows `case_queue.transitions`; only an analyst action resolves and only `close_case` closes
  (constitution #6);
- each customer write carries a fresh action id, used once; only a verifying read mints a V- id (D-025);
- `get_case`, `list_cases`, `product_status`, `verifications` and `list_notifications` take the caller's `run_id` (and
  the customer where it applies); `customer_id` comes from the session row, never from text. The calls that take only
  a case id (`events`, `queue_status`, `append_event`, `change_status`, `block_product`, `add_notification`) expect a
  case the caller first loaded with `get_case` in the session's scope; task 03a may add scope arguments to them.
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
# a related case that exists, a block with its override row, a V- id and a verified block only from a read, a send
# with its row.
RESERVED_EVENTS: frozenset[str] = frozenset({"case_opened", "status_changed", "analyst_action", "assigned",
                                             "related_case_opened", "card_blocked", "action_verified",
                                             "block_verified", "notification_sent"})
# The events of the six customer writes (open_case, block_card, add_case_info, request_call, request_reevaluation,
# send_case_summary; §6.3): each carries the write's own action id, which a verifying read cites (D-025).
WRITE_EVENTS: frozenset[str] = frozenset({"case_opened", "card_blocked", "customer_info_added", "call_requested",
                                          "reevaluation_requested", "notification_sent"})
# policies.yaml case_queue.transitions; switch to `engine.transition` (spec 02) when task 02a merges.
TRANSITIONS: dict[str, list[str]] = yaml.safe_load((CONTRACTS_DIR / "policies.yaml").read_text())["case_queue"][
    "transitions"]
# The statuses these analyst actions may move a case to [assumption] (task 01c); other actions follow TRANSITIONS.
ANALYST_TARGETS: dict[str, frozenset[str]] = {"close_case": frozenset({"closed"}), "resolve": frozenset({"resolved"}),
                                              "take": frozenset({"review", "verification"})}
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
    deadline_source: Optional[str] = Field(None, min_length=1)
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
    actor: str
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


def check_transition(current: str, to: Optional[str], *, analyst_action: Optional[str] = None) -> None:
    """Refuse an analyst action outside ANALYST_TARGETS, a change outside `TRANSITIONS[current]` (a closed case has
    none), `resolved` unless an analyst action resolves it (spec 18 A7) and `closed` unless an analyst `close_case`
    asks for it (constitution #6). `to=None` keeps the status; only `record_analyst_action` passes `analyst_action`.
    Every backend calls it before it writes anything. With 02a, `record_analyst_action` takes `to` from
    `engine.transition(current, action, actor)` and this check stays for agent and customer changes."""
    targets = ANALYST_TARGETS.get(analyst_action or "")
    if targets is not None and to not in targets:
        raise StoreError(f"{analyst_action} moves a case only to {' or '.join(sorted(targets))}")
    if to is None:
        return
    if to == "closed" and analyst_action != "close_case":
        raise StoreError("only an analyst close_case action closes a case (constitution #6)")
    if to == "resolved" and analyst_action is None:
        raise StoreError("only an analyst action resolves a case (spec 18 A7)")
    if to not in TRANSITIONS.get(current, []):
        raise StoreError(f"{current} -> {to} is not in case_queue.transitions")


@runtime_checkable
class Store(Protocol):
    """Cases, their append-only events, analyst actions, product blocks, verifications and notifications (spec 01
    §6.5). Accessors for the other §6.5 tables land with the tasks that use them."""

    def create_case(self, case: NewCase, *, actor: str, action_id: str) -> CaseRecord:
        """Insert the case under a fresh case id (T9) with `case_opened` `{action_id}` and, when `related_case_id` is
        set (a case of the same customer and run), `related_case_opened` on that case, all in one operation. A write
        has no V- id: only `record_verification` mints one (D-025). A used `action_id` is refused."""

    def get_case(self, case_id: str, *, run_id: Optional[str], customer_id: Optional[str]) -> Optional[CaseRecord]:
        """The case if it belongs to `run_id` (None = production) and to `customer_id` (None = analyst console),
        with the V- id of the latest `action_verified` of its `case_opened` action."""

    def list_cases(self, customer_id: str, *, run_id: Optional[str]) -> list[CaseRecord]:
        """The customer's cases in `run_id`: active (not closed) first, newest first within each group."""

    def append_event(self, case_id: str, type: EventType, *, actor: str, trace_id: str,
                     payload: Optional[dict[str, Any]] = None) -> CaseEvent:
        """Append one event with the next `seq`; reserved types (RESERVED_EVENTS) are refused. A write event
        (`customer_info_added`, `call_requested`, `reevaluation_requested`) needs a fresh `payload["action_id"]`."""

    def events(self, case_id: str) -> list[CaseEvent]:
        """Every event of the case in `seq` order."""

    def queue_status(self, case_id: str) -> QueueStatus:
        """The `to` of the last `status_changed` event, `new` before the first one."""

    def change_status(self, case_id: str, to: QueueStatus, *, on: dt.date, actor: str, trace_id: str,
                      reason: Optional[str] = None) -> CaseEvent:
        """Append `status_changed` `{from, to, on, reason?}` (`on` = business date) if `check_transition` allows it;
        never `resolved` or `closed`, whatever the actor."""

    def record_analyst_action(self, action: AnalystActionIn, *, new_status: Optional[QueueStatus], on: dt.date,
                              trace_id: str) -> AnalystActionOut:
        """Append `analyst_action` (and `assigned` for `take`) with actor `analyst:<actor_id>`, then the
        `status_changed` to `new_status` (None keeps the status). The only way to resolve or close; `close_case`,
        `resolve` and `take` need a status of ANALYST_TARGETS. The api checks `action.idempotency_key` before
        calling (spec 01 §10 T9)."""

    def block_product(self, case_id: str, product_id: str, *, action_id: str, actor: str,
                      trace_id: str) -> CaseEvent:
        """Block the case's own product in the case's run: a `product_overrides(Blocked)` row whose `override_id` is
        a fresh `action_id`, and `card_blocked` `{action_id, product_id}`. Gold is never written; no V- id is
        minted."""

    def product_status(self, product_id: str, *, run_id: Optional[str]) -> Optional[ProductOverride]:
        """The latest override of the product in `run_id`, with the V- id of the latest `action_verified` of its
        action (None until a read verified it); None = read gold."""

    def record_verification(self, case_id: str, action_id: str, *, run_id: Optional[str], actor: str,
                            trace_id: str) -> CaseEvent:
        """Called by the verifying read after it read the post-condition of a write of the case (WRITE_EVENTS): mint
        a V- id and append `action_verified` `{action_id, verification_id, read_at}` (D-025). Every read adds one;
        earlier ones stay as the audit trail. The first read of a `card_blocked` action also writes `block_verified`
        `{action_id, product_id}`, once. A read with nothing to verify does not call it."""

    def verifications(self, case_id: str, action_id: str, *, run_id: Optional[str]) -> list[CaseEvent]:
        """Every `action_verified` of the action in `seq` order, which is `read_at` ascending ([] when the case is not
        in `run_id`), so the auditor can accept any V- id a turn showed (D-025)."""

    def add_notification(self, case_id: str, *, event: str, channel: Channel, masked_address: Optional[str],
                         text: str, trigger: Literal["auto", "on_request"], actor: str, trace_id: str,
                         provider_message_id: Optional[str] = None, action_id: Optional[str] = None) -> Notification:
        """Store a notification for the case's customer, its first `queued` delivery and a `notification_sent`
        event `{notification_id, event, channel, action_id?}` (every send is a case event, policies.yaml
        `notifications`). An `on_request` send (`send_case_summary`) needs a fresh `action_id`; `auto` has none."""

    def add_delivery(self, notification_id: str, status: DeliveryStatus,
                     provider_event: Optional[dict[str, Any]] = None) -> None:
        """Append a delivery row; the notification's delivery status becomes `status`."""

    def list_notifications(self, customer_id: str, *, run_id: Optional[str]) -> list[Notification]:
        """The customer's notifications whose case is in `run_id`, newest first, with their delivery status."""
