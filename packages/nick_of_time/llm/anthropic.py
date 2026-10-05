"""`anthropic` provider: Anthropic API fallback (ADR 0009, spec 04 T7a). The key comes from ANTHROPIC_API_KEY (read by
the SDK; not in spec 01 section 6.9 yet).

The fallback is an operator switch (`LLM_PROVIDER=anthropic`). A runtime provider failure does not switch provider:
it raises `ProviderUnavailable` and the graph degrades to S0 (spec 04 section 5). `prices` must be the row of the
provider actually called: API prices differ from the Bedrock regional rows in eval/bench/prices.yaml.
"""
from __future__ import annotations

import re

from .base import LLMClient, ProviderUnavailable, classify_validation

# [assumption] short enough for spec 04 section 5 (degrade to S0, turn p95 <= 6 s): 2 attempts of at most 15 s
TIMEOUT_S, MAX_RETRIES = 15.0, 1
TOOL_CHOICES = {"tool": lambda name: {"type": "tool", "name": name}, "any": lambda name: {"type": "any"},
                "auto": lambda name: {"type": "auto"}}


_PREFIX = re.compile(r"^(?:[a-z]+\.)?anthropic\.")   # region or global inference-profile prefix, or bare `anthropic.`
_SUFFIX = re.compile(r"-v\d+:\d+$")


def api_model_id(bedrock_id: str) -> str:
    """[assumption] The API id is the Bedrock id without the inference-profile prefix and the `-vN:M` suffix.
    A non-Anthropic id has no API equivalent: ValueError (it would 404 and silently become S0)."""
    if not _PREFIX.match(bedrock_id):
        raise ValueError(f"not an Anthropic model id: {bedrock_id!r}")
    return _SUFFIX.sub("", _PREFIX.sub("", bedrock_id))


def provider_error(exc: BaseException) -> Exception | None:
    import anthropic
    if isinstance(exc, anthropic.BadRequestError):
        return classify_validation(str(exc))
    if isinstance(exc, anthropic.APIError):   # connection, timeout, auth, quota, throttling, 5xx
        return ProviderUnavailable(f"{type(exc).__name__}: {exc}"[:300])
    return None


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model: str, *, sdk_client=None, **kw) -> None:
        super().__init__(model, **kw)
        if sdk_client is None:
            import anthropic
            sdk_client = anthropic.Anthropic(
                timeout=self.read_timeout_s or TIMEOUT_S,
                max_retries=MAX_RETRIES if self.max_attempts is None else max(self.max_attempts - 1, 0))
        self._client = sdk_client

    def _call(self, system, user, schema, tool_name, max_tokens, mode, temperature):
        kw: dict = {"model": self.model, "system": system, "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": user}]}
        if temperature is not None:
            kw["temperature"] = temperature
        if schema:
            kw["tools"] = [{"name": tool_name, "description": "Record the output.", "input_schema": schema}]
            kw["tool_choice"] = TOOL_CHOICES[mode](tool_name)
        try:
            r = self._client.messages.create(**kw)
        except Exception as exc:
            mapped = provider_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        return {"text": "".join(b.text for b in r.content if b.type == "text"),
                "tool_input": next((b.input for b in r.content if b.type == "tool_use"), None),
                "stop_reason": r.stop_reason or "", "tokens_in": r.usage.input_tokens,
                "tokens_out": r.usage.output_tokens}
