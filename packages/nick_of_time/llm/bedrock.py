"""`bedrock` provider: boto3 Converse in us-east-2 (ADR 0008/0009). Credentials only from the environment."""
from __future__ import annotations

from .base import LLMClient, ProviderUnavailable, classify_validation

REGION = "us-east-2"
TOOL_CHOICES = {"tool": lambda name: {"tool": {"name": name}}, "any": lambda name: {"any": {}},
                "auto": lambda name: {"auto": {}}}


def provider_error(exc: BaseException) -> Exception | None:
    """Mapped provider error, or None when the request itself is malformed (ParamValidationError, a schema error)."""
    from botocore.exceptions import BotoCoreError, ClientError, ParamValidationError
    if isinstance(exc, ClientError):
        err = exc.response.get("Error", {})
        if err.get("Code") != "ValidationException":
            return ProviderUnavailable(f"{err.get('Code', '')}: {err.get('Message', '')}")
        return classify_validation(err.get("Message", ""))
    if isinstance(exc, BotoCoreError) and not isinstance(exc, ParamValidationError):
        return ProviderUnavailable(f"{type(exc).__name__}: {exc}")
    return None


class BedrockClient(LLMClient):
    provider = "bedrock"

    def __init__(self, model: str, *, boto_client=None, region: str = REGION, **kw) -> None:
        super().__init__(model, **kw)
        if boto_client is None:
            import boto3
            boto_client = boto3.client("bedrock-runtime", region_name=region)
        self._client = boto_client

    def request(self, system, user, schema, tool_name, max_tokens, mode, temperature) -> dict:
        cfg: dict = {"maxTokens": max_tokens}
        if temperature is not None:
            cfg["temperature"] = temperature
        req = {"modelId": self.model, "system": [{"text": system}],
               "messages": [{"role": "user", "content": [{"text": user}]}], "inferenceConfig": cfg}
        if schema:
            req["toolConfig"] = {"tools": [{"toolSpec": {"name": tool_name, "description": "Record the output.",
                                                         "inputSchema": {"json": schema}}}],
                                 "toolChoice": TOOL_CHOICES[mode](tool_name)}
        return req

    def _call(self, system, user, schema, tool_name, max_tokens, mode, temperature):
        try:
            r = self._client.converse(**self.request(system, user, schema, tool_name, max_tokens, mode, temperature))
        except Exception as exc:
            mapped = provider_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        blocks = r["output"]["message"]["content"]
        usage = r.get("usage", {})
        return {"text": "".join(b.get("text", "") for b in blocks),
                "tool_input": next((b["toolUse"]["input"] for b in blocks if "toolUse" in b), None),
                "stop_reason": r.get("stopReason", ""), "tokens_in": usage.get("inputTokens", 0),
                "tokens_out": usage.get("outputTokens", 0)}
