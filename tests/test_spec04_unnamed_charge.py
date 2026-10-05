"""Spec 04 task 04h (D-067 [assumption], pending the lead): a charge the customer did not name is confirmed before
anything is done. A dispute turn with no amount, date or merchant whose search finds one charge shows it as a card with
the confirm chips; no case, no block and no write in that turn (AC-02, AC-16). A later confirm proceeds as a named
charge does; a decline answers D-039 and does nothing. Fake MCP, no LLM; replay today is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

import pytest

from nick_of_time import receipt as msg
from tests.test_spec04_decide import TRX, WRITES, record, score, server
from tests.test_spec04_graph import Chat

CONFIRM_CHIPS = ["confirm_yes", "confirm_no", "talk_to_person"]


def asked(calls: list, answer=score(72.0), text="No reconozco un cargo", language="es"):
    chat = Chat(mcp_transport=server(calls, get_fraud_score=answer))
    return chat, chat.say(text, language=language)


@pytest.mark.parametrize("language, question", [
    ("es", "¿Es este el cargo que quieres reportar? Aún no hice ningún cambio."),
    ("pt", "É esta a cobrança que você quer informar? Ainda não fiz nenhuma alteração.")])
def test_ac_02_a_charge_the_customer_did_not_name_is_shown_as_a_card_to_confirm_and_nothing_is_done(language, question):
    calls = []
    _, turn = asked(calls, text="No reconozco un cargo" if language == "es" else "Não reconheço uma cobrança",
                    language=language)
    assert turn.decision == "ask" and turn.zone is None and not turn.plan and not turn.actions and turn.case_id is None
    assert [o.label for o in turn.options] == [msg.option_label(TRX)] and turn.reply.splitlines()[-1] == question
    assert [s.id for s in turn.suggestions] == CONFIRM_CHIPS
    assert record(turn)["input"]["candidates"] == 0 and "search_transaction" in calls
    assert not set(calls) & WRITES and "request_call" not in calls


@pytest.mark.parametrize("yes", [{"action": {"type": "confirm", "value": "yes"}}, {"text": "Sí"},
                                 {"action": {"type": "choose_option", "value": TRX["transaction_id"]}}])
def test_ac_16_once_confirmed_the_high_zone_states_the_plan_then_opens_and_blocks_as_today(yes):
    calls = []
    chat, _ = asked(calls)
    done = chat.say(**yes)
    assert (done.decision, done.zone) == ("block_and_open_case", "high") and done.plan[0].startswith("1. ")
    assert [(a.tool, a.state) for a in done.actions] == [("open_case", "verified"), ("block_card", "verified")]
    assert done.case_id == "K-104233" and record(done)["input"]["candidates"] == 1


def test_ac_11_a_medium_zone_charge_confirmed_once_opens_the_case_without_a_second_question():
    chat, _ = asked([], answer=score(40.0))
    done = chat.say(action={"type": "confirm", "value": "yes"})
    assert (done.decision, done.zone) == ("handoff", "medium") and record(done)["input"]["customer_confirmed"] is True
    assert [(a.tool, a.state) for a in done.actions] == [("open_case", "verified")]


@pytest.mark.parametrize("no", [{"action": {"type": "confirm", "value": "no"}}, {"text": "No es ese cargo"}])
def test_d_039_declining_the_card_answers_that_nothing_changed_and_does_nothing(no):
    calls = []
    chat, _ = asked(calls)
    turn = chat.say(**no)
    assert turn.decision == "ask" and turn.reply.startswith("Entendido, no hice ningún cambio") and not turn.plan
    assert not turn.actions and turn.case_id is None and chat.state()["selected_transaction"] is None
    assert not set(calls) & WRITES


def test_ac_16_a_call_request_with_an_unnamed_charge_registers_only_the_call():
    calls = []
    _, turn = asked(calls, text="Quiero hablar con una persona, no reconozco un cargo")
    assert turn.decision == "connect_person" and turn.case_id is None and not turn.plan
    assert [(a.tool, a.state) for a in turn.actions] == [("request_call", "requested")]
    assert not set(calls) & WRITES


@pytest.mark.parametrize("text", ["No reconozco un cargo de 1250 USD", "No reconozco un cargo en TIENDA X"])
def test_ac_01_a_charge_named_by_amount_or_merchant_still_acts_in_the_same_turn(text):
    _, turn = asked([], text=text)
    assert (turn.decision, turn.zone) == ("block_and_open_case", "high") and not turn.options
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "verified"), ("block_card", "verified")]
