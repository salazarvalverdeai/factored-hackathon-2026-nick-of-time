"""Spec 04 task 04h (D-067 [assumption], pending the lead): a charge the customer did not name is confirmed before
anything is done. A dispute turn whose slots do not name the one charge its search finds (no amount or date, and no
merchant whose every content word is in the charge's merchant) shows it as a card with the confirm chips; no case, no
block and no write in that turn (AC-02, AC-16). Only the chip, a tap on the card, or a typed reply that equals an entry
of a closed list confirms it; any longer reply is read by the classifier, so a person request stays a person request
(D-029). A later confirm proceeds as a named charge does; a decline answers D-039 and does nothing. A call request with
an unnamed charge registers a general call and shows the card; its confirm opens the case and keeps that one call
(AC-11, AC-16, AC-28, D-029). Fake MCP, no LLM; replay today is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

import re

import pytest

from contracts.tools import ToolError
from nick_of_time import receipt as msg
from nick_of_time.nlu import Slots
from nick_of_time.nlu.text import fold
from tests.test_spec04_decide import TRX, WRITES, record, score, server
from tests.test_spec04_graph import Chat, intake

CARD_CHIPS = ["confirm_charge", "confirm_no", "talk_to_person"]
QUESTION = {"es": "¿Es este el cargo que quieres reportar? Aún no hice ningún cambio.",
            "pt": "É esta a cobrança que você quer informar? Ainda não fiz nenhuma alteração."}
CALL_QUESTION = {"es": "¿Es este el cargo que quieres reportar?", "pt": "É esta a cobrança que você quer informar?"}
FIRST = {"es": "No reconozco un cargo", "pt": "Não reconheço uma cobrança"}
CALL_FIRST = {"es": "Quiero hablar con una persona, no reconozco un cargo",
              "pt": "Quero falar com uma pessoa, não reconheço uma cobrança"}
YES = {"action": {"type": "confirm", "value": "yes"}}
TAP = {"action": {"type": "choose_option", "value": TRX["transaction_id"]}}
# An active case on ANOTHER charge (its get_case fails, so it is not this charge's) and a general call with no case.
OTHER_CASE = {"cases": [{"case_id": "K-200001", "queue_status": "review", "status_label": "En revisión",
                         "updated_at": "2026-05-30T10:00:00Z"}], "read_at": "2026-06-01T15:04:11Z"}
GENERAL = {"action_id": "A-9A4D07E2C5B1", "case_id": None, "event_id": "E-3B6C1D9F2A85",
           "expected_contact_by": "2026-06-02"}
# D-067: every entry of the closed list (intake.CHARGE_WORDS), typed with case, accents and punctuation.
CLOSED_LIST = [("es", "Sí"), ("es", "si"), ("es", "¡Sí!"), ("es", "Sí, es ese"), ("es", "Sí, es ese cargo"),
               ("es", "Correcto."), ("es", "Ese es"), ("es", "Ese mismo"), ("pt", "Sim"),
               ("pt", "Sim, é essa cobrança"), ("pt", "É essa"), ("pt", "Essa mesma"), ("pt", "Correto")]
# Round-2 bypasses: a yes that also asks for a person, or names or hints at another charge. None confirms the card.
PERSON = [("es", "Sí, quiero hablar con alguien"), ("pt", "Sim, quero falar com alguém"),
          ("es", "Sí, quiero hablar con un asesor"), ("es", "Si, quiero un humano"), ("es", "Sí, quiero un agente"),
          ("pt", "Sim, quero um atendente"), ("es", "Sí, quiero hablar con una persona"),
          ("pt", "Sim, quero falar com uma pessoa")]
OTHER = [("es", "Sí, el de Amazon"), ("es", "Sí, el de ayer"), ("es", "Sí, el de quinientos"), ("es", "Sí, el de 500"),
         ("es", "Sí, pero es otro"), ("es", "Sí, ese es"), ("pt", "Sim, a da Amazon"), ("pt", "Sim, a de ontem"),
         ("pt", "Sim, a de 500"), ("pt", "Isso mesmo"), ("pt", "Sim, é esse")]


def asked(calls: list, text="No reconozco un cargo", language="es", seen=None, **answers):
    chat = Chat(mcp_transport=server(calls, seen, **{"get_fraud_score": score(72.0), **answers}))
    return chat, chat.say(text, language=language)


def call_turn(calls, seen, language="es"):
    """A call request with an unnamed charge from a customer with an active case on another charge."""
    return asked(calls, CALL_FIRST[language], language, seen=seen, list_my_cases=OTHER_CASE,
                 get_case=lambda a: ToolError(code="NOT_FOUND", message="x") if a["case_id"] == "K-200001" else None,
                 request_call=lambda a: None if a.get("case_id") else GENERAL)


def card_shown(language: str, row: str):
    """The turn that shows the unnamed charge's card on `row` (confirm_charge or confirm_call)."""
    calls, seen = [], []
    chat, turn = call_turn(calls, seen, language) if row == "confirm_call" else asked(calls, FIRST[language], language,
                                                                                         seen=seen)
    return chat, turn, calls, seen


def is_card(turn, language="es", chips=CARD_CHIPS, trx=TRX, question=QUESTION) -> bool:
    """The unnamed charge shown as one card to confirm, and nothing done."""
    return (turn.decision in ("ask", "connect_person") and turn.case_id is None and not turn.plan
            and [o.label for o in turn.options] == [msg.option_label(trx)]
            and turn.reply.splitlines()[-1] == question[language] and [s.id for s in turn.suggestions] == chips)


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
    ("No reconozco un cargo en Amazon", TRX),                               # a merchant that is not this charge's
    ("No reconozco un cargo en Mercado Central", {**TRX, "merchant": "Laboratorio Central"}),   # a generic word only
    ("No reconozco un cargo en Tienda", {**TRX, "merchant": "Tienda General"}),
    ("No reconozco un cargo de Servicios", {**TRX, "merchant": "Servicios Públicos"}),
    ("No reconozco un cargo en TIENDA X", TRX)])                            # no content word: "tienda" and "x"
def test_ac_02_a_merchant_slot_that_does_not_name_the_charge_shows_the_card(text, trx):
    calls = []
    _, turn = asked(calls, text, search_transaction={"candidates": [trx]})
    assert is_card(turn, trx=trx) and not set(calls) & WRITES and "block_card" not in calls


def test_ac_02_a_currency_alone_never_names_the_charge(monkeypatch):
    parse = intake.NLU.parse
    monkeypatch.setattr(intake.NLU, "parse", lambda *a, **k: parse(*a, **k).model_copy(
        update={"slots": Slots(currency="USD")}))
    calls = []
    _, turn = asked(calls, "No reconozco un cargo en dólares")
    assert is_card(turn) and not set(calls) & WRITES


@pytest.mark.parametrize("yes", [YES, TAP, {"text": "Sí"}, {"text": "Sí, es ese cargo"}])
def test_ac_16_once_confirmed_the_high_zone_states_the_plan_then_opens_and_blocks_as_today(yes):
    chat, _ = asked([])
    done = chat.say(**yes)
    assert (done.decision, done.zone) == ("block_and_open_case", "high") and done.plan[0].startswith("1. ")
    assert [(a.tool, a.state) for a in done.actions] == [("open_case", "verified"), ("block_card", "verified")]
    assert done.case_id == "K-104233" and record(done)["input"]["candidates"] == 1 and "note" not in record(done)


def test_d_067_the_closed_list_holds_every_entry_folded():
    folded = {" ".join(re.findall(r"\w+", fold(reply))) for _, reply in CLOSED_LIST}
    assert folded == {said for said, yes in intake.CHARGE_WORDS.items() if yes}


@pytest.mark.parametrize("language, reply", CLOSED_LIST)
def test_ac_16_a_typed_reply_equal_to_a_closed_list_entry_confirms_the_card_shown(language, reply):
    chat, _, calls, _ = card_shown(language, "confirm_charge")
    done = chat.say(reply)
    assert done.decision == "block_and_open_case" and done.case_id == "K-104233"
    assert [(a.tool, a.state) for a in done.actions] == [("open_case", "verified"), ("block_card", "verified")]


@pytest.mark.parametrize("language, reply", CLOSED_LIST)
def test_ac_16_d_029_a_closed_list_reply_on_the_call_card_opens_the_case_keeps_the_one_call_and_never_blocks(
        language, reply):
    chat, _, calls, seen = card_shown(language, "confirm_call")
    done = chat.say(reply)
    assert (done.decision, done.zone) == ("connect_person", "high") and done.case_id == "K-104233"
    assert "block_card" not in calls and calls.count("request_call") == 1      # M12: the call path, one callback


@pytest.mark.parametrize("row", ["confirm_charge", "confirm_call"])
@pytest.mark.parametrize("language, reply", PERSON + OTHER)
def test_ac_02_d_029_a_yes_that_says_more_never_confirms_the_card_and_never_blocks(row, language, reply):
    """Round 2: "Sí, quiero hablar con alguien" confirmed the card and blocked it with no call registered."""
    chat, first, calls, seen = card_shown(language, row)
    before = calls.count("request_call")
    turn = chat.say(reply)
    assert not turn.case_id and not set(calls) & WRITES and "block_card" not in calls
    assert chat.state()["customer_confirmed"] is not True
    if (language, reply) in PERSON:         # heard as a person request: a general call, the card shown again
        assert turn.decision == "connect_person" and [(a.tool, a.state) for a in turn.actions] == [
            ("request_call", "requested")] and calls.count("request_call") == before + 1
        assert [args.get("case_id") for tool, args in seen if tool == "request_call"] == [None] * (before + 1)
        assert is_card(turn, language, chips=["confirm_charge", "confirm_no"], question=CALL_QUESTION)


@pytest.mark.parametrize("reply", ["Sí", "Sim", "Correcto", "Sí, es ese cargo"])
def test_m1_a_typed_yes_with_no_card_row_offered_writes_nothing(reply):
    calls = []
    chat = Chat(mcp_transport=server(calls, get_fraud_score=score(72.0)))
    assert not chat.say(reply, language="es").case_id                         # a fresh thread: no row at all
    chat.say("No reconozco un cargo")                                         # the card
    status = chat.say("¿Cuál es el estado de mi caso?")                       # another row replaces it
    assert "confirm_charge" not in [s.id for s in status.suggestions]
    turn = chat.say(reply)
    assert not turn.case_id and not set(calls) & WRITES and chat.state()["customer_confirmed"] is not True


def test_m2_the_medium_zone_confirm_row_keeps_its_own_words():
    calls = []
    chat = Chat(mcp_transport=server(calls, get_fraud_score=score(40.0)))
    first = chat.say("No reconozco un cargo de 1250 USD", language="es")
    assert first.decision == "confirm" and [s.id for s in first.suggestions][0] == "confirm_yes"
    done = chat.say("Sí")                                                     # its own word still confirms
    assert done.decision == "handoff" and [(a.tool, a.state) for a in done.actions] == [("open_case", "verified")]


@pytest.mark.parametrize("reply", ["Sí, ese es", "Ese mismo", "Correcto", "Sí, es ese cargo", "Sí, quiero hablar con alguien"])
def test_m2b_a_card_reply_on_the_medium_zone_confirm_row_is_not_a_plan_confirm(reply):
    calls = []
    chat = Chat(mcp_transport=server(calls, get_fraud_score=score(40.0)))
    chat.say("No reconozco un cargo de 1250 USD", language="es")
    turn = chat.say(reply)
    assert not turn.case_id and not set(calls) & WRITES and chat.state()["customer_confirmed"] is not True


def test_ac_11_a_medium_zone_charge_confirmed_once_opens_the_case_without_a_second_question():
    chat, _ = asked([], get_fraud_score=score(40.0))
    done = chat.say(**YES)
    assert (done.decision, done.zone) == ("handoff", "medium") and record(done)["input"]["customer_confirmed"] is True
    assert [(a.tool, a.state) for a in done.actions] == [("open_case", "verified")]


@pytest.mark.parametrize("no", [{"action": {"type": "confirm", "value": "no"}}, {"text": "No es ese cargo"},
                                {"text": "No"}])
def test_d_039_declining_the_card_answers_that_nothing_changed_and_does_nothing(no):
    calls = []
    chat, _ = asked(calls)
    turn = chat.say(**no)
    assert turn.decision == "ask" and turn.reply.startswith("Entendido, no hice ningún cambio") and not turn.plan
    assert not turn.actions and turn.case_id is None and chat.state()["selected_transaction"] is None
    assert not set(calls) & WRITES


@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_28_d_067_a_call_request_with_an_unnamed_charge_registers_a_general_call_and_shows_the_card(language):
    calls, seen = [], []
    _, turn = call_turn(calls, seen, language)
    assert is_card(turn, language, chips=["confirm_charge", "confirm_no"], question=CALL_QUESTION)
    assert turn.decision == "connect_person" and "ningún cambio" not in turn.reply and "nenhuma" not in turn.reply
    assert [(a.tool, a.state) for a in turn.actions] == [("request_call", "requested")]
    assert [args.get("case_id") for tool, args in seen if tool == "request_call"] == [None]    # never K-200001
    assert "K-200001" not in turn.reply and not set(calls) & WRITES


@pytest.mark.parametrize("yes", [YES, TAP, {"text": "Sí, es ese cargo"}])
def test_ac_16_d_029_confirming_the_card_after_the_call_opens_the_case_keeps_the_one_call_and_never_blocks(yes):
    calls, seen = [], []
    chat, _ = call_turn(calls, seen)
    done = chat.say(**yes)
    assert (done.decision, done.zone) == ("connect_person", "high") and done.case_id == "K-104233"
    # the general call of the last turn stands: no second request_call, the turn states that one (its own result)
    assert [(a.tool, a.state, a.action_id) for a in done.actions][1:] == [("request_call", "requested",
                                                                            GENERAL["action_id"])]
    assert done.actions[0].tool == "open_case" and done.actions[0].state == "verified"
    assert calls.count("request_call") == 1 and "block_card" not in calls
    assert "Tu solicitud de llamada ya quedó registrada" in done.reply and GENERAL["expected_contact_by"] in done.reply
    assert record(done)["decision"]["request_call"] == "opened_case" and "talk_to_person" not in [
        s.id for s in done.suggestions]
    assert chat.state()["call_held"] is None


def test_d_067_the_kept_call_lasts_one_turn_a_later_call_request_registers_a_new_one():
    calls, seen = [], []
    chat, _ = call_turn(calls, seen)
    chat.say("¿Cuál es el estado de mi caso?")                   # the card is gone, and the held call with it
    assert chat.state()["call_held"] is None
    chat.say(action={"type": "request_call"})
    assert calls.count("request_call") == 2 and "open_case" not in calls


def test_d_039_declining_the_card_after_the_call_does_nothing_more():
    calls, seen = [], []
    chat, _ = call_turn(calls, seen)
    turn = chat.say(action={"type": "confirm", "value": "no"})
    assert turn.reply.startswith("Entendido, no hice ningún cambio") and not turn.actions and turn.case_id is None
    assert calls.count("request_call") == 1 and not set(calls) & WRITES


@pytest.mark.parametrize("text, merchant", [("No reconozco un cargo de 1250 USD", "TIENDA X"),
                                            ("No reconozco un cargo en Amazon", "AMAZON MX"),
                                            ("No reconozco un cargo en Mercado Central", "Mercado Central")])
def test_ac_01_a_charge_named_by_amount_or_its_merchant_still_acts_in_the_same_turn(text, merchant):
    _, turn = asked([], text, search_transaction={"candidates": [{**TRX, "merchant": merchant}]})
    assert (turn.decision, turn.zone) == ("block_and_open_case", "high") and not turn.options
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "verified"), ("block_card", "verified")]


@pytest.mark.parametrize("slots, merchant, named", [
    ({"merchant": "café central"}, "CAFE CENTRAL", True), ({"merchant": "Amazon"}, None, False),
    ({"merchant": "USD"}, "USD STORE", False), ({"currency": "USD"}, "TIENDA X", False),
    ({"amount": "1250.00"}, None, True), ({"date": "2026-05-31"}, None, True),
    ({"merchant": "Mercado Central"}, "Laboratorio Central", False),     # M: one generic word in common
    ({"merchant": "Mercado Central"}, "Mercado Central", True),
    ({"merchant": "Tienda"}, "Tienda General", False), ({"merchant": "Servicios"}, "Servicios Públicos", False),
    ({"merchant": "Tienda Amazon"}, "AMAZON MX", True),                   # the generic word is skipped
    ({"merchant": "Amazon Prime"}, "AMAZON MX", False),                   # every content word must be there
    ({"merchant": "Amazon"}, "AMAZON MX", True), ({"merchant": "Amazon MX"}, "AMAZON MX", True),
    ({"merchant": "mx"}, "AMAZON MX", False),                             # M6: 2 letters are skipped
    ({"merchant": "José"}, "Tienda Don José", True), ({"merchant": "jose"}, "Tienda Don José", True),   # M14
    ({"merchant": "José"}, "TIENDA DON JOSE", True), ({"merchant": "Tienda"}, None, False)])
def test_ac_02_names_needs_every_content_word_of_the_merchant_accents_and_case_ignored(slots, merchant, named):
    assert intake.names(slots, {**TRX, "merchant": merchant}) is named
