"""Deterministic `fake` provider: scripted replies, no network. The only provider tests and CI use (CLAUDE.md)."""
from __future__ import annotations

import re
import time

from .base import DEFAULT_TOOL, LLMClient, LLMResult, ProviderUnavailable


class FakeClient(LLMClient):
    """`script` items, consumed in order: a str (text reply), a dict (tool input) or an Exception (raised).
    Every request is kept in `calls`. No script (an unconfigured deployment) raises ProviderUnavailable, so the graph
    degrades to S0; an explicit script that runs out raises AssertionError, so an under-scripted test fails loudly."""

    provider = "fake"

    def __init__(self, model: str = "fake", *, script: list | None = None, **kw) -> None:
        super().__init__(model, **kw)
        self.script, self.calls = (None if script is None else list(script)), []

    def _call(self, system, user, schema, tool_name, max_tokens, mode, temperature):
        self.calls.append({"system": system, "user": user, "schema": schema, "tool_name": tool_name,
                           "max_tokens": max_tokens, "mode": mode, "temperature": temperature})
        if self.script is None:
            raise ProviderUnavailable("FakeClient has no script (LLM_PROVIDER unset)")
        if not self.script:
            raise AssertionError("FakeClient script exhausted: the test scripted too few replies")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        text, tool = (item, None) if isinstance(item, str) else ("", item)
        return {"text": text, "tool_input": tool, "stop_reason": "tool_use" if tool else "end_turn",
                "tokens_in": len(system + user) // 4, "tokens_out": len(text or str(tool)) // 4}

    def stream(self, system, user, on_text, *, max_tokens=512) -> LLMResult:
        """A scripted str is handed over word by word (each piece keeps its trailing space or newline), as a provider's
        stream would; an Exception item is raised before any text."""
        t0 = time.perf_counter()
        raw = self._call(system, user, None, DEFAULT_TOOL, max_tokens, None, self.temperature)
        for piece in re.findall(r"\S+\s*|\s+", raw["text"]):
            on_text(piece)
        return self._result(raw, t0)
