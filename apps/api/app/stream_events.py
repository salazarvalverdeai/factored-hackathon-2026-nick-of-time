"""Spec 01 §6.4.1 / AC-09: the only shapes of the graph's custom stream that may reach a browser.

The graph writes `tool` and `text` chunks to LangGraph's `custom` stream; the api re-emits them only when they validate
against the shared models of `nick_of_time.events` (the one definition the graph builds them with), which forbid any
field they do not declare, so a chunk carrying a score, a zone threshold, a raw tool payload or a prompt is dropped
whole. On top of the shape, no customer string may hold internal vocabulary (a policy or guardrail id, the bank's
score) nor run past a bound, so a leak inside an allowed field is dropped too."""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import ValidationError

from nick_of_time.events import TextChunk, ToolEvent

_INTERNAL = re.compile(r"\bPOL-[A-Z0-9-]+|\bG-[A-Z]{3}-\d+|\bfraud_score\b", re.I)
_MAX_TEXT = 4000                    # [assumption] no customer string of a stream event is longer; a prompt would be
_MODELS = {"tool": ToolEvent, "text": TextChunk}


def _clean(value: Any) -> bool:
    """No internal vocabulary (policy or guardrail id, the bank's score) and no runaway text in any customer string."""
    if isinstance(value, str):
        return len(value) <= _MAX_TEXT and not _INTERNAL.search(value)
    if isinstance(value, dict):
        return all(_clean(v) for v in value.values())
    if isinstance(value, list):
        return all(_clean(v) for v in value)
    return True


def project(data: Any) -> Optional[tuple[str, dict]]:
    """`(sse_event, body)` for a custom chunk of kind `tool` or `text`, the body being the chunk less its `kind` (the SSE
    event name carries it), else None (dropped, never failing the turn)."""
    if not isinstance(data, dict):
        return None
    model = _MODELS.get(data.get("kind"))
    if model is None:
        return None
    try:
        body = model.model_validate(data).model_dump(mode="json", exclude={"kind"})
    except ValidationError:
        return None
    return (data["kind"], body) if _clean(body) else None
