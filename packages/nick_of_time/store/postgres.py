"""Postgres `Store` over the spec 01 §6.5 tables of `schema.sql` (ADR 0010, T9): the same rules as `MemoryStore`.

Each write runs in one transaction that first takes a transaction-scoped advisory lock on its case, so what it checks
(status, action ids, a block's latest override, a summary's latest delivery) and what it inserts are one unit, even
across the api and MCP processes; a refused call rolls back and writes nothing. The lock needs no UPDATE grant, so
the app role keeps INSERT and SELECT only on the append-only tables (T10). One connection per store, used under a
lock and reopened when dropped. The latest override or delivery is the row inserted last (the highest `row_no`, as
`MemoryStore`'s insertion order), never the latest `created_at`, which a fixed or skewed clock can repeat (§6.5). The
connection string comes from `DATABASE_URL`, never from the repo.
"""
from __future__ import annotations

import datetime as dt
import os
import secrets
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Literal, Optional, get_args

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn, AnalystActionOut, QueueStatus
from nick_of_time.store import (CUSTOMER_VISIBLE, RESERVED_EVENTS, UNDELIVERED, VERIFIED_WITH, WRITE_EVENTS, WRITE_TOOL,
                                CaseEvent, CaseRecord, Channel, DeliveryStatus, EventType, NewCase, Notification,
                                NotVerified, ProductOverride, StoreError, VerifyingRead, _check_writer, _json,
                                _utc_now, check_action_id, check_business_date, check_text, check_transition,
                                insert_with_fresh_case_id)
from nick_of_time.store.accounts import (CHANNEL_CASE_EVENT, CHANNEL_ID, DENIAL_ID, ChannelEvent, CustomerChannel,
                                         LinkedChannel, NewDenial, NewSession, PolicyDenial, SessionRecord,
                                         check_channel_event, check_denial_session, check_key, new_row_id, parse,
                                         window_start)

WRITES = sorted(WRITE_EVENTS)
EVENT = "event_id, case_id, seq, type, actor, payload, customer_visible, trace_id, created_at"
FACTS, VALUES = ", ".join(NewCase.model_fields), ", ".join(f"%({f})s" for f in NewCase.model_fields)
# A case with the action of its case_opened, the V- id of that action's latest read and its status (the last change).
CASES = """
select c.*, o.payload ->> 'action_id' as action_id, v.verification_id, coalesce(s.status, 'new') as status
from cases c
join case_events o on o.case_id = c.case_id and o.type = 'case_opened'
left join lateral (select payload ->> 'verification_id' as verification_id from case_events
                   where case_id = c.case_id and type = 'action_verified'
                     and payload ->> 'action_id' = o.payload ->> 'action_id' order by seq desc limit 1) v on true
left join lateral (select payload ->> 'to' as status from case_events
                   where case_id = c.case_id and type = 'status_changed' order by seq desc limit 1) s on true
where c.run_id is not distinct from %(run_id)s and (%(customer_id)s::text is null or c.customer_id = %(customer_id)s)
"""


def _record(row: dict[str, Any]) -> CaseRecord:
    return CaseRecord(**{k: v for k, v in row.items() if k != "status"})


class PostgresStore:
    def __init__(self, conninfo: Optional[str] = None, *, now: Callable[[], dt.datetime] = _utc_now,
                 **connect: Any) -> None:
        conninfo = conninfo or os.environ.get("DATABASE_URL")
        if not conninfo:
            raise StoreError("DATABASE_URL is not set")
        self._now, self._lock, self._connect = now, threading.RLock(), (conninfo, connect)
        self._conn: Optional[psycopg.Connection] = None
        self._open()

    def _open(self) -> psycopg.Connection:
        """The store's connection, opened again when the server dropped it; a failed call is never retried."""
        if self._conn is None or self._conn.closed:
            conninfo, connect = self._connect
            self._conn = psycopg.connect(conninfo, autocommit=True, row_factory=dict_row, **connect)
            self._conn.execute("set time zone 'UTC'")
        return self._conn

    def close(self) -> None:
        self._conn.close()

    # ---------- cases ----------
    def create_case(self, case: NewCase, *, actor: str, action_id: str) -> CaseRecord:
        _check_writer(actor, case.trace_id)
        check_text(*case.model_dump().values())
        related = case.related_case_id
        with self._tx(related):
            if related is not None and (self.get_case(related, run_id=case.run_id, customer_id=case.customer_id)
                                        is None or self.queue_status(related) != "closed"):
                raise StoreError(f"related case {related} is not a closed case of this customer in this run")
            self._check_new_action(action_id)
            row = {**case.model_dump(), "created_at": self._now()}
            case_id = insert_with_fresh_case_id(lambda case_id: bool(self._rows(   # a PK conflict returns no row
                f"insert into cases (case_id, created_at, {FACTS}) values (%(case_id)s, %(created_at)s, {VALUES}) "
                "on conflict (case_id) do nothing returning case_id", {**row, "case_id": case_id})))
            self._append(case_id, "case_opened", actor, case.trace_id, {"action_id": action_id})
            if related is not None:
                self._append(related, "related_case_opened", actor, case.trace_id, {"case_id": case_id})
            return self.get_case(case_id, run_id=case.run_id, customer_id=None)

    def get_case(self, case_id: str, *, run_id: Optional[str], customer_id: Optional[str]) -> Optional[CaseRecord]:
        rows = self._rows(CASES + "and c.case_id = %(case_id)s",
                          {"case_id": case_id, "run_id": run_id, "customer_id": customer_id})
        return _record(rows[0]) if rows else None

    def list_cases(self, customer_id: str, *, run_id: Optional[str]) -> list[CaseRecord]:
        rows = self._rows(CASES + "order by coalesce(s.status, 'new') = 'closed', c.created_at desc, "
                          "c.case_id collate \"C\" desc",
                          {"run_id": run_id, "customer_id": customer_id})
        return [_record(r) for r in rows]

    # ---------- events ----------
    def append_event(self, case_id: str, type: EventType, *, actor: str, trace_id: str,
                     payload: Optional[dict[str, Any]] = None) -> CaseEvent:
        _check_writer(actor, trace_id)
        if type in RESERVED_EVENTS:
            raise StoreError(f"{type} is written only by the store's own methods")
        payload = payload or {}
        if "action_id" in payload:                          # any action id is an A- id (the case_events CHECK)
            check_action_id(payload["action_id"])
        with self._tx(case_id):
            if type in WRITE_EVENTS:                        # a customer write
                self._check_open(case_id)
                self._check_new_action(payload.get("action_id"))
            return self._append(case_id, type, actor, trace_id, payload)

    def events(self, case_id: str) -> list[CaseEvent]:
        self._case(case_id)
        return [CaseEvent(**r) for r in self._rows(f"select {EVENT} from case_events where case_id = %s order by seq",
                                                   (case_id,))]

    def queue_status(self, case_id: str) -> QueueStatus:
        self._case(case_id)
        rows = self._rows("select payload ->> 'to' as status from case_events where case_id = %s "
                          "and type = 'status_changed' order by seq desc limit 1", (case_id,))
        return rows[0]["status"] if rows else "new"

    def change_status(self, case_id: str, to: QueueStatus, *, on: dt.date, actor: str, trace_id: str,
                      reason: Optional[str] = None) -> CaseEvent:
        _check_writer(actor, trace_id)
        check_business_date(on)
        with self._tx(case_id):
            current = self.queue_status(case_id)
            check_transition(current, to)
            return self._change(case_id, current, to, on, actor, trace_id, reason)

    def record_analyst_action(self, action: AnalystActionIn, *, new_status: Optional[QueueStatus], on: dt.date,
                              trace_id: str) -> AnalystActionOut:
        actor = _check_writer(f"analyst:{action.actor_id}", trace_id)   # a blank sub is refused
        check_business_date(on)
        with self._tx(action.case_id):
            previous = self.queue_status(action.case_id)
            check_transition(previous, new_status, analyst_action=action.action)
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
        _check_writer(actor, trace_id)
        with self._tx(case_id):
            case = self._case(case_id)
            self._check_open(case_id)
            self._check_new_action(action_id)
            if product_id != case["product_id"]:
                raise StoreError(f"{product_id} is not the product of case {case_id}")
            self._rows("insert into product_overrides (override_id, product_id, status, case_id, actor, run_id, "
                       "created_at) values (%s, %s, 'Blocked', %s, %s, %s, %s)",
                       (action_id, product_id, case_id, actor, case["run_id"], self._now()))
            return self._append(case_id, "card_blocked", actor, trace_id,
                                {"action_id": action_id, "product_id": product_id})

    def product_status(self, product_id: str, *, run_id: Optional[str]) -> Optional[ProductOverride]:
        rows = self._rows(
            "select o.product_id, o.status, o.case_id, o.override_id as action_id, o.actor, o.run_id, o.created_at, "
            "(select payload ->> 'verification_id' from case_events where case_id = o.case_id "
            " and type = 'action_verified' and payload ->> 'action_id' = o.override_id order by seq desc limit 1) "
            "as verification_id from product_overrides o where o.product_id = %s and o.run_id is not distinct from %s "
            "order by o.row_no desc limit 1", (product_id, run_id))
        return ProductOverride(**rows[0]) if rows else None

    def action_write(self, action_id: str, *, run_id: Optional[str],
                     customer_id: Optional[str]) -> Optional[CaseEvent]:
        rows = self._rows(f"select {EVENT} from case_events where type = any(%s) and payload ->> 'action_id' = %s",
                          (WRITES, action_id))
        if not rows or self.get_case(rows[0]["case_id"], run_id=run_id, customer_id=customer_id) is None:
            return None
        return CaseEvent(**rows[0])

    def record_verification(self, case_id: str, action_id: str, *, read: VerifyingRead, run_id: Optional[str],
                            customer_id: Optional[str], actor: str, trace_id: str) -> CaseEvent:
        _check_writer(actor, trace_id)
        with self._tx(case_id):                             # T9: the post-condition read and the inserts, one unit
            case = self.get_case(case_id, run_id=run_id, customer_id=customer_id)
            if case is None:
                raise StoreError(f"unknown case {case_id} for this customer in this run")
            write = self._write(case_id, action_id)
            if write is None:
                raise StoreError(f"action {action_id} was never written for case {case_id}")
            if VERIFIED_WITH[WRITE_TOOL[write.type]] != read:
                raise StoreError(f"{write.type} is verified with {VERIFIED_WITH[WRITE_TOOL[write.type]]}, not {read}")
            first_block_read = False
            if write.type == "card_blocked":                # post-condition: this block is the card's current status
                current = self.product_status(write.payload["product_id"], run_id=case.run_id)
                if current is None or current.action_id != action_id or current.status != "Blocked":
                    raise NotVerified(f"block {action_id} is no longer the card's current status; nothing is verified")
                first_block_read = not self._reads(case_id, action_id)
            if write.type == "notification_sent":           # post-condition (D-035): the summary was not lost
                delivery = self._rows("select status from notification_deliveries where notification_id = %s "
                                      "order by row_no desc limit 1", (write.payload["notification_id"],))
                if delivery[0]["status"] in UNDELIVERED:
                    raise NotVerified(f"summary {action_id} {delivery[0]['status']}; nothing is verified")
            payload = {"action_id": action_id, "verification_id": ids.new_id("verification"),
                       "read_at": self._now().isoformat(), "read": read}
            verified = self._append(case_id, "action_verified", actor, trace_id, payload)
            if first_block_read:                            # the customer milestone, once per block
                self._append(case_id, "block_verified", actor, trace_id,
                             {"action_id": action_id, "product_id": write.payload["product_id"]})
            return verified

    def verifications(self, case_id: str, action_id: str, *, run_id: Optional[str]) -> list[CaseEvent]:
        if self.get_case(case_id, run_id=run_id, customer_id=None) is None:
            return []
        return self._reads(case_id, action_id)

    # ---------- notifications ----------
    def add_notification(self, case_id: str, *, event: str, channel: Channel, masked_address: Optional[str],
                         text: str, trigger: Literal["auto", "on_request"], actor: str, trace_id: str,
                         provider_message_id: Optional[str] = None, action_id: Optional[str] = None) -> Notification:
        _check_writer(actor, trace_id)
        check_text(event, masked_address, text, provider_message_id)
        with self._tx(case_id):
            case = self._case(case_id)
            if trigger == "on_request":                     # send_case_summary is a customer write
                self._check_new_action(action_id)
            elif action_id is not None:
                raise StoreError("an auto notification is not a customer write and carries no action id")
            sent = Notification(notification_id=ids.new_id("notification"), case_id=case_id,
                                customer_id=case["customer_id"], event=event, channel=channel,
                                masked_address=masked_address, text=text, trigger=trigger,
                                provider_message_id=provider_message_id, created_at=self._now())
            row = sent.model_dump(exclude={"delivery_status"})
            self._rows(f"insert into notifications ({', '.join(row)}) values ({', '.join(f'%({c})s' for c in row)})",
                       row)
            self._delivery(sent.notification_id, "queued", None)
            self._append(case_id, "notification_sent", actor, trace_id,
                         {"notification_id": sent.notification_id, "event": event, "channel": channel,
                          **({"action_id": action_id} if action_id else {})})
            return sent

    def add_delivery(self, notification_id: str, status: DeliveryStatus,
                     provider_event: Optional[dict[str, Any]] = None) -> None:
        with self._tx():
            if not self._rows("select 1 from notifications where notification_id = %s", (notification_id,)):
                raise StoreError(f"unknown notification {notification_id}")
            if status not in get_args(DeliveryStatus):
                raise StoreError(f"not a delivery status: {status!r}")
            self._delivery(notification_id, status, _json(provider_event))

    def list_notifications(self, customer_id: str, *, run_id: Optional[str]) -> list[Notification]:
        rows = self._rows(
            "select n.*, d.status as delivery_status from notifications n join cases c on c.case_id = n.case_id "
            "join lateral (select status from notification_deliveries where notification_id = n.notification_id "
            "              order by row_no desc limit 1) d on true "
            "where n.customer_id = %s and c.run_id is not distinct from %s "
            "order by n.created_at desc, n.notification_id collate \"C\" desc",
            (customer_id, run_id))
        return [Notification(**r) for r in rows]

    # ---------- internals ----------
    @contextmanager
    def _tx(self, case_id: Optional[str] = None) -> Iterator[None]:
        """One transaction, under the case's advisory lock when given; a schema or data refusal becomes a StoreError."""
        with self._lock:
            try:
                with self._open().transaction():
                    if case_id is not None:
                        self._conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (case_id,))
                    yield
            except psycopg.errors.UniqueViolation as error:  # the action-id index (D-025) behind _check_new_action
                raise StoreError(f"already written ({error.diag.constraint_name})") from None
            except psycopg.IntegrityError as error:
                raise StoreError(f"refused by the schema: {error.diag.message_primary}") from None
            except psycopg.DataError as error:              # e.g. NUL in text; the store checks it first
                raise StoreError(f"refused by the server: {error}") from None
            except UnicodeEncodeError:                      # e.g. a lone surrogate in an id, before the server
                raise StoreError("refused: text with no UTF-8 form") from None

    def _rows(self, query: str, params: Any = None) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._open().execute(query, params)
            return cursor.fetchall() if cursor.description else []

    def _case(self, case_id: str) -> dict[str, Any]:
        rows = self._rows("select * from cases where case_id = %s", (case_id,))
        if not rows:
            raise StoreError(f"unknown case {case_id}")
        return rows[0]

    def _check_open(self, case_id: str) -> None:
        if self.queue_status(case_id) == "closed":
            raise StoreError(f"case {case_id} is closed: a customer write opens a related case instead")

    def _check_new_action(self, action_id: Any) -> None:
        check_action_id(action_id)
        if self._rows("select 1 from case_events where type = any(%s) and payload ->> 'action_id' = %s",
                      (WRITES, action_id)):
            raise StoreError(f"action {action_id} was already written; a write takes a fresh action id")

    def _write(self, case_id: str, action_id: str) -> Optional[CaseEvent]:
        rows = self._rows(f"select {EVENT} from case_events where case_id = %s and type = any(%s) "
                          "and payload ->> 'action_id' = %s", (case_id, WRITES, action_id))
        return CaseEvent(**rows[0]) if rows else None

    def _reads(self, case_id: str, action_id: str) -> list[CaseEvent]:   # seq order = read_at order
        return [CaseEvent(**r) for r in self._rows(
            f"select {EVENT} from case_events where case_id = %s and type = 'action_verified' "
            "and payload ->> 'action_id' = %s order by seq", (case_id, action_id))]

    def _delivery(self, notification_id: str, status: DeliveryStatus, provider_event: Optional[dict]) -> None:
        delivery_id = "D-" + secrets.token_hex(6).upper()  # [assumption] the ids.py shape; the interface never names it
        self._rows("insert into notification_deliveries (delivery_id, notification_id, status, provider_event, "
                   "created_at) values (%s, %s, %s, %s, %s)",
                   (delivery_id, notification_id, status, None if provider_event is None else Jsonb(provider_event),
                    self._now()))

    def _change(self, case_id: str, current: QueueStatus, to: QueueStatus, on: dt.date, actor: str, trace_id: str,
                reason: Optional[str]) -> CaseEvent:
        payload = {"from": current, "to": to, "on": on.isoformat(), **({"reason": reason} if reason else {})}
        return self._append(case_id, "status_changed", actor, trace_id, payload)

    def _append(self, case_id: str, type: EventType, actor: str, trace_id: str, payload: dict[str, Any]) -> CaseEvent:
        self._case(case_id)
        payload = _json(payload)
        rows = self._rows(
            f"insert into case_events ({EVENT}) select %s, %s, coalesce(max(seq), 0) + 1, %s, %s, %s, %s, %s, %s "
            f"from case_events where case_id = %s returning {EVENT}",
            (ids.new_id("event"), case_id, type, actor, Jsonb(payload), type in CUSTOMER_VISIBLE, trace_id,
             self._now(), case_id))
        return CaseEvent(**rows[0])

    # ---------- sessions, policy denials and customer channels (task 01g; arguments as in `Store`) ----------
    def create_session(self, **fields: Any) -> SessionRecord:
        session = parse(NewSession, fields)
        record = SessionRecord(**session.model_dump(), session_id=ids.new_id("session"), created_at=self._now())
        self._insert("sessions", {**record.model_dump(), "tool_faults": list(record.tool_faults)})
        return record

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        rows = self._rows(f"select {', '.join(SessionRecord.model_fields)} from sessions where session_id = %s",
                          (check_key(session_id),))
        return SessionRecord(**rows[0]) if rows else None

    def summary_sends(self, session_id: str, *, since: dt.datetime) -> int:
        session = self.get_session(session_id)
        start = window_start(session, session_id, since)
        return self._rows(
            "select count(*) as sends from notifications n join cases c on c.case_id = n.case_id "
            "where n.customer_id = %s and n.trigger = 'on_request' and c.run_id is not distinct from %s "
            "and n.created_at >= %s", (session.customer_id, session.run_id, start))[0]["sends"]

    def add_denial(self, **fields: Any) -> PolicyDenial:
        denial = parse(NewDenial, fields)
        row = PolicyDenial(**{**denial.model_dump(), "detail": _json(denial.detail)},
                           denial_id=new_row_id(DENIAL_ID), created_at=self._now())
        # no lock needed: a session row is never changed by the store
        check_denial_session(denial, self.get_session(denial.session_id) if denial.session_id else None)
        self._insert("policy_denials", {**row.model_dump(), "detail": Jsonb(row.detail)})
        return row

    def list_denials(self, *, run_id: Optional[str], session_id: Optional[str] = None) -> list[PolicyDenial]:
        rows = self._rows(
            f"select {', '.join(PolicyDenial.model_fields)} from policy_denials where run_id is not distinct from %s "
            "and (%s::text is null or session_id = %s) order by created_at, denial_id collate \"C\"",
            (check_key(run_id), check_key(session_id), session_id))
        return [PolicyDenial(**r) for r in rows]

    def add_channel_event(self, case_id: str, channel: LinkedChannel, address: str, event: ChannelEvent, *,
                          actor: str, trace_id: str) -> CustomerChannel:
        _check_writer(actor, trace_id)
        with self._tx(check_key(case_id)):                  # the case's lock, then the customer's channels' lock
            customer_id = self._case(case_id)["customer_id"]
            self._conn.execute("select pg_advisory_xact_lock(hashtext(%s))", ("channels:" + customer_id,))
            check_channel_event({c.channel: c for c in self.channels(customer_id)}.get(channel), channel, address,
                                event)
            row = CustomerChannel(channel_id=new_row_id(CHANNEL_ID), customer_id=customer_id, channel=channel,
                                  address=address, event=event, created_at=self._now())
            self._insert("customer_channels", row.model_dump())
            if (channel, event) in CHANNEL_CASE_EVENT:
                self._append(case_id, CHANNEL_CASE_EVENT[channel, event], actor, trace_id,
                             {"channel_id": row.channel_id, "channel": channel})
            return row

    def channels(self, customer_id: str) -> list[CustomerChannel]:
        rows = self._rows(
            "select distinct on (channel collate \"C\") channel_id, customer_id, channel, address, event, created_at "
            "from customer_channels where customer_id = %s order by channel collate \"C\", row_no desc",
            (check_key(customer_id),))
        return [CustomerChannel(**r) for r in rows]

    def _insert(self, table: str, row: dict[str, Any]) -> None:
        """One row into a table whose columns are the row's keys (names from the models, never from input)."""
        with self._tx():
            self._rows(f"insert into {table} ({', '.join(row)}) values ({', '.join(f'%({c})s' for c in row)})", row)
