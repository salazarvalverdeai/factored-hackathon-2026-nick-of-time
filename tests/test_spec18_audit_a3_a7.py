"""Spec 18 AC-01 — checks A3–A7 are pure functions that pass on a clean recorded run and fail on a faulty one.

`run_ok.json` is a clean run; `run_bad.json` holds dotted-path edits on it that stack several faults per check. The
single-fault tests apply one edit to `run_ok`, so each rule is pinned on its own.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from nick_of_time.audit import (ActionRead, LifecycleEvent, check_actions, check_coherence, check_grounding,
                                check_lifecycle, check_privacy)
from nick_of_time.contracts import ActionRecord, CustomerReceipt, StatusReply, load_schema

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
    return check_actions([ActionRecord(**a) for a in run["actions"]], [ActionRead(**r) for r in run["verified_reads"]],
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
CASE = "A-71C0D5E8A2F3"
NO_BLOCK_READ = {k: "no action_verified read with V-8B2D41C7E0A9" for k in BLOCK_KEYS}


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


def test_ac_01_run_ok_handoff_follows_its_schema():
    jsonschema.validate(OK["handoff"], load_schema("handoff.schema.json"), format_checker=jsonschema.FormatChecker())


def test_ac_06_nothing_to_check_is_not_applicable():
    assert check_actions([], []).status == "not_applicable"
    assert check_coherence([]).status == "not_applicable"
    assert check_lifecycle([]).status == "not_applicable" and check_lifecycle([]).observed == {}


# ---------- A3 (D-025: the verifying read mints the V- id in an action_verified event) ----------
def test_ac_01_a3_names_every_surface_without_its_read():
    assert a3(BAD).observed == {**NO_BLOCK_READ,
                                CASE: "claims 2026-06-01T15:04:12+00:00, read at 2026-06-01T15:04:09+00:00"}


def test_ac_01_a3_no_verifying_read_alone():
    assert a3(edit({"verified_reads": OK["verified_reads"][:1]})).observed == NO_BLOCK_READ


def test_ac_01_a3_a_v_id_no_read_minted_is_not_evidence():
    """The claims cite V-8B2D41C7E0A9 (as if copied from a write's output); the block's read minted another id."""
    assert a3(edit({"verified_reads.1.verification_id": "V-FFFFFFFFFFFF"})).observed == NO_BLOCK_READ


def test_ac_01_a3_a_v_id_read_for_another_action_is_not_evidence():
    assert a3(edit({"verified_reads.1.action_id": CASE})).observed == NO_BLOCK_READ


def test_ac_01_a3_read_before_the_request_fails_and_the_same_second_passes():
    late = edit({"verified_reads.1.requested_at": "2026-06-01T15:04:12Z"})
    assert a3(late).observed == {k: "post-condition read before the request" for k in BLOCK_KEYS}
    assert a3(edit({"verified_reads.1.requested_at": "2026-06-01T15:04:11Z"})).status == "passed"


def test_ac_01_a3_the_claimed_time_must_equal_the_read():
    run = edit({"receipt.actions.0.verified_at": "2026-06-01T15:04:10Z"})
    claim = "claims 2026-06-01T15:04:10+00:00, read at 2026-06-01T15:04:11+00:00"
    assert a3(run).observed == {f"receipt:{BLOCK}": claim}


def test_ac_01_a3_any_read_of_the_action_backs_the_claim_that_cites_it():
    again = {**OK["verified_reads"][1], "verification_id": "V-AAAAAAAAAAAA", "read_at": "2026-06-01T15:04:20Z"}
    assert a3(edit({"verified_reads.2": again})).status == "passed"


def test_ac_01_a3_receipt_says_verified_without_a_read():
    run = edit({"actions": OK["actions"][:1], "verified_reads": OK["verified_reads"][1:]})
    assert a3(run).observed == {f"receipt:{CASE}": "no action_verified read with V-0C6A93F1B57D"}


def test_ac_01_a3_handoff_says_verified_without_a_read():
    assert check_actions([], [], handoff=OK["handoff"]).observed == {f"handoff:{BLOCK}": NO_BLOCK_READ[BLOCK]}


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
                                         ("Son 1.250 pesos", 1250), ("Son 0,75 USD", 0.75),
                                         ("Son COP 3 500 000", 3500000), ("Son COP 3\u00a0500\u00a0000,00", 3500000)])
def test_ac_01_a4_amounts_are_locale_aware(text, known):
    assert check_grounding([{"amount": known}], reply=text).status == "passed"


def test_ac_01_a4_a_wrong_amount_in_another_locale_is_found():
    f = check_grounding([{"amount": 1300.0}], reply="Son R$ 1.250,00")
    assert f.observed == {"reply": ["1250"]}
    assert check_grounding([{"amount": 15}], reply="Son 1,5 días").observed == {"reply": ["1.5"]}
    assert check_grounding([{"amount": 125}], reply="Son 0.125").observed == {"reply": ["0.125"]}
    assert check_grounding([{"amount": 3500000}], reply="Son COP 3 600 000").observed == {"reply": ["3600000"]}


def test_ac_01_a4_a_timestamp_states_its_date_not_its_clock():
    read = [{"read_at": "2026-06-01T15:04:03Z"}]
    f = check_grounding(read, reply="Te devolvemos en 3 días hábiles.", policy_facts=["2"])
    assert f.observed == {"reply": ["3"]}
    assert check_grounding(read, reply="Verificado el 2026-06-01.").status == "passed"


@pytest.mark.parametrize("key, value, ungrounded", [
    ("deadline_source", "Banxico Circular 9/2012", ["9"]),
    ("source_url", "https://www.dof.gob.mx/nota_detalle.php?codigo=5539863", ["5539863"]),
    ("verified_on", "2026-09-30", ["2026-09-30"])])
def test_ac_01_a4_the_legal_source_is_a_tool_fact(key, value, ungrounded):
    assert a4(edit({f"receipt.deadline.{key}": value})).observed == {"receipt": ungrounded}


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
    assert check_privacy({"notification": "Tu caso no cambió."}, transcript=["no"]).status == "passed"


def test_ac_01_a6_transcript_applies_to_notifications_only():
    said = "no reconozco este cargo"
    assert check_privacy({"reply": f"Entiendo: {said}."}, transcript=[said]).status == "passed"
    assert check_privacy({"notification": f"Entiendo: {said}."}, transcript=[said]).status == "finding"
    assert check_privacy({"notification": f"{said}ado"}, transcript=[said]).status == "passed"
    f = check_privacy({"notification": "Dijo: no reconozco ESTE CARGO."}, transcript=["No Reconozco este cargo"])
    assert f.observed == {"notification": ["transcript:No Reconozco este cargo"]}


@pytest.mark.parametrize("text", ["Plazo 2026-05-31 2026-06-01.", "MX debit 2026-06-03 2026-06-07",
                                  "Llama al 5215512345679.", f"Cargo {TX}."])
def test_ac_01_a6_card_regex_needs_luhn(text):
    assert check_privacy({"reply": text}).status == "passed"


@pytest.mark.parametrize("cvv", ["código de seguridad", "código de segurança"])
def test_ac_01_a6_card_with_luhn_and_cvv_in_spanish_and_portuguese(cvv):
    f = check_privacy({"reply": f"Tarjeta 4111-1111-1111-1111, {cvv} 123"})
    assert f.observed == {"reply": ["card_number", "cvv"]}


@pytest.mark.parametrize("text", ["Score 62,5.", "Puntaje: 62.5", "Tu puntaje es 62."])
def test_ac_01_a6_score_in_any_number_format(text):
    assert check_privacy({"reply": text}, score=62.0 if text.endswith("62.") else 62.5).observed == {"reply": ["score"]}


@pytest.mark.parametrize("text, flagged", [
    ("Te devolvemos en 10 días hábiles.", False),
    ("Tu puntaje no cambia nada de tu caso, que sigue igual. Plazo: 10 días hábiles.", False),
    ("Tu riesgo: 10. Te devolvemos en 10 días hábiles.", True)])
def test_ac_01_a6_the_score_needs_a_score_word_nearby(text, flagged):
    assert check_privacy({"reply": text}, score=10).observed == ({"reply": ["score"]} if flagged else {})


def test_ac_01_a6_score_equal_to_an_amount_is_not_flagged():
    assert check_privacy({"reply": "Riesgo bajo: son USD 50.00 el 2026-06-03."}, score=50).status == "passed"
    assert check_privacy({"reply": "Tu puntaje no cambia: son 50,00 USD."}, score=50.0).status == "passed"


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


def test_ac_01_a7_an_analyst_without_a_sub_is_not_a_person():
    f = check_lifecycle(events(("new", "agent"), ("verification", "agent"), ("resolved", "analyst:a"),
                               ("closed", "analyst:")))
    assert f.observed == {"K-1": ["closed by analyst:, not a person"]}


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
