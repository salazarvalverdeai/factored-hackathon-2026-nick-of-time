"""Contract models shared by api, mcp, agent and eval (spec 01 §6.4, §6.6–§6.8, FR-01).

Every public name defined in `contracts/tools.py` (source of truth, lead approves) is re-exported here unchanged,
whatever version is checked in. This module adds the shared vocabularies and the customer receipt (`CustomerReceipt`,
mirror of `contracts/customer_receipt.schema.json`), the graph output (`TurnResult`, customer projection
`CustomerTurn`), the evaluation `FinalState` and the api view models (`CaseView`, customer projection
`CustomerCaseView`). Optional fields serialize as null, which the schemas accept.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
from functools import cache
from pathlib import Path
from typing import Any, Literal, Optional

import jsonschema
import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts import tools as _tools
from nick_of_time.ids import GOLD_PATTERN, PATTERN


def _defined_names(path: Path) -> set[str]:
    """Public top-level names a module defines itself (classes, functions, assignments, type aliases)."""
    type_alias = getattr(ast, "TypeAlias", ())     # the `type X = …` statement exists from Python 3.12 only
    names: set[str] = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, type_alias):
            names.add(node.name.id)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {n for n in names if not n.startswith("_")}


# ---------- re-export of contracts/tools.py ----------
TOOL_NAMES: tuple[str, ...] = tuple(sorted(_defined_names(Path(_tools.__file__))))
globals().update({name: getattr(_tools, name) for name in TOOL_NAMES})

# FR-01: a name defined in contracts/tools.py is re-exported, never re-declared below (classes and type aliases alike).
# The scan reads this file's source, so it runs before anything else here can fail.
_CLASH = set(TOOL_NAMES) & _defined_names(Path(__file__))
if _CLASH:
    raise ImportError(f"nick_of_time.contracts re-declares names of contracts/tools.py: {sorted(_CLASH)}")

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
ProductType = Literal["debit", "credit"]                                         # policies.yaml regulatory_clock
DECIMAL = r"^-?[0-9]+(\.[0-9]+)?$"
HTTPS_URL = r"^https://\S+$"
# a gold transaction or product id, or a K-/V- id from nick_of_time.ids
SOURCE_ID = "^(" + "|".join(p.strip("^$") for p in (GOLD_PATTERN["transaction"], GOLD_PATTERN["product"],
                                                     PATTERN["case"], PATTERN["verification"])) + ")$"


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
    verified_at: Optional[AwareDatetime] = None

    @model_validator(mode="after")
    def _verified_means_read(self) -> ReceiptAction:
        require_verification(self.state, self.verification_id, self.verified_at)
        return self


class ReceiptDeadline(_Contract):
    country: str = Field(pattern=r"^[A-Z]{2}$")
    product: ProductType
    credit_deadline: Optional[dt.date] = None
    ruling_deadline: Optional[dt.date] = None
    deadline_source: str
    source_url: str = Field(pattern=HTTPS_URL)
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
    issued_at: AwareDatetime
    verified_facts: list[ReceiptFact]
    mode: Optional[Mode] = None
    product_last4: Optional[str] = Field(None, pattern=r"^[0-9]{4}$")
    amount: Optional[ReceiptAmount] = None
    actions: list[ReceiptAction]
    deadline: Optional[ReceiptDeadline]         # required; null when the country has no verified clock entry
    what_ai_did: str
    what_a_person_does: str
    next_steps: list[str] = []                  # never null; empty by default
    case_url: Optional[str] = Field(None, pattern=HTTPS_URL)


def sample_receipt() -> CustomerReceipt:
    """The fixture receipt kept in the schema's `examples` [simulated]; stubs and the echo graph return it (AC-04)."""
    return CustomerReceipt.model_validate(load_schema("customer_receipt.schema.json")["examples"][0])


# ---------- graph output (§6.4) ----------
LAST4 = r"^[0-9]{4}$"
# A path on our own host: URL-safe characters only, so "//", "/\" and tabs or newlines (browsers strip them) fail.
INTERNAL_HREF = r"^/([A-Za-z0-9._~%?#=&-][A-Za-z0-9._~%/?#=&-]*)?$"
MAX_OPTIONS: int = yaml.safe_load((CONTRACTS_DIR / "policies.yaml").read_text())["clarify"][
    "max_candidate_transactions"]


class TurnAction(_Contract):                    # a button or chip press; skips the classifier
    type: Literal["confirm", "choose_option", "verify_now", "request_call", "request_reevaluation", "send_summary"]
    value: Optional[str] = None


class Option(_Contract):
    id: str
    label: str


class ProgressItem(_Contract):
    step: str
    label: str
    state: ActionState
    at: AwareDatetime


class ActionRecord(_Contract):
    tool: str
    action_id: str = Field(pattern=PATTERN["action"])
    state: ActionState
    verification_id: Optional[str] = Field(None, pattern=PATTERN["verification"])
    read_at: Optional[AwareDatetime] = None

    @model_validator(mode="after")
    def _verified_means_read(self) -> ActionRecord:
        require_verification(self.state, self.verification_id, self.read_at)
        return self


class Suggestion(_Contract):
    id: str
    label: str
    kind: Literal["text", "action", "link"]
    action: Optional[TurnAction] = None
    href: Optional[str] = Field(None, pattern=INTERNAL_HREF)

    @model_validator(mode="after")
    def _payload_matches_kind(self) -> Suggestion:
        if (self.kind == "action") != (self.action is not None) or (self.kind == "link") != (self.href is not None):
            raise ValueError("an action chip carries `action`, a link chip carries `href`, a text chip neither")
        return self


class Denial(_Contract):
    policy_id: Optional[str] = None
    guardrail_id: Optional[str] = None
    detail: str


class CustomerDenial(_Contract):
    guardrail_id: Optional[str] = None
    detail: str


class Usage(_Contract):
    provider: str
    model: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class TraceStep(_Contract):
    node: str
    status: Literal["ok", "deny", "error"]
    ms: int = Field(ge=0)
    detail: Optional[str] = None


class _TurnCore(_Contract):                     # fields the customer may see
    reply: str
    language: Language
    decision: Optional[Decision] = None
    intent: Optional[Intent] = None
    intent_confidence: Optional[float] = Field(None, ge=0, le=1)
    options: list[Option] = Field(default_factory=list, max_length=MAX_OPTIONS)
    case_id: Optional[str] = Field(None, pattern=PATTERN["case"])
    plan: list[str] = []
    progress: list[ProgressItem] = []
    actions: list[ActionRecord] = []
    suggestions: list[Suggestion] = Field(min_length=2, max_length=3)   # spec 04 §4.5, AC-29
    receipt: Optional[CustomerReceipt] = None
    guardrails_triggered: list[str] = []
    mode: Mode
    trace_id: str

    @model_validator(mode="after")
    def _verified_progress_was_read(self) -> _TurnCore:
        """Constitution #4 for progress labels too: "verified" needs a verified action record of the same tool."""
        read = {a.tool for a in self.actions if a.state == "verified"}
        if any(p.state == "verified" and p.step not in read for p in self.progress):
            raise ValueError("a verified progress item needs a verified actions[] record with the same tool")
        return self


class CustomerTurn(_TurnCore):
    """What the browser receives (D-013): no handoff, zone, usage, trace or policy ids."""
    denials: list[CustomerDenial] = []


class TurnResult(_TurnCore):
    """The graph's full output; internal to api, agent and eval. Customers get `for_customer()`."""
    zone: Optional[Zone] = None
    handoff: Optional[dict[str, Any]] = None    # contracts/handoff.schema.json, checked below
    denials: list[Denial] = []
    usage: list[Usage] = []
    trace: list[TraceStep] = []

    @model_validator(mode="after")
    def _handoff_follows_its_schema(self) -> TurnResult:
        if self.handoff is not None:
            try:
                jsonschema.validate(self.handoff, load_schema("handoff.schema.json"))
            except jsonschema.ValidationError as err:
                raise ValueError(f"handoff: {err.message}") from None
        return self

    def for_customer(self) -> CustomerTurn:
        data = self.model_dump(include=set(CustomerTurn.model_fields) - {"denials"})
        return CustomerTurn(**data, denials=[CustomerDenial(guardrail_id=d.guardrail_id, detail=d.detail)
                                             for d in self.denials])


# ---------- evaluation (§6.8) ----------
class StatusReply(_Contract):
    subject: str
    stated_status: str
    read_status: str


class Cost(_Contract):
    latency_ms: int = Field(ge=0)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class TurnCost(Cost):
    turn: int = Field(ge=1)


class RunMeta(_Contract):
    git_sha: str
    platform_revision: Optional[str] = None
    policies_version: int
    provider: str
    model_graph: Optional[str] = None
    model_fast: Optional[str] = None
    prompt_hash: Optional[str] = None
    classifier_version: Optional[str] = None


class FinalState(_Contract):
    run_id: str                                 # "<eval case id>:<arm>:<k>"
    arm: str
    decision: Optional[Decision] = None
    zone: Optional[Zone] = None
    intent: Optional[Intent] = None
    transaction_id: Optional[str] = None
    product_id: Optional[str] = None
    candidate_transaction_ids: list[str] = []
    product_status: Optional[str] = None
    case_open: bool
    case_id: Optional[str] = Field(None, pattern=PATTERN["case"])
    queue_status: Optional[QueueStatus] = None
    handoff_emitted: bool
    receipt_issued: bool
    receipt_has_deadline: bool
    notifications: list[str] = []
    guardrail_ids: list[str] = []
    other_customer_data_exposed: bool
    mode: Literal["replay"] = "replay"          # the eval seed only creates replay sessions (AC-08, ADR 0020)
    action_states: dict[str, ActionState] = {}
    status_replies: list[StatusReply] = []
    turns: list[TurnCost] = []
    totals: Cost
    run_meta: RunMeta


# ---------- api view models (§6.6) ----------
class _CaseCore(_Contract):
    case_id: str = Field(pattern=PATTERN["case"])
    country: str
    queue_status: QueueStatus
    credit_deadline: Optional[dt.date] = None
    ruling_deadline: Optional[dt.date] = None
    created_at: AwareDatetime


class CaseSummary(_CaseCore):
    customer_id: str
    zone: Zone
    sla_due_at: Optional[AwareDatetime] = None
    priority: Literal["normal", "high"] = "normal"   # [assumption] raised by policies.yaml case_queue.deadline_sla
    tags: list[str] = []


class CaseTransaction(_Contract):
    transaction_id: str
    amount: float                               # [assumption] same type as contracts/tools.py Transaction.amount
    currency: str
    date: dt.date
    merchant: Optional[str] = None
    synthetic: bool = False                     # true only for live-mode demo_transactions


class TimelineItem(_Contract):
    event_id: str = Field(pattern=PATTERN["event"])
    type: str
    label: str
    created_at: AwareDatetime


class CaseChannels(_Contract):
    telegram: bool = False
    email: bool = False


class CaseNotification(_Contract):
    notification_id: str = Field(pattern=PATTERN["notification"])
    channel: Literal["log", "telegram", "email"]
    masked_address: Optional[str] = None
    delivery_status: Literal["queued", "sent", "delivered", "bounced", "failed"]
    created_at: AwareDatetime


class _CaseDetail(_CaseCore):
    transaction: CaseTransaction
    product_last4: Optional[str] = Field(None, pattern=LAST4)
    status_label: str
    taken_by_person: bool = False
    related_case_id: Optional[str] = Field(None, pattern=PATTERN["case"])
    mode: Mode
    receipt: Optional[CustomerReceipt] = None
    timeline: list[TimelineItem] = []           # customer-visible events only
    deadline_countdown_days: Optional[int] = None
    deadline_source: Optional[str] = None
    deadline_source_url: Optional[str] = Field(None, pattern=HTTPS_URL)
    deadline_verified_on: Optional[dt.date] = None   # [assumption] D-014: stored with the case's deadline
    channels: CaseChannels = Field(default_factory=CaseChannels)
    notifications: list[CaseNotification] = []

    @model_validator(mode="after")
    def _a_legal_date_has_its_source(self) -> _CaseDetail:
        if (self.credit_deadline or self.ruling_deadline) and not (self.deadline_source and self.deadline_source_url):
            raise ValueError("a legal deadline travels with deadline_source and deadline_source_url (ADR 0019)")
        return self


class CustomerCaseView(_CaseDetail):
    """What `GET /api/cases/{id}` returns (D-013): no zone, priority, tags, SLA or customer id."""


class CaseView(CaseSummary, _CaseDetail):
    """The analyst console's case; customers get `for_customer()`."""

    def for_customer(self) -> CustomerCaseView:
        return CustomerCaseView.model_validate(self.model_dump(include=set(CustomerCaseView.model_fields)))


class CustomerCaseSummary(_Contract):
    case_id: str = Field(pattern=PATTERN["case"])
    status_label: str
    credit_deadline: Optional[dt.date] = None
    ruling_deadline: Optional[dt.date] = None
    product_last4: Optional[str] = Field(None, pattern=LAST4)
    related_case_id: Optional[str] = Field(None, pattern=PATTERN["case"])
    updated_at: AwareDatetime


class ProductView(_Contract):
    product_id: str
    type: str
    last4: str = Field(pattern=LAST4)
    status: str
    verification_id: Optional[str] = Field(None, pattern=PATTERN["verification"])
    read_at: AwareDatetime
