"""Spec 18 AC-01 — checks A1 (decision) and A2 (deadline) re-derive with the engine and the clock and fail on drift.

`decision_deadline.json` holds a recorded decision with its inputs and the stored deadlines of three countries (MX
with its charge date, AR with a holiday skipped, ZZ unknown), all produced by the code under test at policies v2.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from nick_of_time.audit import check_deadline, check_decision

FX = json.loads((Path(__file__).parent / "fixtures" / "audit" / "decision_deadline.json").read_text())
DEC, DL = FX["decision"], FX["deadlines"]


def a2(country: str, **stored_edits):
    case = copy.deepcopy(DL[country])
    case["stored"].update(stored_edits)
    charged = dt.datetime.fromisoformat(case["charged_at"]) if "charged_at" in case else None
    return check_deadline(case["stored"], charged_at=charged)


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


def test_ac01_a1_fails_closed_on_inputs_the_engine_rejects():
    assert check_decision({**DEC["inputs"], "intent": "invented"}, DEC["recorded"]).status == "finding"


@pytest.mark.parametrize("country", ["MX", "AR", "ZZ"])
def test_ac01_a2_passes_on_the_stored_deadlines(country):
    f = a2(country)
    assert (f.check_id, f.severity, f.status, f.observed) == ("A2", "critical", "passed", {})


@pytest.mark.parametrize("field,value", [("credit_deadline", "2026-06-04"), ("ruling_deadline", "2026-06-17"),
                                         ("policies_version", 1), ("holidays_skipped", [])])
def test_ac01_a2_fails_when_any_stored_deadline_differs(field, value):
    f = a2("AR", **{field: value})
    assert f.status == "finding" and list(f.observed) == [field]


def test_ac01_a2_fails_when_the_mx_credit_date_is_moved():
    f = a2("MX", credit_deadline="2026-06-05")
    assert f.status == "finding" and list(f.observed) == ["credit_deadline"]


def test_ac01_a2_fails_on_an_invented_date_for_an_unknown_country():
    f = a2("ZZ", ruling_deadline="2026-06-16", rule_ids=[])
    assert f.status == "finding" and {"ruling_deadline", "rule_ids"} <= set(f.observed)


def test_ac01_a2_unknown_country_dropping_the_unknown_marker_is_a_finding():
    assert a2("ZZ", rule_ids=[]).status == "finding"


def test_ac01_a2_mx_without_the_charge_date_is_a_finding_not_a_crash():
    f = check_deadline(DL["MX"]["stored"])   # the charge date is a recorded input; without it the clock cannot match
    assert f.status == "finding" and "charged_at" in f.observed["inputs"]
