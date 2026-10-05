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


CASE_UNSURE = "Apertura del caso: SIN CONFIRMAR. Pide que te llame una persona para revisarlo."
BLOCK_UNSURE = "Bloqueo de la tarjeta: SIN CONFIRMAR."
DENY = ToolError(code="DENY", policy_id="POL-DEFAULT-DENY", message="not allowed")
CALL = "Quiero hablar con una persona, " + EV_0001.lower()


@pytest.mark.parametrize("block", [DOWN, DENY])
def test_ac_04_with_no_verified_case_every_unconfirmed_action_says_so_and_promises_no_review(block):
    """MCP down (or open_case unanswered and block_card refused, spec 03 AC-10): the plan promised a block, so the
    reply says the block is not confirmed too, with no case id and no promised review."""
    calls = []
    turn = Chat(mcp_transport=server(calls, open_case=DOWN, block_card=block)).say(EV_0001, language="es")
    assert calls.count("open_case") == 1 + intake.RETRIES and turn.case_id is None
    assert calls.count("block_card") == (1 + intake.RETRIES if block is DOWN else 1)
    assert turn.reply.splitlines()[-2:] == [CASE_UNSURE, BLOCK_UNSURE] and "revisará" not in turn.reply
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "not_confirmed"),
                                                         ("block_card", "not_confirmed")]
    assert turn.decision == "escalate_unconfirmed_action" and "bloqueada" not in told(turn)
    assert labels(turn)[0] == "Hablar con una persona" and not any(s.href for s in turn.suggestions)


def test_ac_18_an_unanswered_case_still_tries_the_block_and_reports_each_state():
    turn = Chat(mcp_transport=server(open_case=DOWN)).say(EV_0001, language="es")
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "not_confirmed"), ("block_card", "verified")]
    assert turn.case_id is None and "K-104233" not in turn.reply and CASE_UNSURE in turn.reply.splitlines()


@pytest.mark.parametrize("code", ["DENY", "NOT_FOUND"])
def test_ac_18_a_final_open_case_error_sends_no_block(code):
    calls = []
    turn = Chat(mcp_transport=server(calls, open_case=ToolError(code=code, message="no"))).say(EV_0001, language="es")
    assert calls.count("open_case") == 1 and "block_card" not in calls
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "not_confirmed")]
    assert turn.reply.splitlines()[-1] == CASE_UNSURE


def test_ac_18_an_expired_session_on_open_case_asks_to_sign_in_again():
    calls = []
    expired = ToolError(code="SESSION_EXPIRED", message="expired")
    turn = Chat(mcp_transport=server(calls, open_case=expired)).say(CALL, language="es")
    assert "block_card" not in calls and "request_call" not in calls
    assert (turn.decision, turn.case_id) == ("reauthenticate", None)
    assert turn.reply.splitlines()[-1].startswith("Necesito que verifiques tu sesión")
    assert [s.id for s in turn.suggestions] == ["reauthenticate", "talk_to_person"]


def test_ac_18_a_call_request_with_an_unconfirmed_case_does_not_ask_for_the_call_it_registers():
    turn = Chat(mcp_transport=server(open_case=DOWN, get_fraud_score=score(40.0))).say(CALL, language="es")
    lines = turn.reply.splitlines()
    assert "Apertura del caso: SIN CONFIRMAR." in lines and not any("Pide que te llame" in line for line in lines)
    assert lines[-1].startswith("Listo, registré tu solicitud") and turn.case_id is None   # a general call


def test_ac_18_a_reading_of_another_action_never_verifies():
    other = {**fake.FIXTURES["get_product_status"], "action_id": "A-9A4D07E2C5B1"}   # request_call's action, with a V-
    turn = Chat(mcp_transport=server(get_product_status=other)).say(EV_0001, language="es")
    assert next(a for a in turn.actions if a.tool == "block_card").state == "not_confirmed"


@pytest.mark.parametrize("read", [DOWN, {**fake.FIXTURES["get_case"], "case_id": "K-999999"}])
def test_ac_18_an_unverified_case_id_never_reaches_the_customer(read):
    turn = Chat(mcp_transport=server(get_case=read)).say(EV_0001, language="es")
    assert turn.case_id is None and "K-104233" not in turn.reply and "K-999999" not in turn.reply
    assert next(a for a in turn.actions if a.tool == "open_case").state == "not_confirmed"
    assert not any(s.href for s in turn.suggestions)


@pytest.mark.parametrize("text, decision", [(EV_0001, None), (CALL, "connect_person")])
def test_ac_18_d_050_open_case_duplicate_of_blocks_nothing_and_reports_as_duplicate(text, decision):
    calls = []
    dup = {**fake.FIXTURES["open_case"], "duplicate_of": "K-104233"}
    turn = Chat(mcp_transport=server(calls, open_case=dup)).say(text, language="es")
    assert "block_card" not in calls and turn.decision == decision and turn.case_id == "K-104233"
    assert "Este cargo ya está en tu caso K-104233" in turn.reply and "Tarjeta terminada" not in turn.reply
    if decision is None:
        assert [s.id for s in turn.suggestions] == ["view_case", "add_info", "request_call"]


def test_ac_18_a_verifying_read_deny_is_never_retried():
    calls = []
    card = fake.FIXTURES["list_my_cards"]["cards"][0]
    reads = server(calls, get_product_status=lambda args: DENY if args.get("action_id") else card)
    turn = Chat(mcp_transport=reads).say(EV_0001, language="es")
    assert calls.count("get_product_status") == 2                  # retrieve's read, then one verifying read
    assert next(a for a in turn.actions if a.tool == "block_card").state == "not_confirmed"


def test_ac_18_a_deny_is_final_and_never_retried():
    calls = []
    turn = Chat(mcp_transport=server(calls, block_card=DENY)).say(EV_0001, language="es")
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
    turn = Chat(mcp_transport=server(calls)).say(CALL, language="es")
    assert record(turn)["decision"]["allowed_actions"] == ["open_case"] and "block_card" not in calls
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "verified"), ("request_call", "verified")]
    assert "Registré tu solicitud en el caso K-104233" in turn.reply
