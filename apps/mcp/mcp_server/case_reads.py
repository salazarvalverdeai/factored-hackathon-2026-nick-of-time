"""Case and card reads (spec 03 T5): `get_product_status`, `list_my_cards`, `get_case`, `list_my_cases`.

Every call reads the store and gold again and returns `read_at`; nothing is cached (AC-16). The customer and run come
only from `call.session` (constitution #3); another customer's card or case answers NOT_FOUND as an unknown id does,
and the gate logs the probe (D-052). A card's status is the run's latest overlay row, else gold's (AC-04).
Accepted ≠ verified (D-025): `get_product_status` and `get_case`, called with a write's `action_id`, mint its V- id
through `store.record_verification` only when that write is the customer's, belongs to this card or case, is verified
by this read (`VERIFIED_WITH`) and its post-condition holds; otherwise, and always for the two listings, the answer is
a plain reading with `read_at` only. Stored deadlines are returned as stored, never recomputed.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Optional

import yaml

from contracts import tools as t
from mcp_server.cards import GoldCard, GoldCards, cards_of
from mcp_server.gate import UNAVAILABLE, Call, Handler
from mcp_server.gold import Gold, find, synthetic_from
from mcp_server.writes import NO_CARD, NO_CASE, probe
from nick_of_time.contracts import CONTRACTS_DIR
from nick_of_time.policy import Policies
from nick_of_time.store import CUSTOMER_VISIBLE, VERIFIED_WITH, WRITE_TOOL, CaseRecord, NotVerified, Store

ACTOR = "agent"
_LABELS = yaml.safe_load((CONTRACTS_DIR / "messages.yaml").read_text())["status"]["label"]
# messages.yaml status.label: queue status → {es, pt} (Recibido, En revisión, Resuelto, Cerrado).
STATUS_LABEL: dict[str, dict[str, str]] = {status: {"es": entry["es"], "pt": entry["pt"]}
                                           for entry in _LABELS.values() for status in entry["from"]}
# [assumption] timeline labels until messages.yaml carries them (a contract change for the lead): one per
# customer-visible event type of the store (spec 01 §6.5 ✓ list).
TIMELINE_LABEL: dict[str, dict[str, str]] = {
    "case_opened": {"es": "Caso abierto", "pt": "Caso aberto"},
    "card_blocked": {"es": "Bloqueo de la tarjeta solicitado", "pt": "Bloqueio do cartão solicitado"},
    "block_verified": {"es": "Bloqueo de la tarjeta verificado", "pt": "Bloqueio do cartão verificado"},
    "status_changed": {"es": "Estado actualizado", "pt": "Situação atualizada"},
    "assigned": {"es": "Una persona tomó tu caso", "pt": "Uma pessoa assumiu seu caso"},
    "customer_info_added": {"es": "Información agregada", "pt": "Informação adicionada"},
    "call_requested": {"es": "Llamada solicitada", "pt": "Ligação solicitada"},
    "reevaluation_requested": {"es": "Reevaluación solicitada", "pt": "Reavaliação solicitada"},
    "related_case_opened": {"es": "Caso relacionado abierto", "pt": "Caso relacionado aberto"},
    "notification_sent": {"es": "Notificación enviada", "pt": "Notificação enviada"},
    "receipt_issued": {"es": "Comprobante emitido", "pt": "Comprovante emitido"},
    "telegram_linked": {"es": "Telegram vinculado", "pt": "Telegram vinculado"},
    "email_confirmed": {"es": "Correo confirmado", "pt": "E-mail confirmado"}}
if set(TIMELINE_LABEL) != set(CUSTOMER_VISIBLE):
    raise RuntimeError("every customer-visible event type needs a timeline label (spec 01 §6.5)")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def case_reads_handlers(gold: Gold, policies: Policies, store: Store, *, cards: Optional[GoldCards] = None,
                        now: Callable[[], dt.datetime] = _utc_now) -> dict[str, Handler]:
    """The entry point (spec 03 T8) wires this factory by its parameter names; `cards` defaults to `cards_of(gold)`.
    `now` is the audit time of a reading (`read_at`), never a business date."""
    cards = cards or cards_of(gold)

    def lang(call: Call) -> str:
        return call.session.language if call.session.language in ("es", "pt") else "es"

    def verify(call: Call, action_id: Optional[str], read: str, case_id: Optional[str] = None,
               product_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """D-025: `{action_id, verification_id, read_at}` when this read verifies that write now, else None."""
        if action_id is None:
            return None
        session = call.session
        write = store.action_write(action_id, run_id=session.run_id, customer_id=session.customer_id)
        if (write is None or VERIFIED_WITH[WRITE_TOOL[write.type]] != read or case_id not in (None, write.case_id)
                or product_id not in (None, write.payload.get("product_id"))):
            return None                                     # another write, case or card: a plain reading
        try:
            event = store.record_verification(write.case_id, action_id, read=read, run_id=session.run_id,
                                              customer_id=session.customer_id, actor=ACTOR, trace_id=call.trace_id)
        except NotVerified:                                 # the post-condition does not hold now
            return None
        return {"action_id": action_id, "verification_id": event.payload["verification_id"],
                "read_at": event.payload["read_at"]}

    def card_out(card: GoldCard, call: Call, read_at: dt.datetime) -> dict[str, Any]:
        override = store.product_status(card.product_id, run_id=call.session.run_id)
        return {"product_id": card.product_id, "type": card.type, "last4": card.last4,
                "status": override.status if override else card.status, "read_at": read_at}

    def get_product_status(call: Call, args: t.GetProductStatusIn):
        card = cards.card(call.session.customer_id, args.product_id)
        if card is None:
            return probe(NO_CARD) if cards.owner(args.product_id) else NO_CARD
        verified = verify(call, args.action_id, "get_product_status", product_id=card.product_id)
        return t.GetProductStatusOut(**{**card_out(card, call, now()), **(verified or {})})

    def list_my_cards(call: Call, args: t.ListMyCardsIn):
        read_at = now()
        return t.ListMyCardsOut(cards=[t.Card(**card_out(card, call, read_at))
                                       for card in cards.cards(call.session.customer_id)], read_at=read_at)

    def related(case: CaseRecord, events) -> Optional[str]:
        """The case this one follows, else the newest case opened to follow it."""
        followers = [e.payload["case_id"] for e in events if e.type == "related_case_opened"]
        return case.related_case_id or (followers[-1] if followers else None)

    def get_case(call: Call, args: t.GetCaseIn):
        session = call.session
        case = store.get_case(args.case_id, run_id=session.run_id, customer_id=session.customer_id)
        if case is None:
            other = store.get_case(args.case_id, run_id=session.run_id, customer_id=None)
            return probe(NO_CASE) if other else NO_CASE
        trx = find(gold, synthetic_from(store), session, case.transaction_id)
        if trx is None:
            return UNAVAILABLE                              # no fact to state: never a guess
        verified = verify(call, args.action_id, "get_case", case_id=case.case_id)
        events, status, card = store.events(case.case_id), store.queue_status(case.case_id), \
            cards.card(session.customer_id, case.product_id)
        visible = [t.CaseEventItem(event_id=e.event_id, type=e.type, label=TIMELINE_LABEL[e.type][lang(call)],
                                   created_at=e.created_at) for e in events if e.customer_visible]
        return t.GetCaseOut(
            case_id=case.case_id, queue_status=status, status_label=STATUS_LABEL[status][lang(call)],
            transaction=t.CaseCharge(transaction_id=trx.transaction_id, amount=trx.amount, currency=trx.currency,
                                     transaction_date=trx.transaction_date, merchant=trx.merchant),
            product_last4=card.last4 if card else None, timeline=visible,
            taken_by_person=any(e.type == "assigned" for e in events), related_case_id=related(case, events),
            credit_deadline=case.credit_deadline, ruling_deadline=case.ruling_deadline,
            deadline_source=case.deadline_source, deadline_source_url=case.deadline_source_url,
            deadline_verified_on=case.deadline_verified_on, **(verified or {"read_at": now()}))

    def list_my_cases(call: Call, args: t.ListMyCasesIn):
        session, mine = call.session, []
        for case in store.list_cases(session.customer_id, run_id=session.run_id):   # active first, newest first
            events, status = store.events(case.case_id), store.queue_status(case.case_id)
            card = cards.card(session.customer_id, case.product_id)
            mine.append(t.MyCase(case_id=case.case_id, queue_status=status,
                                 status_label=STATUS_LABEL[status][lang(call)], credit_deadline=case.credit_deadline,
                                 ruling_deadline=case.ruling_deadline, product_last4=card.last4 if card else None,
                                 related_case_id=related(case, events),   # the customer's last visible change
                                 updated_at=max(e.created_at for e in events if e.customer_visible)))
        return t.ListMyCasesOut(cases=mine, read_at=now())

    return {"get_product_status": get_product_status, "list_my_cards": list_my_cards, "get_case": get_case,
            "list_my_cases": list_my_cases}
