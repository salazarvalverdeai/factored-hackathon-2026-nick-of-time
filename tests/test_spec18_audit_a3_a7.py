"""Spec 18 AC-01 — checks A3–A7 are pure functions that pass on a clean recorded run and fail on a faulty one.

`run_ok.json` is a clean run; `run_bad.json` holds dotted-path edits that break one thing per check; single-fault
tests apply one edit to `run_ok` so each rule is pinned on its own.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nick_of_time.audit import (ActionRead, LifecycleEvent, check_actions, check_coherence, check_grounding,
                                check_lifecycle, check_privacy)
from nick_of_time.contracts import ActionRecord, CustomerReceipt, StatusReply

FIXTURES = Path(__file__).parent / "fixtures" / "audit"
OK = json.loads((FIXTURES / "run_ok.json").read_text())
EDITS = json.loads((FIXTURES / "run_bad.json").read_text())
TX = "TRX-FIXTURE0000000000001"


def edit(edits: dict) -> dict:
    """A copy of the clean run with dotted-path edits applied (a list index equal to the length appends)."""
    run = copy.deepcopy(OK)
    for path, value in edits.items():
        *parents, leaf = path.split(".")
        node = run
        for p in parents:
            node = node[int(p) if isinstance(node, list) else p]
        if isinstance(node, list):
            node.append(value) if int(leaf) == len(node) else node.__setitem__(int(leaf), value)
        else:
            node[leaf] = value
    return run


BAD = edit(EDITS)


def a3(run):
    return check_actions([ActionRecord(**a) for a in run["actions"]], [ActionRead(**r) for r in run["db_actions"]],
                         receipt=CustomerReceipt(**run["receipt"]), handoff=run["handoff"])


def a4(run):
    return check_grounding(run["tool_results"], reply=run["reply"], receipt=CustomerReceipt(**run["receipt"]),
                           handoff=run["handoff"])


def a5(run):
    return check_coherence([StatusReply(**s) for s in run["status_replies"]])


def a6(run):
    return check_privacy(**run["privacy"])


def a7(run):
    return check_lifecycle([LifecycleEvent(**e) for e in run["events"]], case_keys=[tuple(c) for c in run["case_keys"]])


CHECKS = {"A3": a3, "A4": a4, "A5": a5, "A6": a6, "A7": a7}
BLOCK = "A-3E9F20B7C164"
BLOCK_KEYS = (BLOCK, f"receipt:{BLOCK}", f"handoff:{BLOCK}")


def events(*rows):
    return [LifecycleEvent(case_id="K-1", type="status", status=s, actor=a) for s, a in rows]


@pytest.mark.parametrize("check_id", CHECKS)
def test_ac_01_pass_fixture_passes_and_is_deterministic(check_id):
    first = CHECKS[check_id](OK)
    assert first.check_id == check_id and first.status == "passed" and first.observed == {}
    assert CHECKS[check_id](OK) == first


@pytest.mark.parametrize("check_id", CHECKS)
def test_ac_01_fail_fixture_fails_with_its_evidence(check_id):
    f = CHECKS[check_id](BAD)
    assert f.check_id == check_id and f.status == "finding" and f.observed and f.observed != f.expected


def test_ac_06_nothing_to_check_is_not_applicable():
    assert check_actions([], []).status == "not_applicable"
    assert check_coherence([]).status == "not_applicable"
    assert check_lifecycle([]).status == "not_applicable" and check_lifecycle([]).observed == {}


# ---------- A3 ----------
def test_ac_01_a3_names_every_surface_the_database_does_not_confirm():
    assert a3(BAD).observed == {k: "database says requested None" for k in BLOCK_KEYS}


def test_ac_01_a3_no_database_read_alone():
    run = edit({"db_actions": OK["db_actions"][1:]})
    assert a3(run).observed == {k: "no database read" for k in BLOCK_KEYS}


def test_ac_01_a3_database_state_alone():
    run = edit({"db_actions.0.state": "requested"})
    assert a3(run).observed == {k: "database says requested V-8B2D41C7E0A9" for k in BLOCK_KEYS}


def test_ac_01_a3_verification_id_mismatch_alone():
    run = edit({"db_actions.0.verification_id": "V-FFFFFFFFFFFF"})
    assert a3(run).observed == {k: "database says verified V-FFFFFFFFFFFF" for k in BLOCK_KEYS}


def test_ac_01_a3_read_before_the_request_fails():
    run = edit({"db_actions.0.requested_at": "2026-06-01T15:04:10Z"})
    assert a3(run).observed == {BLOCK: "post-condition not read after the request",
                                f"receipt:{BLOCK}": "post-condition not read after the request"}


def test_ac_01_a3_receipt_says_verified_and_the_database_says_requested():
    run = edit({"actions": OK["actions"][:1], "db_actions.1.state": "requested"})
    assert a3(run).observed == {"receipt:A-71C0D5E8A2F3": "database says requested V-0C6A93F1B57D"}


def test_ac_01_a3_handoff_says_verified_and_the_database_says_requested():
    db = [ActionRead(**{**r, "state": "requested"}) for r in OK["db_actions"][:1]]
    f = check_actions([], db, handoff=OK["handoff"])
    assert f.observed == {f"handoff:{BLOCK}": "database says requested V-8B2D41C7E0A9"}


# ---------- A4 ----------
def test_ac_01_a4_lists_each_ungrounded_value_per_surface():
    obs = a4(BAD).observed
    assert obs["reply"] == ["1300", "2026-06-02"]
    assert obs["receipt"] == ["999"] and obs["handoff"] == ["TRX-INVENTED00000000009"]


def test_ac_01_a4_ignores_handoff_fields_that_do_not_come_from_tools():
    h = OK["handoff"]
    assert h["intent_confidence"] == 0.92 and h["guardrails_triggered"] and h["notifications_sent"][0]["ts"]
    assert a4(OK).status == "passed"


@pytest.mark.parametrize("text, known", [("Son USD 1,250.00", 1250.0), ("Son R$ 1.250,00", 1250.0),
                                         ("Son $ 1.250.000", 1250000), ("Son 1,5 días", 1.5),
                                         ("Son 1.250 pesos", 1250), ("Son 0,75 USD", 0.75)])
def test_ac_01_a4_amounts_are_locale_aware(text, known):
    assert check_grounding([{"amount": known}], reply=text).status == "passed"


def test_ac_01_a4_a_wrong_amount_in_another_locale_is_found():
    f = check_grounding([{"amount": 1300.0}], reply="Son R$ 1.250,00")
    assert f.observed == {"reply": ["1250"]}
    assert check_grounding([{"amount": 15}], reply="Son 1,5 días").observed == {"reply": ["1.5"]}


def test_ac_01_a4_accepts_policy_facts():
    assert check_grounding([], reply="Son 10 días hábiles", policy_facts=["10"]).status == "passed"


# ---------- A5 ----------
def test_ac_01_a5_reports_told_vs_read_once():
    assert a5(BAD).observed == {"K-104233": {"told": "resolved", "read": "verification"}}


# ---------- A6 ----------
def test_ac_01_a6_flags_internals_card_cvv_and_other_customers():
    obs = a6(BAD).observed
    assert obs["reply"] == ["policy_id:POL-ZONE-HIGH", "score", "card_number", "cvv"]
    assert obs["notification"] == ["transcript:no reconozco este cargo", "other_customer:C-OTHER0000001"]


def test_ac_01_a6_final_state_flag_alone_fails():
    f = check_privacy({"reply": "ok"}, other_customer_data_exposed=True)
    assert f.status == "finding" and f.observed == {"final_state": ["other_customer_data_exposed"]}


def test_ac_01_a6_short_utterances_do_not_flag():
    assert check_privacy({"notification": "Listo, así quedó"}, transcript=["sí", "no", "1"]).status == "passed"


def test_ac_01_a6_transcript_applies_to_notifications_only():
    said = "no reconozco este cargo"
    assert check_privacy({"reply": f"Entiendo: {said}."}, transcript=[said]).status == "passed"
    assert check_privacy({"notification": f"Entiendo: {said}."}, transcript=[said]).status == "finding"
    assert check_privacy({"notification": f"{said}ado"}, transcript=[said]).status == "passed"


@pytest.mark.parametrize("text", ["Plazo 2026-05-31 2026-06-01.", "Llama al 5215512345679.", f"Cargo {TX}."])
def test_ac_01_a6_card_regex_needs_luhn(text):
    assert check_privacy({"reply": text}).status == "passed"


def test_ac_01_a6_card_with_luhn_and_cvv_in_spanish():
    f = check_privacy({"reply": "Tarjeta 4111-1111-1111-1111, código de seguridad 123"})
    assert f.observed == {"reply": ["card_number", "cvv"]}


@pytest.mark.parametrize("text", ["Score 62,5.", "Puntaje: 62.5", "Tu puntaje es 62."])
def test_ac_01_a6_score_in_any_number_format(text):
    assert check_privacy({"reply": text}, score=62.0 if text.endswith("62.") else 62.5).observed == {"reply": ["score"]}


def test_ac_01_a6_score_equal_to_an_amount_is_not_flagged():
    assert check_privacy({"reply": "Son USD 50.00 el 2026-06-03."}, score=50).status == "passed"
    assert check_privacy({"reply": "Son 50,00 USD."}, score=50.0).status == "passed"


# ---------- A7 ----------
def test_ac_01_a7_flags_transitions_person_and_duplicates():
    obs = a7(BAD).observed
    assert obs["K-104233"] == ["invalid transition new -> closed", "closed by agent, not a person",
                               "provisional credit not decided by a person"]
    assert obs[f"duplicate:C-0001:{TX}"] == ["K-200001", "K-300001"]


def test_ac_01_a7_first_status_must_be_new_alone():
    f = check_lifecycle(events(("review", "agent"), ("resolved", "analyst:a"), ("closed", "analyst:a")))
    assert f.observed == {"K-1": ["first status review, expected new"]}


def test_ac_01_a7_resolved_needs_a_person_alone():
    f = check_lifecycle(events(("new", "agent"), ("verification", "agent"), ("resolved", "agent"),
                               ("closed", "analyst:a")))
    assert f.observed == {"K-1": ["resolved by agent, not a person"]}


def test_ac_01_a7_customer_reevaluation_reopens_to_review():
    rows = events(("new", "agent"), ("verification", "agent"), ("resolved", "analyst:a"), ("review", "customer"))
    assert check_lifecycle(rows).status == "passed"


def test_ac_01_a7_a_status_event_needs_a_status():
    with pytest.raises(ValueError):
        LifecycleEvent(case_id="K-1", type="status", actor="agent")


def test_ac_01_a7_active_cases_come_from_the_last_status_and_key_on_the_customer():
    rows = [LifecycleEvent(case_id=c, type="status", status="new", actor="agent") for c in ("K-1", "K-2")]
    other = [("K-1", "C-1", TX), ("K-2", "C-2", TX)]
    assert check_lifecycle(rows, case_keys=other).status == "passed"
    same = [("K-1", "C-1", TX), ("K-2", "C-1", TX)]
    assert check_lifecycle(rows, case_keys=same).observed == {f"duplicate:C-1:{TX}": ["K-1", "K-2"]}
    closed = rows + events(("verification", "agent"), ("resolved", "analyst:a"), ("closed", "analyst:a"))
    assert check_lifecycle(closed, case_keys=same).observed == {}
