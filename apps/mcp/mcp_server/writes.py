"""Write tools (spec 03 T4): `open_case` and `block_card`. The customer comes only from `call.session` (constitution #3).

- Idempotent: each runs inside `store.once` with the call's `idempotency_key` (policies.yaml
  `reliability.idempotency_key`), so a retry replays the first result and writes nothing (AC-03); the same key with
  other arguments is refused with DENY. A refusal raised inside the write rolls it back and is not remembered.
- Trusted inputs only: the zone, product, country and amount come from gold and the case, never from the agent;
  `open_case` refuses a `zone` other than the score's (AC-09) and returns an active case of the same transaction instead
  of opening a second one (AC-15); `block_card` needs an open case of that card in the session's run and the engine's
  `check()` (AC-10), with `call_requested` read from the case's events (D-042, D-043; `call_open`).
- Another customer's transaction, card or case answers NOT_FOUND as an unknown id does; the gate logs the probe (D-052).
- [assumption] `supervised_mode=False` until the store exposes the console toggle's `settings_events` (spec 08
  AC-05, spec 01 §6.5); the file's `approval.supervised_mode` switch still applies inside the engine.
- Accepted ≠ verified (D-025): both answer `state: "requested"` and no V- id; `get_case` and `get_product_status` verify.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from typing import Optional, Union

from pydantic import BaseModel

from contracts import tools as t
from mcp_server.cards import GoldCards, cards_of
from mcp_server.gate import UNAVAILABLE, Call, Handler
from mcp_server.gold import Gold
from mcp_server.reads import COUNTRY, NOT_FOUND, PROBE, STATUSES
from nick_of_time import ids
from nick_of_time.nlu.text import fold
from nick_of_time.policy import Deny, Policies, PolicyEngine, clock
from nick_of_time.store import CaseEvent, CaseRecord, NewCase, Store, StoreError
from nick_of_time.store.accounts import idempotency_key

ACTOR = "agent"
CROSS_CUSTOMER = "POL-CROSS-CUSTOMER"
# D-042 (lead, 2026-10-05): only these analyst actions end a call hold; take, request_customer_info, mark_ambiguous and
# every other one keep it.
ENDS_HOLD = frozenset({"approve_block", "resolve", "close_case"})
# [assumption] pending D-054: a block is for a case still being worked on, never a resolved or closed one.
BLOCKABLE = frozenset({"new", "verification", "review"})
NO_CARD = t.ToolError(code="NOT_FOUND", message="No such card among yours.")
NO_CASE = t.ToolError(code="NOT_FOUND", message="No such case among yours.")


class Refused(Exception):
    """A refusal inside a write: `store.once` rolls the write back and stores nothing, the tool answers `error`."""

    def __init__(self, error: t.ToolError) -> None:
        super().__init__(error.code)
        self.error = error


def deny(policy_id: str, message: str) -> t.ToolError:
    return t.ToolError(code="DENY", policy_id=policy_id, message=message)


def probe(answer: t.ToolError) -> t.ToolError:
    """D-052: another customer's record answers exactly as an unknown one; the policy id only tells the gate to log it."""
    return answer.model_copy(update={"policy_id": CROSS_CUSTOMER})


def call_open(events: Iterable[CaseEvent]) -> bool:
    """Spec 03 §8 (D-042, ADR 0024): the case has an open call while its latest `call_requested` event, or `handoff_emitted`
    with `handoff_reason` `person_requested` [assumption, D-055: any such handoff of the case, a superset of the opening
    turn's, so a missed one fails closed], has no later `analyst_action` of ENDS_HOLD. Per case: it reads only these
    events. A request after an end opens a new hold."""
    started = ended = 0
    for event in events:
        if event.type == "call_requested" or (event.type == "handoff_emitted"
                                              and event.payload.get("handoff_reason") == "person_requested"):
            started = event.seq
        elif event.type == "analyst_action" and event.payload.get("action") in ENDS_HOLD:
            ended = event.seq
    return started > ended


def zone_of(score: Optional[float], policies: Policies) -> str:
    """Rules 6–9 of spec 02 for a gold score (`dataset`, a deciding source): null → human, else the score's band."""
    if score is None:
        return "human"
    zones = policies.zones
    return "high" if score >= zones["high"].score_min else "medium" if score >= zones["medium"].score_min else "human"


def run_once(store: Store, call: Call, args: t._WriteIn,
             write: Callable[[], BaseModel]) -> Union[BaseModel, t.ToolError]:
    """AC-03: `write` runs at most once per key (scope `[run_id:]c=<customer>`, store.once); later calls get its stored
    result. [assumption] The arguments hashed with the key leave out `session_id`, so a retry after signing in again
    replays; a key reused with other arguments or for another tool is refused (DENY POL-DEFAULT-DENY)."""
    model_out, ran = t.CUSTOMER_TOOLS[call.tool][1], []
    try:
        idempotency_key(args.idempotency_key, call.tool, call.session.customer_id, call.session.run_id)
    except StoreError:                                      # blank, NUL or a lone surrogate: not a key
        return deny("POL-DEFAULT-DENY", "The idempotency key is not valid.")

    def once() -> dict:
        ran.append(True)
        return write().model_dump(mode="json")

    try:
        done = store.once(args.idempotency_key, action=call.tool, customer_id=call.session.customer_id,
                          run_id=call.session.run_id, write=once,
                          arguments=args.model_dump(mode="json", exclude={"session_id", "idempotency_key"}))
    except Refused as refused:
        return refused.error
    except StoreError:
        if ran:                                             # the write itself failed: UNAVAILABLE through the gate
            raise
        return deny("POL-DEFAULT-DENY", "This idempotency key was already used with other arguments.")
    return model_out.model_validate(done.result)


def writes_handlers(gold: Gold, policies: Policies, store: Store, *, cards: Optional[GoldCards] = None,
                    now: Optional[Callable[[], dt.datetime]] = None) -> dict[str, Handler]:
    """The entry point (spec 03 T8) wires this factory by its parameter names. `cards` defaults to the process's
    index over `gold`'s folder (`cards_of`); `now` (an aware UTC datetime) feeds `clock.today` in live mode only, and
    None lets the clock read it (ADR 0020)."""
    engine, cards = PolicyEngine(policies), cards or cards_of(gold)

    def country_of(call: Call) -> Optional[str]:
        """The customer's country from gold; a country with no regulatory_clock entry still opens its case with no
        deadline (POL-CLOCK-UNKNOWN), whether or not it has an amount gate."""
        row = gold.customer(call.session.customer_id)
        return COUNTRY.get(fold(row.country or "")) if row else None

    def case_out(case: CaseRecord, **extra) -> t.OpenCaseOut:
        return t.OpenCaseOut(action_id=case.action_id, case_id=case.case_id, country=case.country,
                             credit_deadline=case.credit_deadline, ruling_deadline=case.ruling_deadline,
                             deadline_source=case.deadline_source, deadline_source_url=case.deadline_source_url,
                             deadline_verified_on=case.deadline_verified_on, related_case_id=case.related_case_id,
                             **extra)

    def active(call: Call) -> list[CaseRecord]:
        cases = store.list_cases(call.session.customer_id, run_id=call.session.run_id)
        return [case for case in cases if store.queue_status(case.case_id) != "closed"]   # newest first

    def open_case(call: Call, args: t.OpenCaseIn):
        customer, run_id = call.session.customer_id, call.session.run_id
        country = country_of(call)
        if country is None:
            return UNAVAILABLE                              # no country, no deadline: never a guess
        trx = gold.transaction(customer, args.transaction_id)
        if trx is None:
            return PROBE if gold.owner(args.transaction_id) else NOT_FOUND
        if trx.transaction_status not in STATUSES:          # Q2: a declined or reversed charge takes no dispute
            return deny("POL-DEFAULT-DENY", "This transaction was declined or reversed; there is no charge to dispute.")
        card = cards.card(customer, trx.product_id)
        if card is None:
            return UNAVAILABLE

        def write() -> t.OpenCaseOut:
            # AC-15 under concurrency: calls with different keys on one transaction run one after the other, so the
            # second sees the first's case (Postgres: an advisory lock held until once's transaction commits).
            with store.serialize(f"open_case:{run_id or '-'}:{customer}:{trx.transaction_id}"):
                return checked_write()

        def checked_write() -> t.OpenCaseOut:
            same = next((c for c in active(call) if c.transaction_id == trx.transaction_id), None)
            if same is not None:                            # AC-15, first: the active case, nothing written
                return case_out(same, duplicate_of=same.case_id)
            if args.zone != zone_of(trx.fraud_score, policies):     # AC-09: the zone is the score's, never the agent's
                raise Refused(deny("POL-ZONE-MISMATCH", "The zone does not match the transaction's fraud score."))
            verdict = engine.check("open_case", args.zone, supervised_mode=False, call_requested=False)
            if isinstance(verdict, Deny):
                raise Refused(deny(verdict.policy_id, "The policy does not allow opening this case."))
            if args.related_case_id is not None:
                related = store.get_case(args.related_case_id, run_id=run_id, customer_id=customer)
                if related is None:
                    other = store.get_case(args.related_case_id, run_id=run_id, customer_id=None)
                    raise Refused(probe(NO_CASE) if other else NO_CASE)
                if store.queue_status(related.case_id) != "closed":
                    raise Refused(deny("POL-DEFAULT-DENY", "Only a closed case can be the related case."))
            opened_on = clock.today(call.session.mode, country, utc_now=now() if now else None, policies=policies)
            where = cards.transaction_country(customer, trx.transaction_id)
            abroad = bool(where) and COUNTRY.get(fold(where)) != country    # [assumption] no country: not abroad
            legal = clock.deadline(country, card.type, opened_on, abroad=abroad, charged_at=trx.transaction_date,
                                   policies=policies)
            case = store.create_case(NewCase(
                customer_id=customer, transaction_id=trx.transaction_id, product_id=trx.product_id, country=country,
                product_type=card.type, zone=args.zone, dispute_type=args.dispute_type, opened_on=opened_on,
                credit_deadline=legal.credit_deadline, ruling_deadline=legal.ruling_deadline,
                deadline_source=legal.deadline_source, deadline_source_url=legal.source_url,
                deadline_verified_on=legal.verified_on, related_case_id=args.related_case_id,
                mode=call.session.mode, run_id=run_id, trace_id=call.trace_id), actor=ACTOR,
                action_id=ids.new_id("action"))
            return case_out(case)

        return run_once(store, call, args, write)

    def block_card(call: Call, args: t.BlockCardIn):
        customer = call.session.customer_id
        if cards.card(customer, args.product_id) is None:
            return probe(NO_CARD) if cards.owner(args.product_id) else NO_CARD

        def write() -> t.BlockCardOut:
            # [assumption] pending D-054: a case names its customer and run, not its session. The block is for a case
            # of this card in BLOCKABLE: the one opened in this turn (same trace id) when there is one, else the
            # newest; its hold is the one read (per case, D-042).
            cases = [c for c in active(call) if c.product_id == args.product_id
                     and store.queue_status(c.case_id) in BLOCKABLE]
            case = next((c for c in cases if c.trace_id == call.trace_id), cases[0] if cases else None)
            if case is None:                                # AC-10: no open case of this card
                raise Refused(deny("POL-DEFAULT-DENY", "There is no open case for this card."))
            trx = gold.transaction(customer, case.transaction_id)
            verdict = engine.check("block_card", case.zone, supervised_mode=False,
                                   call_requested=call_open(store.events(case.case_id)),
                                   amount=trx.amount if trx else None, currency=trx.currency if trx else None,
                                   country=case.country)
            if isinstance(verdict, Deny):                   # AC-10, D-043: POL-HUMAN-REQUEST while the call is open
                raise Refused(deny(verdict.policy_id, "The policy does not allow blocking this card now."))
            action_id = ids.new_id("action")
            store.block_product(case.case_id, args.product_id, action_id=action_id, actor=ACTOR,
                                trace_id=call.trace_id)
            return t.BlockCardOut(action_id=action_id, product_id=args.product_id)

        return run_once(store, call, args, write)

    return {"open_case": open_case, "block_card": block_card}
