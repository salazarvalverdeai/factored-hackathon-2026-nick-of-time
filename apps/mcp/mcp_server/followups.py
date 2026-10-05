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
# [assumption] G-IN-04's rule in policies.yaml is POL-OUT-OF-SCOPE; a PII rule id is a question for the lead.
SECRET_DENY = t.ToolError(code="DENY", policy_id="POL-OUT-OF-SCOPE",
                          message="Card numbers, CVV codes and passwords are never stored; nothing was saved.")
CLOSED = t.ToolError(code="DENY", policy_id="POL-DEFAULT-DENY",
                     message="This case is closed; a closed case takes no customer change.")
OUT_OF_WINDOW = t.ToolError(code="DENY", policy_id="POL-REEVAL-WINDOW",
                            message="The re-evaluation window of this case has passed; a person can call instead.")
HOLD_ENDS = frozenset({"approve_block", "resolve", "close_case"})   # D-042: the analyst actions that end an open call
ACTIVE = ("new", "verification", "review")
# [assumption] spec 02 §4.4 proposes 30 days for every country until `reevaluation_allowed()` (spec 02 T7) ships.
REEVALUATION_WINDOW_DAYS = 30
Reevaluation = Callable[[str, dt.date, dt.date], bool]       # (country, resolved_on, today) -> allowed


def within_window(country: str, resolved_on: dt.date, on: dt.date) -> bool:
    return (on - resolved_on).days <= REEVALUATION_WINDOW_DAYS


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


def gold_deadline(gold: Gold, policies: Policies) -> Callable[[CaseRecord, dt.date], Optional[Deadline]]:
    """A related case's deadline from the new notice over its gold charge; [assumption] `abroad` is False (the
    loader has no transaction country), the earlier ruling date. A charge not in gold gets none."""
    def deadline_of(case: CaseRecord, on: dt.date) -> Optional[Deadline]:
        trx = gold.transaction(case.customer_id, case.transaction_id)
        return deadline(case.country, case.product_type, on, charged_at=trx.transaction_date,
                        policies=policies) if trx else None
    return deadline_of


def followups_handlers(store: Store, policies: Policies, gold: Optional[Gold] = None, *,
                       reevaluation_allowed: Reevaluation = within_window,
                       country_of: Optional[Callable[[str], Optional[str]]] = None,
                       deadline_of: Optional[Callable[[CaseRecord, dt.date], Optional[Deadline]]] = None,
                       ) -> dict[str, Handler]:
    """The T8 entry point wires `store`, `policies` and `gold` by name. `country_of(customer_id)` (default: gold) gives
    the country of a call with no case; without one that call promises no date. `deadline_of(case, opened_on)`
    (default: gold) gives a related case's legal deadline; without one the related case opens with no deadline and a
    person sets it [assumption]."""
    if gold is not None:
        country_of = country_of or gold_country(gold)
        deadline_of = deadline_of or gold_deadline(gold, policies)
    contact = policies.contact.callback_within_business_days if policies.contact else None

    def owned(call: Call, case_id: str) -> CaseRecord:
        session = call.session
        case = store.get_case(case_id, run_id=session.run_id, customer_id=session.customer_id)
        if case is None:
            raise _Refused(PROBE if store.get_case(case_id, run_id=session.run_id, customer_id=None) else NOT_FOUND)
        return case

    def business_day(call: Call, country: str) -> dt.date:
        return today(call.session.mode, country, policies=policies)

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

        def write():
            case = owned(call, args.case_id)
            status, events = store.queue_status(case.case_id), store.events(case.case_id)
            if status in ACTIVE:                             # nothing written: the write that holds it active
                holder = [e for e in events if e.type in ("case_opened", "reevaluation_requested")][-1]
                return t.RequestReevaluationOut(action_id=holder.payload["action_id"], event_id=holder.event_id,
                                                case_id=case.case_id, outcome="already_in_progress")
            on = business_day(call, case.country)
            if status == "resolved":
                resolved = [e for e in events if e.type == "status_changed" and e.payload["to"] == "resolved"][-1]
                if not reevaluation_allowed(case.country, dt.date.fromisoformat(resolved.payload["on"]), on):
                    raise _Refused(OUT_OF_WINDOW)
                event = reason(case.case_id)
                store.change_status(case.case_id, "review", on=on, actor=ACTOR, trace_id=call.trace_id,
                                    reason="reevaluation_requested")
                return t.RequestReevaluationOut(action_id=event.payload["action_id"], event_id=event.event_id,
                                                case_id=case.case_id, outcome="back_to_review")
            # closed: never reopened; a related case from the new notice, decided by a person (spec 03 §6 lifecycle)
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
