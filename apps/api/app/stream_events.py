"""Spec 01 §6.4.1 / AC-09: the only shapes of the graph's custom stream that may reach a browser.

The graph writes `tool` and `text` chunks to LangGraph's `custom` stream; the api re-emits them through these models
and nothing else. Every model ignores unknown fields on input and serializes only the fields it declares, so a score,
a zone threshold, a policy id, a raw tool payload or a prompt that a chunk happens to carry never leaves the api."""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictStr, ValidationError, model_validator

from nick_of_time.contracts import ActionState
from nick_of_time.ids import PATTERN

Step = Literal["search_transaction", "list_recent_transactions", "evaluate_policy", "block_card", "open_case",
               "get_case", "compute_deadline", "request_call", "get_case_status"]
_INTERNAL = re.compile(r"\bPOL-[A-Z0-9-]+|\bG-[A-Z]{3}-\d+|\bfraud_score\b", re.I)


class _Shape(BaseModel):
    model_config = ConfigDict(extra="ignore", str_max_length=2000)


class ChargeCard(_Shape):
    type: Literal["charge"]
    transaction_id: StrictStr
    date: StrictStr
    amount: float
    currency: StrictStr
    merchant: Optional[StrictStr] = None
    last4: StrictStr
    synthetic: StrictBool = False


class VerdictCard(_Shape):
    type: Literal["verdict"]
    headline: StrictStr
    actions: list[StrictStr] = []


class ActionCard(_Shape):
    type: Literal["action"]
    tool: StrictStr
    state: ActionState
    verification_id: Optional[str] = Field(None, pattern=PATTERN["verification"])

    @model_validator(mode="after")
    def _verified_means_v_id(self) -> "ActionCard":
        if self.state == "verified" and self.verification_id is None:    # constitution #4
            raise ValueError("verified needs a V- id")
        return self


class DeadlineCard(_Shape):
    type: Literal["deadline"]
    kind: StrictStr
    date: Optional[StrictStr] = None
    source_label: StrictStr
    source_url: Optional[StrictStr] = None


class CaseCard(_Shape):
    type: Literal["case"]
    case_id: StrictStr
    status: StrictStr


Card = Annotated[Union[ChargeCard, VerdictCard, ActionCard, DeadlineCard, CaseCard], Field(discriminator="type")]


class ToolEvent(_Shape):
    id: StrictStr = Field(min_length=1, max_length=80)
    step: Step
    title: StrictStr
    status: Literal["running", "done", "failed"]
    summary: Optional[StrictStr] = None
    cards: list[Card] = []
    at: AwareDatetime

    @model_validator(mode="after")
    def _cards_on_done_only(self) -> "ToolEvent":
        if self.cards and self.status != "done":
            raise ValueError("cards only on done")
        return self


class TextChunk(_Shape):
    message_id: StrictStr = Field(min_length=1, max_length=80)
    delta: StrictStr = Field(max_length=4000)


def _clean(value: Any) -> bool:
    """No internal vocabulary (policy or guardrail id, the bank's score) in any customer string."""
    if isinstance(value, str):
        return not _INTERNAL.search(value)
    if isinstance(value, dict):
        return all(_clean(v) for v in value.values())
    if isinstance(value, list):
        return all(_clean(v) for v in value)
    return True


def project(data: Any) -> Optional[tuple[str, dict]]:
    """`(sse_event, body)` for a custom chunk of kind `tool` or `text`, else None (dropped, never failing the turn)."""
    if not isinstance(data, dict):
        return None
    model = {"tool": ToolEvent, "text": TextChunk}.get(data.get("kind"))
    if model is None:
        return None
    try:
        body = model.model_validate({k: v for k, v in data.items() if k != "kind"}).model_dump(mode="json")
    except ValidationError:
        return None
    return (data["kind"], body) if _clean(body) else None
