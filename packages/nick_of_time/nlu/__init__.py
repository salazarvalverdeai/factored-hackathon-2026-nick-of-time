"""Understanding of a customer message (spec 11 §6): intent, slots, language and injection flag.

Only the B0 rules arm exists here (task 11a). B1 and B2 land with their tasks behind the same `load_nlu` call.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..contracts import DECIMAL, Intent, Language
from .dates import parse_date
from .injection import injection_flagged
from .rules import parse_rules

__all__ = ["NLU", "NLUResult", "Slots", "load_nlu", "parse_date", "injection_flagged"]


class Slots(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Optional[str] = Field(default=None, pattern=DECIMAL)      # decimal string, as in the contracts
    # None for a bare "$" or "pesos": the NLU has no session; the country comes from the session and MX gold amounts
    # are USD, so retrieve/search_transaction resolves the currency against the customer's own transactions.
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    date: Optional[str] = None            # YYYY-MM-DD
    merchant: Optional[str] = None


class NLUResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    confidence: float
    slots: Slots
    language: Language
    injection_flagged: bool
    dispute_detected: bool                # required: dispute words seen even if human_request or status wins (D-020)
    arm: Literal["B0", "B1", "B2", "B3"]
    version: str


class NLU:
    """The B0 rules arm: deterministic, no model file, no network, no system clock (AC-08, AC-09)."""

    def parse(self, text: str, language_hint: Optional[str] = None, *, today: date) -> NLUResult:
        return NLUResult.model_validate(parse_rules(text, language_hint, today))


def load_nlu(arm: str = "B0", path: Optional[str] = None) -> NLU:
    if arm != "B0":
        raise NotImplementedError(f"arm {arm} is not implemented yet (spec 11 T3/T4); only B0 needs no model file")
    return NLU()
