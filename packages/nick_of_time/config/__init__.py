"""`config.resolve(arm)`: arm -> provider, model and options (spec 01 sections 6.8-6.9, spec 04 section 4.4)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"   # spec 15 section 4.1, incumbent
SONNET = "us.anthropic.claude-sonnet-4-6"
PROVIDERS = ("fake", "bedrock", "anthropic")


@dataclass(frozen=True)
class ArmConfig:
    arm: str
    provider: str            # fake | bedrock | anthropic | none (S0)
    model: str | None
    temperature: float | None = 0
    tool_choice: str = "tool"   # first rung of the D-011 ladder

    @property
    def uses_llm(self) -> bool:
        return self.provider != "none"


def resolve(arm: str, env: Mapping[str, str] | None = None, extra: Mapping[str, Mapping] | None = None) -> ArmConfig:
    """S0 no LLM; S1 BEDROCK_MODEL_FAST (Haiku 4.5); S2 BEDROCK_MODEL_GRAPH (Sonnet 4.6). `extra` adds benchmark arms,
    {arm_id: {"model": ..., "temperature": ..., "tool_choice": ...}}. `LLM_PROVIDER` picks the provider; unset means
    `fake`, so nothing reaches a real model unless deployment sets it [assumption]. Unknown arm -> ValueError."""
    env = os.environ if env is None else env
    if arm == "S0":
        return ArmConfig(arm, "none", None)
    provider = env.get("LLM_PROVIDER") or "fake"
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {PROVIDERS}, got {provider!r}")
    if arm == "S1":
        return ArmConfig(arm, provider, env.get("BEDROCK_MODEL_FAST") or HAIKU)
    if arm == "S2":
        return ArmConfig(arm, provider, env.get("BEDROCK_MODEL_GRAPH") or SONNET)
    if extra and arm in extra:
        return ArmConfig(arm, provider, **{"model": None, **extra[arm]})
    raise ValueError(f"unknown arm {arm!r}")
