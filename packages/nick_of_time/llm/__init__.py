"""Shared LLM client: `fake`, `bedrock`, `anthropic` behind one `complete()` (spec 04 T-LLM)."""
from __future__ import annotations

from .base import (LADDER, LLMClient, LLMResult, ProviderUnavailable, TemperatureUnsupported, ToolChoiceUnsupported,
                   cost_usd)
from .fake import FakeClient

__all__ = ["LADDER", "LLMClient", "LLMResult", "ProviderUnavailable", "TemperatureUnsupported",
           "ToolChoiceUnsupported", "FakeClient", "cost_usd", "make_client"]


def make_client(cfg, *, prices: dict | None = None, **kw) -> LLMClient:
    """Client for a `config.resolve(arm)` result; `prices` is the arm's {"input_per_1m", "output_per_1m"} row.
    Extra keywords (script=, boto_client=, sdk_client=) go to the provider class."""
    kw.setdefault("temperature", cfg.temperature)
    kw.setdefault("mode", cfg.tool_choice)
    if cfg.provider == "fake":
        return FakeClient(cfg.model or "fake", prices=prices, **kw)
    if cfg.provider == "bedrock":
        from .bedrock import BedrockClient
        return BedrockClient(cfg.model, prices=prices, **kw)
    if cfg.provider == "anthropic":
        from .anthropic import AnthropicClient, api_model_id
        return AnthropicClient(api_model_id(cfg.model), prices=prices, **kw)
    raise ValueError(f"arm {cfg.arm} has no LLM (provider {cfg.provider!r})")
