"""Spec 04 D-071 (AC-35, AC-36): the ask that follows a charge the customer named, when the intent is below τ (the
D-065 cap kept), offers chips that state the intent, and the next message goes on with the charge shown. On the fake
MCP (FastMCP in-memory client); no LLM, no network; replay today is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

import pytest

from nick_of_time import receipt as msg
from tests.test_spec04_decide import TRX, WRITES, score, server
from tests.test_spec04_graph import PERSON, Chat, intake, labels

UNCLEAR_ES = "Me aparece un retiro de 1250 dólares del 31 de mayo y yo no lo hice."   # B0: out_of_scope 0.5, named
UNCLEAR_PT = "Tem um saque de 1250 dólares do dia 31 de maio no meu cartão."
CARD = f"USD 1250.00 · 2026-05-31 · {TRX['merchant']}"
CONFIRM_YES = {"type": "confirm", "value": "yes"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "DEMO_TODAY", "MCP_URL"):
        monkeypatch.delenv(name, raising=False)


def asked(chat: Chat, text: str = UNCLEAR_ES, language: str = "es"):
    turn = chat.say(text, language=language)
    assert (turn.decision, turn.intent_confidence) == ("ask", 0.5) and turn.intent_confidence < intake.TAU
    return turn


@pytest.mark.parametrize("text, language", [(UNCLEAR_ES, "es"), (UNCLEAR_PT, "pt")])
def test_ac_35_a_named_charge_with_an_unclear_intent_asks_with_the_intent_chips_and_a_person(text, language):
    """AC-35: one charge the customer named and an intent below τ: the card, clarify.ask_intent and the ask_intent row
    (the two intent chips and a person, by rule); nothing is written."""
    calls: list[str] = []
    turn = asked(Chat(mcp_transport=server(calls)), text, language)
    assert [o.label for o in turn.options] == [CARD] and turn.options[0].id == TRX["transaction_id"]
    assert turn.reply.splitlines()[-1] == msg.text("clarify.ask_intent", language)
    assert [s.id for s in turn.suggestions] == ["intent_unrecognized", "intent_wrongful", "talk_to_person"]
    assert labels(turn) == [msg.text(f"suggest.{c}", language) for c in msg.ROWS["ask_intent"]]
    assert [s.kind for s in turn.suggestions] == ["text", "text", "action"] and PERSON & set(labels(turn))
    assert not set(calls) & WRITES and not turn.actions and turn.case_id is None


def test_ac_35_the_chips_are_the_rule_table_row_in_both_languages():
    """AC-35 (with AC-29): the row lives in the server's rule table; ES and PT labels from messages.yaml."""
    for language in ("es", "pt"):
        row = msg.suggestions("ask_intent", language)
        assert [s.label for s in row] == [msg.messages()["suggest"][c][language] for c in msg.ROWS["ask_intent"]]
    assert {c: msg.TEXT_CHIP_INTENT[c] for c in msg.INTENT_CHIPS} == {
        "intent_unrecognized": "unrecognized_charge", "intent_wrongful": "wrongful_charge"}


@pytest.mark.parametrize("answer, intent", [("No reconozco este cargo", "unrecognized_charge"),         # the chip
                                            ("No lo reconozco. Yo no hice ese retiro.", "unrecognized_charge"),
                                            ("Lo reconozco, pero el cobro está mal", "wrongful_charge"),
                                            ("La compra sí fue mía, pero me cobraron de más.", "wrongful_charge")])
def test_ac_36_the_next_message_states_the_intent_and_goes_on_with_the_charge_shown(answer, intent):
    """AC-36: after the ask_intent row, a reply (a chip or typed) that names no charge keeps the one shown: no new
    search, and the rules decide on it (high zone here: the case opens and the block is verified)."""
    seen: list[tuple] = []
    chat = Chat(mcp_transport=server(seen=seen))
    asked(chat)
    searches = sum(1 for tool, _ in seen if tool == "search_transaction")
    turn = chat.say(answer, language="es")
    assert sum(1 for tool, _ in seen if tool == "search_transaction") == searches     # the charge shown, kept
    assert (turn.decision, turn.intent, turn.case_id) == ("block_and_open_case", intent, "K-104233")
    opened = next(args for tool, args in seen if tool == "open_case")
    assert (opened["transaction_id"], opened["dispute_type"]) == (TRX["transaction_id"], intent)
    assert turn.handoff and turn.receipt                                          # AC-34 (D-070) too


def test_ac_36_a_reply_that_names_a_charge_searches_again():
    """AC-36: the charge is kept only when the reply names none; an amount or a date starts a new search."""
    seen: list[tuple] = []
    chat = Chat(mcp_transport=server(seen=seen))
    asked(chat)
    chat.say("No reconozco el cargo de 1250 dólares del 31 de mayo", language="es")
    assert sum(1 for tool, _ in seen if tool == "search_transaction") == 2


def test_ac_36_an_unclear_reply_to_the_confirm_question_asks_it_again_and_keeps_the_charge():
    """AC-36 (with AC-11): in the medium zone, a reply to plan.confirm_ask that is neither a yes nor a no and names no
    charge keeps the charge and the plan: clarify.confirm_again with the confirm chips, nothing written; then a yes
    (typed or the chip) opens the case and hands it off."""
    for yes in ("Sí", CONFIRM_YES):
        calls: list[str] = []
        chat = Chat(mcp_transport=server(calls, get_fraud_score=score(35.0)))
        assert chat.say("No reconozco un cargo de 1250 dólares del 31 de mayo en TIENDA X", language="es").decision \
            == "confirm"
        again = chat.say("Sí, es ese cargo. Confirmo que yo no lo hice.", language="es")
        assert again.decision == "ask" and again.reply.splitlines() == [msg.text("clarify.confirm_again", "es")]
        assert [s.id for s in again.suggestions] == ["confirm_yes", "confirm_no", "talk_to_person"]
        assert not set(calls) & WRITES and not again.options and again.case_id is None
        done = chat.say(yes, language="es") if isinstance(yes, str) else chat.say(action=yes)
        assert (done.decision, done.zone, done.case_id) == ("handoff", "medium", "K-104233")
        assert done.handoff["copilot_proposal"]["action"] == "approve_block" and "block_card" not in calls


def test_ac_36_the_confirm_goes_on_with_the_dispute_read_before_the_unclear_reply():
    """AC-36: the dispute a confirm answer goes on with is the last one read (here wrongful), not the default."""
    seen: list[tuple] = []
    chat = Chat(mcp_transport=server(seen=seen, get_fraud_score=score(35.0)))
    assert chat.say("Me cobraron dos veces 1250 dólares en TIENDA X el 31 de mayo.", language="es").decision == "confirm"
    assert chat.say("Sí, es ese cargo. Confirmo que yo no lo hice.", language="es").decision == "ask"
    done = chat.say("Sí", language="es")
    assert (done.decision, done.intent) == ("handoff", "wrongful_charge")
    assert next(args for tool, args in seen if tool == "open_case")["dispute_type"] == "wrongful_charge"


def test_ac_36_a_person_stays_one_chip_away_and_the_clarification_turns_still_count():
    """AC-36 (with AC-13): the ask is still an ask: unclear replies count clarification turns, and the person chip
    of the row registers a call (never refused)."""
    chat = Chat(mcp_transport=server())
    asked(chat)
    assert chat.state()["clarification_turns"] == 1
    turn = chat.say(action={"type": "request_call"})
    assert turn.decision == "connect_person" and any(a.tool == "request_call" for a in turn.actions)
