"""B0 rules arm (spec 11 §4, AC-09): ES/PT keyword and pattern lists, regex slots, no model file, no network.

Priority when several intents match: `human_request` > `status_inquiry` > `wrongful_charge` > `unrecognized_charge`
> `out_of_scope`. A customer who asks for a person is never blocked, even inside a dispute message (AC-10). Status wins
over a dispute only when the dispute words are absent or in a past "already reported" form; `dispute_detected` is true
whenever dispute words are present, so the graph still opens the case (spec 11 §6, decision D-020).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from .dates import parse_date
from .injection import injection_flagged
from .text import fold

ARM, VERSION = "B0", "b0-v1"

_PERSON = r"(?:persona|humano|agente|asesor|ejecutivo|operador|atendente|pessoa|alguem|alguien|representante|gerente|supervisor|ser humano)"
_INTENT_RULES: list[tuple[str, list[str]]] = [
    ("human_request", [
        r"\b(?:hablar|conversar|comunicar\w*|pas\w*|falar|passar) (?:\w+ ){0,2}(?:con|com|para|a) (?:un |una |um |uma |o |a )?"
        + _PERSON,
        r"\b(?:quiero|necesito|quero|preciso|prefiero|prefiro) (?:\w+ ){0,2}(?:un |una |um |uma |o |a )?" + _PERSON,
        r"\b(?:que me llamen|llamenme|llamame|me llamen|me ligue\w*|me liga\w*|ligacao|llamada)\b",
        r"\b(?:atencion|atendimento) (?:humana|humano|personal)\b",
        r"\b(?:pueden|puede|podrian|podria) llamar\w*|\bllamarme\b|\bpode me ligar\b|\bpodem me ligar\b",
    ]),
    ("status_inquiry", [
        r"\b(?:como va|como esta|como anda|en que va|en que esta|como esta indo|status|estado(?! de cuenta)|andamento|novedades|"
        r"novidades|noticias)\b.*\b(?:caso|reclamo|reclamacion|disputa|tarjeta|cartao|chamado|protocolo|contestacao)\b",
        r"\b(?:ya|ja)\b.*\b(?:bloquearon|bloqueada|bloqueado|bloquearam|bloqueou|bloqueo)\b",
        r"\b(?:estado(?! de cuenta)|status|situacao) (?:de|do|da) (?:mi |meu |minha )?(?:caso|reclamo|disputa|tarjeta|cartao)\b",
        r"\b(?:mi|meu) (?:caso|chamado)\b.*\b(?:avance|avanzo|progreso|resolvieron|resolveram|resolvido)\b",
    ]),
    ("wrongful_charge", [
        r"\b(?:cobraron|cobrado|cobraram|cobrou|cargaron|debitaron|debitado|debitaram)\b.*"
        r"\b(?:dos veces|2 veces|doble|duas vezes|2 vezes|de mas|a mais|dobro|otra vez|de novo)\b",
        r"\b(?:cobro|cargo|cobranca|debito|compra) (?:duplicad[oa]|doble|repetid[oa]|em duplicidade)\b",
        r"\bdoble (?:cobro|cargo)\b|\bcobranca em duplicidade\b",
        r"\b(?:monto|importe|valor) (?:incorrecto|erroneo|equivocado|errado|incorreto)\b",
        r"\b(?:no recibi|nao recebi|nunca llego|nunca chegou)\b",
        r"\b(?:cancele|cancelei|cancelamos|devolvi|devolvei|reembolso|reembolsaron)\b.*\b(?:cobr|cargo|debit)\w*",
    ]),
    ("unrecognized_charge", [
        r"\b(?:no|nao) (?:reconozco|reconheco|conozco|fui yo|fui eu|fue mio|foi eu|foi meu)\b",
        r"\b(?:no|nao) (?:hice|fiz|realice|realizei|autorice|autorizei|compre|comprei|reconhecemos)\b",
        r"\b(?:desconozco|desconheco|desconhecida|desconocida|desconocido|desconhecido)\b",
        r"\b(?:cargo|compra|cobro|cobranca|movimiento|transacao|lancamento)\b.*"
        r"\b(?:raro|extrano|sospechos\w*|suspeit\w*|estranh\w*|fraud\w*|indebid\w*|no autorizad\w*|nao autorizad\w*)\b",
        r"\b(?:fraude|fraudulent\w*|clonaron|clonaram|clonado|robaron mi tarjeta|roubaram meu cartao)\b",
    ]),
]
_COMPILED = [(intent, [re.compile(p) for p in pats]) for intent, pats in _INTENT_RULES]

_REPORTED = re.compile(r"\b(?:reporte|reclame|registre|reportei|reclamei|registrei)\b")   # "already reported" (past)
_PT_WORDS = {"nao", "voce", "meu", "minha", "cartao", "compra", "fui", "cobrado", "cobraram", "reconheco", "quero",
             "falar", "uma", "duas", "vezes", "ontem", "obrigado", "preciso", "esta", "ja", "foi", "com", "pessoa",
             "atendente", "desconheco", "fiz", "caso"}
_ES_WORDS = {"no", "mi", "tarjeta", "cargo", "fui", "yo", "cobraron", "reconozco", "quiero", "hablar", "una", "dos",
             "veces", "ayer", "gracias", "necesito", "esta", "ya", "con", "persona", "desconozco", "hice", "el", "la",
             "los", "que", "me", "un", "por"}

# Bare "$" and "pesos" stay currency None on purpose: the NLU has no session, the country comes from the session and
# MX gold amounts are USD (spec 02 §4.2), so guessing MXN would be wrong. `search_transaction` resolves it.
_CURRENCY = {"mx$": "MXN", "u$s": "USD", "r$": "BRL", "reais": "BRL", "real": "BRL", "brl": "BRL", "us$": "USD", "usd": "USD", "dolares": "USD",
             "dolar": "USD", "dolares americanos": "USD", "mxn": "MXN", "ars": "ARS", "cop": "COP", "eur": "EUR"}
_CUR = r"(?:r\$|us\$|u\$s|mx\$|usd|brl|mxn|ars|cop|eur|\$|pesos?|reais|real|dolares|dolar)"
_NUM = r"\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_AMOUNT_BEFORE = re.compile(rf"(?<![\w/-])({_CUR})\s*({_NUM})(?![\d/-])")
_AMOUNT_AFTER = re.compile(rf"(?<![\w/-])({_NUM})\s*({_CUR})(?!\w)")
_AMOUNT_CUE = re.compile(rf"\b(?:cargo|compra|cobro|cobranca|monto|importe|valor|por|de|pagos?)\s+({_NUM})(?![\d/-])")
_DATE_NOISE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2} de [a-zç]+(?: de \d{4})?", re.I)
_MERCHANT = re.compile(r"\b(?:en|em|de|do|da)\s+((?:[A-ZÁÉÍÓÚÑÃÕÇ][\w&'.-]*)(?:\s+[A-ZÁÉÍÓÚÑÃÕÇ][\w&'.-]*){0,3})(?![\w$])")
_THOUSANDS = re.compile(r"(\d+(?:[.,]\d{1,2})?) ?mil\b(?! ?(?:millon|milhao))")
_MILLIONS = re.compile(r"\d+(?:[.,]\d+)? ?(?:millon|millones|milhao|milhoes)\b")
_NOT_MERCHANT = {"Hola", "Oi", "Ola", "Mexico", "Brasil", "Argentina", "Colombia", "Ayer", "Ontem"}


def _to_decimal(raw: str) -> Optional[str]:
    """'1.250,50' / '1,250.50' / '1,250' / '89,90' -> '1250.50' / '1250.50' / '1250' / '89.90'."""
    s = raw.replace(" ", "")
    seps = [i for i, c in enumerate(s) if c in ".,"]
    if seps:
        last = seps[-1]
        tail = s[last + 1:]
        if len(tail) == 3:
            s = re.sub(r"[.,]", "", s)                       # a 3-digit tail is thousands, not decimals
        else:
            s = re.sub(r"[.,]", "", s[:last]) + "." + tail
    try:
        return str(Decimal(s))
    except InvalidOperation:
        return None


def _amount(text: str) -> tuple[Optional[str], Optional[str]]:
    t = _DATE_NOISE.sub(" ", fold(text))
    t = _MILLIONS.sub(" ", t)                                # never guess a multiplier: no amount beats a wrong one
    t = _THOUSANDS.sub(lambda m: format((Decimal(_to_decimal(m[1]) or "0") * 1000), "f"), t)
    for pattern, num_idx, cur_idx in ((_AMOUNT_BEFORE, 2, 1), (_AMOUNT_AFTER, 1, 2)):
        if m := pattern.search(t):
            return _to_decimal(m[num_idx]), _CURRENCY.get(m[cur_idx])
    if m := _AMOUNT_CUE.search(t):
        return _to_decimal(m[1]), None
    return None, None


def _merchant(text: str) -> Optional[str]:
    for m in _MERCHANT.finditer(text):
        if m[1] not in _NOT_MERCHANT:
            return m[1]
    return None


def detect_language(text: str, hint: Optional[str] = None) -> str:
    if hint in ("es", "pt"):
        return hint
    words = set(fold(text).split())
    return "pt" if len(words & _PT_WORDS) > len(words & _ES_WORDS) else "es"


def classify_intent(text: str) -> tuple[str, float, bool]:
    """(intent, confidence, dispute_detected). The confidence is fixed: 0.9 for a match (above the policy floor
    `clarify.intent_confidence_min`), 0.5 for no match."""
    t = fold(text)
    hits = {intent for intent, patterns in _COMPILED if any(p.search(t) for p in patterns)}
    dispute = bool(hits & {"wrongful_charge", "unrecognized_charge"})
    if "status_inquiry" in hits and dispute and not _REPORTED.search(t):
        hits.discard("status_inquiry")                        # a new dispute is not a read-only status question
    for intent, _ in _COMPILED:
        if intent in hits:
            return intent, 0.9, dispute
    return "out_of_scope", 0.5, False                         # no rule fired: the arm does not know


def parse_rules(text: str, language_hint: Optional[str], today: date) -> dict:
    """B0 reading of one message; `today` is the session's today (never the system clock)."""
    intent, confidence, dispute = classify_intent(text)
    amount, currency = _amount(text)
    found = parse_date(text, today)
    return {
        "intent": intent, "confidence": confidence, "dispute_detected": dispute, "language": detect_language(text, language_hint),
        "slots": {"amount": amount, "currency": currency, "date": found.isoformat() if found else None,
                  "merchant": _merchant(text)},
        "injection_flagged": injection_flagged(text), "arm": ARM, "version": VERSION,
    }
