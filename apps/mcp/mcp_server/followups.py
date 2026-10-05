"""Follow-up tools of a returning customer (spec 03 T6): `add_case_info`, `request_call`, `request_reevaluation`.

Each handler takes the customer and run only from `call.session` (constitution #3) and writes through the store's
`once`, so a replayed idempotency key returns the stored result and writes nothing. A write answers `state:
"requested"` with its `action_id`; only `get_case` verifies it (D-025). Another customer's case answers NOT_FOUND, as an
unknown id does, and the gate logs it as POL-CROSS-CUSTOMER (D-052). Customer text is stored marked `origin: customer`
and never interpreted.
"""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from typing import Optional

from pydantic import BaseModel

from contracts import tools as t
from mcp_server.cards import cards_of
from mcp_server.gate import ACTOR, Call, Handler
from mcp_server.gold import Gold
from mcp_server.reads import COUNTRY
from nick_of_time import ids
from nick_of_time.nlu.text import fold
from nick_of_time.policy import Policies
from nick_of_time.policy.clock import CalendarNotCovered, Deadline, add_business_days, deadline, today
from nick_of_time.store import CaseEvent, CaseRecord, NewCase, Store

NOT_FOUND = t.ToolError(code="NOT_FOUND", message="No such case among yours.")
PROBE = NOT_FOUND.model_copy(update={"policy_id": "POL-CROSS-CUSTOMER"})     # the gate logs it and strips the id
# AC-17 (G-IN-04) [assumption]: 13-19 digits (Luhn or not), a CVV with its digits, a password stated with its value.
SECRET = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"
                    r"|(?i:\b(?:cvv2?|cvc|cvn|c[oó]digo de segur(?:idad|an[cç]a))\D{0,12}\d{3,4}\b)"
                    r"|(?i:\b(?:contrase[nñ]a|password|senha|clave|nip|pin)\b\s*(?:[:=]|es\b|é\b|is\b)\s*\S+)")
# [assumption] D-062 pending: POL-PII (guardrail G-IN-04) in policies.yaml.
SECRET_DENY = t.ToolError(code="DENY", policy_id="POL-PII",
                          message="Card numbers, CVV codes and passwords are never stored; nothing was saved.")
CLOSED = t.ToolError(code="DENY", policy_id="POL-DEFAULT-DENY",
                     message="This case is closed; a closed case takes no customer change.")
OUT_OF_WINDOW = t.ToolError(code="DENY", policy_id="POL-REEVAL-WINDOW",
                            message="The re-evaluation window of this case has passed; a person can call instead.")
# [assumption] D-062: a country with no window is denied by default, not as a window that passed; a call is offered.
NO_WINDOW = t.ToolError(code="DENY", policy_id="POL-DEFAULT-DENY",
                        message="This case cannot be re-evaluated here; a person can call instead.")
HOLD_ENDS = frozenset({"approve_block", "resolve", "close_case"})   # D-042: the analyst actions that end an open call
ACTIVE = ("new", "verification", "review")             # AC-19's "active"; AC-15 and AC-17 mean "not closed"
# (country, resolved_on, today) -> allowed; None: the country has no window at all
Reevaluation = Callable[[str, dt.date, dt.date], Optional[bool]]
TransactionCountry = Callable[[str, str], Optional[str]]     # (customer_id, transaction_id) -> gold transaction_country


def policy_window(policies: Policies) -> Reevaluation:
    """The case country's `reevaluation.window_days` of policies.yaml ([assumption] D-062, until spec 02 T7's
    `reevaluation_allowed()`): day `window_days` after the resolution still qualifies; a country with no window, or a
    policy with none, has no window (None): nothing goes back, the most conservative answer."""
    windows = policies.reevaluation.window_days if policies.reevaluation else {}

    def allowed(country: str, resolved_on: dt.date, on: dt.date) -> Optional[bool]:
        days = windows.get(country)
        return None if days is None else (on - resolved_on).days <= days
    return allowed


def abroad(where: Optional[str], country: str) -> bool:
    """A charge in another country than the customer's, by open_case's rule (PR #123); no country: not abroad."""
    return bool(where) and COUNTRY.get(fold(where)) != country


def holder(events: list[CaseEvent]) -> Optional[CaseEvent]:
    """AC-19 (D-025): the write that holds an active case, its `case_opened`, or the `reevaluation_requested` that moved
    it from resolved back to review (a related case's reason event holds nothing: its `case_opened` does)."""
    held = None
    for before, event in zip([None, *events], events):
        if event.type == "case_opened":
            held = event
        elif (event.type == "status_changed" and event.payload.get("from") == "resolved" and before is not None
              and before.type == "reevaluation_requested"):
            held = before
    return held


def open_call(events: list[CaseEvent]) -> Optional[CaseEvent]:
    """AC-18: the case's open call request, the latest `call_requested` with no approve_block, resolve or close_case
    after it (D-042 [assumption]: the same end as the block hold), else None."""
    latest = None
    for event in events:
        if event.type == "call_requested":
            latest = event
        elif event.type == "analyst_action" and event.payload.get("action") in HOLD_ENDS:
            latest = None
    return latest


class _Refused(Exception):
    """Raised inside a `once` write so the store keeps nothing; the handler answers its error."""

    def __init__(self, error: t.ToolError) -> None:
        super().__init__(error.code)
        self.error = error


def gold_country(gold: Gold) -> Callable[[str], Optional[str]]:
    def country_of(customer_id: str) -> Optional[str]:
        row = gold.customer(customer_id)
        return COUNTRY.get(fold(row.country or "")) if row else None
    return country_of


def gold_deadline(gold: Gold, policies: Policies,
                  transaction_country: Optional[TransactionCountry]) -> Callable[[CaseRecord, dt.date], Optional[Deadline]]:
    """A related case's deadline from the new notice over its gold charge, `abroad` as open_case derives it. A charge
    not in gold gets none."""
    def deadline_of(case: CaseRecord, on: dt.date) -> Optional[Deadline]:
        trx = gold.transaction(case.customer_id, case.transaction_id)
        if trx is None:
            return None
        where = transaction_country(case.customer_id, case.transaction_id) if transaction_country else None
        return deadline(case.country, case.product_type, on, abroad=abroad(where, case.country),
                        charged_at=trx.transaction_date, policies=policies)
    return deadline_of


def followups_handlers(store: Store, policies: Policies, gold: Optional[Gold] = None, *,
                       reevaluation_allowed: Optional[Reevaluation] = None,
                       country_of: Optional[Callable[[str], Optional[str]]] = None,
                       deadline_of: Optional[Callable[[CaseRecord, dt.date], Optional[Deadline]]] = None,
                       transaction_country: Optional[TransactionCountry] = None,
                       now: Optional[Callable[[], dt.datetime]] = None) -> dict[str, Handler]:
    """The T8 entry point wires `store`, `policies` and `gold` by name. `country_of(customer_id)` (default: gold) gives
    the country of a call with no case; without one that call promises no date. `deadline_of(case, opened_on)`
    (default: gold, with `transaction_country`, else the card index `cards_of(gold)`) gives a related case's legal deadline; without one
    the related case opens with no deadline and a person sets it [assumption]. `now` (aware UTC) feeds `clock.today`
    in live mode only; None lets the clock read it (ADR 0020)."""
    reevaluation_allowed = reevaluation_allowed or policy_window(policies)
    if gold is not None:
        country_of = country_of or gold_country(gold)
        deadline_of = deadline_of or gold_deadline(gold, policies, transaction_country or cards_of(gold).transaction_country)
    contact = policies.contact.callback_within_business_days if policies.contact else None

    def owned(call: Call, case_id: str) -> CaseRecord:
        session = call.session
        case = store.get_case(case_id, run_id=session.run_id, customer_id=session.customer_id)
        if case is None:
            raise _Refused(PROBE if store.get_case(case_id, run_id=session.run_id, customer_id=None) else NOT_FOUND)
        return case

    def business_day(call: Call, country: str) -> dt.date:
        return today(call.session.mode, country, utc_now=now() if now else None, policies=policies)

    def contact_by(call: Call, country: Optional[str]) -> Optional[dt.date]:
        """D-008: `contact.callback_within_business_days` from today; None when the policy or calendar has none."""
        if not contact or not country:
            return None
        try:
            return add_business_days(country, business_day(call, country), contact)
        except CalendarNotCovered:
            return None

    def once(call: Call, args: t._WriteIn, write: Callable[[], BaseModel]):
        try:
            stored = store.once(args.idempotency_key, action=call.tool, customer_id=call.session.customer_id,
                                run_id=call.session.run_id, arguments=args.model_dump(mode="json", exclude={"session_id"}),
                                write=lambda: write().model_dump(mode="json"))
        except _Refused as refused:
            return refused.error
        return t.CUSTOMER_TOOLS[call.tool][1].model_validate(stored.result)

    def add_case_info(call: Call, args: t.AddCaseInfoIn):
        if SECRET.search(args.text):                         # before anything is read, hashed or stored
            return SECRET_DENY

        def write():
            case = owned(call, args.case_id)
            if store.queue_status(case.case_id) == "closed":
                raise _Refused(CLOSED)
            action_id = ids.new_id("action")
            event = store.append_event(case.case_id, "customer_info_added", actor=ACTOR, trace_id=call.trace_id,
                                       payload={"action_id": action_id, "text": args.text, "origin": "customer"})
            return t.AddCaseInfoOut(action_id=action_id, event_id=event.event_id, case_id=case.case_id)
        return once(call, args, write)

    def request_call(call: Call, args: t.RequestCallIn):
        session = call.session
        if args.preferred_time and SECRET.search(args.preferred_time):    # free customer text too (G-IN-04)
            return SECRET_DENY

        def write():
            if args.case_id is None:                         # a general request: a call_requests row (D-026)
                country = country_of(session.customer_id) if country_of else None
                row = store.add_call_request(customer_id=session.customer_id, session_id=session.session_id,
                                             action_id=ids.new_id("action"), trace_id=call.trace_id,
                                             expected_contact_by=contact_by(call, country),
                                             preferred_time=args.preferred_time, run_id=session.run_id)
                return t.RequestCallOut(action_id=row.action_id, event_id=row.event_id,
                                        expected_contact_by=row.expected_contact_by)
            case = owned(call, args.case_id)
            if store.queue_status(case.case_id) == "closed":
                raise _Refused(CLOSED)
            if (held := open_call(store.events(case.case_id))) is not None:      # one open request per case
                return t.RequestCallOut(action_id=held.payload["action_id"], event_id=held.event_id,
                                        case_id=case.case_id, expected_contact_by=held.payload.get("expected_contact_by"))
            action_id, when = ids.new_id("action"), contact_by(call, case.country)
            payload = {"action_id": action_id, "expected_contact_by": when.isoformat() if when else None}
            if args.preferred_time:
                payload |= {"preferred_time": args.preferred_time, "origin": "customer"}
            event = store.append_event(case.case_id, "call_requested", actor=ACTOR, trace_id=call.trace_id,
                                       payload=payload)
            if store.queue_status(case.case_id) == "new":    # [assumption] D-063: a held case waits in review (its
                store.change_status(case.case_id, "review", on=business_day(call, case.country), actor=ACTOR,
                                    trace_id=call.trace_id, reason="call_requested")   # SLA), in the same once
            return t.RequestCallOut(action_id=action_id, event_id=event.event_id, case_id=case.case_id,
                                    expected_contact_by=when)
        return once(call, args, write)

    def request_reevaluation(call: Call, args: t.RequestReevaluationIn):
        if SECRET.search(args.reason):
            return SECRET_DENY

        def reason(case_id: str) -> CaseEvent:
            return store.append_event(case_id, "reevaluation_requested", actor=ACTOR, trace_id=call.trace_id,
                                      payload={"action_id": ids.new_id("action"), "reason": args.reason,
                                               "origin": "customer"})

        def in_progress(case: CaseRecord, events: list[CaseEvent]) -> t.RequestReevaluationOut:
            held = holder(events)
            return t.RequestReevaluationOut(action_id=held.payload["action_id"], event_id=held.event_id,
                                            case_id=case.case_id, outcome="already_in_progress",
                                            related_case_id=case.related_case_id)

        def write():
            case = owned(call, args.case_id)
            status, events = store.queue_status(case.case_id), store.events(case.case_id)
            if status in ACTIVE:                             # nothing written: the write that holds it active
                return in_progress(case, events)
            on = business_day(call, case.country)
            if status == "resolved":
                resolved = [e for e in events if e.type == "status_changed" and e.payload["to"] == "resolved"][-1]
                verdict = reevaluation_allowed(case.country, dt.date.fromisoformat(resolved.payload["on"]), on)
                if not verdict:
                    raise _Refused(NO_WINDOW if verdict is None else OUT_OF_WINDOW)
                event = reason(case.case_id)
                store.change_status(case.case_id, "review", on=on, actor=ACTOR, trace_id=call.trace_id,
                                    reason="reevaluation_requested")
                return t.RequestReevaluationOut(action_id=event.payload["action_id"], event_id=event.event_id,
                                                case_id=case.case_id, outcome="back_to_review")
            # closed: never reopened; a related case from the new notice, decided by a person (spec 03 §6 lifecycle).
            # AC-15: one case not closed per transaction, so an earlier related case (or open_case's) is the answer,
            # under open_case's lock on the same key, so concurrent calls of either tool open one case.
            session = call.session
            with store.serialize(f"open_case:{session.run_id or '-'}:{session.customer_id}:{case.transaction_id}"):
                return related_case(case, on)

        def related_case(case: CaseRecord, on: dt.date) -> t.RequestReevaluationOut:
            session = call.session
            same = next((c for c in store.list_cases(session.customer_id, run_id=session.run_id)
                         if c.transaction_id == case.transaction_id and store.queue_status(c.case_id) != "closed"), None)
            if same is not None:
                return in_progress(same, store.events(same.case_id))
            term = deadline_of(case, on) if deadline_of else None
            dates = {} if term is None or not (term.credit_deadline or term.ruling_deadline) else dict(
                credit_deadline=term.credit_deadline, ruling_deadline=term.ruling_deadline,
                deadline_source=term.deadline_source, deadline_source_url=term.source_url,
                deadline_verified_on=term.verified_on)
            facts = case.model_dump(include={"customer_id", "transaction_id", "product_id", "country", "product_type",
                                             "zone", "dispute_type", "mode", "run_id"})
            action_id = ids.new_id("action")
            related = store.create_case(NewCase(**facts, **dates, opened_on=on, related_case_id=case.case_id,
                                                trace_id=call.trace_id), actor=ACTOR, action_id=action_id)
            opened = store.events(related.case_id)[0]
            reason(related.case_id)
            store.change_status(related.case_id, "review", on=on, actor=ACTOR, trace_id=call.trace_id,
                                reason="related_case")
            return t.RequestReevaluationOut(action_id=action_id, event_id=opened.event_id, case_id=related.case_id,
                                            outcome="related_case_opened", related_case_id=case.case_id)
        return once(call, args, write)

    return {"add_case_info": add_case_info, "request_call": request_call,
            "request_reevaluation": request_reevaluation}
