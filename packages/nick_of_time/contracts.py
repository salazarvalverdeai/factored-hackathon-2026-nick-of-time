"""Contract models shared by api, mcp, agent and eval (spec 01 §6.4, §6.7, FR-01).

The tool models live in `contracts/tools.py` (source of truth, lead approves) and are re-exported here unchanged,
whatever version is checked in. This module adds the shared vocabularies and the customer receipt (`CustomerReceipt`,
mirror of `contracts/customer_receipt.schema.json`). Optional fields serialize as null, which the schema accepts.
"""
from __future__ import annotations

import datetime as dt
import json
from functools import cache
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from contracts import tools as _tools
from nick_of_time.ids import PATTERN

# ---------- re-export of contracts/tools.py ----------
TOOL_MODELS: tuple[str, ...] = tuple(
    name for name, obj in vars(_tools).items()
    if not name.startswith("_") and isinstance(obj, type) and obj.__module__ == _tools.__name__)
globals().update({name: getattr(_tools, name) for name in TOOL_MODELS})

CONTRACTS_DIR = Path(_tools.__file__).resolve().parent


@cache
def load_schema(name: str) -> dict[str, Any]:
    """A JSON schema from contracts/, e.g. "customer_receipt.schema.json"."""
    return json.loads((CONTRACTS_DIR / name).read_text())


# ---------- shared vocabularies (§6.4) ----------
Language = Literal["es", "pt"]
Mode = Literal["replay", "live"]
Zone = Literal["high", "medium", "human"]
QueueStatus = Literal["new", "verification", "review", "resolved", "closed"]
ActionState = Literal["in_progress", "requested", "verified", "not_confirmed"]   # the only words for an action
Decision = Literal["block_and_open_case", "confirm", "ask", "handoff", "answer_status", "connect_person", "deny",
                   "reauthenticate", "escalate_unconfirmed_action"]
Intent = Literal["unrecognized_charge", "wrongful_charge", "status_inquiry", "human_request", "out_of_scope"]
DECIMAL = r"^-?[0-9]+(\.[0-9]+)?$"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- customer receipt (§6.7) ----------
class ReceiptFact(_Contract):
    fact: str
    source_id: str                      # TRX-/PRD- from gold, or V-/K- from nick_of_time.ids


class Money(_Contract):
    amount: str = Field(pattern=DECIMAL)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class DisplayMoney(Money):
    rate: str = Field(pattern=DECIMAL)
    rate_source: str
    as_of: dt.date


class ReceiptAmount(_Contract):
    original: Money
    display: Optional[DisplayMoney] = None      # only from convert_amount with a verified rate (ADR 0019)


class ReceiptAction(_Contract):
    label: str
    action_id: str = Field(pattern=PATTERN["action"])
    state: ActionState
    verification_id: Optional[str] = Field(None, pattern=PATTERN["verification"])
    verified_at: Optional[dt.datetime] = None


class ReceiptDeadline(_Contract):
    country: str
    product: str
    credit_deadline: Optional[dt.date] = None
    ruling_deadline: Optional[dt.date] = None
    deadline_source: str
    source_url: str
    verified_on: dt.date


class CustomerReceipt(_Contract):
    receipt_id: str = Field(pattern=PATTERN["receipt"])
    case_id: str = Field(pattern=PATTERN["case"])
    language: Language
    issued_at: dt.datetime
    verified_facts: list[ReceiptFact]
    mode: Optional[Mode] = None
    product_last4: Optional[str] = Field(None, pattern=r"^[0-9]{4}$")
    amount: Optional[ReceiptAmount] = None
    actions: list[ReceiptAction]
    deadline: Optional[ReceiptDeadline]         # required; null when the country has no verified clock entry
    what_ai_did: str
    what_a_person_does: str
    next_steps: list[str] = []
    case_url: Optional[str] = None


def sample_receipt() -> CustomerReceipt:
    """The fixture receipt kept in the schema's `examples` [simulated]; stubs and the echo graph return it (AC-04)."""
    return CustomerReceipt.model_validate(load_schema("customer_receipt.schema.json")["examples"][0])


# FR-01: a model declared in contracts/tools.py is re-exported, never re-declared here.
_CLASH = set(TOOL_MODELS) & {n for n, v in list(globals().items()) if isinstance(v, type) and v.__module__ == __name__}
if _CLASH:
    raise ImportError(f"nick_of_time.contracts re-declares models of contracts/tools.py: {sorted(_CLASH)}")
