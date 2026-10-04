"""Pydantic model of contracts/policies.yaml (spec 02 FR-01, FR-07).

Loaded and validated once: an invalid file fails at startup, never at decision time. The loaded model is deeply frozen
(mappings are read-only proxies, lists are tuples), so no caller can loosen a rule at runtime. Sections the engine does
not read yet stay untyped until the task that uses them types them (clock: 02b, queue: 02c).
"""
from __future__ import annotations

from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from nick_of_time.contracts import CONTRACTS_DIR, Zone

ApprovalMode = Literal["auto", "manual_check", "human_required"]
MODES: tuple[ApprovalMode, ...] = ("auto", "manual_check", "human_required")     # stricter to the right (FR-04)
POLICIES_PATH = CONTRACTS_DIR / "policies.yaml"


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    return tuple(_freeze(item) for item in value) if isinstance(value, list) else value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _deep_freeze(self) -> _Strict:
        for name in list(self.__dict__):
            object.__setattr__(self, name, _freeze(self.__dict__[name]))
        return self


class Scoring(_Strict):
    provider: str
    providers: dict[str, dict[str, str]]
    deciding_sources: list[str] = Field(min_length=1)   # any other source puts the case in zone human (rule 6)
    record_source_in_audit: Literal[True]
    null_score_zone: Literal["human"]


class Rule(_Strict):
    text: str = Field(min_length=1)
    guardrail: Optional[str] = None


class ZoneBand(_Strict):
    score_min: int = Field(ge=0, le=100)
    score_max: int = Field(ge=0, le=100)
    include_null: bool = False
    note: str = ""


class Tiers(_Strict):
    up_to_low: ApprovalMode
    up_to_high: ApprovalMode
    above_high: ApprovalMode


class CountryGate(_Strict):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    usd_rate: float = Field(gt=0)          # local units per USD, only for the tier comparison (§4.2)
    low: float = Field(gt=0)
    high: float = Field(gt=0)


class AmountGate(_Strict):                 # extra="forbid": no deadline or clock key can live here (AC-06)
    amount: str
    tiers: Tiers
    by_country: dict[str, CountryGate]


class Approval(_Strict):
    supervised_mode: bool
    money_actions: list[str]
    per_action: dict[str, dict[Zone, ApprovalMode]]
    manual_check_leaves_case_in: Literal["verification"]
    close: Literal["human_only"]


class Clarify(_Strict):
    intent_confidence_min: float = Field(gt=0, le=1)
    max_candidate_transactions: int = Field(ge=1)
    max_clarification_turns: int = Field(ge=0)


class Handoff(_Strict):
    triggers: list[str]
    payload_schema: str
    never_include_raw_transcript: Literal[True]


class Policies(_Strict):
    version: int = Field(ge=1)
    default: Literal["deny"]               # nothing runs unless a rule allows it (AC-05)
    rules: dict[str, Rule]
    identity: dict[str, Any]
    scope: dict[str, Any]
    scoring: Scoring
    zones: dict[Zone, ZoneBand]
    amount_gate: AmountGate
    approval: Approval
    actions: dict[str, Any]
    actors: dict[str, Any]
    clarify: Clarify
    handoff: Handoff
    regulatory_clock: dict[str, Any]
    reliability: dict[str, Any]
    security: dict[str, Any]
    case_queue: dict[str, Any]
    notifications: dict[str, Any]
    guardrails: list[dict[str, Any]]
    data_splits: dict[str, Any]

    @model_validator(mode="after")
    def _firm_rules_hold(self) -> Policies:
        """Business rules no edit of the file may break (CLAUDE.md constitution and spec 02)."""
        guardrails = {g["id"] for g in self.guardrails}
        problems = [f"rule id {r} must start with POL-" for r in self.rules if not r.startswith("POL-")]
        problems += [f"rule {r} cites unknown guardrail {v.guardrail}" for r, v in self.rules.items()
                     if v.guardrail and v.guardrail not in guardrails]
        if "llm" in self.scoring.deciding_sources:
            problems.append("an llm score never decides a zone (POL-SCORE-LLM)")
        z = self.zones
        if set(z) != {"high", "medium", "human"} or not (
                z["human"].score_min == 0 and z["human"].score_max + 1 == z["medium"].score_min
                and z["medium"].score_max + 1 == z["high"].score_min and z["high"].score_max == 100
                and z["human"].include_null):
            problems.append("zones must be contiguous bands human < medium < high over 0-100, null in human")
        per_action, money = self.approval.per_action, set(self.approval.money_actions)
        if any(set(modes) != set(z) for modes in per_action.values()):
            problems.append("approval.per_action needs a mode for every zone")
        if set(per_action.get("open_case", {}).values()) != {"auto"}:
            problems.append("open_case must be auto in every zone (POL-TICKET-ALWAYS)")
        if set(per_action.get("provisional_credit", {}).values()) != {"human_required"}:
            problems.append("provisional_credit must be human_required in every zone (AC-09)")
        if money != set(per_action) - {"open_case"}:
            problems.append("money_actions must be every action in per_action except open_case (AC-15)")
        tiers = self.amount_gate.tiers
        if not MODES.index(tiers.up_to_low) <= MODES.index(tiers.up_to_high) <= MODES.index(tiers.above_high):
            problems.append("amount tiers must get stricter as the amount grows")
        problems += [f"amount_gate {c}: low must be below high" for c, g in self.amount_gate.by_country.items()
                     if g.low >= g.high]
        if problems:
            raise ValueError("; ".join(problems))
        return self


@cache
def load_policies(path: Path = POLICIES_PATH) -> Policies:
    """Read and validate policies.yaml once per path (FR-01)."""
    return Policies.model_validate(yaml.safe_load(Path(path).read_text()))
