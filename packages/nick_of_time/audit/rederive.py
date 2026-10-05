"""Checks A1–A2 of spec 18 §4.1: re-run the policy engine and the regulatory clock on a run's recorded inputs.

They re-derive, they never decide: the recorded decision and the stored deadlines are compared with what the same code
gives today on the same inputs. Pure: no network, no store, no LLM; the clock is called with the case's own dates, so
nothing reads the system clock (ADR 0020).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Optional, Union

from pydantic import ValidationError

from nick_of_time.audit.checks import Finding, _finding
from nick_of_time.policy import DecisionInput, Policies, PolicyDecision, PolicyEngine
from nick_of_time.policy.clock import Deadline, deadline


def _diff(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: {"expected": expected[k], "observed": observed.get(k)} for k in expected if expected[k] != observed.get(k)}


def check_decision(inputs: Union[DecisionInput, Mapping[str, Any]], recorded: Union[PolicyDecision, Mapping[str, Any]],
                   *, engine: Optional[PolicyEngine] = None) -> Finding:
    """A1: `decide()` on the recorded inputs gives the recorded decision, with the same `policies_version`.

    Every field of the decision is compared (rule ids, zone, modes, allowed actions, queue status), so a recorded
    decision that is merely similar is a finding. Inputs the engine rejects are a finding too: a run cannot record
    a decision from inputs the engine would not accept (fail closed).
    """
    expected = "decide(recorded inputs) equals the recorded decision and policies_version"
    engine = engine or PolicyEngine.load()
    observed = PolicyDecision.model_validate(recorded).model_dump(mode="json")
    try:
        got = engine.decide(DecisionInput.model_validate(inputs)).model_dump(mode="json")
    except ValidationError as e:
        return _finding("A1", "critical", {"inputs": f"rejected by the engine: {e.error_count()} error(s)"}, expected)
    return _finding("A1", "critical", _diff(got, observed), expected)


def check_deadline(stored: Union[Deadline, Mapping[str, Any]], *, abroad: bool = False,
                   charged_at: Union[dt.date, dt.datetime, None] = None, noticed_at: Optional[dt.datetime] = None,
                   policies: Optional[Policies] = None) -> Finding:
    """A2: `clock.deadline()` on the case's country, product and opening date equals every stored deadline field.

    `abroad`, `charged_at` and `noticed_at` are the case's recorded inputs to the clock (MX needs the charge date).
    A country without a verified entry must be stored as POL-CLOCK-UNKNOWN with no dates: an invented date differs
    from the recomputed null and is a finding; the recorded unknown passes.
    """
    stored_d = Deadline.model_validate(stored)
    try:
        got = deadline(stored_d.country, stored_d.product, stored_d.opened_on, abroad=abroad, charged_at=charged_at,
                       noticed_at=noticed_at, policies=policies)
    except ValueError as e:   # [assumption] a record that lacks the clock's input (MX charge date) is a finding, not a crash
        return _finding("A2", "critical", {"inputs": str(e)}, "a recorded case the clock can re-derive")
    return _finding("A2", "critical", _diff(got.model_dump(mode="json"), stored_d.model_dump(mode="json")),
                    "clock.deadline() on the case's country, product and opening date equals the stored deadlines")
