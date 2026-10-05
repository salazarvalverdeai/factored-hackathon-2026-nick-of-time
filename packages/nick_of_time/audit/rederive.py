"""Checks A1–A2 of spec 18 §4.1: re-run the policy engine and the regulatory clock on a run's recorded inputs.

They re-derive, they never decide: the recorded decision and the stored deadlines are compared with what the same code
gives today on the same inputs. Pure: no network, no store, no LLM; the clock is called with the case's own dates, so
nothing reads the system clock (ADR 0020).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Union

from pydantic import ValidationError

from contracts.tools import Transaction

from nick_of_time.audit.checks import Finding, _finding
from nick_of_time.policy import DecisionInput, Policies, PolicyDecision, PolicyEngine
from nick_of_time.policy.clock import deadline
from nick_of_time.store import NewCase


def _diff(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: {"expected": expected[k], "observed": observed.get(k)} for k in expected if expected[k] != observed.get(k)}


def check_decision(inputs: Union[DecisionInput, Mapping[str, Any]], recorded: Union[PolicyDecision, Mapping[str, Any]],
                   *, engine: Optional[PolicyEngine] = None) -> Finding:
    """A1: `decide()` on the recorded inputs gives the recorded decision, with the same `policies_version`.

    Every field of the decision is compared (rule ids, zone, modes, allowed actions, queue status), so a recorded
    decision that is merely similar is a finding. Inputs or a decision the models reject are a finding too, never an
    exception (fail closed). Audits against the policies.yaml in force now (spec 18 §6).
    """
    expected = "decide(recorded inputs) equals the recorded decision and policies_version"
    engine = engine or PolicyEngine.load()
    try:
        observed = PolicyDecision.model_validate(recorded).model_dump(mode="json")
    except ValidationError as e:
        return _finding("A1", "critical", {"record": f"rejected: {e.error_count()} error(s)"}, expected)
    try:
        got = engine.decide(DecisionInput.model_validate(inputs)).model_dump(mode="json")
    except ValidationError as e:
        return _finding("A1", "critical", {"inputs": f"rejected: {e.error_count()} error(s)"}, expected)
    return _finding("A1", "critical", _diff(got, observed), expected)


def check_deadline(case: Union[NewCase, Mapping[str, Any]], transaction: Union[Transaction, Mapping[str, Any]], *,
                   policies: Optional[Policies] = None) -> Finding:
    """A2: `clock.deadline()` on the case's country, product and opening date equals the deadlines the case stores.

    Compares only what a case row holds: both dates, `deadline_source` (vs the entry's `source`), `deadline_source_url`
    and `deadline_verified_on`. `charged_at` is the transaction's `transaction_date`. [assumption] `abroad` is False
    (no field records it) and `noticed_at` is not passed (a case holds a date, not a time): an entry with an hours
    window cannot be re-derived and is a finding. A country with no verified entry (POL-CLOCK-UNKNOWN) must store
    both dates and the provenance as null: an invented date is a finding. Audits against the policies.yaml in force now.
    """
    expected = "clock.deadline() on the case's country, product and opening date equals the stored deadlines"
    try:
        c = NewCase.model_validate({k: v for k, v in dict(case if isinstance(case, Mapping) else case.model_dump())
                                    .items() if k in NewCase.model_fields})
        tx = (Transaction.model_validate({k: v for k, v in transaction.items() if k in Transaction.model_fields})
              if isinstance(transaction, Mapping) else transaction)   # a gold row's extra columns are not a finding
    except ValidationError as e:
        return _finding("A2", "critical", {"recorded": f"rejected: {e.error_count()} error(s)"}, expected)
    try:
        got = deadline(c.country, c.product_type, c.opened_on, charged_at=tx.transaction_date, policies=policies)
    except ValueError as e:   # [assumption] a record that lacks a clock input is a finding, not a crash
        return _finding("A2", "critical", {"inputs": str(e)}, expected)
    want = {"credit_deadline": got.credit_deadline, "ruling_deadline": got.ruling_deadline,
            "deadline_source": got.deadline_source, "deadline_source_url": got.source_url,
            "deadline_verified_on": got.verified_on}
    have = {k: getattr(c, k) for k in want}
    return _finding("A2", "critical", _diff({k: _j(v) for k, v in want.items()}, {k: _j(v) for k, v in have.items()}),
                    expected)


def _j(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v
