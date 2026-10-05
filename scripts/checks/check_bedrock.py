"""Access check for Amazon Bedrock: one tiny call per configured model. Usage: make check-bedrock"""
from __future__ import annotations

import time

import boto3

from _common import fail, ok, setting

REGION = setting("AWS_REGION", "us-east-2")
PROFILE = setting("AWS_PROFILE", "nickoftime")  # explicit team profile: ignores dataset keys an old .env may export
MODELS = {
    "BEDROCK_MODEL_FAST": setting("BEDROCK_MODEL_FAST", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    "BEDROCK_MODEL_GRAPH": setting("BEDROCK_MODEL_GRAPH", "us.anthropic.claude-sonnet-4-6"),
}

client = boto3.Session(profile_name=PROFILE, region_name=REGION).client("bedrock-runtime")
failed = False
for name, model_id in MODELS.items():
    started = time.perf_counter()
    try:
        out = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Responde solo: ok"}]}],
            inferenceConfig={"maxTokens": 5, "temperature": 0},
        )
    except Exception as exc:  # noqa: BLE001 — report any provider error as a failed check
        print(f"FAIL  {name} ({model_id}): {type(exc).__name__}: {exc}")
        failed = True
        continue
    ms = (time.perf_counter() - started) * 1000
    usage = out.get("usage", {})
    ok(f"{name} {model_id} answered in {ms:.0f} ms (tokens in {usage.get('inputTokens')}, out {usage.get('outputTokens')})")

if failed:
    fail("at least one Bedrock model is not reachable")
