"""Structured-output smoke test (spec 15 AC-11): one valid JSON object matching the intent schema per LLM arm."""
from __future__ import annotations

import json
import re
from typing import Callable

import jsonschema

# [assumption] minimal intent schema until spec 11 delivers the real one (five intents, slots).
INTENT_SCHEMA = {
    "type": "object",
    "required": ["intent", "language"],
    "properties": {"intent": {"type": "string", "minLength": 1},
                   "language": {"enum": ["es", "pt"]}},
}
SYSTEM = ("Classify the customer message. Reply with exactly one JSON object and nothing else: "
          '{"intent": "<short snake_case intent>", "language": "es" or "pt"}.')
PROMPT = "No reconozco un cargo de 45 dólares en mi tarjeta."
Provider = Callable[[str, str, str], str]  # (model_id, system, user) -> raw text


def bedrock_provider(region: str = "us-east-2") -> Provider:
    """[assumption] replace with nick_of_time.llm when the task LLM lands. Bedrock Converse API, temperature 0."""
    import boto3
    client = boto3.client("bedrock-runtime", region_name=region)

    def call(model_id: str, system: str, user: str) -> str:
        r = client.converse(modelId=model_id, system=[{"text": system}],
                            messages=[{"role": "user", "content": [{"text": user}]}],
                            inferenceConfig={"temperature": 0, "maxTokens": 100})
        return "".join(b.get("text", "") for b in r["output"]["message"]["content"])
    return call


def parse_object(text: str) -> dict:
    """Strict: the whole reply must be one JSON object (a ```json fence around it is tolerated)."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    obj = json.loads(t)
    jsonschema.validate(obj, INTENT_SCHEMA)
    return obj


def smoke_test(arms: list[dict], provider: Provider) -> dict[str, dict]:
    """Per LLM arm: pass | "no structured output" | unavailable (with reason). Never silently dropped."""
    out = {}
    for arm in arms:
        if not arm.get("llm"):
            continue
        try:
            text = provider(arm["model_id"], SYSTEM, PROMPT)
        except Exception as exc:
            out[arm["id"]] = {"result": "unavailable", "reason": f"{type(exc).__name__}: {exc}"[:300]}
            continue
        try:
            parse_object(text)
            out[arm["id"]] = {"result": "pass", "reason": None}
        except (ValueError, jsonschema.ValidationError) as exc:
            out[arm["id"]] = {"result": "no structured output", "reason": type(exc).__name__}
    return out


def eligible(results: dict[str, dict]) -> list[str]:
    return [a for a, r in results.items() if r["result"] == "pass"]


if __name__ == "__main__":  # opt-in, local, never in CI: needs Bedrock credentials in the environment
    from eval.bench.core import load_arms
    for a, r in smoke_test(load_arms(), bedrock_provider()).items():
        print(f"{a}: {r['result']}" + (f" ({r['reason']})" if r["reason"] else ""))
