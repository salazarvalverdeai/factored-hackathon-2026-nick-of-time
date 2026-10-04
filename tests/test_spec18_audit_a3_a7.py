"""Spec 18 AC-01 — checks A3–A7 are pure functions that pass on a clean recorded run and fail on a faulty one."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nick_of_time.audit import (ActionRead, CaseEvent, check_actions, check_coherence, check_grounding,
                                check_lifecycle, check_privacy)
from nick_of_time.contracts import ActionRecord, CustomerReceipt, StatusReply

FIXTURES = Path(__file__).parent / "fixtures" / "audit"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


OK, BAD = _load("run_ok.json"), _load("run_bad.json")


def a3(run):
    return check_actions([ActionRecord(**a) for a in run["actions"]], [ActionRead(**r) for r in run["db_actions"]])


def a4(run):
    return check_grounding(run["tool_results"], reply=run["reply"], receipt=CustomerReceipt(**run["receipt"]),
                           handoff=run["handoff"])


def a5(run):
    return check_coherence([StatusReply(**s) for s in run["status_replies"]],
                           told_queue_status=run["told_queue_status"], read_queue_status=run["read_queue_status"])


def a6(run):
    return check_privacy(**run["privacy"])


def a7(run):
    return check_lifecycle([CaseEvent(**e) for e in run["events"]], active_cases=[tuple(c) for c in run["active_cases"]])


CHECKS = {"A3": a3, "A4": a4, "A5": a5, "A6": a6, "A7": a7}


@pytest.mark.parametrize("check_id", CHECKS)
def test_ac_01_pass_fixture_passes_and_is_deterministic(check_id):
    first = CHECKS[check_id](OK)
    assert first.check_id == check_id and first.passed
    assert CHECKS[check_id](OK) == first


@pytest.mark.parametrize("check_id", CHECKS)
def test_ac_01_fail_fixture_fails_with_its_evidence(check_id):
    f = CHECKS[check_id](BAD)
    assert f.check_id == check_id and not f.passed and f.observed != f.expected


def test_ac_01_a3_names_the_action_the_database_does_not_confirm():
    assert a3(BAD).observed == {"A-3E9F20B7C164": "database says requested None"}


def test_ac_01_a3_read_before_the_request_fails():
    run = json.loads(json.dumps(OK))
    run["db_actions"][0]["requested_at"] = "2026-06-01T15:04:10Z"
    assert a3(run).observed == {"A-3E9F20B7C164": "post-condition not read after the request"}


def test_ac_01_a4_lists_each_ungrounded_value_per_surface():
    obs = a4(BAD).observed
    assert obs["reply"] == ["1300", "2026-06-02"]
    assert obs["receipt"] == ["999"] and obs["handoff"] == ["TRX-INVENTED00000000009"]


def test_ac_01_a4_normalises_amounts_and_accepts_policy_facts():
    assert check_grounding([{"amount": 1250.0}], reply="Son USD 1,250.00 y 10 días hábiles", policy_facts=["10"]).passed


def test_ac_01_a5_reports_told_vs_read():
    assert a5(BAD).observed == {"K-104233": {"told": "resolved", "read": "verification"},
                                "case": {"told": "resolved", "read": "verification"}}


def test_ac_01_a6_flags_internals_card_cvv_and_other_customers():
    obs = a6(BAD).observed
    assert obs["reply"] == ["policy_id:P-ZONE-HIGH", "score", "card_number", "cvv"]
    assert obs["notification"] == ["transcript:no reconozco este cargo", "other_customer:C-OTHER0000001"]


def test_ac_01_a6_final_state_flag_alone_fails():
    f = check_privacy({"reply": "ok"}, other_customer_data_exposed=True)
    assert not f.passed and f.observed == {"final_state": ["other_customer_data_exposed"]}


def test_ac_01_a7_flags_transitions_person_and_duplicates():
    obs = a7(BAD).observed
    assert obs["K-104233"] == ["invalid transition new -> closed", "closed by agent, not a person",
                               "provisional credit not decided by a person"]
    assert obs["duplicate:TRX-FIXTURE0000000000001"] == ["K-104233", "K-200001"]
