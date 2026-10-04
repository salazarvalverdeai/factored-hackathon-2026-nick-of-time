"""Structured-output smoke test (spec 15 AC-11): each LLM arm must return one valid object matching the intent
schema through forced Converse tool use (the same path B1 runs; decision D-011)."""
from __future__ import annotations

from typing import Callable

import jsonschema

from eval.bench.core import ProviderUnavailable, check_budget, load_prices, projected_spend

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
# provider(model_id, system, user, schema) -> {"tool_input": dict | None, "text": str, "stop_reason": str}
Provider = Callable[[str, str, str, dict], dict]


def bedrock_provider(region: str = "us-east-2") -> Provider:
    """[assumption] replace with nick_of_time.llm when the task LLM lands. Bedrock Converse API with forced
    tool use, temperature 0. Access, quota and outage errors become ProviderUnavailable; a ValidationException
    (for example a model without tool use) is a model that cannot return structured output."""
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    client = boto3.client("bedrock-runtime", region_name=region)

    def call(model_id: str, system: str, user: str, schema: dict) -> dict:
        try:
            r = client.converse(
                modelId=model_id, system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"temperature": 0, "maxTokens": MAX_TOKENS},
                toolConfig={"tools": [{"toolSpec": {"name": TOOL_NAME, "description": "Record the intent.",
                                                    "inputSchema": {"json": schema}}}],
                            "toolChoice": {"tool": {"name": TOOL_NAME}}})
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ValidationException":
                return {"tool_input": None, "text": str(exc), "stop_reason": "validation_error"}
            raise ProviderUnavailable(f'{exc.response["Error"]["Code"]}: {exc}') from exc
        except BotoCoreError as exc:
            raise ProviderUnavailable(f"{type(exc).__name__}: {exc}") from exc
        blocks = r["output"]["message"]["content"]
        tool = next((b["toolUse"]["input"] for b in blocks if "toolUse" in b), None)
        return {"tool_input": tool, "text": "".join(b.get("text", "") for b in blocks),
                "stop_reason": r.get("stopReason", "")}
    return call


def smoke_test(arms: list[dict], provider: Provider) -> dict[str, dict]:
    """Per LLM arm: pass | "no structured output" | unavailable (with reason). Never silently dropped."""
    out = {}
    for arm in arms:
        if not arm.get("llm"):
            continue
        try:
            r = provider(arm["model_id"], SYSTEM, PROMPT, INTENT_SCHEMA)
        except ProviderUnavailable as exc:
            out[arm["id"]] = {"result": "unavailable", "reason": str(exc)[:300]}
            continue
        detail = f'stopReason={r.get("stop_reason")}; reply={r.get("text", "")[:200]!r}'
        try:
            if r.get("tool_input") is None:
                raise jsonschema.ValidationError("no tool call returned")
            jsonschema.validate(r["tool_input"], INTENT_SCHEMA)
            out[arm["id"]] = {"result": "pass", "reason": detail}
        except jsonschema.ValidationError as exc:
            out[arm["id"]] = {"result": "no structured output", "reason": f"{exc.message}; {detail}"[:400]}
    return out


def eligible(results: dict[str, dict]) -> list[str]:
    return [a for a, r in results.items() if r["result"] == "pass"]


def run_smoke(arms: list[dict], provider: Provider, prices: dict | None = None) -> dict[str, dict]:
    """Entry point (AC-08): the budget guard runs first (one call per LLM arm, about 150 tokens in and
    MAX_TOKENS out at worst), then the calls."""
    llm = [a for a in arms if a.get("llm")]
    check_budget(projected_spend(llm, prices or load_prices(), 1, 150, MAX_TOKENS))
    return smoke_test(arms, provider)


if __name__ == "__main__":  # opt-in, local, never in CI: needs Bedrock credentials in the environment
    from eval.bench.core import load_arms
    for a, r in run_smoke(load_arms(), bedrock_provider()).items():
        print(f"{a}: {r['result']}" + (f" ({r['reason']})" if r["result"] != "pass" else ""))
