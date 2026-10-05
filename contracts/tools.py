"""Tool contracts v1.1 (spec 01 §6.3, contract 1.4.0; spec 03 §6). Permissions live HERE, not in the prompt.

Each of the 16 customer tools has `<Name>In` / `<Name>Out` models, listed in `CUSTOMER_TOOLS` in the order of
`policies.yaml` `actors.customer.tools`. Every input carries `session_id` and never `customer_id`: the server resolves
the customer from the session row (constitution #3), and inputs forbid unknown fields. Accepted ≠ verified
(constitution #4): a write answers `state: "requested"` at most and carries no `V-` id; only its read tool in
`VERIFIED_WITH`, called with the write's `action_id`, mints a `verification_id` with `read_at`, which the store
persists (D-025 `[assumption]`, task 01c).
Every tool answers `ToolError` instead of raising.
"""
from datetime import date
from typing import Literal, Optional, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nick_of_time.ids import GOLD_PATTERN, PATTERN

_HTTPS = r"^https://\S+$"
_COUNTRY = r"^[A-Z]{2}$"
_CURRENCY = r"^[A-Z]{3}$"
_DECIMAL = r"^-?[0-9]+(\.[0-9]+)?$"
_CASE = PATTERN["case"]
_TRX, _PRD = GOLD_PATTERN["transaction"], GOLD_PATTERN["product"]   # gold ids, unchanged
_Queue = Literal["new", "verification", "review", "resolved", "closed"]      # policies.yaml case_queue.states
_Channel = Literal["telegram", "email"]                                       # channels the customer confirms


class ToolError(BaseModel):
    code: Literal["DENY", "NOT_FOUND", "SESSION_EXPIRED", "UNAVAILABLE"]
    policy_id: Optional[str] = None
    message: str


# A write only reports that it asked; "verified" comes from its read tool (VERIFIED_WITH), never from the write.
WriteState = Literal["requested"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _In(_Model):
    session_id: str = Field(pattern=PATTERN["session"])   # the customer comes from this session row only


class _WriteIn(_In):
    idempotency_key: str = Field(min_length=1)   # {key} of policies.yaml reliability.idempotency_key (1.4.0)


class _WriteOut(_Model):
    action_id: str = Field(pattern=PATTERN["action"])
    state: WriteState = "requested"


class _Reading(_Model):               # a post-condition read: what TurnResult.actions[] needs to say "verified"
    # D-025 [assumption]: called with a write's action_id, the read returns it with a V- only when that write's
    # post-condition holds (minted by this read, persisted by the store as action_verified); otherwise, and for a
    # plain status read, both are None and only read_at is set.
    action_id: Optional[str] = Field(None, pattern=PATTERN["action"])
    verification_id: Optional[str] = Field(None, pattern=PATTERN["verification"])
    read_at: AwareDatetime

    @model_validator(mode="after")
    def _a_verification_names_its_action(self):
        if (self.action_id is None) != (self.verification_id is None):
            raise ValueError("action_id and verification_id come both or neither (D-025)")
        return self


class _VerifyingIn(_In):              # the read tools of VERIFIED_WITH
    action_id: Optional[str] = Field(None, pattern=PATTERN["action"])   # the write whose post-condition is read


class _Deadlines(_Model):             # stored with the case, never recomputed (spec 03 AC-16)
    credit_deadline: Optional[date] = None
    ruling_deadline: Optional[date] = None
    deadline_source: Optional[str] = None
    deadline_source_url: Optional[str] = Field(None, pattern=_HTTPS)
    deadline_verified_on: Optional[date] = None   # [assumption] D-014

    @model_validator(mode="after")
    def _a_date_has_its_source(self):
        if (self.credit_deadline or self.ruling_deadline) and not (
                self.deadline_source and self.deadline_source_url and self.deadline_verified_on):
            raise ValueError("a legal deadline travels with its source, https URL and verified_on (ADR 0019, D-014)")
        return self


# ---------- get_customer_profile (R) ----------
class GetCustomerProfileIn(_In):
    pass


class ConfirmedChannel(_Model):
    channel: _Channel
    masked_address: str


class GetCustomerProfileOut(_Model):
    first_name: str                   # first name only; no document, e-mail, phone or address (spec 03 AC-11)
    language: Literal["es", "pt"]
    country: str = Field(pattern=_COUNTRY)
    display_currency: str = Field(pattern=_CURRENCY)
    channels: list[ConfirmedChannel] = []


# ---------- search_transaction (R) ----------
class SearchTransactionIn(_In):
    amount: Optional[float] = Field(None, allow_inf_nan=False, description="amount in local currency; ±2% tolerance")
    currency: Optional[str] = Field(None, pattern=_CURRENCY)
    approx_date: Optional[date] = None
    window_days: int = Field(7, ge=0, le=30)
    merchant: Optional[str] = Field(None, max_length=100)


class Transaction(_Model):
    # No fraud_score or split (D-026 [assumption]): the zone comes only from get_fraud_score; the score is never sent.
    transaction_id: str = Field(pattern=_TRX)
    product_id: str = Field(pattern=_PRD)
    transaction_date: date
    amount: float
    currency: str = Field(pattern=_CURRENCY)
    amount_usd: float
    merchant: Optional[str]
    transaction_status: Literal["Approved", "Declined", "Pending", "Reversed"]
    synthetic: bool = False           # true only for live-mode demo_transactions (spec 01 AC-08)


class SearchTransactionOut(_Model):
    candidates: list[Transaction] = Field(max_length=4)   # only the session customer's (scope.only_own_products)


# ---------- get_fraud_score (R, swappable provider) ----------
class GetFraudScoreIn(_In):
    transaction_id: str = Field(pattern=_TRX)


class GetFraudScoreOut(_Model):
    transaction_id: str = Field(pattern=_TRX)
    score: Optional[float] = Field(ge=0, le=100, allow_inf_nan=False)   # 0-100 or None (required, nullable)
    source: Literal["dataset", "rules", "model", "llm", "synthetic"]   # synthetic: live-mode demo transactions (ADR 0020)
    version: str                      # e.g. "gold-v1", "model-v0"
    features_used: Optional[dict] = None   # rules/model only; goes to the evidence


class ScoreProvider(Protocol):
    """Contract the swappable providers meet (dataset, rules, model, llm); 'synthetic' is the score stored with a
    live-mode demo transaction. The policy reads 'score'; the audit log keeps 'source' and 'version'."""
    def score(self, transaction: "Transaction") -> GetFraudScoreOut: ...


# ---------- compute_deadline (R) ----------
class ComputeDeadlineIn(_In):
    transaction_id: str = Field(pattern=_TRX)


class ComputeDeadlineOut(_Model):
    country: str = Field(pattern=_COUNTRY)
    product: Literal["debit", "credit"]
    credit_deadline: Optional[date]   # per the country's and product's regulatory_clock
    ruling_deadline: Optional[date]
    deadline_source: str
    source_url: str = Field(pattern=_HTTPS)
    verified_on: date


# ---------- open_case (W) ----------
class OpenCaseIn(_WriteIn):
    transaction_id: str = Field(pattern=_TRX)
    dispute_type: Literal["unrecognized_charge", "wrongful_charge"]
    zone: Literal["high", "medium", "human"]
    related_case_id: Optional[str] = Field(None, pattern=_CASE)


class OpenCaseOut(_WriteOut, _Deadlines):
    case_id: str = Field(pattern=_CASE)
    country: str = Field(pattern=_COUNTRY)
    # AC-15: for an active case of the same transaction nothing is written; the result is that case, with
    # duplicate_of = its case_id and the action_id of the open_case call that created it.
    duplicate_of: Optional[str] = Field(None, pattern=_CASE)
    related_case_id: Optional[str] = Field(None, pattern=_CASE)


# ---------- block_card (W) ----------
class BlockCardIn(_WriteIn):
    product_id: str = Field(pattern=_PRD)
    reason: Literal["high_zone_dispute", "confirmed_dispute"]


class BlockCardOut(_WriteOut):
    product_id: str = Field(pattern=_PRD)


# ---------- get_product_status / list_my_cards (R) ----------
class GetProductStatusIn(_VerifyingIn):
    product_id: str = Field(pattern=_PRD)


class Card(_Reading):
    product_id: str = Field(pattern=_PRD)
    type: Literal["debit", "credit"]
    last4: str = Field(pattern=r"^[0-9]{4}$")
    status: Literal["Active", "Blocked", "Closed", "Suspended"]   # latest override of the run, else gold


class GetProductStatusOut(Card):
    pass


class ListMyCardsIn(_In):
    pass


class ListMyCardsOut(_Model):
    cards: list[Card]                 # plain status reads: list_my_cards verifies no write (D-025)
    read_at: AwareDatetime            # 1.4.0: the listing's own reading time, set even with no cards (spec 04 AC-19)

    @model_validator(mode="after")
    def _a_listing_verifies_nothing(self):
        if any(card.action_id or card.verification_id for card in self.cards):
            raise ValueError("list_my_cards verifies no write: its cards carry no action_id or V- (D-025)")
        return self


# ---------- get_case / list_my_cases (R) ----------
class GetCaseIn(_VerifyingIn):
    case_id: str = Field(pattern=_CASE)


class CaseCharge(_Model):
    transaction_id: str = Field(pattern=_TRX)
    amount: float
    currency: str = Field(pattern=_CURRENCY)
    transaction_date: date
    merchant: Optional[str] = None
    synthetic: bool = False


class CaseEventItem(_Model):          # customer-visible case_events only
    event_id: str = Field(pattern=PATTERN["event"])
    type: str
    label: str
    created_at: AwareDatetime


class GetCaseOut(_Reading, _Deadlines):
    case_id: str = Field(pattern=_CASE)
    queue_status: _Queue
    status_label: str                 # customer-facing label from messages.yaml
    transaction: CaseCharge
    product_last4: Optional[str] = Field(None, pattern=r"^[0-9]{4}$")
    timeline: list[CaseEventItem] = []
    taken_by_person: bool = False
    related_case_id: Optional[str] = Field(None, pattern=_CASE)


class ListMyCasesIn(_In):
    pass


class MyCase(_Model):
    case_id: str = Field(pattern=_CASE)
    queue_status: _Queue
    status_label: str
    credit_deadline: Optional[date] = None
    ruling_deadline: Optional[date] = None
    product_last4: Optional[str] = Field(None, pattern=r"^[0-9]{4}$")
    related_case_id: Optional[str] = Field(None, pattern=_CASE)
    updated_at: AwareDatetime


class ListMyCasesOut(_Model):
    cases: list[MyCase]               # active first
    read_at: AwareDatetime


# ---------- add_case_info / request_call / request_reevaluation (W) ----------
class _CaseEventOut(_WriteOut):
    event_id: str = Field(pattern=PATTERN["event"])
    case_id: Optional[str] = Field(None, pattern=_CASE)


class AddCaseInfoIn(_WriteIn):
    case_id: str = Field(pattern=_CASE)
    text: str = Field(min_length=1, max_length=1000)   # PAN, CVV and passwords are rejected with G-IN-04


class AddCaseInfoOut(_CaseEventOut):
    pass


class RequestCallIn(_WriteIn):
    case_id: Optional[str] = Field(None, pattern=_CASE)   # None: a general request with no case (spec 04 `connect`);
    # it answers case_id None and stays "requested": no customer read verifies it (D-026, spec 03 §6)
    preferred_time: Optional[str] = None


class RequestCallOut(_CaseEventOut):
    # AC-18 [assumption] (D-025): a second request for a case with an open one writes nothing and returns the ORIGINAL
    # request's action_id, event_id and expected_contact_by, so its action_id stays verifiable by get_case.
    # D-008: the tool computes it from policies.yaml contact.callback_within_business_days counted from
    # clock.today(mode, country), stores it in the call_requested event and never recomputes it; None = no promise.
    expected_contact_by: Optional[date] = None


RequestCallResult = RequestCallOut    # [assumption] the name D-008 uses; same model


class RequestReevaluationIn(_WriteIn):
    case_id: str = Field(pattern=_CASE)
    reason: str = Field(min_length=1, max_length=1000)


class RequestReevaluationOut(_CaseEventOut):
    # AC-19 [assumption] (D-025): already_in_progress writes nothing and returns the ORIGINAL action_id and event_id of
    # the write that holds the case active (its open_case and case_opened, or the earlier request_reevaluation and
    # reevaluation_requested), so action_id stays required and verifiable by get_case.
    outcome: Literal["back_to_review", "related_case_opened", "already_in_progress"]   # spec 03 AC-19
    related_case_id: Optional[str] = Field(None, pattern=_CASE)


# ---------- convert_amount (R) ----------
class ConvertAmountIn(_In):
    amount: float = Field(allow_inf_nan=False)
    currency: str = Field(pattern=_CURRENCY)
    to_currency: Optional[str] = Field(None, pattern=_CURRENCY)   # None: the session's display currency


class ConvertedAmount(_Model):
    amount: str = Field(pattern=_DECIMAL)
    currency: str = Field(pattern=_CURRENCY)
    rate: str = Field(pattern=_DECIMAL)
    rate_source: str
    as_of: date


class ConvertAmountOut(_Model):
    converted: Optional[ConvertedAmount]   # None when no verified rate exists (ADR 0019)


# ---------- send_case_summary (N) / list_my_notifications (R) ----------
class SendCaseSummaryIn(_WriteIn):
    case_id: str = Field(pattern=_CASE)
    channel: _Channel                 # only a channel the customer confirmed (spec 03 AC-21)


class SendCaseSummaryOut(_WriteOut):
    notification_id: str = Field(pattern=PATTERN["notification"])
    channel: _Channel
    masked_address: str


class ListMyNotificationsIn(_VerifyingIn):
    case_id: Optional[str] = Field(None, pattern=_CASE)


class NotificationItem(_Model):
    notification_id: str = Field(pattern=PATTERN["notification"])
    case_id: str = Field(pattern=_CASE)
    event: str
    channel: Literal["log", "telegram", "email"]
    masked_address: Optional[str] = None
    text: str
    delivery_status: Literal["queued", "sent", "delivered", "bounced", "failed"]   # latest notification_deliveries row
    created_at: AwareDatetime


class ListMyNotificationsOut(_Reading):
    notifications: list[NotificationItem]


def _models(tool: str) -> tuple[type[BaseModel], type[BaseModel]]:
    stem = "".join(part.title() for part in tool.split("_"))
    return globals()[f"{stem}In"], globals()[f"{stem}Out"]


# Tool name → (input model, output model), in the order of spec 01 §6.3 and policies.yaml actors.customer.tools.
CUSTOMER_TOOLS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {tool: _models(tool) for tool in (
    "get_customer_profile", "search_transaction", "get_fraud_score", "compute_deadline", "open_case", "block_card",
    "get_product_status", "list_my_cards", "get_case", "list_my_cases", "add_case_info", "request_call",
    "request_reevaluation", "convert_amount", "send_case_summary", "list_my_notifications")}

# Write or notification tool → the read tool that verifies its post-condition (spec 01 §6.3 "Verified with").
VERIFIED_WITH: dict[str, str] = {
    "open_case": "get_case", "block_card": "get_product_status", "add_case_info": "get_case",
    "request_call": "get_case", "request_reevaluation": "get_case", "send_case_summary": "list_my_notifications"}


# ---------- api-side notifier (spec 13): automatic notification on each status change; not an MCP tool ----------
class NotifyCustomerIn(BaseModel):
    session_id: str
    case_id: str
    event: Literal["case_opened", "card_blocked", "in_review", "resolved"]


class NotifyCustomerOut(BaseModel):
    notification_id: str
    provider: Literal["log", "telegram", "email"]
    delivered: bool               # always True with 'log'; with telegram/email, whatever the provider reports


# ---------- ANALYST tools (console API only; the agent never sees them) ----------
class AnalystActionIn(BaseModel):
    case_id: str
    actor_id: str                     # analyst authenticated in the console
    action: Literal["take", "approve_credit", "approve_block", "unblock_card",
                    "request_customer_info", "mark_ambiguous", "resolve", "close_case", "reopen_case"]
    reason: Optional[str] = None      # required except for take and approve_*
    idempotency_key: str


class AnalystActionOut(BaseModel):
    event_id: str
    previous_status: str
    new_status: Literal["new", "verification", "review", "resolved", "closed"]
    notification_id: Optional[str]    # set when the status change triggers notify_customer


# Usage contract (the orchestrator follows it, the harness checks it):
# 1. block_card -> get_product_status status == "Blocked" before telling the customer "blocked".
# 2. open_case  -> get_case returns the case                before giving out the case_id.
# 3. Any ToolError DENY is logged with policy_id and ends in a handoff or an explicit refusal.
# 4. The zone is ALWAYS computed from get_fraud_score(); never from a number in the customer's text.
#    If source == 'llm', the policy forces the human zone (scoring.providers.llm).
# 5. No case is closed without a person: close_case is an AnalystAction, never a customer tool.
# 6. Every DENY cites the guardrail id (policies.yaml: guardrails[].id) and is recorded in policy_denials.
