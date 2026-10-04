"""Text helpers shared by the rules arm, the date parser and the injection rules (spec 11 §4)."""
from __future__ import annotations

import re
import unicodedata


def fold(text: str) -> str:
    """Lower-case, accent-free text with collapsed whitespace; the form every pattern is written against."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", plain).strip()
