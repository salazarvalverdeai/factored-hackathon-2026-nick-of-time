"""Spec 04 task 04e (T6): the status and connect nodes and the returning customer, on the fake MCP (FastMCP in-memory
client) with tool answers overridden per test. No LLM, no network; replay today is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

import asyncio

import pytest

from contracts.tools import ToolError
from tests.test_spec04_decide import NO_CASES, WRITES, record, score, server
from tests.test_spec04_graph import Chat, fake, intake, labels

CASE = fake.FIXTURES["get_case"]
PLAIN_CASE = {k: v for k, v in CASE.items() if k not in ("action_id", "verification_id")}   # a plain status read
DOWN = ToolError(code="UNAVAILABLE", message="down")
ALREADY_REPORTED = "Ya reporté un cargo que no reconozco, ¿cómo va mi caso?"   # status_inquiry + dispute (D-020)


def case(**changes) -> dict:
    return {**PLAIN_CASE, **changes}


def args_of(seen: list, answer):
    """A tool answer that also records the arguments it was called with."""
    return lambda arguments: seen.append(arguments) or (answer(arguments) if callable(answer) else answer)


def test_ac_06_a_returning_customer_gets_get_cases_label_deadline_and_next_step():
    turn = Chat(mcp_transport=server(list_my_cases=fake.FIXTURES["list_my_cases"])).say("¿Cómo va mi caso?",
                                                                                        language="es")
    body = turn.reply.splitlines()[-3:]                  # a new thread: the greeting comes first (AC-15)
    assert body == ["Estado de tu caso K-104233: En revisión (consultado el 2026-06-01 15:04 UTC).",
                    "Plazo legal del banco para pronunciarse sobre los fondos en disputa: 2026-06-03. Fuente: "
                    "Banxico Circular 3/2012, as amended by Circular 14/2018.",
                    intake.msg.text("receipt.what_a_person_does", "es")]
    assert (turn.decision, turn.case_id) == ("answer_status", "K-104233") and not turn.actions
    assert [s.id for s in turn.suggestions] == ["view_case", "add_info", "request_call"]
    assert turn.suggestions[0].href == "/case/K-104233"
    assert not any(word in turn.reply for word in ("POL-", "72", "score", "zona", "high"))   # tool facts only


def test_ac_06_the_label_is_localized_and_a_finished_case_promises_no_deadline():
    chat = Chat(mcp_transport=server(list_my_cases=fake.FIXTURES["list_my_cases"],
                                     get_case=case(queue_status="resolved", status_label="Resuelto",
                                                   credit_deadline=None, deadline_source=None,
                                                   deadline_source_url=None, deadline_verified_on=None)))
    turn = chat.say("Como está meu caso?", language="pt")
    assert turn.reply.splitlines()[-2].startswith("Situação do seu caso K-104233: Resolvido (consultado em")
    assert turn.reply.splitlines()[-1] == intake.msg.text("status.case_done", "pt") and "Ainda não há" not in turn.reply
    assert [s.id for s in turn.suggestions] == ["view_case", "report_another", "request_call"]   # no AC-24 chip yet


def test_ac_06_the_case_named_by_the_web_is_the_one_read_and_no_case_says_so():
    seen, cases = [], {"cases": [{**fake.FIXTURES["list_my_cases"]["cases"][0], "case_id": "K-200001"},
                                 *fake.FIXTURES["list_my_cases"]["cases"]], "read_at": "2026-06-01T15:04:11Z"}
    Chat(case_id="K-104233", mcp_transport=server(list_my_cases=cases, get_case=args_of(seen, PLAIN_CASE))
         ).say("¿Cómo va mi caso?", language="es")
    assert [a["case_id"] for a in seen] == ["K-104233"]
    none = Chat(mcp_transport=server()).say("¿Cómo va mi caso?", language="es")
    assert none.reply.splitlines()[-1].startswith("No tienes casos registrados (consultado el 2026-06-01 15:04 UTC)")
    assert none.case_id is None and [s.id for s in none.suggestions][-1] == "talk_to_person"


def test_ac_19_every_status_question_reads_the_system_again_in_that_turn():
    """Two questions in one thread: each one reads list_my_cases and get_case again and answers what this read says,
    never what the thread remembers."""
    calls, labels_read = [], iter(["verification", "resolved"])
    chat = Chat(mcp_transport=server(calls, list_my_cases=fake.FIXTURES["list_my_cases"],
                                     get_case=lambda a: case(queue_status=next(labels_read))))
    first = chat.say("¿Cómo va mi caso?", language="es")
    assert calls.count("get_case") == 1 and calls.count("list_my_cases") == 1 and "En revisión" in first.reply
    second = chat.say("¿Y ahora cómo va mi caso?")
    assert calls.count("get_case") == 2 and calls.count("list_my_cases") == 2
    assert "Resuelto" in second.reply and "En revisión" not in second.reply and not set(calls) & WRITES


def test_ac_19_a_card_question_reads_the_cards_with_the_reading_time():
    calls = []
    chat = Chat(mcp_transport=server(calls))
    turn = chat.say("estado de mi tarjeta", language="es")
    assert turn.reply.splitlines()[-1] == "Tu tarjeta terminada en 4417: bloqueada (consultado el 2026-06-01 15:04 UTC)."
    assert chat.say("estado de mi tarjeta").decision == "answer_status" and calls.count("list_my_cards") == 2
    assert "Bloquear" not in " ".join(labels(turn))      # AC-30: never offer a block


@pytest.mark.parametrize("text, down", [("¿Cómo va mi caso?", "list_my_cases"), ("¿Cómo va mi caso?", "get_case"),
                                        ("estado de mi tarjeta", "list_my_cards")])
def test_ac_19_a_failed_read_says_it_could_not_verify_and_states_no_status(text, down):
    chat = Chat(mcp_transport=server(**{"list_my_cases": fake.FIXTURES["list_my_cases"], down: DOWN}))
    chat.say(language="es")                              # the greeting, so the reply below is the status turn only
    turn = chat.say(text)
    assert turn.reply == intake.msg.text("status.read_failed", "es")
    assert not any(w in turn.reply for w in ("Recibido", "En revisión", "bloqueada", "K-104233")) and not turn.case_id
    assert next(s for s in turn.trace if s.node == "status").detail == f"{down}: not_confirmed"
    assert turn.suggestions[0].id == "check_case" and turn.suggestions[1].id == "talk_to_person"


def test_ac_28_a_call_request_goes_on_the_active_case_and_is_verified_by_get_case():
    seen = []
    turn = Chat(mcp_transport=server(list_my_cases=fake.FIXTURES["list_my_cases"],
                                     request_call=args_of(seen, fake.FIXTURES["request_call"]),
                                     get_case=lambda a: {**PLAIN_CASE, "action_id": a["action_id"],
                                                         "verification_id": "V-5C2F8A1E7B04"})).say(
        "Quiero hablar con una persona", language="es")
    assert seen[0]["case_id"] == "K-104233" and turn.case_id == "K-104233"
    assert turn.reply.splitlines()[-1] == ("Registré tu solicitud en el caso K-104233. Una persona te llamará a más "
                                           "tardar el 2026-06-02.")
    assert [(a.tool, a.state, a.verification_id) for a in turn.actions] == [("request_call", "verified", "V-5C2F8A1E7B04")]
    assert [s.id for s in turn.suggestions] == ["view_case", "report_another"] and turn.suggestions[0].href == "/case/K-104233"


def test_ac_28_without_an_active_case_the_call_is_general_and_stays_requested():
    seen, calls = [], []
    general = {**fake.FIXTURES["request_call"], "case_id": None}
    cases = {"cases": [{**fake.FIXTURES["list_my_cases"]["cases"][0], "queue_status": "closed"}],
             "read_at": "2026-06-01T15:04:11Z"}
    turn = Chat(mcp_transport=server(calls, list_my_cases=cases,
                                     request_call=args_of(seen, general))).say(
        "Quiero hablar con una persona", language="es")
    assert "case_id" not in seen[0] and turn.case_id is None and "get_case" not in calls
    assert [(a.tool, a.state) for a in turn.actions] == [("request_call", "requested")]          # D-026
    assert [s.id for s in turn.suggestions] == ["report_another", "check_case", "report_duplicate"]


@pytest.mark.parametrize("on_case", [True, False])
def test_ac_28_d_008_the_contact_date_is_shown_only_when_the_tool_returned_it(on_case):
    answer = {**fake.FIXTURES["request_call"], "expected_contact_by": None, **({} if on_case else {"case_id": None})}
    turn = Chat(mcp_transport=server(list_my_cases=fake.FIXTURES["list_my_cases"] if on_case else NO_CASES,
                                     request_call=answer)).say("Quiero hablar con una persona", language="es")
    key = "connect.requested_case_no_window" if on_case else "connect.requested_no_window"
    assert turn.reply.splitlines()[-1] == intake.msg.text(key, "es", case_id="K-104233")
    assert "2026-06-02" not in turn.reply and "más tardar" not in turn.reply


def test_d_020_f_010_status_with_dispute_words_answers_the_active_case_and_offers_another_charge():
    calls = []
    turn = Chat(mcp_transport=server(calls, list_my_cases=fake.FIXTURES["list_my_cases"])).say(ALREADY_REPORTED,
                                                                                               language="es")
    assert (turn.intent, turn.decision) == ("status_inquiry", "answer_status") and "search_transaction" not in calls
    assert "Estado de tu caso K-104233" in turn.reply and calls.count("list_my_cases") == 2   # route's read, then status's
    assert [s.id for s in turn.suggestions] == ["view_case", "report_another", "request_call"]


def test_d_020_f_010_status_with_dispute_words_and_no_active_case_takes_the_dispute_path():
    calls = []
    turn = Chat(mcp_transport=server(calls, get_fraud_score=score(72.0))).say(
        ALREADY_REPORTED + " Fue de 1250 USD en TIENDA X", language="es")
    assert record(turn)["decision"]["rule_ids"][0] == "POL-STATUS" and turn.decision != "answer_status"
    assert "search_transaction" in calls and "Estado de tu caso" not in turn.reply and turn.plan


def test_d_020_f_010_status_with_dispute_words_and_unread_cases_never_guesses():
    turn = Chat(mcp_transport=server(list_my_cases=DOWN)).say(ALREADY_REPORTED, language="es")
    assert turn.decision == "answer_status" and turn.reply.splitlines()[-1] == intake.msg.text("status.read_failed", "es")


@pytest.mark.parametrize("cases", [NO_CASES, fake.FIXTURES["list_my_cases"]])
def test_d_020_f_010_person_with_dispute_registers_the_call_and_never_decides_the_block(cases):
    """D-029/D-031: the engine decides whether the high zone blocks; the graph registers the call. With no verified case
    for this charge (T4 not run yet), the call is general and never names another charge's active case [assumption]."""
    seen, calls = [], []
    other = case(transaction={**CASE["transaction"], "transaction_id": "TRX-FIXTURE0000000000009"})
    general = {**fake.FIXTURES["request_call"], "case_id": None}
    turn = Chat(mcp_transport=server(calls, list_my_cases=cases, get_fraud_score=score(72.0), get_case=other,
                                     request_call=args_of(seen, general))).say(
        "Quiero hablar con una persona, no reconozco un cargo de 1250 USD en TIENDA X", language="es")
    decision = record(turn)["decision"]
    assert decision["request_call"] == "opened_case" and turn.zone == "high" and turn.plan
    assert "case_id" not in seen[0] and calls.count("request_call") == 1
    assert "K-104233" not in turn.reply and turn.case_id is None
    assert ("block_card" in calls) <= ("block_card" in decision["allowed_actions"])


def test_d_020_connect_uses_the_case_opened_this_turn_only_once_verified():
    """The contract with T4: `opened_case` names the case act opened only when its open_case is verified; otherwise
    the call is general, even when another charge has an active case [assumption], and is still registered."""
    another = fake.FIXTURES["list_my_cases"]                # K-104233, active, about another charge
    config = {"configurable": {"session_id": fake.SESSION_ID, "mcp_transport": server(list_my_cases=another)}}
    state = {"route": {"request_call": "opened_case"}, "case_id": "K-300001", "case_id_in": None}
    opened = {"tool": "open_case", "action_id": "A-71C0D5E8A2F3"}
    assert asyncio.run(intake.call_case({**state, "actions": [{**opened, "state": "verified"}]}, config)) == "K-300001"
    assert asyncio.run(intake.call_case({**state, "actions": [{**opened, "state": "not_confirmed"}]}, config)) is None
    assert asyncio.run(intake.call_case({**state, "case_id": None, "actions": []}, config)) is None
    assert asyncio.run(intake.call_case({**state, "route": {"request_call": "general"}}, config)) is None
    assert asyncio.run(intake.call_case({**state, "route": {"request_call": "active_or_general"}}, config)) == "K-104233"
