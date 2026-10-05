"""Shared LLM client contract (spec 04 T7a; spec 15 section 4.1, decisions D-011 and D-016).

Structured output is a forced tool call. The ladder tool -> any -> auto steps down only when the provider rejects a
toolChoice mode, and the accepted mode is kept on the client (`mode`) so a run records it per arm (D-011).
Temperature 0 is sent first; a provider that rejects it gets no temperature, recorded as `temperature=None` (D-016).
Provider errors become `ProviderUnavailable` (the graph falls back to S0); our own malformed requests re-raise.
With a schema, the accepted mode must return a tool input that validates against it; otherwise `NoStructuredOutput`
(not a `ProviderUnavailable`: the caller decides). `latency_ms` covers the whole `complete()`, ladder and temperature
retries included (spec 01 section 6.5 `llm_calls.latency_ms`, spec 04 section 6 usage row, ADR 0009).
D-011 "no structured output" maps to both: exhausted ladder -> `ToolChoiceUnsupported` (a `ProviderUnavailable`),
schema failure -> `NoStructuredOutput`.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError, validate

LADDER = ("tool", "any", "auto")
DEFAULT_TOOL = "record_output"


class LLMError(RuntimeError):
    """Base of the errors this module raises on purpose."""


class ProviderUnavailable(LLMError):
    """No access, quota, throttling, outage or wrong model id: the arm cannot answer (graph falls back to S0)."""


class ToolChoiceUnsupported(ProviderUnavailable):
    """Every toolChoice mode of the ladder was rejected, so the model has no structured output."""


class NoStructuredOutput(LLMError):
    """The accepted mode returned no tool input, or one that does not match the schema (for example `auto` answered
    in text, or `max_tokens` cut the input). Not a provider outage: the caller decides (retry, repair or S0).
    `result` is the billed call, so its usage, cost and latency are still logged (ADR 0009, spec 01 section 6.5)."""

    def __init__(self, message: str, *, result: LLMResult) -> None:
        super().__init__(message)
        self.result = result


class TemperatureUnsupported(RuntimeError):
    """The provider rejected the temperature parameter (internal: the client retries without it)."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    tool_input: dict | None
    stop_reason: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None      # None when no price was passed in
    provider: str
    model: str
    mode: str | None            # toolChoice mode that was accepted; None without a schema
    temperature: float | None   # what was sent; None = provider default
    latency_ms: int             # perf_counter around the whole complete(): ladder and temperature retries included


def cost_usd(prices: dict | None, tokens_in: int, tokens_out: int) -> float | None:
    """`prices` = {"input_per_1m": x, "output_per_1m": y} (same shape as eval/bench/prices.yaml rows)."""
    if not prices:
        return None
    return (tokens_in * prices["input_per_1m"] + tokens_out * prices["output_per_1m"]) / 1_000_000


_CONFIG_MSG = re.compile(r"model identifier is invalid|inference profile|on-demand throughput", re.I)
_TOOL_MSG = re.compile(r"tool_?choice|tool ?use|tool calling", re.I)
_TEMP_MSG = re.compile(r"temperature", re.I)


def classify_validation(message: str) -> Exception | None:
    """What a validation (HTTP 400) message means; None = our request is malformed (the caller re-raises)."""
    if _CONFIG_MSG.search(message):
        return ProviderUnavailable(f"config: {message}"[:300])
    if _TEMP_MSG.search(message):
        return TemperatureUnsupported(message)
    if _TOOL_MSG.search(message):
        return ToolChoiceUnsupported(message)
    return None


class LLMClient:
    """Subclasses implement `_call`; `complete` owns the ladder and the temperature rule."""

    provider = "base"

    def __init__(self, model: str, *, prices: dict | None = None, temperature: float | None = 0,
                 mode: str = LADDER[0], read_timeout_s: float | None = None, max_attempts: int | None = None) -> None:
        self.model, self.prices = model, prices
        # HTTP read timeout and total attempts (first try included); None keeps the provider default. Fake ignores them.
        if read_timeout_s is not None and read_timeout_s <= 0:
            raise ValueError(f"read_timeout_s must be > 0, got {read_timeout_s!r}")
        if max_attempts is not None and max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {max_attempts!r}")
        self.read_timeout_s, self.max_attempts = read_timeout_s, max_attempts
        self.temperature = temperature   # current setting; becomes None once the provider rejects it
        self.mode = mode                 # first mode to try; after a call, the accepted one

    def _call(self, system: str, user: str, schema: dict | None, tool_name: str, max_tokens: int,
              mode: str | None, temperature: float | None) -> dict[str, Any]:
        """Return {"text", "tool_input", "stop_reason", "tokens_in", "tokens_out"}; raise ToolChoiceUnsupported,
        TemperatureUnsupported or ProviderUnavailable for provider answers, anything else for our own bugs."""
        raise NotImplementedError

    def complete(self, system: str, user: str, *, schema: dict | None = None, tool_name: str = DEFAULT_TOOL,
                 max_tokens: int = 512) -> LLMResult:
        t0 = time.perf_counter()
        modes = LADDER[LADDER.index(self.mode):] if schema else (None,)
        rejected: list[str] = []
        for mode in modes:
            while True:
                try:
                    raw = self._call(system, user, schema, tool_name, max_tokens, mode, self.temperature)
                except TemperatureUnsupported:
                    if self.temperature is None:
                        raise
                    self.temperature = None
                    continue
                except ToolChoiceUnsupported as exc:
                    rejected.append(f"{mode}: {exc}"[:130])
                    break
                if mode:
                    self.mode = mode
                result = LLMResult(text=raw["text"], tool_input=raw["tool_input"], stop_reason=raw["stop_reason"],
                                   tokens_in=raw["tokens_in"], tokens_out=raw["tokens_out"],
                                   cost_usd=cost_usd(self.prices, raw["tokens_in"], raw["tokens_out"]),
                                   provider=self.provider, model=self.model, mode=mode, temperature=self.temperature,
                                   latency_ms=round((time.perf_counter() - t0) * 1000))
                if schema:
                    self._check_tool_input(result, schema)
                return result
        raise ToolChoiceUnsupported("; ".join(rejected))

    @staticmethod
    def _check_tool_input(result: LLMResult, schema: dict) -> None:
        if not isinstance(result.tool_input, dict):
            raise NoStructuredOutput(f"mode {result.mode} returned no tool input (stop_reason {result.stop_reason!r})",
                                     result=result)
        try:
            validate(result.tool_input, schema)
        except ValidationError as exc:
            raise NoStructuredOutput(f"mode {result.mode} tool input does not match the schema: {exc.message}"[:300],
                                     result=result) from exc
