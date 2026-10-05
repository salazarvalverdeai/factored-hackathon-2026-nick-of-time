"""Structured-output smoke test (spec 15 AC-11): each LLM arm must return one valid object matching the intent
schema through Converse tool use (the same path B1 runs; decision D-011). toolChoice `tool` is documented only for
Anthropic Claude 3+ and Amazon Nova, so each arm walks the ladder tool -> any -> auto and records the mode B1 reuses."""
from __future__ import annotations

import re
import time
from typing import Callable

import jsonschema
from botocore.exceptions import ClientError

from eval.bench.core import (ProviderUnavailable, ToolChoiceUnsupported, check_budget, load_prices, projected_spend,
                             provider_error)
from nick_of_time.llm.base import TOOL_DESCRIPTION

# [assumption] PLACEHOLDER minimal intent schema until spec 11 delivers the real one (five intents, slots).
INTENT_SCHEMA = {
    "type": "object",
    "required": ["intent", "language"],
    "properties": {"intent": {"type": "string", "minLength": 1},
                   "language": {"enum": ["es", "pt"]}},
}
TOOL_NAME = "record_intent"
SYSTEM = "Classify the customer message by calling the record_intent tool. Do not answer in prose."
PROMPT = "No reconozco un cargo de 45 dólares en mi tarjeta."
MAX_TOKENS = 512
# Converse ToolChoice members, strongest first; the ladder steps down only when Bedrock rejects a mode.
TOOL_CHOICES = {"tool": {"tool": {"name": TOOL_NAME}}, "any": {"any": {}}, "auto": {"auto": {}}}
LADDER = tuple(TOOL_CHOICES)
# provider(model_id, system, user, schema, mode) -> {"tool_input": dict | None, "text": str, "stop_reason": str};
# raises ToolChoiceUnsupported (mode rejected) or ProviderUnavailable (arm unavailable). The result also carries
# "temperature" (0, or None when the model rejected it and the provider default was sent, D-016), "latency_ms" and
# "usage" (Converse token usage); smoke_arm copies them into its result via meta().
Provider = Callable[[str, str, str, dict, str], dict]


_TEMPERATURE_MSG = re.compile(r"temperature", re.I)


def temperature_rejected(exc: BaseException) -> bool:
    """True when Bedrock rejected the request because the model does not accept `temperature` (a
    ValidationException that names it)."""
    if not isinstance(exc, ClientError):  # timeouts and dropped connections carry no response
        return False
    err = (exc.response or {}).get("Error", {})
    return err.get("Code") == "ValidationException" and bool(_TEMPERATURE_MSG.search(err.get("Message", "")))


def converse_request(model_id: str, system: str, user: str, schema: dict, mode: str,
                     temperature: float | None = 0) -> dict:
    """The Converse request of the smoke test and of B1: one tool with the schema and the production tool description
    (`nick_of_time.llm.base.TOOL_DESCRIPTION`, D-011), the arm's toolChoice mode,
    MAX_TOKENS and temperature 0, or the provider default (no `temperature` key) when `temperature` is None
    (D-016, spec 15 section 4.1: 0 where the model accepts it, otherwise the provider default)."""
    inference = {"maxTokens": MAX_TOKENS} if temperature is None else {"temperature": temperature,
                                                                       "maxTokens": MAX_TOKENS}
    return {"modelId": model_id, "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": inference,
            "toolConfig": {"tools": [{"toolSpec": {"name": TOOL_NAME, "description": TOOL_DESCRIPTION,
                                                   "inputSchema": {"json": schema}}}],
                           "toolChoice": TOOL_CHOICES[mode]}}


def bedrock_provider(region: str = "us-east-2") -> Provider:
    """[assumption] replace with nick_of_time.llm when the task LLM lands. Errors are mapped by
    core.provider_error; a ValidationException that is not about tool use or the model id, and botocore's
    ParamValidationError, are bugs in our request and propagate."""
    import boto3
    client = boto3.client("bedrock-runtime", region_name=region)
    no_temperature: set[str] = set()  # models that rejected temperature: B1 sends them the provider default

    def call(model_id: str, system: str, user: str, schema: dict, mode: str) -> dict:
        temp = None if model_id in no_temperature else 0
        started = time.monotonic()
        try:
            try:
                r = client.converse(**converse_request(model_id, system, user, schema, mode, temp))
            except Exception as exc:
                if temp is None or not temperature_rejected(exc):
                    raise
                no_temperature.add(model_id)  # D-016: retry once without temperature, record it
                temp = None
                r = client.converse(**converse_request(model_id, system, user, schema, mode, None))
        except Exception as exc:
            mapped = provider_error(exc)
            if mapped is None or mapped is exc:
                raise
            raise mapped from exc
        blocks = r["output"]["message"]["content"]
        tool = next((b["toolUse"]["input"] for b in blocks if "toolUse" in b), None)
        return {"tool_input": tool, "text": "".join(b.get("text", "") for b in blocks),
                "stop_reason": r.get("stopReason", ""), "temperature": temp,
                "latency_ms": round((time.monotonic() - started) * 1000), "usage": r.get("usage", {})}
    return call


def meta(r: dict) -> dict:
    """Per-arm record of the temperature sent (0, None = provider default per D-016, or "unreported" when the
    provider omits it), latency and token usage."""
    return {"temperature": r.get("temperature", "unreported"), "latency_ms": r.get("latency_ms"),
            "usage": r.get("usage")}


def smoke_arm(model_id: str, provider: Provider, *, system: str = SYSTEM, user: str = PROMPT,
              schema: dict = INTENT_SCHEMA) -> dict:
    """Walk the ladder: a mode Bedrock rejects (ToolChoiceUnsupported) moves to the next one; the first accepted mode
    decides, and its tool input must match the schema. Every mode rejected means "no structured output". B1 passes
    its own system prompt and schema, so the smoke call is the B1 request (D-011)."""
    rejected = []
    for mode in LADDER:
        try:
            r = provider(model_id, system, user, schema, mode)
        except ToolChoiceUnsupported as exc:
            rejected.append(f"{mode}: {exc}"[:130])
            continue
        except ProviderUnavailable as exc:
            return {"result": "unavailable", "reason": str(exc)[:300], "tool_choice_mode": None}
        detail = f'toolChoice={mode}; stopReason={r.get("stop_reason")}; reply={r.get("text", "")[:200]!r}'
        try:
            if r.get("tool_input") is None:
                raise jsonschema.ValidationError("no tool call returned")
            jsonschema.validate(r["tool_input"], schema)
        except jsonschema.ValidationError as exc:
            return {"result": "no structured output", "reason": f"{exc.message}; {detail}"[:400],
                    "tool_choice_mode": mode, **meta(r)}
        return {"result": "pass", "reason": detail, "tool_choice_mode": mode, **meta(r)}
    return {"result": "no structured output", "reason": "every toolChoice mode rejected: " + " | ".join(rejected),
            "tool_choice_mode": None}


def smoke_test(arms: list[dict], provider: Provider) -> dict[str, dict]:
    """Per LLM arm: pass | "no structured output" | unavailable, with the reason and `tool_choice_mode` (the mode
    B1 sends that arm). Never silently dropped."""
    return {arm["id"]: smoke_arm(arm["model_id"], provider) for arm in arms if arm.get("llm")}


def eligible(results: dict[str, dict]) -> list[str]:
    return [a for a, r in results.items() if r["result"] == "pass"]


def run_smoke(arms: list[dict], provider: Provider, prices: dict | None = None) -> dict[str, dict]:
    """Entry point (AC-08): the budget guard runs first (worst case: every mode of the ladder per LLM arm plus one retry
    without temperature per arm, about 150 tokens in and MAX_TOKENS out each), then the calls."""
    llm = [a for a in arms if a.get("llm")]
    check_budget(projected_spend(llm, prices or load_prices(), len(LADDER) + 1, 150, MAX_TOKENS))
    return smoke_test(arms, provider)


if __name__ == "__main__":  # opt-in, local, never in CI: needs Bedrock credentials in the environment
    from eval.bench.core import load_arms
    for a, r in run_smoke(load_arms(), bedrock_provider()).items():
        print(f"{a}: {r['result']} (toolChoice={r['tool_choice_mode']}, temperature={r.get('temperature')})"
              + (f" ({r['reason']})" if r["result"] != "pass" else ""))
