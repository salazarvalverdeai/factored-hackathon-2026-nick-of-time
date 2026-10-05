"""Notification tools (spec 03 T7): `send_case_summary` (N) and `list_my_notifications` (R).

`send_case_summary` renders only the approved `messages.yaml receipt.*` lines with the case's stored facts, sends only to
a channel the customer confirmed (`customer_channels`, never the dataset's e-mails), at most 3 per hour per session
(D-041), once per idempotency key; it answers `state: "requested"`. The provider is called only after the write is
committed and only on a first call, never on a replay or inside the store's transaction. `list_my_notifications` is its verifying read: with
the send's `action_id` it mints a `V-` only while that send's latest delivery is not failed or bounced (D-035, D-025).
Addresses leave this module masked only; the raw address goes only to the sender.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Optional, Protocol

from contracts import tools as t
from mcp_server.followups import NOT_FOUND, PROBE, _Refused
from mcp_server.gate import ACTOR, Call, Handler
from mcp_server.gold import Gold
from mcp_server.reads import mask
from nick_of_time import ids
from nick_of_time.receipt import amount_text, text
from nick_of_time.store import CaseRecord, NotVerified, Store

SENDS_PER_HOUR = 3                                           # D-041, the gate's notifications_per_hour
UNCONFIRMED = t.ToolError(code="DENY", policy_id="POL-DEFAULT-DENY",
                          message="That channel is not confirmed by the customer; nothing was sent.")
TOO_MANY = t.ToolError(code="DENY", policy_id="POL-DEFAULT-DENY",
                       message="Too many summaries in this session; try again later.")


class Sender(Protocol):
    """The api's sender (Telegram or Resend, spec 13) [assumption]: returns the provider message id or raises. None
    leaves the notification `queued` for the api's notifier; tests use a fake, never a real provider."""
    def __call__(self, channel: str, address: str, text: str) -> Optional[str]: ...


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)                           # audit time only, never a business date


def notify_handlers(store: Store, gold: Optional[Gold] = None, *, sender: Optional[Sender] = None,
                    now: Callable[[], dt.datetime] = _utc_now) -> dict[str, Handler]:
    """The T8 entry point wires `store` and `gold` by name (no policy input: the templates are messages.yaml's and the
    limit is D-041's); `gold` gives the charge line of the summary, `sender` the provider (none: stays `queued`)."""

    def owned(call: Call, case_id: str) -> t.ToolError | CaseRecord:
        session = call.session
        case = store.get_case(case_id, run_id=session.run_id, customer_id=session.customer_id)
        if case is None:
            return PROBE if store.get_case(case_id, run_id=session.run_id, customer_id=None) else NOT_FOUND
        return case

    def summary(case: CaseRecord, language: str) -> str:
        """The receipt lines whose facts the store holds; a line without its fact is not rendered."""
        lines = [text("receipt.title", language, case_id=case.case_id)]
        trx = gold.transaction(case.customer_id, case.transaction_id) if gold else None
        if trx is not None:
            facts = dict(amount=amount_text(trx.amount), currency=trx.currency)
            lines.append(text("receipt.transaction", language, merchant=trx.merchant, **facts) if trx.merchant
                         else text("receipt.transaction_no_merchant", language, **facts))
        source = dict(deadline_source=case.deadline_source, source_url=case.deadline_source_url,
                      verified_on=case.deadline_verified_on and case.deadline_verified_on.isoformat())
        for name in ("credit_deadline", "ruling_deadline"):
            if (day := getattr(case, name)) is not None:
                lines.append(text(f"receipt.{name}", language, **{name: day.isoformat()}, **source))
        if not (case.credit_deadline or case.ruling_deadline):
            lines.append(text("receipt.deadline_unknown", language))
        blocks = [e for e in store.events(case.case_id) if e.type == "card_blocked"]
        current = store.product_status(case.product_id, run_id=case.run_id)
        if not blocks:
            done = "what_ai_did_case_only"
        elif current and current.status == "Blocked" and current.verification_id and current.case_id == case.case_id:
            done = "what_ai_did_blocked"
        else:
            done = "what_ai_did_block_unconfirmed"
        return "\n".join([*lines, text(f"receipt.{done}", language), text("receipt.what_a_person_does", language)])

    def deliver(notification_id: str, channel: str, address: str, body: str) -> None:
        """One more delivery row after the committed write: `sent` with the provider's message id (to match a later
        bounce, D-035), or `failed`, never `sent` on an error."""
        try:
            provider_message_id = sender(channel, address, body)
        except Exception as error:
            store.add_delivery(notification_id, "failed", {"error": type(error).__name__})
        else:
            store.add_delivery(notification_id, "sent", {"provider_message_id": provider_message_id})

    def send_case_summary(call: Call, args: t.SendCaseSummaryIn):
        session, pending = call.session, {}

        def write() -> dict:
            found = owned(call, args.case_id)
            if isinstance(found, t.ToolError):
                raise _Refused(found)
            address = next((c.address for c in store.channels(session.customer_id)
                            if c.channel == args.channel and c.confirmed), None)
            if address is None:
                raise _Refused(UNCONFIRMED)
            if store.summary_sends(session.session_id, since=now() - dt.timedelta(hours=1)) >= SENDS_PER_HOUR:
                raise _Refused(TOO_MANY)                     # durable twin of the gate's per-session limit (D-041)
            action_id, masked = ids.new_id("action"), mask(args.channel, address)
            body = summary(found, session.language)
            sent = store.add_notification(found.case_id, event="case_summary", channel=args.channel,
                                          masked_address=masked, text=body, trigger="on_request", actor=ACTOR,
                                          trace_id=call.trace_id, action_id=action_id)
            pending.update(notification_id=sent.notification_id, channel=args.channel, address=address, body=body)
            return t.SendCaseSummaryOut(action_id=action_id, notification_id=sent.notification_id,
                                        channel=args.channel, masked_address=masked).model_dump(mode="json")
        try:
            stored = store.once(args.idempotency_key, action=call.tool, customer_id=session.customer_id,
                                run_id=session.run_id, arguments=args.model_dump(mode="json", exclude={"session_id"}),
                                write=write)
        except _Refused as refused:                          # nothing kept: a replay of the key is refused again
            return refused.error
        if sender is not None and pending and not stored.replayed:   # [assumption] no sender: the api's notifier
            deliver(**pending)
        return t.SendCaseSummaryOut.model_validate(stored.result)

    def list_my_notifications(call: Call, args: t.ListMyNotificationsIn):
        session = call.session
        if args.case_id is not None and isinstance(found := owned(call, args.case_id), t.ToolError):
            return found
        rows = [n for n in store.list_notifications(session.customer_id, run_id=session.run_id)
                if args.case_id in (None, n.case_id)]
        items = [t.NotificationItem(notification_id=n.notification_id, case_id=n.case_id, event=n.event,
                                    channel=n.channel, masked_address=n.masked_address, text=n.text,
                                    delivery_status=n.delivery_status, created_at=n.created_at) for n in rows]
        write = store.action_write(args.action_id, run_id=session.run_id,
                                   customer_id=session.customer_id) if args.action_id else None
        if write is not None and write.type == "notification_sent":
            try:
                read = store.record_verification(write.case_id, args.action_id, read="list_my_notifications",
                                                 run_id=session.run_id, customer_id=session.customer_id, actor=ACTOR,
                                                 trace_id=call.trace_id)
            except NotVerified:                              # D-035: failed or bounced → a plain read
                pass
            else:
                return t.ListMyNotificationsOut(action_id=args.action_id, notifications=items,
                                                verification_id=read.payload["verification_id"],
                                                read_at=read.payload["read_at"])
        return t.ListMyNotificationsOut(notifications=items, read_at=now())

    return {"send_case_summary": send_case_summary, "list_my_notifications": list_my_notifications}
