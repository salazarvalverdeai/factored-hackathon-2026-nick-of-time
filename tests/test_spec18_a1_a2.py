"""Spec 18 AC-01 — checks A1 (decision) and A2 (deadline) re-derive with the engine and the clock and fail on drift.

`decision_deadline.json` holds a recorded decision with its inputs, and the case rows exactly as the store writes
them (`NewCase.model_dump`) with their transactions for MX (charge date), AR (holiday skipped) and ZZ (unknown).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nick_of_time.audit import check_deadline, check_decision

FX = json.loads((Path(__file__).parent / "fixtures" / "audit" / "decision_deadline.json").read_text())
DEC, DL = FX["decision"], FX["deadlines"]


def a2(country: str, **case_edits):
    row = copy.deepcopy(DL[country])
    return check_deadline({**row["case"], **case_edits}, row["transaction"])


def test_ac01_a1_passes_on_the_recorded_decision():
    f = check_decision(DEC["inputs"], DEC["recorded"])
    assert (f.check_id, f.severity, f.status, f.observed) == ("A1", "critical", "passed", {})


@pytest.mark.parametrize("edit", [{"decision": "handoff"}, {"zone": "medium"}, {"rule_ids": ["POL-ZONE-HIGH"]},
                                  {"allowed_actions": ["open_case"]}, {"queue_status_after": "review"}])
def test_ac01_a1_fails_when_the_recorded_decision_differs(edit):
    f = check_decision(DEC["inputs"], {**DEC["recorded"], **edit})
    assert f.status == "finding" and set(edit) <= set(f.observed)


def test_ac01_a1_fails_when_the_policies_version_differs():
    f = check_decision(DEC["inputs"], {**DEC["recorded"], "policies_version": 1})
    assert f.status == "finding" and list(f.observed) == ["policies_version"]


def test_ac01_a1_fails_when_the_inputs_change_the_outcome():
    f = check_decision({**DEC["inputs"], "score": 10.0}, DEC["recorded"])
    assert f.status == "finding" and "zone" in f.observed


def test_ac01_a1_fails_closed_on_inputs_or_a_decision_the_models_reject():
    assert check_decision({**DEC["inputs"], "intent": "invented"}, DEC["recorded"]).status == "finding"
    assert check_decision(DEC["inputs"], {"decision": "nonsense"}).status == "finding"


@pytest.mark.parametrize("country", ["MX", "AR", "ZZ"])
def test_ac01_a2_passes_on_the_deadlines_a_case_row_stores(country):
    f = a2(country)
    assert (f.check_id, f.severity, f.status, f.observed) == ("A2", "critical", "passed", {})


@pytest.mark.parametrize("field,value", [("credit_deadline", "2026-06-04"), ("ruling_deadline", "2026-06-17"),
                                         ("deadline_source", "Another rule"),
                                         ("deadline_source_url", "https://example.com/"),
                                         ("deadline_verified_on", "2026-01-01")])
def test_ac01_a2_fails_when_any_stored_field_differs(field, value):
    f = a2("AR", **{field: value})
    assert f.status == "finding" and list(f.observed) == [field]


def test_ac01_a2_fails_when_the_mx_credit_date_is_moved():
    f = a2("MX", credit_deadline="2026-06-05")
    assert f.status == "finding" and list(f.observed) == ["credit_deadline"]


def test_ac01_a2_fails_on_an_invented_date_for_an_unknown_country():
    f = a2("ZZ", ruling_deadline="2026-06-16", deadline_source="Invented",
           deadline_source_url="https://example.com/", deadline_verified_on="2026-10-04")
    assert f.status == "finding" and "ruling_deadline" in f.observed


def test_ac01_a2_mx_charge_outside_the_window_changes_the_expected_deadline():
    row = copy.deepcopy(DL["MX"])
    row["transaction"]["transaction_date"] = "2026-01-01"
    assert check_deadline(row["case"], row["transaction"]).status == "finding"


def test_ac01_a2_fails_closed_on_a_row_the_store_model_rejects():
    row = DL["AR"]
    assert check_deadline({**row["case"], "deadline_source_url": "ftp://x"}, row["transaction"]).status == "finding"
