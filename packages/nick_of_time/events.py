"""Live stream events of a run (spec 01 §6.4.1, contract 1.8.0, ADR 0030): `tool` and `text` chunks of LangGraph's
`custom` stream, next to the unchanged `ProgressItem`. The graph builds them (spec 04 AC-37, AC-38); the api forwards
them through the projection that hides score, zone thresholds and policy ids (spec 01 AC-09).

Cards are built from tool results and nothing else; `verdict.headline`, `title` and `summary` are `messages.yaml`
text, never engine output or LLM text.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nick_of_time.contracts import PATTERN, ActionState

TOOL_STEPS = ("search_transaction", "list_recent_transactions", "evaluate_policy", "block_card", "open_case",
              "get_case", "compute_deadline", "request_call", "get_case_status")


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChargeCard(_Event):
    type: Literal["charge"] = "charge"
    transaction_id: str
    date: str
    amount: float
    currency: str
    merchant: Optional[str]
    last4: Optional[str] = None       # [assumption] null for a candidate whose card was not read this turn
    synthetic: bool = False


class VerdictCard(_Event):
    type: Literal["verdict"] = "verdict"
    headline: str
    actions: list[str] = []


class ActionCard(_Event):
    type: Literal["action"] = "action"
    tool: str
    state: ActionState
    verification_id: Optional[str] = Field(None, pattern=PATTERN["verification"])

    @model_validator(mode="after")
    def _verified_only_with_its_id(self) -> ActionCard:
        if (self.state == "verified") != bool(self.verification_id):
            raise ValueError("an action card is verified exactly when it carries a V- id (constitution #4)")
        return self


class DeadlineCard(_Event):
    type: Literal["deadline"] = "deadline"
    kind: Literal["credit", "ruling"]
    date: Optional[str]
    source_label: str
    source_url: Optional[str] = None


class CaseCard(_Event):
    type: Literal["case"] = "case"
    case_id: str = Field(pattern=PATTERN["case"])
    status: str


Card = Annotated[Union[ChargeCard, VerdictCard, ActionCard, DeadlineCard, CaseCard], Field(discriminator="type")]


class ToolEvent(_Event):
    kind: Literal["tool"] = "tool"
    id: str
    step: Literal[TOOL_STEPS]
    title: str
    status: Literal["running", "done", "failed"]
    summary: Optional[str] = None
    cards: list[Card] = []
    at: AwareDatetime

    @model_validator(mode="after")
    def _cards_only_on_done(self) -> ToolEvent:
        if self.cards and self.status != "done":
            raise ValueError("cards travel on `done` only (spec 01 §6.4.1)")
        return self


class TextChunk(_Event):
    kind: Literal["text"] = "text"
    message_id: str
    delta: str
