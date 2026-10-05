"""`config.resolve(arm)`: arm -> provider, model and options (spec 01 sections 6.8-6.9, spec 04 section 4.4), and
`config.today(mode)`: the session's "today" (ADR 0020)."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from typing import Mapping, Optional
from zoneinfo import ZoneInfo

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
    read_timeout_s: float | None = None   # optional pass-through to the client (spec 18 section 5); None = default
    max_attempts: int | None = None

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


DEMO_TODAY = "2026-06-01"       # replay "today" when DEMO_TODAY is unset (ADR 0020, spec 01 section 6.8)
TIME_ZONES = {"MX": "America/Mexico_City", "AR": "America/Argentina/Buenos_Aires", "BR": "America/Sao_Paulo",
              "CO": "America/Bogota", "PE": "America/Lima", "CL": "America/Santiago"}


def today(mode: str, country: Optional[str] = None, *, env: Mapping[str, str] | None = None,
          now: Optional[dt.datetime] = None) -> dt.date:
    """clock.today(mode, country) (spec 01 section 5): replay is DEMO_TODAY; live is the date in the customer's country
    time zone. The only place the agent may read the system clock. [assumption] live without a known country uses
    UTC, as the api stub does."""
    env = os.environ if env is None else env
    if mode == "replay":
        return dt.date.fromisoformat(env.get("DEMO_TODAY") or DEMO_TODAY)
    if mode != "live":
        raise ValueError(f"mode must be replay or live, not {mode!r} (ADR 0020)")
    zone = ZoneInfo(TIME_ZONES.get(country or "", "UTC"))
    return (now.astimezone(zone) if now else dt.datetime.now(zone)).date()
