"""Spec 04 task 04c (T4): act and verify, with retries, the four action states and the unconfirmed path, on the fake
MCP (FastMCP in-memory client). No LLM, no network; replay today is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

import asyncio

import pytest
from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult

from contracts.tools import CUSTOMER_TOOLS, ToolError
from tests.test_spec04_decide import NO_CASES, record, score, server
from tests.test_spec04_graph import Chat, fake, intake, labels

EV_0001 = "No reconozco un cargo de 1250 USD en TIENDA X"        # MX, debit, score 72 (high), replay
DOWN = ToolError(code="UNAVAILABLE", message="down")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "DEMO_TODAY", "MCP_URL"):
        monkeypatch.delenv(name, raising=False)


def told(turn) -> str:
    """The reply after the greeting (whose capability line says the assistant can block a card)."""
    lines = turn.reply.splitlines()
    return "\n".join(lines[lines.index("Esto es lo que voy a hacer:"):]).lower()


def hanging(seen: list, hang: str) -> FastMCP:
    """The fake server, except that `hang` stores each call's arguments in `seen` and never answers in time."""
    srv = FastMCP("fake-with-a-hanging-tool")
    for name, (model_in, model_out) in CUSTOMER_TOOLS.items():
        class Tool(fake.FixtureTool):
            async def run(self, arguments):
                if self.name == "list_my_cases":
                    return ToolResult(structured_content=NO_CASES)
                if self.name == hang:
                    seen.append(arguments)
                    await asyncio.sleep(5)
                return await super().run(arguments)
        srv.add_tool(Tool(name=name, description=name, parameters=model_in.model_json_schema(),
                          output_schema=model_out.model_json_schema()))
    return srv


def test_ac_01_ev_0001_ends_with_the_card_blocked_and_verified_and_the_case_open():
    calls = []
    chat = Chat(mcp_transport=server(calls), mode="replay")
    turn = chat.say(EV_0001, language="es")
    assert (turn.decision, turn.zone, turn.case_id, turn.mode) == ("block_and_open_case", "high", "K-104233", "replay")
    assert chat.state()["today"] == "2026-06-01"
    assert [(a.tool, a.state, a.verification_id) for a in turn.actions] == [
        ("open_case", "verified", "V-0C6A93F1B57D"), ("block_card", "verified", "V-8B2D41C7E0A9")]
    assert all(a.read_at for a in turn.actions)
    writes = [c for c in calls if c in ("open_case", "block_card")]
    assert writes == ["open_case", "block_card"]                    # the ticket first, then the block (spec 03 Q3)
    reply = turn.reply.splitlines()
    assert "Caso K-104233 abierto y verificado (verificación V-0C6A93F1B57D, 2026-06-01T15:04:11Z)." in reply
    assert ("Tarjeta terminada en 4417: bloqueada y verificada (verificación V-8B2D41C7E0A9, 2026-06-01T15:04:09Z)."
            in reply)
    deadline = next(line for line in reply if "2026-06-03" in line)  # the MX deadline, from get_case, with its source
    assert "Banxico Circular 3/2012" in deadline and "https://www.gob.mx/condusef/" in deadline
    assert [s.id for s in turn.suggestions] == ["view_case", "send_summary", "request_call"]
    assert turn.suggestions[0].href == "/case/K-104233"
    assert [s.node for s in turn.trace][-4:] == ["plan", "act", "verify", "respond"]


def test_ac_04_block_card_that_times_out_on_every_retry_escalates_and_never_says_blocked(monkeypatch):
    monkeypatch.setattr(intake, "TIMEOUT_S", 0.05)
    seen = []
    turn = Chat(mcp_transport=hanging(seen, "block_card")).say(EV_0001, language="es")
    assert len(seen) == 1 + intake.RETRIES                           # the first call and its retries
    assert len({args["idempotency_key"] for args in seen}) == 1      # one key: the server writes once
    assert turn.decision == "escalate_unconfirmed_action" and turn.case_id == "K-104233"
    block = next(a for a in turn.actions if a.tool == "block_card")
    assert block.state == "not_confirmed" and block.verification_id is None and block.action_id.startswith("A-")
    assert "Bloqueo de la tarjeta: SIN CONFIRMAR. Una persona lo revisará." in turn.reply.splitlines()
    assert "bloqueada" not in told(turn) and "blocked" not in told(turn)
    assert [s.id for s in turn.suggestions] == ["view_case", "add_info", "request_call"]
    step = next(s for s in turn.trace if s.node == "verify")
    assert (step.status, step.detail) == ("error", "block_card: not_confirmed")


def test_ac_04_a_write_accepted_whose_verifying_read_fails_is_not_confirmed():
    calls = []
    card = fake.FIXTURES["list_my_cards"]["cards"][0]
    reads = server(calls, get_product_status=lambda args: DOWN if args.get("action_id") else card)
    turn = Chat(mcp_transport=reads).say(EV_0001, language="es")
    block = next(a for a in turn.actions if a.tool == "block_card")
    assert (block.state, block.action_id, block.verification_id) == ("not_confirmed", "A-3E9F20B7C164", None)
    assert calls.count("block_card") == 1                            # the write was accepted once; only reads retry
    assert calls.count("get_product_status") == 1 + 1 + intake.RETRIES   # retrieve's read, then verify's reads
    assert turn.decision == "escalate_unconfirmed_action" and "bloqueada" not in told(turn)


def test_ac_04_a_read_without_the_post_condition_never_verifies():
    """A V- for the right action is not enough: block_card holds only when the card reads Blocked."""
    active = {**fake.FIXTURES["get_product_status"], "status": "Active"}
    turn = Chat(mcp_transport=server(get_product_status=active)).say(EV_0001, language="es")
    assert next(a for a in turn.actions if a.tool == "block_card").state == "not_confirmed"
    assert turn.decision == "escalate_unconfirmed_action"


def test_ac_18_an_unconfirmed_case_gives_no_case_id_and_promises_no_review():
    calls = []
    turn = Chat(mcp_transport=server(calls, open_case=DOWN)).say(EV_0001, language="es")
    assert calls.count("open_case") == 1 + intake.RETRIES and turn.case_id is None
    assert turn.decision == "escalate_unconfirmed_action" and "K-104233" not in turn.reply
    assert turn.reply.splitlines()[-1].startswith("No pude confirmar la apertura de tu caso")
    assert next(a for a in turn.actions if a.tool == "open_case").state == "not_confirmed"
    assert labels(turn)[0] == "Hablar con una persona" and not any(s.href for s in turn.suggestions)


def test_ac_18_a_deny_is_final_and_never_retried():
    calls = []
    deny = ToolError(code="DENY", policy_id="POL-DEFAULT-DENY", message="not allowed")
    turn = Chat(mcp_transport=server(calls, block_card=deny)).say(EV_0001, language="es")
    assert calls.count("block_card") == 1 and "get_product_status" not in calls[calls.index("block_card"):]
    assert next(a for a in turn.actions if a.tool == "block_card").state == "not_confirmed"


def test_ac_18_the_four_action_states_and_only_verified_carries_the_read_time():
    lines = {state: intake.msg.action_line("block_card", state, "es", verified_at="2026-06-01T15:04:09Z")
             for state in ("in_progress", "requested", "verified", "not_confirmed")}
    assert lines == {"in_progress": "Bloqueo de la tarjeta: en curso.",
                     "requested": "Bloqueo de la tarjeta: solicitud enviada.",
                     "verified": "Bloqueo de la tarjeta: verificación confirmada (2026-06-01T15:04:09Z).",
                     "not_confirmed": "Bloqueo de la tarjeta: SIN CONFIRMAR. Una persona lo revisará."}
    pt = intake.msg.action_line("open_case", "not_confirmed", "pt")
    assert pt == "Abertura do caso: SEM CONFIRMAÇÃO. Uma pessoa vai revisar."
    turn = Chat(mcp_transport=server(get_fraud_score=score(12.0))).say(EV_0001, language="pt")   # human zone, PT
    assert (turn.decision, turn.case_id) == ("handoff", "K-104233")
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "verified")]      # never a block
    assert "Caso K-104233 aberto e verificado (verificação V-0C6A93F1B57D, 2026-06-01T15:04:11Z)." in turn.reply
    assert [s.id for s in turn.suggestions] == ["view_case", "add_info", "request_call"]


def test_ac_18_d_029_only_the_writes_decide_allowed_run(monkeypatch):
    """With the D-029 flip the engine withholds the block on a call request: the graph opens the case, registers the
    call on it and never calls block_card."""
    monkeypatch.setattr("nick_of_time.policy.engine.D029_CALL_WITHHOLDS_BLOCK_REASON", "supervised_mode")
    calls = []
    turn = Chat(mcp_transport=server(calls)).say("Quiero hablar con una persona, " + EV_0001.lower(), language="es")
    assert record(turn)["decision"]["allowed_actions"] == ["open_case"] and "block_card" not in calls
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "verified"), ("request_call", "requested")]
    assert "Registré tu solicitud en el caso K-104233" in turn.reply
