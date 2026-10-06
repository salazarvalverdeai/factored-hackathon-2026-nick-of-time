"""Spec 04 AC-38 and AC-40 (spec 01 §6.4.1 shapes, AC-09; ADR 0030): every tool call of a turn streams one `tool`
event `running`, then exactly one `done` or `failed` with the same id, whose cards hold only fields a tool returned.
Offline: fake MCP (FastMCP in-memory), arm S0, the template writer (the default)."""
from __future__ import annotations

import asyncio
import json
import re

import pytest

from contracts.tools import ToolError
from nick_of_time.contracts import ProgressItem, TurnResult
from nick_of_time.events import TextChunk, ToolEvent
from tests.test_spec04_decide import server
from tests.test_spec04_graph import Chat

EV_0001 = "No reconozco un cargo de 1250 USD en TIENDA X"        # MX, debit, score 72 (high), replay
CALL = "Quiero hablar con una persona, " + EV_0001.lower()
DOWN = ToolError(code="UNAVAILABLE", message="down")
# Spec 01 AC-09: no event carries a score, a zone, a policy id or a raw tool payload
INTERNAL = re.compile(r"score|POL-|\bzone\b|\bzona\b|product_id|amount_usd|idempotency|features_used", re.I)


def stream(chat: Chat, text: str, language: str = "es") -> tuple[list[tuple[str, dict]], TurnResult]:
    payload = {"messages": [{"role": "user", "content": text}], "language": language, "action": None}

    async def run():
        return [(mode, chunk) async for mode, chunk in chat.graph.astream(payload, chat.config,
                                                                        stream_mode=["custom", "values"])]
    chunks = asyncio.run(run())
    turn = TurnResult.model_validate({k: v for k, v in chunks[-1][1].items() if k in TurnResult.model_fields})
    return chunks, turn


def tools(chunks) -> list[ToolEvent]:
    return [ToolEvent.model_validate(c) for m, c in chunks if m == "custom" and c.get("kind") == "tool"]


def paired(events: list[ToolEvent]) -> dict[str, list[ToolEvent]]:
    """AC-38: per id, `running` first and then exactly one `done` or `failed`."""
    by_id: dict[str, list[ToolEvent]] = {}
    for e in events:
        by_id.setdefault(e.id, []).append(e)
    for steps in by_id.values():
        assert [e.status for e in steps][:1] == ["running"] and len(steps) == 2, [e.status for e in steps]
        assert steps[1].status in ("done", "failed") and steps[0].step == steps[1].step
        assert not steps[0].cards and steps[0].summary is None
    return by_id


def test_ac_38_ev_0001_streams_each_tool_running_then_done_with_cards_from_tool_results_only():
    chunks, turn = stream(Chat(mcp_transport=server(), mode="replay"), EV_0001)
    events = tools(chunks)
    by_id = paired(events)
    assert [e.step for e in events if e.status == "running"] == [
        "search_transaction", "evaluate_policy", "open_case", "block_card"]
    done = {steps[1].step: steps[1] for steps in by_id.values()}
    assert all(e.status == "done" for e in done.values())
    # the charge card is search_transaction's row, with get_product_status's last4
    charge = done["search_transaction"].cards[0]
    receipt = turn.receipt.model_dump(mode="json")
    assert charge.type == "charge" and receipt["product_last4"] == charge.last4
    assert (charge.amount, charge.currency, charge.merchant) == (1250.0, "USD", "TIENDA X")
    # the verdict is customer text, with no score, zone or rule id
    verdict = done["evaluate_policy"].cards[0]
    assert verdict.type == "verdict" and verdict.headline and not INTERNAL.search(verdict.headline)
    # the actions are verify's readings: verified only with the V- id the turn reports (constitution #4)
    verified = {a.tool: a.verification_id for a in turn.actions}
    for tool in ("open_case", "block_card"):
        action = next(c for c in done[tool].cards if c.type == "action")
        assert action.state == "verified" and action.verification_id == verified[tool]
    case = next(c for c in done["open_case"].cards if c.type == "case")
    assert case.case_id == turn.case_id
    deadlines = {c.kind: c.date for c in done["open_case"].cards if c.type == "deadline"}
    assert deadlines and set(deadlines.values()) <= set(json.dumps(receipt).split('"'))
    assert not INTERNAL.search(json.dumps([e.model_dump(mode="json") for e in events]))


def test_ac_38_a_failed_search_is_running_then_failed_with_no_cards():
    chunks, _ = stream(Chat(mcp_transport=server(search_transaction=DOWN), mode="replay"), EV_0001)
    events = tools(chunks)
    paired(events)
    assert [(e.step, e.status) for e in events] == [("search_transaction", "running"),
                                                    ("search_transaction", "failed")]
    assert events[1].cards == [] and events[1].summary


def test_ac_38_a_write_the_tool_refused_ends_failed_and_is_never_shown_as_done():
    chunks, turn = stream(Chat(mcp_transport=server(block_card=DOWN), mode="replay"), EV_0001)
    by_id = paired(tools(chunks))
    ends = {steps[1].step: steps[1].status for steps in by_id.values()}
    assert ends["block_card"] == "failed" and ends["open_case"] == "done"
    assert {a.tool: a.state for a in turn.actions}["block_card"] == "not_confirmed"


def test_ac_38_a_call_request_streams_request_call_with_its_action_card():
    chunks, turn = stream(Chat(mcp_transport=server(), mode="replay"), CALL)
    by_id = paired(tools(chunks))
    call = next(steps[1] for steps in by_id.values() if steps[0].step == "request_call")
    action = next(c for c in call.cards if c.type == "action")
    record = next(a for a in turn.actions if a.tool == "request_call")
    assert (action.state, action.verification_id) == (record.state, record.verification_id)


def test_ac_38_a_status_question_streams_get_case_with_the_case_read_now():
    chat = Chat(mode="replay")                     # the fixture server keeps the case the first turn opened
    stream(chat, EV_0001)
    chunks, turn = stream(chat, "¿Cómo va mi caso?")
    by_id = paired(tools(chunks))
    read = next(steps[1] for steps in by_id.values() if steps[0].step == "get_case")
    assert read.status == "done" and next(c for c in read.cards if c.type == "case").case_id == turn.case_id


@pytest.mark.parametrize("text", [EV_0001, CALL])
def test_ac_40_spec01_ac_09_template_writer_streams_no_text_and_every_custom_chunk_has_a_known_shape(text):
    chunks, _ = stream(Chat(mcp_transport=server(), mode="replay"), text)
    for mode, chunk in chunks:
        if mode != "custom":
            continue
        kind = chunk.get("kind")
        assert kind in (None, "tool"), chunk                     # no `text` chunk with the template writer
        (ToolEvent if kind else ProgressItem).model_validate(chunk)
    assert not [c for m, c in chunks if m == "custom" and c.get("kind") == "text"]
    assert TextChunk.model_fields.keys() == {"kind", "message_id", "delta"}
