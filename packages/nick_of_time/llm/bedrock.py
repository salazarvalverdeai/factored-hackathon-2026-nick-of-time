"""`bedrock` provider: boto3 Converse in us-east-2 (ADR 0008/0009). Credentials only from the environment."""
from __future__ import annotations

import time

from .base import DEFAULT_TOOL, TOOL_DESCRIPTION, LLMClient, LLMResult, ProviderUnavailable, classify_validation

REGION = "us-east-2"
# [assumption] short enough for spec 04 section 5 (degrade to S0, turn p95 <= 6 s): 2 attempts of at most 15 s.
# botocore `total_max_attempts` counts the first try; its `max_attempts` counts retries (2 would mean 3 attempts).
CONNECT_TIMEOUT_S, READ_TIMEOUT_S, MAX_ATTEMPTS = 2, 15, 2
TOOL_CHOICES = {"tool": lambda name: {"tool": {"name": name}}, "any": lambda name: {"any": {}},
                "auto": lambda name: {"auto": {}}}


def provider_error(exc: BaseException) -> Exception | None:
    """Mapped provider error, or None when the request itself is malformed (ParamValidationError, a schema error)."""
    from botocore.exceptions import BotoCoreError, ClientError, ParamValidationError
    if isinstance(exc, ClientError):
        err = exc.response.get("Error", {})
        if err.get("Code") != "ValidationException":
            return ProviderUnavailable(f"{err.get('Code', '')}: {err.get('Message', '')}"[:300])   # may carry IAM ARNs
        return classify_validation(err.get("Message", ""))
    if isinstance(exc, BotoCoreError) and not isinstance(exc, ParamValidationError):
        return ProviderUnavailable(f"{type(exc).__name__}: {exc}"[:300])
    return None


class BedrockClient(LLMClient):
    provider = "bedrock"

    def __init__(self, model: str, *, boto_client=None, region: str = REGION, **kw) -> None:
        super().__init__(model, **kw)
        if boto_client is None:
            import boto3
            from botocore.config import Config
            boto_client = boto3.client("bedrock-runtime", region_name=region, config=Config(
                connect_timeout=CONNECT_TIMEOUT_S, read_timeout=READ_TIMEOUT_S if self.read_timeout_s is None else self.read_timeout_s,
                retries={"total_max_attempts": MAX_ATTEMPTS if self.max_attempts is None else self.max_attempts, "mode": "standard"}))
        self._client = boto_client

    def request(self, system, user, schema, tool_name, max_tokens, mode, temperature) -> dict:
        cfg: dict = {"maxTokens": max_tokens}
        if temperature is not None:
            cfg["temperature"] = temperature
        req = {"modelId": self.model, "system": [{"text": system}],
               "messages": [{"role": "user", "content": [{"text": user}]}], "inferenceConfig": cfg}
        if schema:
            req["toolConfig"] = {"tools": [{"toolSpec": {"name": tool_name, "description": TOOL_DESCRIPTION,
                                                         "inputSchema": {"json": schema}}}],
                                 "toolChoice": TOOL_CHOICES[mode](tool_name)}
        return req

    def _call(self, system, user, schema, tool_name, max_tokens, mode, temperature):
        return self._converse(self.request(system, user, schema, tool_name, max_tokens, mode, temperature))

    def _transcribe(self, audio, fmt, prompt, max_tokens, temperature):
        """Voxtral speech to text (D-072): Converse with an `audio` content block (format + raw bytes) and the
        instruction as text. Shape checked on 2026-10-05 against the Converse API reference
        (https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_AudioBlock.html) and the model card
        (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-mistral-ai-voxtral-mini-3b-2507.html:
        Converse and Invoke, speech input, in-region us-east-2 only)."""
        cfg: dict = {"maxTokens": max_tokens}
        if temperature is not None:
            cfg["temperature"] = temperature
        content = [{"audio": {"format": fmt, "source": {"bytes": audio}}}, {"text": prompt}]
        return self._converse({"modelId": self.model, "messages": [{"role": "user", "content": content}],
                               "inferenceConfig": cfg})

    def _converse(self, req: dict) -> dict:
        try:
            r = self._client.converse(**req)
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

    def stream(self, system, user, on_text, *, max_tokens=512) -> LLMResult:
        """ConverseStream: each text delta goes to `on_text` as it arrives; usage comes in the closing metadata."""
        t0, text, stop, usage = time.perf_counter(), [], "", {}
        try:
            r = self._client.converse_stream(**self.request(system, user, None, DEFAULT_TOOL, max_tokens, None,
                                                            self.temperature))
            for event in r["stream"]:
                delta = (event.get("contentBlockDelta") or {}).get("delta", {}).get("text")
                if delta:
                    text.append(delta)
                    on_text(delta)
                stop = (event.get("messageStop") or {}).get("stopReason", stop)
                usage = (event.get("metadata") or {}).get("usage", usage)
        except Exception as exc:
            mapped = provider_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        return self._result({"text": "".join(text), "stop_reason": stop, "tokens_in": usage.get("inputTokens", 0),
                             "tokens_out": usage.get("outputTokens", 0)}, t0)
