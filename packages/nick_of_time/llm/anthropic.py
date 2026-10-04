"""`anthropic` provider: Anthropic API fallback (ADR 0009). The key comes from ANTHROPIC_API_KEY, read by the SDK."""
from __future__ import annotations

from .base import LLMClient, ProviderUnavailable, classify_validation

TOOL_CHOICES = {"tool": lambda name: {"type": "tool", "name": name}, "any": lambda name: {"type": "any"},
                "auto": lambda name: {"type": "auto"}}


def api_model_id(bedrock_id: str) -> str:
    """[assumption] The API id is the Bedrock id without the `us.anthropic.` prefix and the `-v1:0` suffix."""
    return bedrock_id.removeprefix("us.anthropic.").removesuffix("-v1:0")


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
            sdk_client = anthropic.Anthropic()
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
