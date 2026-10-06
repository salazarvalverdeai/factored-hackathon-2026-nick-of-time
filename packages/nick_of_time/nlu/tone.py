"""Spec 04 AC-44 (lead request 2026-10-06, tone): the customer's tone by rules, ES and PT, no LLM.

`tone(text)` is "frustrated", "urgent" or "calm". It only words the reply (one acknowledgement label and line); it never
changes intent, slots, the decision, the zone, the chips or any policy outcome.

Limits [assumption]: keyword rules over accent-free text, no negation ("no es urgente" reads urgent), no sarcasm, no
context across turns; a message of mostly upper-case names (a merchant in capitals) can read as shouting. "ya"/"já" count as urgency only as "ya mismo", "para ya" or at the end of a clause ("bloquéala
ya!"), so "ya pagué" / "já paguei" stay calm; "agora" counts only as "agora mesmo" or at the end of a clause.
"""
from __future__ import annotations

import re
from typing import Literal

from .text import fold

Tone = Literal["calm", "urgent", "frustrated"]
END = r"(?=\s*(?:[.!?,;]|$))"
URGENT = re.compile(
    r"\burgente?s?\b|\burgencia\b|\bahora mismo\b|\bde inmediato\b|\binmediatamente\b|\brapid[oa]\b|"
    r"\bya mismo\b|\bpara ya\b|\bya" + END + r"|"
    r"\bagora mesmo\b|\bimediatamente\b|\bagora" + END + r"|\bja" + END)
FRUSTRATED = re.compile(
    r"\botra vez\b|\bde nuevo\b|\bnadie me (?:ayuda|responde)\b|\bhart[oa]s?\b|\bcansad[oa]s?\b|\bestafa\b|"
    r"\bde novo\b|\boutra vez\b|\bninguem\b|\bgolpe\b|\babsurd[oa]\b")
SHOUT = re.compile(r"!{2,}")


def shouting(text: str) -> bool:
    """At least 60% upper case over at least 4 letters, or a run of two or more "!"."""
    letters = [c for c in text if c.isalpha()]
    upper = sum(c.isupper() for c in letters)
    return bool(SHOUT.search(text)) or (len(letters) >= 4 and upper >= 0.6 * len(letters))


def tone(text: str) -> Tone:
    """Frustration words win over urgency; shouting with no frustration word reads urgent [assumption]."""
    if not text or not text.strip():
        return "calm"
    plain = fold(text)
    if FRUSTRATED.search(plain):
        return "frustrated"
    return "urgent" if URGENT.search(plain) or shouting(text) else "calm"
