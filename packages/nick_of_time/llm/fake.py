"""Deterministic `fake` provider: scripted replies, no network. The only provider tests and CI use (CLAUDE.md)."""
from __future__ import annotations

from .base import LLMClient, ProviderUnavailable


class FakeClient(LLMClient):
    """`script` items, consumed in order: a str (text reply), a dict (tool input) or an Exception (raised).
    Every request is kept in `calls`. No script (an unconfigured deployment) raises ProviderUnavailable, so the graph
    degrades to S0; an explicit script that runs out raises AssertionError, so an under-scripted test fails loudly."""

    provider = "fake"

    def __init__(self, model: str = "fake", *, script: list | None = None, **kw) -> None:
        super().__init__(model, **kw)
        self.script, self.calls = (None if script is None else list(script)), []

    def _transcribe(self, audio, fmt, prompt, max_tokens, temperature):
        """A scripted str is the transcript; the clip's size is recorded, never its bytes (D-072)."""
        self.calls.append({"audio_bytes": len(audio), "format": fmt, "user": prompt, "max_tokens": max_tokens})
        raw = self._next(prompt)
        return {**raw, "tokens_in": len(audio) // 100 + len(prompt) // 4}

    def _call(self, system, user, schema, tool_name, max_tokens, mode, temperature):
        self.calls.append({"system": system, "user": user, "schema": schema, "tool_name": tool_name,
                           "max_tokens": max_tokens, "mode": mode, "temperature": temperature})
        return self._next(system + user)

    def _next(self, sent: str) -> dict:
        if self.script is None:
            raise ProviderUnavailable("FakeClient has no script (LLM_PROVIDER unset)")
        if not self.script:
            raise AssertionError("FakeClient script exhausted: the test scripted too few replies")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        text, tool = (item, None) if isinstance(item, str) else ("", item)
        return {"text": text, "tool_input": tool, "stop_reason": "tool_use" if tool else "end_turn",
                "tokens_in": len(sent) // 4, "tokens_out": len(text or str(tool)) // 4}
