"""Tool contracts. Permissions live HERE, not in the prompt.
Every tool receives session_id and resolves customer_id from the session; it never accepts customer_id from the text.
"""
from datetime import date
from typing import Literal, Optional, Protocol
from pydantic import BaseModel, Field


class ToolError(BaseModel):
    code: Literal["DENY", "NOT_FOUND", "SESSION_EXPIRED", "UNAVAILABLE"]
    policy_id: Optional[str] = None
    message: str


# ---------- search_transaction ----------
class SearchTransactionIn(BaseModel):
    session_id: str
    amount: Optional[float] = Field(None, description="amount in local currency; ±2% tolerance")
    currency: Optional[str] = None
    approx_date: Optional[date] = None
    window_days: int = 7
    merchant: Optional[str] = None


class Transaction(BaseModel):
    transaction_id: str
    product_id: str
    transaction_date: date
    amount: float
    currency: str
    amount_usd: float
    merchant: Optional[str]
    transaction_status: Literal["Approved", "Declined", "Pending", "Reversed"]
    fraud_score: Optional[float]      # 0-100 or None (20.6% of frauds)
    split: Literal["train", "dev", "heldout"]   # customer partition (gold_contract.md)


class SearchTransactionOut(BaseModel):
    candidates: list[Transaction]     # only from the session's customer_id (policy scope.only_own_products)


# ---------- get_fraud_score (swappable provider) ----------
class GetFraudScoreIn(BaseModel):
    session_id: str
    transaction_id: str


class GetFraudScoreOut(BaseModel):
    transaction_id: str
    score: Optional[float]            # 0-100 or None
    source: Literal["dataset", "rules", "model", "llm"]
    version: str                      # e.g. "gold-v1", "model-v0"
    features_used: Optional[dict] = None   # rules/model only; goes to the evidence


class ScoreProvider(Protocol):
    """Contract all four providers meet. The policy reads 'score'; the audit log keeps 'source' and 'version'."""
    def score(self, transaction: "Transaction") -> GetFraudScoreOut: ...


# ---------- block_card ----------
class BlockCardIn(BaseModel):
    session_id: str
    product_id: str
    idempotency_key: str
    reason: Literal["high_zone_dispute", "confirmed_dispute"]


class BlockCardOut(BaseModel):
    action_id: str
    accepted: bool                    # accepted != verified


# ---------- open_case ----------
class OpenCaseIn(BaseModel):
    session_id: str
    transaction_id: str
    dispute_type: Literal["unrecognized_charge", "wrongful_charge"]
    zone: Literal["high", "medium", "human"]
    idempotency_key: str


class OpenCaseOut(BaseModel):
    case_id: str
    country: str
    credit_deadline: Optional[date]   # per the country's and product's regulatory_clock
    ruling_deadline: Optional[date]
    deadline_source: str


# ---------- compute_deadline ----------
class ComputeDeadlineIn(BaseModel):
    session_id: str
    transaction_id: str


class ComputeDeadlineOut(BaseModel):
    country: str
    product: str
    credit_deadline: Optional[date]
    ruling_deadline: Optional[date]
    deadline_source: str


# ---------- notify_customer (swappable provider: log | telegram | email) ----------
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


# ---------- verification (post-conditions) ----------
class ProductStatusOut(BaseModel):    # get_product_status
    product_id: str
    product_status: Literal["Active", "Blocked", "Closed", "Suspended"]
    checked_at: str


class CaseStatusOut(BaseModel):       # get_case_status
    case_id: str
    case_status: Literal["Open", "In review", "Closed"]
    checked_at: str


# Usage contract (the orchestrator follows it, the harness checks it):
# 1. block_card -> get_product_status == "Blocked" before telling the customer "blocked".
# 2. open_case  -> get_case_status == "Open"       before giving out the case_id.
# 3. Any ToolError DENY is logged with policy_id and ends in a handoff or an explicit refusal.
# 4. The zone is ALWAYS computed from get_fraud_score(); never from a number in the customer's text.
#    If source == 'llm', the policy forces the human zone (scoring.providers.llm).
# 5. No case is closed without a person: close_case is an AnalystAction, never a customer tool.
# 6. Every DENY cites the guardrail id (policies.yaml: guardrails[].id) and is recorded in policy_denials.
