"""Structured-output smoke test (spec 15 AC-11): each LLM arm must return one valid object matching the intent
schema through Converse tool use (the same path B1 runs; decision D-011). toolChoice `tool` is documented only for
Anthropic Claude 3+ and Amazon Nova, so each arm walks the ladder tool -> any -> auto and records the mode B1 reuses."""
from __future__ import annotations

from typing import Callable

import jsonschema

from eval.bench.core import (ProviderUnavailable, ToolChoiceUnsupported, check_budget, load_prices, projected_spend,
                             provider_error)

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
# raises ToolChoiceUnsupported (mode rejected) or ProviderUnavailable (arm unavailable).
Provider = Callable[[str, str, str, dict, str], dict]


def converse_request(model_id: str, system: str, user: str, schema: dict, mode: str) -> dict:
    """The Converse request of the smoke test and of B1: one tool with the schema, the arm's toolChoice mode,
    temperature 0 and MAX_TOKENS."""
    return {"modelId": model_id, "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"temperature": 0, "maxTokens": MAX_TOKENS},
            "toolConfig": {"tools": [{"toolSpec": {"name": TOOL_NAME, "description": "Record the intent.",
                                                   "inputSchema": {"json": schema}}}],
                           "toolChoice": TOOL_CHOICES[mode]}}


def bedrock_provider(region: str = "us-east-2") -> Provider:
    """[assumption] replace with nick_of_time.llm when the task LLM lands. Errors are mapped by
    core.provider_error; a ValidationException that is not about tool use or the model id, and botocore's
    ParamValidationError, are bugs in our request and propagate."""
    import boto3
    client = boto3.client("bedrock-runtime", region_name=region)

    def call(model_id: str, system: str, user: str, schema: dict, mode: str) -> dict:
        try:
            r = client.converse(**converse_request(model_id, system, user, schema, mode))
        except Exception as exc:
            mapped = provider_error(exc)
            if mapped is None or mapped is exc:
                raise
            raise mapped from exc
        blocks = r["output"]["message"]["content"]
        tool = next((b["toolUse"]["input"] for b in blocks if "toolUse" in b), None)
        return {"tool_input": tool, "text": "".join(b.get("text", "") for b in blocks),
                "stop_reason": r.get("stopReason", "")}
    return call


def smoke_arm(model_id: str, provider: Provider) -> dict:
    """Walk the ladder: a mode Bedrock rejects (ToolChoiceUnsupported) moves to the next one; the first accepted mode
    decides, and its tool input must match the schema. Every mode rejected means "no structured output"."""
    rejected = []
    for mode in LADDER:
        try:
            r = provider(model_id, SYSTEM, PROMPT, INTENT_SCHEMA, mode)
        except ToolChoiceUnsupported as exc:
            rejected.append(f"{mode}: {exc}"[:130])
            continue
        except ProviderUnavailable as exc:
            return {"result": "unavailable", "reason": str(exc)[:300], "tool_choice_mode": None}
        detail = f'toolChoice={mode}; stopReason={r.get("stop_reason")}; reply={r.get("text", "")[:200]!r}'
        try:
            if r.get("tool_input") is None:
                raise jsonschema.ValidationError("no tool call returned")
            jsonschema.validate(r["tool_input"], INTENT_SCHEMA)
        except jsonschema.ValidationError as exc:
            return {"result": "no structured output", "reason": f"{exc.message}; {detail}"[:400],
                    "tool_choice_mode": mode}
        return {"result": "pass", "reason": detail, "tool_choice_mode": mode}
    return {"result": "no structured output", "reason": "every toolChoice mode rejected: " + " | ".join(rejected),
            "tool_choice_mode": None}


def smoke_test(arms: list[dict], provider: Provider) -> dict[str, dict]:
    """Per LLM arm: pass | "no structured output" | unavailable, with the reason and `tool_choice_mode` (the mode
    B1 sends that arm). Never silently dropped."""
    return {arm["id"]: smoke_arm(arm["model_id"], provider) for arm in arms if arm.get("llm")}


def eligible(results: dict[str, dict]) -> list[str]:
    return [a for a, r in results.items() if r["result"] == "pass"]


def run_smoke(arms: list[dict], provider: Provider, prices: dict | None = None) -> dict[str, dict]:
    """Entry point (AC-08): the budget guard runs first (worst case: every mode of the ladder per LLM arm, about
    150 tokens in and MAX_TOKENS out each), then the calls."""
    llm = [a for a in arms if a.get("llm")]
    check_budget(projected_spend(llm, prices or load_prices(), len(LADDER), 150, MAX_TOKENS))
    return smoke_test(arms, provider)


if __name__ == "__main__":  # opt-in, local, never in CI: needs Bedrock credentials in the environment
    from eval.bench.core import load_arms
    for a, r in run_smoke(load_arms(), bedrock_provider()).items():
        print(f"{a}: {r['result']} (toolChoice={r['tool_choice_mode']})"
              + (f" ({r['reason']})" if r["result"] != "pass" else ""))
