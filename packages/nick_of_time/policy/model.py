"""Pydantic model of contracts/policies.yaml (spec 02 FR-01, FR-07).

Loaded and validated once: an invalid file fails at startup, never at decision time. The loaded model is deeply frozen
(mappings are read-only proxies, lists are tuples), so no caller can loosen a rule at runtime. Sections the engine does
not read yet stay untyped until the task that uses them types them.
"""
from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Literal, Optional, get_args
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_serializer, model_validator

from nick_of_time.contracts import CONTRACTS_DIR, HTTPS_URL, QueueStatus, Zone
from nick_of_time.policy.calendars import holidays

CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
ApprovalMode = Literal["auto", "manual_check", "human_required"]
MODES: tuple[ApprovalMode, ...] = ("auto", "manual_check", "human_required")     # stricter to the right (FR-04)
POLICIES_PATH = CONTRACTS_DIR / "policies.yaml"


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    return tuple(_freeze(item) for item in value) if isinstance(value, list) else value


def _thaw(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {key: _thaw(item) for key, item in value.items()}
    return [_thaw(item) for item in value] if isinstance(value, tuple) else value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _deep_freeze(self) -> _Strict:
        for name in list(self.__dict__):
            object.__setattr__(self, name, _freeze(self.__dict__[name]))
        return self

    @field_serializer("*", mode="wrap")
    def _plain(self, value: Any, handler: Any) -> Any:
        """model_dump() and model_dump_json() give the frozen proxies and tuples back as the file's dicts and lists."""
        return handler(_thaw(value))


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


class Term(_Strict):
    days: int = Field(gt=0)
    calendar: Literal["business", "calendar"]


class ChargeWindow(_Strict):              # the entry applies only to a charge this recent at the notice
    hours: Optional[int] = Field(None, gt=0)
    days: Optional[int] = Field(None, gt=0)

    @model_validator(mode="after")
    def _one_unit(self) -> ChargeWindow:
        if (self.hours is None) == (self.days is None):
            raise ValueError("when_charged_within needs exactly one of hours or days")
        return self


class SourceLabel(_Strict):               # DLANG: the customer's name of an entry's `source`, never translated by the agent
    es: str = Field(min_length=1)
    pt: str = Field(min_length=1)


class ClockEntry(_Strict):                # one verified row of spec 02 §4.3 (ADR 0019)
    when_charged_within: Optional[ChargeWindow] = None
    credit: Optional[Term] = None
    ruling: Optional[Term] = None
    ruling_abroad: Optional[Term] = None
    extendable_once: bool = False
    source: str = Field(min_length=1)    # the analyst's (English) name, stored with the case
    source_label: SourceLabel
    source_url: str = Field(pattern=HTTPS_URL)
    verified_on: date

    @model_validator(mode="after")
    def _has_a_term(self) -> ClockEntry:
        if self.credit is None and self.ruling is None:
            raise ValueError("a regulatory_clock entry needs a credit or a ruling term")
        return self


class Country(_Strict):
    time_zone: str

    @model_validator(mode="after")
    def _known_zone(self) -> Country:
        try:
            ZoneInfo(self.time_zone)
        except (KeyError, ValueError) as e:     # ZoneInfoNotFoundError is a KeyError
            raise ValueError(f"unknown IANA time zone {self.time_zone}") from e
        return self


class SlaScope(_Strict):
    country: CountryCode
    product: Literal["debit", "credit"]


class DeadlineSla(_Strict):               # case_queue.deadline_sla: a person must act before the legal credit date
    applies_to: SlaScope
    deadline: str = Field(min_length=1)
    raise_priority_on_business_day: int = Field(ge=1)
    alert_before_business_day: int = Field(ge=1)


class CaseQueue(_Strict):                 # spec 02 FR-06 (task 02c): typed, so a broken queue fails at startup
    states: list[QueueStatus]
    transitions: dict[QueueStatus, list[QueueStatus]]
    sla_hours: dict[QueueStatus, float]
    ambiguous_queue: dict[str, Any]
    deadline_sla: dict[str, DeadlineSla]

    @model_validator(mode="after")
    def _a_person_closes(self) -> CaseQueue:
        problems = []
        if list(self.states) != list(get_args(QueueStatus)) or set(self.transitions) != set(self.states):
            problems.append("case_queue needs every queue status, in order, each with its transitions")
        if self.transitions.get("closed"):
            problems.append("nothing leaves closed: a closed case is never reopened (spec 02 §4.4)")
        if any("closed" in targets for status, targets in self.transitions.items() if status != "resolved"):
            problems.append("only a resolved case can be closed")
        problems += [f"sla_hours.{s} must be positive" for s, hours in self.sla_hours.items() if hours <= 0]
        problems += [f"deadline_sla.{n}: the priority must rise before the alert is due" for n, d in
                     self.deadline_sla.items() if d.raise_priority_on_business_day >= d.alert_before_business_day]
        if problems:
            raise ValueError("; ".join(problems))
        return self


class Contact(_Strict):                   # D-008: request_call's expected_contact_by; null promises no date
    callback_within_business_days: Optional[StrictInt] = Field(None, ge=1)


class Reevaluation(_Strict):              # spec 02 §4.4, FR-09: per country, the days a resolved case may go back
    window_days: dict[CountryCode, Annotated[StrictInt, Field(ge=0)]]


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
    contact: Optional[Contact] = None
    reevaluation: Optional[Reevaluation] = None   # absent: no window, so no resolved case goes back (POL-REEVAL-WINDOW)
    regulatory_clock: dict[CountryCode, dict[Literal["debit", "credit", "any"], list[ClockEntry]]]
    countries: dict[CountryCode, Country]
    reliability: dict[str, Any]
    security: dict[str, Any]
    case_queue: CaseQueue
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
        providers = set(self.scoring.providers)
        problems += [f"scoring source {s} has no scoring.providers entry (note and version for the audit)"
                     for s in dict.fromkeys((self.scoring.provider, *self.scoring.deciding_sources)) if s not in providers]
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
        block = per_action.get("block_card", {})
        if (block.get("high"), block.get("medium"), block.get("human")) != ("manual_check", "human_required",
                                                                           "human_required"):
            problems.append("block_card must be manual_check in the high zone and human_required in the others (§4.2)")
        if set(per_action.get("unblock_card", {}).values()) != {"human_required"}:
            problems.append("unblock_card must be human_required in every zone")
        if money != set(per_action) - {"open_case"}:
            problems.append("money_actions must be every action in per_action except open_case (AC-15)")
        tiers = self.amount_gate.tiers
        if not MODES.index(tiers.up_to_low) <= MODES.index(tiers.up_to_high) <= MODES.index(tiers.above_high):
            problems.append("amount tiers must get stricter as the amount grows")
        problems += [f"amount_gate {c}: low must be below high" for c, g in self.amount_gate.by_country.items()
                     if g.low >= g.high]
        problems += [f"regulatory_clock {c} needs countries.{c}.time_zone" for c in self.regulatory_clock
                     if c not in self.countries]
        for country, products in self.regulatory_clock.items():      # FR-01: holiday files load with the policies
            terms = [t for entries in products.values() for e in entries for t in (e.credit, e.ruling, e.ruling_abroad)]
            if any(t and t.calendar == "business" for t in terms):
                try:
                    if not holidays(country):
                        problems.append(f"regulatory_clock {country} counts business days but has no holiday file")
                except ValueError as e:                              # pydantic's ValidationError is a ValueError
                    problems.append(f"holiday file of {country}: {e}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


@cache
def load_policies(path: Path = POLICIES_PATH) -> Policies:
    """Read and validate policies.yaml once per path (FR-01)."""
    return Policies.model_validate(yaml.safe_load(Path(path).read_text()))
