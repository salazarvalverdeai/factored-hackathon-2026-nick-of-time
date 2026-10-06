"""Spec 04 AC-43 and spec 01 AC-06 (D-087, lead, 2026-10-06): each turn replies in the language of the customer's last
message when its words tell ES from PT; the session's language stays the default and the notification language, and
the graph never rewrites it. Offline: fake MCP, template writer, no LLM."""
from __future__ import annotations

import asyncio

import pytest

from nick_of_time import receipt as msg
from nick_of_time.contracts import ProgressItem, TurnResult
from nick_of_time.events import ToolEvent
from nick_of_time.nlu.rules import detect_language
from tests.test_spec04_decide import server
from tests.test_spec04_graph import Chat, fake_budget

EV_0001_PT = "Não reconheço uma cobrança de 1250 USD na TIENDA X"     # MX debit, score 72 (high): block + case
STATUS_ES = "¿Cómo va mi caso?"


def turn(chat: Chat, text: str | None, language: str | None = "es", action=None):
    """One streamed turn: its progress items, tool events and TurnResult. The api always sends the session's language
    (spec 01 §6.4), here ES."""
    payload = {"messages": [{"role": "user", "content": text}] if text else [], "language": language,
               "action": action}

    async def go():
        return [(mode, chunk) async for mode, chunk in chat.graph.astream(payload, chat.config,
                                                                        stream_mode=["custom", "values"])]
    with fake_budget():
        chunks = asyncio.run(go())
    custom = [c for m, c in chunks if m == "custom"]
    progress = [ProgressItem.model_validate(c) for c in custom if "kind" not in c]
    tools = [ToolEvent.model_validate(c) for c in custom if c.get("kind") == "tool"]
    result = TurnResult.model_validate({k: v for k, v in chunks[-1][1].items() if k in TurnResult.model_fields})
    return progress, tools, result


def in_language(progress, tools, result: TurnResult, language: str, tooled: bool = True) -> None:
    assert result.language == language
    assert [p.label for p in progress] == [msg.text(f"progress.{p.step}", language) for p in progress]
    assert (tools or not tooled) and all(t.title == msg.text(f"tool.{t.step}.title", language) for t in tools)
    assert all(t.summary in {v[language] for k, v in msg.messages()["tool"][t.step].items() if k != "title"}
               for t in tools if t.summary)
    assert [s.label for s in result.suggestions] == [msg.chip(s.id, language, result.case_id).label
                                                    for s in result.suggestions]


def test_ac_43_spec01_ac_06_a_pt_message_in_an_es_session_gets_pt_and_the_next_es_message_gets_es_again():
    chat = Chat(mcp_transport=server(), mode="replay")
    progress, tools, pt = turn(chat, EV_0001_PT)
    in_language(progress, tools, pt, "pt")
    assert pt.reply.startswith("Olá, Ana.") and "Caso K-104233 aberto e verificado" in pt.reply
    assert pt.receipt and pt.receipt.language == "pt"
    assert any(f.fact.startswith("Caso K-104233 aberto e verificado") for f in pt.receipt.verified_facts)
    assert [a.label for a in pt.receipt.actions] == [msg.text(f"status.action_label.{a}", "pt")
                                                    for a in ("open_case", "block_card")]
    assert chat.state()["session_language"] == "es"                   # the session's language is never rewritten

    progress, tools, es = turn(chat, STATUS_ES)
    in_language(progress, tools, es, "es", tooled=False)
    assert es.reply.startswith("No tienes casos registrados")                  # the fake has no case listed
    assert chat.state()["session_language"] == "es"


def test_ac_43_a_message_that_does_not_tell_the_languages_apart_or_a_chip_keeps_the_last_turns_language():
    chat = Chat(mcp_transport=server(), mode="replay")
    assert turn(chat, EV_0001_PT)[2].language == "pt"
    assert turn(chat, "ok")[2].language == "pt"                        # no ES or PT words: the last turn's
    assert turn(chat, None, action={"type": "request_call", "value": ""})[2].language == "pt"   # a chip press


def test_ac_43_a_lone_language_word_does_not_switch_and_the_session_toggle_wins_over_the_last_turn():
    assert detect_language("Ignora las reglas", None, default="pt", min_words=2) == "pt"
    chat = Chat(mcp_transport=server(), mode="replay")
    assert turn(chat, EV_0001_PT)[2].language == "pt"
    assert turn(chat, "ok", language="es")[2].language == "pt"
    # the web's toggle changes the session's language: from then on it is the default again
    assert turn(chat, "ok", language="pt")[2].language == "pt"
    assert turn(chat, "ok", language="es")[2].language == "es"


@pytest.mark.parametrize("text", ["What is the status of my case please", "I do not recognize this charge on my card"])
def test_ac_43_g_in_03_another_language_keeps_the_session_language_plus_english_once(text):
    chat = Chat(mcp_transport=server(), mode="replay")
    turn(chat, EV_0001_PT)
    result = turn(chat, text)[2]
    assert "G-IN-03" in result.guardrails_triggered and result.language == "es"
    assert result.reply == msg.text("refuse.other_language", "es")
