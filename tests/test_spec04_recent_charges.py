"""Spec 04 D-085 (AC-42, P0 fix): a dispute with no amount, date or merchant, and the `show_recent` and
`dont_remember_amount` chip labels, list the latest charges as option cards instead of asking for details again; a list
counts no clarification turn. On the fake MCP (FastMCP in-memory client) and on the real MCP server over a fixture gold
shaped as the production customer (five charges on three cards in the last 30 days). No LLM, no network; replay today
is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

from contextlib import ExitStack

import pytest

from nick_of_time import receipt as msg
from tests import local_mcp as L
from tests.test_spec04_decide import WRITES, candidates, record, score, server
from tests.test_spec04_graph import PERSON, Chat, intake, labels

NO_DETAILS = {"es": "No reconozco un cargo en mi tarjeta", "pt": "Não reconheço uma cobrança no meu cartão"}
LABELS = [(chip, language) for chip in intake.RECENT_CHIPS for language in ("es", "pt")]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "DEMO_TODAY", "MCP_URL", "MCP_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def label(chip: str, language: str = "es") -> str:
    return msg.text(f"suggest.{chip}", language)


def searches(seen: list[tuple]) -> list[dict]:
    """The arguments of every search_transaction call, without the session (which comes from the run config)."""
    return [{k: v for k, v in args.items() if k != "session_id"} for tool, args in seen if tool == "search_transaction"]


def listed(turn, language: str = "es", shown: int = 3) -> None:
    """AC-42: the latest charges as cards from the tool's candidates, clarify.pick_one, the ask_recent row (a person
    among the chips), nothing written."""
    assert turn.decision == "ask" and turn.case_id is None and not turn.actions and not turn.plan
    assert [o.label for o in turn.options] == [msg.option_label(c) for c in candidates(4)["candidates"][:shown]]
    assert turn.reply.splitlines()[-1] == msg.text("clarify.pick_one", language)
    assert [s.id for s in turn.suggestions] == ["none_of_these", "talk_to_person"] and PERSON & set(labels(turn))


@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_42_a_dispute_with_no_details_and_several_charges_lists_the_latest_as_cards(language):
    """AC-42: no amount, date or merchant and more charges than max_candidate_transactions: the first three the tool
    ranked (most recent first) as cards, never a request for details; no clarification turn counted; only the cards
    shown stay candidates."""
    calls, seen = [], []
    chat = Chat(mcp_transport=server(calls, seen, search_transaction=candidates(4)))
    turn = chat.say(NO_DETAILS[language], language=language)
    listed(turn, language)
    assert searches(seen) == [{}] and not set(calls) & WRITES and "get_fraud_score" not in calls
    assert chat.state()["clarification_turns"] == 0 and len(chat.state()["candidates"]) == intake.MAX_OPTIONS


@pytest.mark.parametrize("chip, language", LABELS)
def test_ac_42_the_chip_labels_list_the_charges_by_rule_without_the_classifier(chip, language, monkeypatch):
    """AC-42 (with AC-32): after a search a slot narrowed still finds too many (that ask for details is unchanged), the
    show_recent or dont_remember_amount label, typed or pressed, in ES or PT, lists the latest charges with a search
    with no slot; the classifier is never asked."""
    seen: list[tuple] = []
    chat = Chat(mcp_transport=server(seen=seen, search_transaction=candidates(4)))
    asked = chat.say("No reconozco un cargo de 1250 USD" if language == "es" else
                     "Não reconheço uma cobrança de 1250 USD", language=language)
    assert asked.decision == "ask" and not asked.options and searches(seen)[0]["amount"] == 1250.0
    assert [s.id for s in asked.suggestions] == ["show_recent", "dont_remember_amount", "talk_to_person"]

    def no_classifier(*args, **kwargs):
        raise AssertionError("the classifier was asked")
    monkeypatch.setattr(intake.NLU, "parse", no_classifier)
    monkeypatch.setattr(intake.arms, "understand", no_classifier)
    turn = chat.say(label(chip, language), language=language)
    listed(turn, language)
    assert searches(seen)[-1] == {} and turn.intent == "unrecognized_charge" and turn.intent_confidence == 1.0


def test_ac_42_a_label_not_offered_still_lists_and_keeps_the_pending_dispute():
    """AC-42: the rule is the fixed label, offered or not (here after a wrongful-charge ask, case and accents ignored);
    the turn goes on with the dispute being clarified."""
    seen: list[tuple] = []
    chat = Chat(mcp_transport=server(seen=seen, search_transaction=candidates(4)))
    chat.say("Me cobraron dos veces 1250 USD", language="es")
    turn = chat.say("muestrame mis ultimos cargos!", language="es")
    listed(turn)
    assert turn.intent == "wrongful_charge"


def test_ac_42_no_recuerdo_el_monto_with_candidates_shows_the_options_and_never_exhausts_clarification():
    """AC-42 (the production path, with AC-13): an ask for details, the show_recent chip, then "No recuerdo el monto":
    every list shows the cards and counts no turn, so no clarify.exhausted and no call; a card picked then goes on to
    the rules on that charge, and an id never shown finds nothing."""
    calls: list[str] = []
    seen: list[tuple] = []
    chat = Chat(mcp_transport=server(calls, seen, search_transaction=candidates(4), get_fraud_score=score(72.0)))
    assert chat.say("No reconozco un cargo de 1250 USD", language="es").decision == "ask"
    assert chat.state()["clarification_turns"] == 1
    for text in (label("show_recent"), label("dont_remember_amount"), label("dont_remember_amount")):
        turn = chat.say(text, language="es")
        listed(turn)
        assert chat.state()["clarification_turns"] == 1 and "request_call" not in calls
    picked = candidates(4)["candidates"][1]["transaction_id"]
    done = chat.say(action={"type": "choose_option", "value": picked})
    assert record(done)["decision"]["decision"] == "block_and_open_case"     # the fake's reads name its own charge
    assert next(args for tool, args in seen if tool == "open_case")["transaction_id"] == picked


def test_ac_42_only_a_card_shown_can_be_picked():
    """AC-42 (with AC-02): the search found four, three were shown; the fourth id is not a candidate, so nothing is
    read or written about it and the turn asks again."""
    calls: list[str] = []
    chat = Chat(mcp_transport=server(calls, search_transaction=candidates(4)))
    chat.say(NO_DETAILS["es"], language="es")
    hidden = candidates(4)["candidates"][3]["transaction_id"]               # found, never shown
    forged = chat.say(action={"type": "choose_option", "value": hidden})
    assert forged.decision == "ask" and not forged.options and "get_fraud_score" not in calls
    assert not set(calls) & WRITES


def test_ac_42_none_of_these_after_a_list_asks_for_the_details():
    """AC-42: the "Ninguno de estos" chip of the ask_recent row asks for the details (ask_details row), a counted turn."""
    chat = Chat(mcp_transport=server(search_transaction=candidates(4)))
    chat.say(NO_DETAILS["es"], language="es")
    turn = chat.say(action=msg.ACTION["none_of_these"])
    assert turn.decision == "ask" and not turn.options
    assert turn.reply.splitlines()[-1] == msg.text("clarify.ask_what", "es")
    assert [s.id for s in turn.suggestions] == ["show_recent", "dont_remember_amount", "talk_to_person"]
    assert chat.state()["clarification_turns"] == 1


def test_ac_42_ac_13_with_no_charge_found_the_details_path_is_unchanged():
    """AC-42 (with AC-13): zero candidates: the labels still search, find nothing, ask for the details and count the
    turn, so the third ask hands off with a general call, as before."""
    calls: list[str] = []
    chat = Chat(mcp_transport=server(calls, search_transaction={"candidates": []}))
    first = chat.say(NO_DETAILS["es"], language="es")
    second = chat.say(label("show_recent"), language="es")
    assert first.decision == second.decision == "ask" and not first.options and not second.options
    assert second.reply.splitlines()[-1] == msg.text("clarify.ask_what", "es")
    assert chat.state()["clarification_turns"] == 2
    third = chat.say(label("dont_remember_amount"), language="es")
    assert third.decision == "handoff" and third.case_id is None
    assert [(a.tool, a.state) for a in third.actions] == [("request_call", "requested")]


def test_ac_42_d_067_one_charge_found_is_still_the_card_to_confirm():
    """AC-42 keeps D-067: the label lists one charge, which is the card to confirm (confirm_charge row), not acted on."""
    calls: list[str] = []
    turn = Chat(mcp_transport=server(calls)).say(label("show_recent"), language="es")
    assert turn.decision == "ask" and len(turn.options) == 1 and not set(calls) & WRITES
    assert turn.reply.splitlines()[-1] == msg.text("clarify.confirm_one", "es")
    assert [s.id for s in turn.suggestions] == ["confirm_charge", "confirm_no", "talk_to_person"]


def test_ac_42_the_ask_recent_row_is_in_the_rule_table_with_a_person():
    """AC-42 (with AC-29, AC-20): the row lives in the server's rule table, 2 chips, a person among them, ES and PT."""
    for language in ("es", "pt"):
        row = msg.suggestions("ask_recent", language)
        assert [s.id for s in row] == ["none_of_these", "talk_to_person"]
        assert [s.kind for s in row] == ["action", "action"]


# ---------- the real MCP server, a fixture gold shaped as the production customer ----------
PRODUCTION = {
    "id": "D-085", "language": "es", "country": "MX",
    "initial_state": {"customer_id": "CLI-RECENT0CHRG1", "session": "verified", "fixtures": [
        {"transaction_id": f"TRX-RECENT{n:014d}", "product_id": product, "product_type": kind, "amount": amount,
         "currency": "USD", "transaction_date": day, "merchant": merchant, "fraud_score": 12.0}
        for n, (product, kind, amount, day, merchant) in enumerate([
            ("PRD-RECENTCARD01", "debit", 95.78, "2026-05-04", None),
            ("PRD-RECENTCARD02", "credit", 299.01, "2026-05-08", "Estación de Servicio"),
            ("PRD-RECENTCARD01", "debit", 22.12, "2026-05-16", "Restaurante El Buen Sabor"),
            ("PRD-RECENTCARD02", "credit", 178.47, "2026-05-19", "Tienda Don José"),
            ("PRD-RECENTCARD03", "debit", 329.32, "2026-05-22", "Servicios Públicos")], 1)]},
}


def test_ac_42_the_production_conversation_on_the_real_mcp_server(tmp_path):
    """AC-42 on the real MCP server (replay, 2026-06-01): the three production messages each list the three latest
    charges (2026-05-22, 05-19, 05-16) as cards from search_transaction, never exhaust clarification nor register a
    call; a card picked opens the case on that charge (human zone: a person reviews it)."""
    with ExitStack() as stack:
        store, kind = stack.enter_context(L.memory_store())
        mcp = L.LocalMCP(L.fixture_gold(tmp_path / "gold", PRODUCTION), store, kind, {}).start()
        stack.callback(mcp.close)
        sid = L.seed_session(store, PRODUCTION["initial_state"]["customer_id"], "es", "D-085:S0:1")
        chat = L.Chat(mcp, sid, thread="d-083")
        latest = [f"TRX-RECENT{n:014d}" for n in (5, 4, 3)]
        for text in (NO_DETAILS["es"], label("show_recent"), label("dont_remember_amount")):
            turn = chat.say(text, language="es")
            assert L.gate_drops(turn) == 0 and "G-OUT-01" not in turn.guardrails_triggered
            assert turn.decision == "ask" and turn.case_id is None and not turn.actions
            assert [o.id for o in turn.options] == latest
            assert turn.options[0].label == "USD 329.32 · 2026-05-22 · Servicios Públicos"
            assert {"talk_to_person"} <= {s.id for s in turn.suggestions}
        done = chat.say(action={"type": "choose_option", "value": latest[1]})
        assert L.gate_drops(done) == 0
        assert (done.decision, done.zone) == ("handoff", "human") and done.case_id and done.handoff
        assert mcp.tool("get_case", sid, case_id=done.case_id).transaction.transaction_id == latest[1]
