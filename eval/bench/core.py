"""Arms, prices, budget guard and result rows of the model benchmark (spec 15: AC-05, AC-06, AC-08)."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable

import yaml

HERE = Path(__file__).parent
BUDGET_USD = 20.0  # [assumption] per full benchmark, decided by the lead 2026-10-04 (spec 15 Q2)


class ProviderUnavailable(RuntimeError):
    """A provider error (no access, no quota, outage, wrong model id) that makes one arm unavailable (AC-06)."""


class ToolChoiceUnsupported(RuntimeError):
    """Bedrock rejected the toolChoice mode or tool use itself for this model (a ValidationException)."""


_CONFIG_MSG = re.compile(r"model identifier is invalid|inference profile|on-demand throughput", re.I)
_TOOL_USE_MSG = re.compile(r"tool_?choice|tool ?use|tool calling", re.I)


def provider_error(exc: BaseException) -> Exception | None:
    """What a provider exception means for the arm, or None when it is a bug in our request (re-raise it).
    ValidationException: invalid id or "use an inference profile" -> ProviderUnavailable("config: ..."); about tool
    use or toolChoice -> ToolChoiceUnsupported; any other -> None. Any other ClientError (access, quota, throttling,
    outage) and BotoCoreError (connection, timeout) -> ProviderUnavailable. ParamValidationError is raised by
    botocore on our malformed request before any call -> None."""
    if isinstance(exc, (ProviderUnavailable, ToolChoiceUnsupported)):
        return exc
    try:
        from botocore.exceptions import BotoCoreError, ClientError, ParamValidationError
    except ImportError:  # pragma: no cover
        return None
    if isinstance(exc, ClientError):
        err = exc.response.get("Error", {})
        code, msg = err.get("Code", ""), err.get("Message", "")
        if code != "ValidationException":
            return ProviderUnavailable(f"{code}: {msg}")
        if _CONFIG_MSG.search(msg):
            return ProviderUnavailable(f"config: {msg}")
        return ToolChoiceUnsupported(msg) if _TOOL_USE_MSG.search(msg) else None
    if isinstance(exc, BotoCoreError) and not isinstance(exc, ParamValidationError):
        return ProviderUnavailable(f"{type(exc).__name__}: {exc}")
    return None


def is_billable(arm: dict) -> bool:
    """Every arm that calls a third party costs money, LLM or not (Jev is billable)."""
    return arm["provider"] not in ("rules", "classifier")


class BudgetExceeded(RuntimeError):
    """The projected spend is over the budget: the run must not call any model (AC-08, G-OPS-01)."""


def load_arms(path: Path = HERE / "arms.yaml") -> list[dict]:
    return yaml.safe_load(path.read_text())["arms"]


def load_prices(path: Path = HERE / "prices.yaml") -> dict[str, dict]:
    return yaml.safe_load(path.read_text())["prices"]


def projected_spend(arms: list[dict], prices: dict, n_messages: int, in_tokens: int, out_tokens: int) -> float:
    """USD for sending `n_messages` (avg `in_tokens` in, `out_tokens` out) to every billable arm.
    A billable arm without a price cannot be projected, so it is an error rather than free."""
    total = 0.0
    for arm in arms:
        if not is_billable(arm):
            continue
        p = prices[arm["id"]]  # KeyError on purpose: no price, no run
        total += n_messages * (in_tokens * p["input_per_1m"] + out_tokens * p["output_per_1m"]) / 1_000_000
    return total


def check_budget(projected: float, budget: float = BUDGET_USD) -> None:
    if projected > budget:
        raise BudgetExceeded(f"projected spend {projected:.2f} USD exceeds the budget of {budget:.2f} USD; "
                             "no model was called")


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def make_row(arm: dict, prices: dict, prompt: str, run_date: str) -> dict:
    """Provenance columns every result row carries (AC-05)."""
    p = prices.get(arm["id"], {})
    return {
        "arm": arm["id"], "model_id": arm.get("model_id"),
        # [assumption] the pinned Bedrock id is the version; Jev carries its version in the id
        "version": arm.get("model_id"),
        "prompt_hash": prompt_hash(prompt),
        "price_input_per_1m": p.get("input_per_1m"), "price_output_per_1m": p.get("output_per_1m"),
        "price_status": p.get("status"), "price_source_url": p.get("source_url"),
        "price_checked_on": p.get("checked_on"), "run_date": run_date, "status": "ok", "reason": None,
    }


def run_arms(arms: list[dict], prices: dict, prompt: str, run_date: str, evaluate: Callable[[dict], dict],
             *, n_messages: int, in_tokens: int, out_tokens: int, budget: float = BUDGET_USD) -> list[dict]:
    """Run `evaluate(arm)` on each arm. The budget is checked first, before any call (AC-08). An arm that fails
    with a provider error (`provider_error` gives ProviderUnavailable) is recorded unavailable with its reason and
    the run continues (AC-06); any other exception is a bug in the harness and propagates."""
    check_budget(projected_spend(arms, prices, n_messages, in_tokens, out_tokens), budget)
    rows = []
    for arm in arms:
        row = make_row(arm, prices, prompt, run_date)
        try:
            row.update(evaluate(arm))
        except Exception as exc:
            unavailable = provider_error(exc)
            if not isinstance(unavailable, ProviderUnavailable):
                raise
            row.update(status="unavailable", reason=str(unavailable)[:300])
        rows.append(row)
    return rows
