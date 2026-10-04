"""Deterministic `fake` provider: scripted replies, no network. The only provider tests and CI use (CLAUDE.md)."""
from __future__ import annotations

from .base import LLMClient, ProviderUnavailable


class FakeClient(LLMClient):
    """`script` items, consumed in order: a str (text reply), a dict (tool input) or an Exception (raised).
    Every request is kept in `calls`. An empty script raises ProviderUnavailable (the graph degrades to S0, like an unconfigured provider)."""

    provider = "fake"

    def __init__(self, model: str = "fake", *, script: list | None = None, **kw) -> None:
        super().__init__(model, **kw)
        self.script, self.calls = list(script or []), []

    def _call(self, system, user, schema, tool_name, max_tokens, mode, temperature):
        self.calls.append({"system": system, "user": user, "schema": schema, "tool_name": tool_name,
                           "max_tokens": max_tokens, "mode": mode, "temperature": temperature})
        if not self.script:
            raise ProviderUnavailable("FakeClient script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        text, tool = (item, None) if isinstance(item, str) else ("", item)
        return {"text": text, "tool_input": tool, "stop_reason": "tool_use" if tool else "end_turn",
                "tokens_in": len(system + user) // 4, "tokens_out": len(text or str(tool)) // 4}
