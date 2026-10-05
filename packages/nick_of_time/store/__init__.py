"""Case state and audit store (spec 01 §6.5, §6.8; ADR 0010).

`Store` is the interface the MCP tools and the api use; `store.memory.MemoryStore` backs tests and the fake MCP;
`store.postgres.PostgresStore` runs it over the §6.5 tables of schema.sql (T9, task 01g). Every backend keeps these
rules:
- events are append-only (no update or delete) and a case's status is its last `status_changed` event (FR-02);
- the store generates every case id, retrying on a primary-key conflict (T9), so no eval run reuses one (§6.8);
- a status change follows `case_queue.transitions` and the analyst-action table (D-034); only `resolve` resolves and
  only `close_case` closes (constitution #6); a closed case takes no analyst action and no customer write;
- each customer write carries a fresh action id, used once; only the read that verifies that write mints a V- id,
  and only while its post-condition holds (D-025, D-035);
- every argument is checked before the first write (actor, trace id, business date, delivery status); payloads are
  JSON, as in Postgres `jsonb`;
- `get_case`, `list_cases`, `action_write`, `record_verification` and `list_notifications` take the caller's
  `run_id` and customer (None = system, analyst or auditor); `product_status` and `verifications` take the `run_id`.
  `customer_id` comes from the session row, never from text. The calls that take only a case id (`events`,
  `queue_status`, `append_event`, `change_status`, `block_product`, `add_notification`) expect a case the caller
  first loaded with `get_case` in the session's scope; task 03a may add scope arguments to them.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable, Iterator
from typing import Any, Literal, Optional, Protocol, get_args, runtime_checkable

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nick_of_time import ids
from nick_of_time.contracts import (CONTRACTS_DIR, HTTPS_URL, AnalystActionIn, AnalystActionOut, Mode, ProductType,
                                    QueueStatus, VERIFIED_WITH as VERIFIED_WITH, Zone)
from nick_of_time.store.accounts import ChannelEvent, CustomerChannel, LinkedChannel, Once, PolicyDenial, SessionRecord

EventType = Literal["case_opened", "card_blocked", "block_verified", "action_verified", "status_changed",
                    "handoff_emitted", "assigned", "analyst_action", "customer_info_added", "call_requested",
                    "reevaluation_requested", "related_case_opened", "notification_sent", "receipt_issued",
                    "telegram_linked", "email_confirmed"]
CUSTOMER_VISIBLE: frozenset[str] = frozenset(get_args(EventType)) - {"action_verified", "handoff_emitted",
                                                                     "analyst_action"}               # §6.5 ✓
# Written only by the store's own methods, so their invariants hold: one opening, checked status changes, analysts,
# a related case that exists, a block with its override row, a V- id and a verified block only from a read, a send
# with its row, a channel event with its customer_channels row (CHANNEL_CASE_EVENT).
RESERVED_EVENTS: frozenset[str] = frozenset({"case_opened", "status_changed", "analyst_action", "assigned",
                                             "related_case_opened", "card_blocked", "action_verified",
                                             "block_verified", "notification_sent", "telegram_linked",
                                             "email_confirmed"})
# Each write event and the customer tool that writes it (§6.3); each carries the write's own action id (D-025).
# `case_opened` also comes from request_reevaluation on a closed case, which is verified with the same read.
WRITE_TOOL: dict[str, str] = {"case_opened": "open_case", "card_blocked": "block_card",
                              "customer_info_added": "add_case_info", "call_requested": "request_call",
                              "reevaluation_requested": "request_reevaluation",
                              "notification_sent": "send_case_summary"}
WRITE_EVENTS: frozenset[str] = frozenset(WRITE_TOOL)
VerifyingRead = Literal["get_case", "get_product_status", "list_my_notifications"]
# A store actor: agent, customer, system or a person, `analyst:<sub>` with a sub that is not blank.
ACTOR = r"^(agent|customer|system|analyst:.*\S.*)$"
# policies.yaml case_queue.transitions; switch to `nick_of_time.policy.transition` (spec 02) when task 02c merges.
TRANSITIONS: dict[str, list[str]] = yaml.safe_load((CONTRACTS_DIR / "policies.yaml").read_text())["case_queue"][
    "transitions"]
# [assumption] D-034 (task 01c) until spec 02 `policy.transition` (AC-10): the statuses an analyst action may move a
# case to (None keeps the status) and the statuses it may start from. An action not in ANALYST_TARGETS keeps the
# status; an action not in ANALYST_SOURCES may start from any status but closed.
KEEP: frozenset[Optional[str]] = frozenset({None})
ANALYST_TARGETS: dict[str, frozenset[Optional[str]]] = {
    "take": frozenset({"review", "verification"}), "resolve": frozenset({"resolved"}),
    "close_case": frozenset({"closed"}), "reopen_case": frozenset({"review"})}
ANALYST_SOURCES: dict[str, frozenset[str]] = {"take": frozenset({"new", "verification", "review"}),
                                              "reopen_case": frozenset({"resolved"})}
Channel = Literal["log", "telegram", "email"]
DeliveryStatus = Literal["queued", "sent", "delivered", "bounced", "failed"]
# [assumption] D-035, pending the lead: a summary send is verified only while its latest delivery is not one of these.
UNDELIVERED: frozenset[str] = frozenset({"bounced", "failed"})
MAX_CASE_ID_ATTEMPTS = 8      # 10^6 case ids; at 1% occupancy, 8 straight conflicts happen once in 10^16 inserts


class StoreError(Exception):
    """A write the store refuses or a row it cannot find; nothing was written."""


class NotVerified(StoreError):
    """The write's post-condition does not hold now (a block that is no longer the card's status, a summary whose
    latest delivery failed or bounced): nothing was written, and the read stays plain (`read_at`, no V- id)."""


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
    actor: str = Field(pattern=ACTOR)
    run_id: Optional[str] = None
    created_at: AwareDatetime


class CaseEvent(_Row):
    event_id: str = Field(pattern=ids.PATTERN["event"])
    case_id: str
    seq: int = Field(ge=1)
    type: EventType
    actor: str = Field(pattern=ACTOR)
    payload: dict[str, Any]                                 # JSON only, as in jsonb
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


def check_actor(actor: str) -> str:
    """Refuse an actor outside ACTOR, such as `analyst:` with a blank sub, before any write."""
    if not isinstance(actor, str) or re.fullmatch(ACTOR, actor) is None:
        raise StoreError(f"not a store actor: {actor!r} (agent, customer, system or analyst:<sub>)")
    return actor


def check_trace_id(trace_id: str) -> str:
    """Refuse a trace id that is not a non-empty string, before any write."""
    if not isinstance(trace_id, str) or not trace_id:
        raise StoreError(f"not a trace id: {trace_id!r}")
    return trace_id


def check_business_date(on: dt.date) -> dt.date:
    """Refuse a business date that is not a `date`; a `datetime` is refused too, since its UTC day may not be the
    country's business day (D-023)."""
    if not isinstance(on, dt.date) or isinstance(on, dt.datetime):
        raise StoreError(f"not a business date: {on!r}")
    return on


def check_text(*values: Any) -> None:
    """Refuse what Postgres text and jsonb cannot hold, NUL and a lone surrogate, before any write; other values pass."""
    for value in values:
        if isinstance(value, str) and ("\x00" in value or not _encodes(value)):
            raise StoreError("not storable text: NUL or a lone surrogate")


def _encodes(value: str) -> bool:
    try:
        value.encode("utf-8")                               # a lone surrogate has no UTF-8 form
    except UnicodeEncodeError:
        return False
    return True


def check_action_id(action_id: Any) -> str:
    """Refuse an action id that is not an `A-` id, before any write (Postgres: the case_events CHECK)."""
    if not isinstance(action_id, str) or not ids.is_valid("action", action_id):
        raise StoreError(f"not an action id: {action_id!r}")
    return action_id


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _json(value: Any) -> Any:
    """What a jsonb column gives back: a JSON copy; a date, a set, NaN, NUL or a lone surrogate is refused, as
    psycopg's Jsonb and Postgres would."""
    try:
        copy = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise StoreError(f"not JSON: {error}") from None
    check_text(*_strings(copy))
    return copy


def _check_writer(actor: str, trace_id: str) -> str:
    check_trace_id(trace_id)
    check_text(actor, trace_id)
    return check_actor(actor)


def check_transition(current: str, to: Optional[str], *, analyst_action: Optional[str] = None) -> None:
    """The status rules every backend checks before it writes anything; only `record_analyst_action` passes
    `analyst_action`. Without one (agent, customer, system), a change needs a status and never resolves or closes.
    With one, a closed case takes no action, the action must start from ANALYST_SOURCES and move only to
    ANALYST_TARGETS (KEEP, `to=None`, for the others). Any change follows `TRANSITIONS[current]`. With 02c,
    `record_analyst_action` takes `to` from `nick_of_time.policy.transition(current, action, actor)` (`Moved.status`)
    and this check stays for agent and customer changes."""
    if analyst_action is None:
        if to is None:
            raise StoreError("a status change needs a status")
        if to in ("resolved", "closed"):
            raise StoreError("only an analyst resolve resolves and only close_case closes a case (constitution #6)")
    else:
        if current == "closed":
            raise StoreError(f"a closed case takes no analyst action ({analyst_action}, D-034)")
        sources = ANALYST_SOURCES.get(analyst_action)
        if sources is not None and current not in sources:
            raise StoreError(f"{analyst_action} starts only from {' or '.join(sorted(sources))}")
        targets = ANALYST_TARGETS.get(analyst_action, KEEP)
        if to not in targets:
            moves = "keeps the status" if targets == KEEP else f"moves a case only to {' or '.join(sorted(targets))}"
            raise StoreError(f"{analyst_action} {moves}")
        if to is None:
            return
    if to not in TRANSITIONS.get(current, []):
        raise StoreError(f"{current} -> {to} is not in case_queue.transitions")


@runtime_checkable
class Store(Protocol):
    """Cases, their append-only events, analyst actions, product blocks, verifications and notifications (spec 01
    §6.5). Accessors for the other §6.5 tables land with the tasks that use them."""

    def create_case(self, case: NewCase, *, actor: str, action_id: str) -> CaseRecord:
        """Insert the case under a fresh case id (T9) with `case_opened` `{action_id}` and, when `related_case_id` is
        set (a closed case of the same customer and run), `related_case_opened` on that case, all in one operation. A
        write has no V- id: only `record_verification` mints one (D-025). A used `action_id` is refused."""

    def get_case(self, case_id: str, *, run_id: Optional[str], customer_id: Optional[str]) -> Optional[CaseRecord]:
        """The case if it belongs to `run_id` (None = production) and to `customer_id` (None = analyst console),
        with the V- id of the latest `action_verified` of its `case_opened` action."""

    def list_cases(self, customer_id: str, *, run_id: Optional[str]) -> list[CaseRecord]:
        """The customer's cases in `run_id`: active (not closed) first, newest first within each group."""

    def append_event(self, case_id: str, type: EventType, *, actor: str, trace_id: str,
                     payload: Optional[dict[str, Any]] = None) -> CaseEvent:
        """Append one event with the next `seq`; reserved types (RESERVED_EVENTS) are refused. A write event
        (`customer_info_added`, `call_requested`, `reevaluation_requested`) needs a fresh `payload["action_id"]` and
        a case that is not closed."""

    def events(self, case_id: str) -> list[CaseEvent]:
        """Every event of the case in `seq` order."""

    def queue_status(self, case_id: str) -> QueueStatus:
        """The `to` of the last `status_changed` event, `new` before the first one."""

    def change_status(self, case_id: str, to: QueueStatus, *, on: dt.date, actor: str, trace_id: str,
                      reason: Optional[str] = None) -> CaseEvent:
        """Append `status_changed` `{from, to, on, reason?}` (`on` = business date) if `check_transition` allows it;
        never `resolved` or `closed`, whatever the actor, and never without a status."""

    def record_analyst_action(self, action: AnalystActionIn, *, new_status: Optional[QueueStatus], on: dt.date,
                              trace_id: str) -> AnalystActionOut:
        """Append `analyst_action` `{action, reason}` (and `assigned` for `take`) with actor `analyst:<actor_id>`, then
        the `status_changed` to `new_status` (None keeps the status). The only way to resolve or close; the status
        must fit ANALYST_SOURCES and ANALYST_TARGETS; a blank `actor_id` is refused. The api checks
        `action.idempotency_key` before calling (spec 01 §10 T9)."""

    def block_product(self, case_id: str, product_id: str, *, action_id: str, actor: str,
                      trace_id: str) -> CaseEvent:
        """Block the product of a case that is not closed, in the case's run: a `product_overrides(Blocked)` row whose
        `override_id` is a fresh `action_id`, and `card_blocked` `{action_id, product_id}`. Gold is never written; no
        V- id is minted."""

    def product_status(self, product_id: str, *, run_id: Optional[str]) -> Optional[ProductOverride]:
        """The latest override of the product in `run_id`, with the V- id of the latest `action_verified` of its
        action (None until a read verified it); None = read gold."""

    def action_write(self, action_id: str, *, run_id: Optional[str],
                     customer_id: Optional[str]) -> Optional[CaseEvent]:
        """The write event (WRITE_EVENTS) that carries `action_id`, in `run_id` and of `customer_id` (None = system,
        analyst or auditor), else None. The reads without a case id (`get_product_status`, `list_my_notifications`)
        find the case with it; the auditor takes `requested_at` from its `created_at`."""

    def record_verification(self, case_id: str, action_id: str, *, read: VerifyingRead, run_id: Optional[str],
                            customer_id: Optional[str], actor: str, trace_id: str) -> CaseEvent:
        """Called by the read of VERIFIED_WITH, asked about a write of the case, after it read the post-condition:
        mint a V- id and append `action_verified` `{action_id, verification_id, read_at, read}` (D-025; `read` is the
        tool that minted it, for the auditor, 18x X1-3). Every read adds
        one; earlier ones stay as the audit trail. A `card_blocked` action verifies only while its override is the
        product's latest in the run and `Blocked`, and its first read also writes `block_verified` `{action_id,
        product_id}`, once; a summary send (`notification_sent`) verifies only while its latest delivery is not in
        UNDELIVERED (D-035). Otherwise it raises NotVerified and the read stays plain. A plain read (no action id)
        does not call it; it returns `read_at` only."""

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
        """Append a delivery row (`status` in DeliveryStatus, `provider_event` JSON); the notification's delivery
        status becomes `status`."""

    def list_notifications(self, customer_id: str, *, run_id: Optional[str]) -> list[Notification]:
        """The customer's notifications whose case is in `run_id`, newest first, with their delivery status."""

    # ---------- sessions, policy denials and customer channels (task 01g, store/accounts.py) ----------
    def create_session(self, *, customer_id: Optional[str], otp_hash: str, expires_at: dt.datetime,
                       language: str, mode: Mode, verified_at: Optional[dt.datetime] = None,
                       display_currency: Optional[str] = None, tool_faults: tuple[str, ...] = (),
                       run_id: Optional[str] = None, arm: Optional[str] = None) -> SessionRecord:
        """Insert a session (NewSession) under a fresh `ids.new_id("session")`, `created_at` from the store's clock.
        There is no update, so `mode` and `run_id` stay as created (AC-07, §6.8)."""

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """The session row, read fresh on every call, else None; the caller checks verification and expiry (spec 03
        AC-02). `customer_id` and `run_id` for every tool come from here (constitution #3)."""

    def summary_sends(self, session_id: str, *, since: dt.datetime) -> int:
        """D-041 (spec 03 AC-21): the `on_request` notifications of the session's customer whose case is in its run,
        created at or after both `since` and the session's start. A notification row names no session, so another
        session of the same customer and run counts too, which only tightens the limit [assumption]."""

    def add_denial(self, *, trace_id: str, session_id: Optional[str], actor: str, policy_id: str,
                   guardrail_id: Optional[str] = None, detail: Optional[dict[str, Any]] = None,
                   run_id: Optional[str] = None) -> PolicyDenial:
        """Insert one `policy_denials` row (NewDenial, spec 03 AC-12) under a fresh id; no guardrail id means
        G-POL-01; a denial of a session must be of a known session and carry its `run_id` (D-023)."""

    def list_denials(self, *, run_id: Optional[str], session_id: Optional[str] = None) -> list[PolicyDenial]:
        """The denials of `run_id` (None = production), only `session_id`'s when given, oldest first (`created_at`,
        then `denial_id`)."""

    def add_channel_event(self, case_id: str, channel: LinkedChannel, address: str, event: ChannelEvent, *,
                          actor: str, trace_id: str) -> CustomerChannel:
        """Append a `customer_channels` row for the case's customer and, for CHANNEL_CASE_EVENT, its case event
        `{channel_id, channel}` in the same operation. `confirmed` needs the channel's `linked` address and `revoked`
        its current one; the address never goes into the event."""

    def channels(self, customer_id: str) -> list[CustomerChannel]:
        """The latest row (inserted last) of each of the customer's channels, by channel name; a tool sends only where
        `confirmed` is true and shows only masked addresses (spec 03 AC-11, AC-21)."""

    # ---------- idempotency (task 01g, store/accounts.py) ----------
    def once(self, key: str, *, action: str, customer_id: Optional[str], run_id: Optional[str],
             arguments: dict[str, Any], write: Callable[[], dict[str, Any]]) -> Once:
        """Spec 03 AC-03 and spec 01 §6.3 Idempotency: the first call with this `key` (of this action, customer and
        run) runs `write()`, stores its JSON result and returns it; every later one returns the stored result with
        `replayed` and writes nothing. On Postgres a concurrent second call waits for the first. A `write` that raises
        stores nothing and leaves none of its writes (both backends); a key used for another action or with other
        `arguments` (the call's JSON arguments, hashed) is a StoreError. `customer_id` None is the api's analyst
        actions (`AnalystActionIn`)."""
