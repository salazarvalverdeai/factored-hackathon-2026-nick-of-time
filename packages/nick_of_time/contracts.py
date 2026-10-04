"""Contract models shared by api, mcp, agent and eval (spec 01 §6.4, §6.7, FR-01).

Every public name defined in `contracts/tools.py` (source of truth, lead approves) is re-exported here unchanged,
whatever version is checked in. This module adds the shared vocabularies and the customer receipt (`CustomerReceipt`,
mirror of `contracts/customer_receipt.schema.json`). Optional fields serialize as null, which the schema accepts.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
from functools import cache
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts import tools as _tools
from nick_of_time.ids import PATTERN


def _defined_names(path: Path) -> set[str]:
    """Public top-level names a module defines itself (classes, functions, assignments, type aliases)."""
    names: set[str] = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.TypeAlias):
            names.add(node.name.id)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {n for n in names if not n.startswith("_")}


# ---------- re-export of contracts/tools.py ----------
TOOL_NAMES: tuple[str, ...] = tuple(sorted(_defined_names(Path(_tools.__file__))))
globals().update({name: getattr(_tools, name) for name in TOOL_NAMES})

CONTRACTS_DIR = Path(_tools.__file__).resolve().parent


@cache
def load_schema(name: str) -> dict[str, Any]:
    """A JSON schema from contracts/, e.g. "customer_receipt.schema.json"."""
    return json.loads((CONTRACTS_DIR / name).read_text())


# ---------- shared vocabularies (§6.4) ----------
Language = Literal["es", "pt"]
Mode = Literal["replay", "live"]
Zone = Literal["high", "medium", "human"]                                        # policies.yaml zones
QueueStatus = Literal["new", "verification", "review", "resolved", "closed"]     # policies.yaml case_queue.states
ActionState = Literal["in_progress", "requested", "verified", "not_confirmed"]   # the only words for an action
Decision = Literal["block_and_open_case", "confirm", "ask", "handoff", "answer_status", "connect_person", "deny",
                   "reauthenticate", "escalate_unconfirmed_action"]
Intent = Literal["unrecognized_charge", "wrongful_charge", "status_inquiry", "human_request", "out_of_scope"]
DECIMAL = r"^-?[0-9]+(\.[0-9]+)?$"
SOURCE_ID = r"^(TRX|PRD|K|V)-[A-Za-z0-9]+$"     # gold transaction/product ids, or K-/V- from nick_of_time.ids


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


def require_verification(state: str, verification_id: Optional[str], at: Optional[dt.datetime]) -> None:
    """Accepted ≠ verified (constitution #4): a "verified" action carries a V- id and the time it was read."""
    if state == "verified" and (verification_id is None or at is None):
        raise ValueError("a verified action needs a verification_id and the time it was verified")


# ---------- customer receipt (§6.7) ----------
class ReceiptFact(_Contract):
    fact: str = Field(min_length=1)
    source_id: str = Field(pattern=SOURCE_ID)


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

    @model_validator(mode="after")
    def _verified_means_read(self) -> ReceiptAction:
        require_verification(self.state, self.verification_id, self.verified_at)
        return self


class ReceiptDeadline(_Contract):
    country: str
    product: str
    credit_deadline: Optional[dt.date] = None
    ruling_deadline: Optional[dt.date] = None
    deadline_source: str
    source_url: str = Field(pattern=r"^https://\S+$")
    verified_on: dt.date

    @model_validator(mode="after")
    def _has_a_date(self) -> ReceiptDeadline:
        if self.credit_deadline is None and self.ruling_deadline is None:
            raise ValueError("a deadline needs credit_deadline or ruling_deadline; use deadline: null otherwise")
        return self


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
    next_steps: list[str] = []                  # never null; empty by default
    case_url: Optional[str] = None


def sample_receipt() -> CustomerReceipt:
    """The fixture receipt kept in the schema's `examples` [simulated]; stubs and the echo graph return it (AC-04)."""
    return CustomerReceipt.model_validate(load_schema("customer_receipt.schema.json")["examples"][0])


# FR-01: a name defined in contracts/tools.py is re-exported, never re-declared here (classes and type aliases alike).
_CLASH = set(TOOL_NAMES) & _defined_names(Path(__file__))
if _CLASH:
    raise ImportError(f"nick_of_time.contracts re-declares names of contracts/tools.py: {sorted(_CLASH)}")
