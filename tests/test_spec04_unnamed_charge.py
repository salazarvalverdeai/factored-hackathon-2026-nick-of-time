"""Spec 04 task 04h (D-067 [assumption], pending the lead): a charge the customer did not name is confirmed before
anything is done. A dispute turn whose slots do not name the one charge its search finds (no amount or date, and no
merchant that matches the charge's) shows it as a card with the confirm chips; no case, no block and no write in that
turn (AC-02, AC-16). A later confirm proceeds as a named charge does; a decline answers D-039 and does nothing. A call
request with an unnamed charge registers a general call and shows the card too (AC-11, AC-16, AC-28, D-029). Fake MCP,
no LLM; replay today is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

import pytest

from contracts.tools import ToolError
from nick_of_time import receipt as msg
from nick_of_time.nlu import Slots
from tests.test_spec04_decide import TRX, WRITES, record, score, server
from tests.test_spec04_graph import Chat, intake

CARD_CHIPS = ["confirm_charge", "confirm_no", "talk_to_person"]
QUESTION = {"es": "¿Es este el cargo que quieres reportar? Aún no hice ningún cambio.",
            "pt": "É esta a cobrança que você quer informar? Ainda não fiz nenhuma alteração."}
FIRST = {"es": "No reconozco un cargo", "pt": "Não reconheço uma cobrança"}
YES = {"action": {"type": "confirm", "value": "yes"}}
# An active case on ANOTHER charge (its get_case fails, so it is not this charge's) and a general call with no case.
OTHER_CASE = {"cases": [{"case_id": "K-200001", "queue_status": "review", "status_label": "En revisión",
                         "updated_at": "2026-05-30T10:00:00Z"}], "read_at": "2026-06-01T15:04:11Z"}


def asked(calls: list, text="No reconozco un cargo", language="es", seen=None, **answers):
    chat = Chat(mcp_transport=server(calls, seen, **{"get_fraud_score": score(72.0), **answers}))
    return chat, chat.say(text, language=language)


def is_card(turn, language="es", chips=CARD_CHIPS, trx=TRX) -> bool:
    """The unnamed charge shown as one card to confirm, and nothing done."""
    return (turn.decision in ("ask", "connect_person") and turn.case_id is None and not turn.plan
            and [o.label for o in turn.options] == [msg.option_label(trx)]
            and turn.reply.splitlines()[-1] == QUESTION[language] and [s.id for s in turn.suggestions] == chips)


@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_02_a_charge_the_customer_did_not_name_is_shown_as_a_card_to_confirm_and_nothing_is_done(language):
    calls = []
    _, turn = asked(calls, FIRST[language], language)
    assert is_card(turn, language) and turn.decision == "ask" and not turn.actions and turn.zone is None
    assert record(turn)["input"]["candidates"] == 0 and record(turn)["note"].startswith("D-067")
    assert "search_transaction" in calls and not set(calls) & WRITES and "request_call" not in calls


@pytest.mark.parametrize("text, trx", [
    ("No reconozco un cargo en USD", TRX),                                  # B0 reads the currency as a merchant
    ("No reconozco un cargo en MXN", TRX),
    ("No reconozco un cargo en Amazon", {**TRX, "merchant": None}),         # the search keeps null-merchant rows
    ("No reconozco un cargo en Amazon", TRX)])                              # a merchant that is not this charge's
def test_ac_02_a_merchant_slot_that_does_not_match_the_charge_does_not_name_it(text, trx):
    calls = []
    _, turn = asked(calls, text, search_transaction={"candidates": [trx]})
    assert is_card(turn, trx=trx) and not set(calls) & WRITES


def test_ac_02_a_currency_alone_never_names_the_charge(monkeypatch):
    parse = intake.NLU.parse
    monkeypatch.setattr(intake.NLU, "parse", lambda *a, **k: parse(*a, **k).model_copy(
        update={"slots": Slots(currency="USD")}))
    calls = []
    _, turn = asked(calls, "No reconozco un cargo en dólares")
    assert is_card(turn) and not set(calls) & WRITES


@pytest.mark.parametrize("yes", [YES, {"text": "Sí"}, {"text": "Sí, es ese cargo"},
                                 {"action": {"type": "choose_option", "value": TRX["transaction_id"]}}])
def test_ac_16_once_confirmed_the_high_zone_states_the_plan_then_opens_and_blocks_as_today(yes):
    chat, _ = asked([])
    done = chat.say(**yes)
    assert (done.decision, done.zone) == ("block_and_open_case", "high") and done.plan[0].startswith("1. ")
    assert [(a.tool, a.state) for a in done.actions] == [("open_case", "verified"), ("block_card", "verified")]
    assert done.case_id == "K-104233" and record(done)["input"]["candidates"] == 1 and "note" not in record(done)


@pytest.mark.parametrize("language, reply", [("es", "Sí, ese es"), ("es", "Sí, es ese"), ("es", "Correcto"),
                                             ("es", "Ese mismo"), ("pt", "Sim, é esse"), ("pt", "Isso mesmo")])
def test_ac_16_a_typed_yes_confirms_the_card_that_was_shown(language, reply):
    chat, _ = asked([], FIRST[language], language)
    done = chat.say(reply)
    assert done.decision == "block_and_open_case" and done.case_id == "K-104233"


@pytest.mark.parametrize("reply", ["Sí, pero es otro", "Sí, quiero hablar con una persona", "Sí, el de 500"])
def test_ac_02_a_yes_that_also_says_something_else_does_not_confirm(reply):
    calls = []
    chat, _ = asked(calls)
    turn = chat.say(reply)
    assert not turn.case_id and not set(calls) & WRITES - {"request_call"}


def test_ac_11_a_medium_zone_charge_confirmed_once_opens_the_case_without_a_second_question():
    chat, _ = asked([], get_fraud_score=score(40.0))
    done = chat.say(**YES)
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


def call_turn(calls, seen):
    general = {"action_id": "A-9A4D07E2C5B1", "case_id": None, "event_id": "E-3B6C1D9F2A85",
               "expected_contact_by": "2026-06-02"}
    return asked(calls, "Quiero hablar con una persona, no reconozco un cargo", seen=seen, list_my_cases=OTHER_CASE,
                 get_case=lambda a: ToolError(code="NOT_FOUND", message="x") if a["case_id"] == "K-200001" else None,
                 request_call=lambda a: None if a.get("case_id") else general)


def test_ac_28_d_067_a_call_request_with_an_unnamed_charge_registers_a_general_call_and_shows_the_card():
    calls, seen = [], []
    _, turn = call_turn(calls, seen)
    assert is_card(turn, chips=["confirm_charge", "confirm_no"]) and turn.decision == "connect_person"
    assert [(a.tool, a.state) for a in turn.actions] == [("request_call", "requested")]
    assert [args.get("case_id") for tool, args in seen if tool == "request_call"] == [None]    # never K-200001
    assert "K-200001" not in turn.reply and not set(calls) & WRITES


def test_ac_16_d_029_confirming_the_card_after_the_call_opens_the_case_keeps_the_call_and_never_blocks():
    calls, seen = [], []
    chat, _ = call_turn(calls, seen)
    done = chat.say(**YES)
    assert (done.decision, done.zone) == ("connect_person", "high") and done.case_id == "K-104233"
    assert [(a.tool, a.state) for a in done.actions] == [("open_case", "verified"), ("request_call", "verified")]
    assert record(done)["decision"]["request_call"] == "opened_case" and "block_card" not in calls


def test_d_039_declining_the_card_after_the_call_does_nothing_more():
    calls, seen = [], []
    chat, _ = call_turn(calls, seen)
    turn = chat.say(action={"type": "confirm", "value": "no"})
    assert turn.reply.startswith("Entendido, no hice ningún cambio") and not turn.actions and turn.case_id is None
    assert calls.count("request_call") == 1 and not set(calls) & WRITES


@pytest.mark.parametrize("text", ["No reconozco un cargo de 1250 USD", "No reconozco un cargo en TIENDA X"])
def test_ac_01_a_charge_named_by_amount_or_its_merchant_still_acts_in_the_same_turn(text):
    _, turn = asked([], text)
    assert (turn.decision, turn.zone) == ("block_and_open_case", "high") and not turn.options
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "verified"), ("block_card", "verified")]


@pytest.mark.parametrize("slots, merchant, named", [
    ({"merchant": "café central"}, "CAFE CENTRAL", True), ({"merchant": "Amazon"}, None, False),
    ({"merchant": "USD"}, "USD STORE", False), ({"currency": "USD"}, "TIENDA X", False),
    ({"amount": "1250.00"}, None, True), ({"date": "2026-05-31"}, None, True)])
def test_ac_02_names_matches_a_merchant_on_its_words_accents_and_case_ignored(slots, merchant, named):
    assert intake.names(slots, {**TRX, "merchant": merchant}) is named
