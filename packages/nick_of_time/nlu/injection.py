"""Injection rules (spec 11 §4, AC-04; guardrail G-IN-01).

ES/PT/EN patterns for the instruction-override, prompt-reveal, role-play and other-customer attempts listed in OWASP
LLM01. The rules only flag text. They never decide an action: a flag sends the turn to the human zone and the policy
engine decides (constitution rules 1 and 3).
"""
from __future__ import annotations

import re

from .text import fold

_SKIP = r"(?:\w+ ){0,3}"     # up to three filler words between a verb and its object
_PATTERNS = [re.compile(p) for p in (
    # override the instructions
    r"\b(?:ignora|ignore|ignorar|olvida|esquece|desconsidera|omite|forget|disregard|override)\w* " + _SKIP +
    r"(?:instruccion\w*|instrucoes|reglas|regras|prompt|indicaciones|orientacoes|instructions|rules|guidelines)",
    # reveal the prompt or the tools
    r"\b(?:system|sistema) ?prompt\b",
    r"\b(?:muestra|muestrame|revela|repite|mostre|mostra|revele|show|reveal|print|repeat)\w* " + _SKIP +
    r"(?:instrucciones|instrucoes|prompt|configuracion|herramientas|ferramentas|instructions)",
    # role-play and mode switches
    r"\b(?:finge|fingir|finja|hazte pasar|pretend|roleplay|role-play)\w*\b",
    r"\bactua\w* (?:\w+ ){0,2}como\b",
    r"\byou are now\b|\bahora eres\b|\bagora voce e\b|\bmodo (?:desarrollador|developer|desenvolvedor|dios|deus)\b"
    r"|\bdeveloper mode\b|\bjailbreak\b",
    # other customers' data
    r"\b(?:muestra|muestrame|dame|mostre|mostra|show|give me)\w* " + _SKIP +
    r"(?:cuenta|conta|tarjeta|cartao|datos|dados|saldo|movimientos|account|card|data) "
    r"(?:de|do|da|of) (?:otro|outro|another|[a-z]+-?\d{3,})",
    r"\b(?:cus|cst|cli|cust)[-_][a-z0-9]{4,}\b",
    r"\bcustomer_?id\b|\bid (?:de|del) cliente\b|\bid do cliente\b",
    # asking for decisions the rules own
    r"\b(?:aprueba|aprova|aprobar|approve)\w* " + _SKIP + r"(?:credito provisional|credito provisorio|provisional credit)",
    r"\b(?:cierra|fecha|cerrar|close)\w* (?:el|o|the) (?:caso|case) (?:sin|without)\b",
)]


def injection_flagged(text: str) -> bool:
    """True when the text matches an injection pattern (rules only; the caller decides what a flag means)."""
    t = fold(text)
    return any(p.search(t) for p in _PATTERNS)
