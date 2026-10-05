"""Spec 04 task 04d (T5): respond — the receipt, the handoff card, the grounding gate (G-OUT-01) and the chips, on the
fake MCP (FastMCP in-memory client). No LLM, no network; replay today is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

import itertools
import json

import pytest

from contracts.tools import ToolError
from nick_of_time import receipt as msg
from nick_of_time.audit.checks import check_grounding
from nick_of_time.contracts import CustomerReceipt
from nick_of_time.receipt import build
from tests.test_spec04_act import DOWN, EV_0001, EXPIRED
from tests.test_spec04_decide import TRX, score, server
from tests.test_spec04_graph import PERSON, Chat, fake, labels

CASE, CARD, OPENED = fake.FIXTURES["get_case"], fake.FIXTURES["get_product_status"], fake.FIXTURES["open_case"]
HELD = ToolError(code="DENY", policy_id="POL-HUMAN-REQUEST", message="a call request holds the block")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "DEMO_TODAY", "MCP_URL"):
        monkeypatch.delenv(name, raising=False)


def test_ac_21_ac_01_ev_0001_receipt_has_last4_verification_case_deadline_and_next_step():
    turn = Chat(mcp_transport=server()).say(EV_0001, language="es")
    r = turn.receipt
    assert (r.case_id, r.product_last4, r.mode, r.issued_at.isoformat()) == ("K-104233", "4417", "replay",
                                                                             "2026-06-01T15:04:11+00:00")
    assert [(a.label, a.verification_id) for a in r.actions] == [("Apertura del caso", "V-0C6A93F1B57D"),
                                                                 ("Bloqueo de la tarjeta", "V-8B2D41C7E0A9")]
    assert (str(r.deadline.credit_deadline), r.deadline.deadline_source) == ("2026-06-03", CASE["deadline_source"])
    assert r.what_ai_did == msg.text("receipt.what_ai_did_blocked", "es")
    assert r.what_a_person_does == msg.text("receipt.what_a_person_does", "es")
    assert {f.source_id for f in r.verified_facts} == {TRX["transaction_id"], "K-104233", "V-8B2D41C7E0A9"}
    assert "score" not in json.dumps(r.model_dump(mode="json")) and "POL-" not in turn.reply   # never_send
    assert "Caso K-104233 abierto y verificado (verificación V-0C6A93F1B57D, 2026-06-01 15:04 UTC)." in [
        f.fact for f in r.verified_facts]                                                     # D-051
    assert "G-OUT-01" not in turn.guardrails_triggered and len(turn.handoff["verified_facts"]) == 5
    assert "copilot_proposal" not in turn.handoff     # the block is verified: nothing to approve (M30)


@pytest.mark.parametrize("source", ["dataset", "synthetic"])
def test_ac_12_human_zone_hands_off_a_card_that_validates_with_requires_human(source):
    turn = Chat(mcp_transport=server(get_fraud_score=score(12.0, source))).say(EV_0001, language="es")
    card = turn.handoff                              # TurnResult validated it against handoff.schema.json
    assert (card["zone"], card["handoff_reason"], card["copilot_proposal"]["requires_human"]) == ("human", "zone_human",
                                                                                                 True)
    # D-033: the score's own source and version, so a synthetic one is shown as [simulated]
    assert (card["score"], card["score_source"], card["score_version"]) == (12.0, source, "gold-v1")
    assert "G-OUT-01" not in turn.guardrails_triggered and len(card["verified_facts"]) == 4
    assert card["verified_facts"][-1] == {"fact": "decision handoff, zone human", "source_id": "POL-ZONE-HUMAN"}


def test_ac_11_medium_zone_once_confirmed_hands_off_with_approve_block():
    chat = Chat(mcp_transport=server(get_fraud_score=score(35.0)))
    assert chat.say(EV_0001, language="es").handoff is None          # confirm: nothing opened yet
    card = chat.say(action={"type": "confirm", "value": "yes"}).handoff
    assert (card["handoff_reason"], card["copilot_proposal"]["action"]) == ("zone_medium", "approve_block")


def test_ac_05_escalation_hands_off_tool_failure_and_never_lists_a_graph_minted_id():
    turn = Chat(mcp_transport=server(block_card=DOWN)).say(EV_0001, language="es")
    minted = next(a.action_id for a in turn.actions if a.tool == "block_card")
    assert turn.decision == "escalate_unconfirmed_action" and turn.handoff["handoff_reason"] == "tool_failure"
    assert minted not in json.dumps(turn.handoff) + json.dumps(turn.receipt.model_dump(mode="json"))
    assert [a["tool"] for a in turn.handoff["actions"]] == ["open_case"]
    assert "block_card: not confirmed" in turn.handoff["open_questions"]
    assert turn.receipt.what_ai_did == msg.text("receipt.what_ai_did_block_unconfirmed", "es")


def facts(merchant, amount, dates, blocked, dispute, zone, fx):
    """One cell of the grid: the tool results of a turn and the builders' input made from them."""
    trx = {**TRX, "merchant": merchant, "amount": amount, "product_type": "credit", "last4": "9031"}
    case = {**CASE, "credit_deadline": None, "ruling_deadline": None, **dates}
    if not dates:
        case |= {"deadline_source": None, "deadline_source_url": None, "deadline_verified_on": None}
    actions = [{"tool": "open_case", "action_id": OPENED["action_id"], "state": "verified",
                "verification_id": case["verification_id"], "read_at": case["read_at"]},
               {"tool": "block_card", "action_id": "A-00000000BEEF", "state": "not_confirmed"}]   # minted
    if blocked:
        actions[1] = {"tool": "block_card", "action_id": CARD["action_id"], "state": "verified",
                      "verification_id": CARD["verification_id"], "read_at": CARD["read_at"]}
    display = {"amount": "21875.00", "currency": "MXN", "rate": "17.50", "rate_source": "Banxico FIX",
               "as_of": "2026-05-29"} if fx else None
    sc = {"transaction_id": TRX["transaction_id"], "score": {"high": 72.0, "medium": 35.0, "human": None}[zone],
          "source": "dataset", "version": "gold-v1"}
    results = [trx, case, {**OPENED, **dates}, *([CARD, {"action_id": CARD["action_id"]}] if blocked else []),
               *([display] if fx else [])]
    paper = {"trx": trx, "opened": {**OPENED, **dates}, "case": case, "card": CARD if blocked else None,
             "display": display, "actions": actions, "returned": {OPENED["action_id"], CARD["action_id"]},
             "held": False, "dispute": dispute, "decision": "handoff", "score": sc, "language": "pt",
             "route": {"decision": "handoff", "zone": zone, "rule_ids": ["POL-ZONE-HIGH", "POL-TICKET-ALWAYS"],
                       "handoff_reason": "zone_human"},
             "mode": "live", "trace_id": "run-1", "intent_confidence": 0.9, "guardrails": []}
    return results, sc, paper


GRID = list(itertools.product(["TIENDA X", None], [1250.0, 99.99, 1234.5],
                              [{"credit_deadline": "2026-06-03"}, {"ruling_deadline": "2026-07-16"}, {}],
                              [True, False], ["unrecognized_charge", "wrongful_charge"], ["high", "human"], [True, False]))


@pytest.mark.parametrize("cell", GRID[::5])
def test_ac_05_property_every_receipt_and_handoff_fact_matches_a_tool_result_and_a_foreign_one_is_dropped(cell):
    results, sc, paper = facts(*cell)
    receipt, handoff = build.receipt(paper), build.handoff(paper)
    found = check_grounding([*results, sc], receipt=CustomerReceipt.model_validate(receipt), handoff=handoff,
                            policy_facts=paper["route"]["rule_ids"] + [build.NO_CLOCK])
    assert found.status == "passed", found.observed                # the auditor's A4 finds nothing to report
    assert "A-00000000BEEF" not in json.dumps([receipt, handoff])   # a graph-minted id is never listed
    assert build.gate(receipt, results, required=("case_id",))[1] == 0
    receipt["verified_facts"].append({"fact": "Reembolso de 999.99 USD.", "source_id": TRX["transaction_id"]})
    receipt["actions"].append({**receipt["actions"][0], "action_id": "A-00000000BEEF"})
    handoff["evidence"].append("K-999999")
    kept, dropped = build.gate(receipt, results, required=("case_id",))
    assert dropped == 2 and "999.99" not in json.dumps(kept) and "BEEF" not in json.dumps(kept)
    assert build.gate(handoff, [*results, sc], paper["route"]["rule_ids"], nullable=False)[1] == 1
    assert build.gate({**receipt, "case_id": "K-999999"}, results, required=("case_id",))[0] is None


def test_ac_05_d_030_a_wrongful_charge_receipt_shows_no_credit_date():
    results, _, paper = facts("TIENDA X", 1250.0, {"credit_deadline": "2026-06-03"}, True, "wrongful_charge", "high",
                              False)
    assert build.receipt(paper)["deadline"] is None


def test_ac_05_a_reply_line_with_a_fact_no_tool_returned_is_dropped_and_logged(monkeypatch):
    real = msg.text
    monkeypatch.setattr(msg, "text", lambda key, language, **f: real(key, language, **f) + (
        " Reembolso: 999.99 USD." if key == "act.case_opened" else ""))
    turn = Chat(mcp_transport=server()).say(EV_0001, language="es")
    assert "999.99" not in turn.reply and "Caso K-104233 abierto" not in turn.reply
    assert "G-OUT-01" in turn.guardrails_triggered
    assert turn.trace[-1].status == "error" and turn.trace[-1].detail.startswith("G-OUT-01: 1")


def test_ac_05_ac_19_d_051_utc_read_times_pass_grounding_and_a_card_and_case_question_reads_both():
    turn = Chat().say("¿Cómo está mi tarjeta y mi caso?", language="es")
    assert "Tu tarjeta terminada en 4417: bloqueada (consultado el 2026-06-01 15:04 UTC)." in turn.reply
    assert "Estado de tu caso K-104233: En revisión (consultado el 2026-06-01 15:04 UTC)." in turn.reply
    assert "G-OUT-01" not in turn.guardrails_triggered and turn.case_id == "K-104233"


def test_d_043_a_block_held_by_a_call_request_is_said_calmly_and_does_not_escalate():
    turn = Chat(mcp_transport=server(block_card=HELD)).say(EV_0001, language="es")
    held = ("Bloqueo de la tarjeta: SIN CONFIRMAR. No bloqueé tu tarjeta; una persona decide si bloquearla después de "
            "la llamada que pediste.")
    assert turn.reply.splitlines()[-1] == held and "revisará" not in turn.reply
    assert turn.decision == "block_and_open_case" and turn.handoff.get("handoff_reason") != "tool_failure"
    assert next(s for s in turn.trace if s.node == "verify").status == "ok"
    assert turn.receipt.what_ai_did == msg.text("receipt.what_ai_did_case_only", "es")
    assert [s.id for s in turn.suggestions] == ["view_case", "add_info", "check_case"]   # a call is already open
    assert "block_card: held by the open call request; decide it after the call" in turn.handoff["open_questions"]


def test_ac_18_ac_20_session_expired_on_block_card_asks_to_sign_in_and_keeps_the_verified_case():
    turn = Chat(mcp_transport=server(block_card=EXPIRED)).say(EV_0001, language="es")
    assert turn.decision == "reauthenticate" and turn.reply.splitlines()[-1] == msg.text("act.sign_in", "es")
    assert "No hice ningún cambio" not in turn.reply and turn.receipt.case_id == turn.case_id == "K-104233"
    assert [s.id for s in turn.suggestions] == ["reauthenticate", "view_case", "talk_to_person"]
    assert turn.suggestions[1].href == "/case/K-104233" and turn.handoff["handoff_reason"] == "identity_unverified"


def test_ac_18_m13b_session_expired_on_the_verifying_read_after_an_accepted_write_never_says_nothing_changed():
    """Human zone: open_case was accepted, then get_case answered SESSION_EXPIRED (finding 1 of the #109 review)."""
    turn = Chat(mcp_transport=server(get_fraud_score=score(12.0), get_case=EXPIRED)).say(EV_0001, language="es")
    assert turn.decision == "reauthenticate" and turn.reply.splitlines()[-1] == msg.text("act.sign_in", "es")
    assert "No hice ningún cambio" not in turn.reply and turn.receipt is None and turn.case_id is None
    assert turn.handoff["handoff_reason"] == "identity_unverified"


UNREAD = {**CASE, "action_id": None, "verification_id": None}       # a plain read: the write is not confirmed


@pytest.mark.parametrize("get_case", [DOWN, UNREAD])
def test_ac_05_m3_no_receipt_without_a_verified_case_and_the_handoff_flags_the_unread_case(get_case):
    """Constitution #4: the receipt needs get_case's V-; the analyst's card keeps the accepted case, flagged (D-056)."""
    turn = Chat(mcp_transport=server(get_case=get_case)).say(EV_0001, language="es")
    assert turn.receipt is None and turn.decision == "escalate_unconfirmed_action"
    card = turn.handoff
    assert (card["case_id"], card["handoff_reason"]) == ("K-104233", "tool_failure") and "queue_status" not in card
    assert "case K-104233 not read back by get_case: confirm it exists before acting" in card["open_questions"]
    assert [(a["tool"], a["verified"]) for a in card["actions"]] == [("open_case", False), ("block_card", True)]


def test_m9_m10_a_duplicate_of_case_gets_no_new_receipt_or_handoff():
    turn = Chat(mcp_transport=server(open_case={**OPENED, "duplicate_of": "K-104233"})).say(EV_0001, language="es")
    assert turn.case_id == "K-104233" and turn.receipt is None and turn.handoff is None


def test_ac_05_m25_m26_respond_gates_the_receipt_and_the_handoff_it_builds(monkeypatch):
    """The tools answer as usual; a builder that adds a fact no tool returned is caught by respond's gate."""
    receipt, handoff = build.receipt, build.handoff
    monkeypatch.setattr(build, "receipt", lambda f: {**receipt(f), "verified_facts": [
        *receipt(f)["verified_facts"], {"fact": "Reembolso de 999.99 USD.", "source_id": TRX["transaction_id"]}]})
    monkeypatch.setattr(build, "handoff", lambda f: {**handoff(f), "evidence": [*handoff(f)["evidence"], "K-999999"]})
    turn = Chat(mcp_transport=server()).say(EV_0001, language="es")
    assert "999.99" not in json.dumps(turn.receipt.model_dump(mode="json")) and len(turn.receipt.verified_facts) == 3
    assert "K-999999" not in turn.handoff["evidence"] and "G-OUT-01" in turn.guardrails_triggered
    assert turn.trace[-1].detail == "G-OUT-01: 2 ungrounded fact(s) dropped"


def test_ac_05_m7_d_030_a_wrongful_charge_reply_shows_the_ruling_date_and_not_the_credit_date():
    ruled = {**CASE, "ruling_deadline": "2026-07-16"}
    turn = Chat(mcp_transport=server(get_case=ruled)).say("Me cobraron dos veces 1250 USD en TIENDA X", language="es")
    assert turn.intent == "wrongful_charge" and "2026-07-16" in turn.reply
    assert "2026-06-03" not in turn.reply and "fondos en disputa" not in turn.reply
    assert (turn.receipt.deadline.credit_deadline, str(turn.receipt.deadline.ruling_deadline)) == (None, "2026-07-16")


def test_ac_05_d_051_a_shown_time_must_match_a_tool_time_exactly():
    """A4 counts a timestamp by its date; the gate also checks the minute (or the second, when shown)."""
    assert not build.bad("Caso K-104233 (consultado el 2026-06-01 15:04 UTC).", [CASE])
    assert build.bad("Caso K-104233 (consultado el 2026-06-01 15:05 UTC).", [CASE])
    assert not build.bad("verificado 2026-06-01T15:04:11Z", [CASE]) and build.bad("verificado 2026-06-01T15:04:12Z", [CASE])


def test_ac_21_issued_at_is_the_latest_read_by_time_not_by_text():
    _, _, paper = facts("TIENDA X", 1250.0, {"credit_deadline": "2026-06-03"}, True, "unrecognized_charge", "high",
                        False)
    paper["actions"][0]["read_at"], paper["actions"][1]["read_at"] = "2026-06-01T10:04:11-05:00", "2026-06-01T12:00:00Z"
    assert build.receipt(paper)["issued_at"] == "2026-06-01T10:04:11-05:00"      # 15:04:11 UTC is the later one


@pytest.mark.parametrize("down, said", [("list_my_cards", "No pude verificar tus tarjetas ahora"),
                                        ("list_my_cases", "No pude verificar tu caso ahora")])
def test_ac_19_a_card_and_case_question_names_the_one_read_that_failed(down, said):
    turn = Chat(mcp_transport=server(**{"list_my_cases": None, down: DOWN})).say("¿Cómo está mi tarjeta y mi caso?",
                                                                                 language="es")
    assert said in turn.reply and msg.text("status.read_failed", "es") not in turn.reply
    assert ("Tu tarjeta terminada en 4417" in turn.reply) == (down == "list_my_cases")
    assert ("Estado de tu caso K-104233" in turn.reply) == (down == "list_my_cards")


def test_ac_29_ac_30_every_row_without_a_case_drops_case_chips_and_keeps_two_or_three_with_a_person():
    for row, language in itertools.product(msg.ROWS, ("es", "pt")):
        chips = [c.id for c in msg.suggestions(row, language)]
        assert 2 <= len(chips) <= 3 and not set(chips) & msg.NEEDS_CASE, row
        assert row == "greet" or row in msg.CALL_OPEN or set(chips) & msg.PERSON, row   # AC-31: starter chips


def test_ac_20_ac_30_m4_a_row_left_without_a_person_gets_one_and_is_filled_to_two(monkeypatch):
    monkeypatch.setitem(msg.ROWS, "probe", ("view_case",))
    assert [c.id for c in msg.suggestions("probe", "es")] == ["talk_to_person", "check_case"]
    assert [c.id for c in msg.suggestions("probe", "es", "K-104233")] == ["view_case", "talk_to_person"]


@pytest.mark.parametrize("answers", [{}, {"get_fraud_score": score(12.0)}, {"block_card": DOWN}])
def test_ac_20_a_reply_with_a_case_links_it_and_keeps_a_person_reachable(answers):
    turn = Chat(mcp_transport=server(**answers)).say(EV_0001, language="es")
    assert f"/case/{turn.case_id}" in [s.href for s in turn.suggestions] and set(labels(turn)) & PERSON


def test_ac_22_no_template_says_a_case_is_assigned_to_a_person():
    """No get_case reading reaches a template with taken_by_person yet, so no text may claim an assignment."""
    words = ("asignad", "atribuíd", "designad", "analista")
    texts = json.dumps(msg.messages(), ensure_ascii=False).lower()
    assert not [w for w in words if w in texts]
