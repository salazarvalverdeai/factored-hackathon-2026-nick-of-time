"""Spec 04 task 04c (T4): act and verify, with retries, the four action states and the unconfirmed path, on the fake
MCP (FastMCP in-memory client). No LLM, no network; replay today is DEMO_TODAY 2026-06-01."""
from __future__ import annotations

import asyncio

import pytest
from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult

from contracts.tools import CUSTOMER_TOOLS, ToolError
from tests.test_spec04_decide import NO_CASES, TRX, record, score, server
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
    assert "Caso K-104233 abierto y verificado (verificación V-0C6A93F1B57D, 2026-06-01 15:04 UTC)." in reply
    assert ("Tarjeta terminada en 4417: bloqueada y verificada (verificación V-8B2D41C7E0A9, 2026-06-01 15:04 UTC)."
            in reply)
    deadline = next(line for line in reply if "2026-06-03" in line)  # the MX deadline, from get_case, with its source
    assert "Banxico Circular 3/2012" in deadline and "https://www.gob.mx/condusef/" in deadline
    # AC-26 (send by channel) is P1: no chip promises a send, so the row offers check_case instead (AC-29)
    assert [s.id for s in turn.suggestions] == ["view_case", "check_case", "request_call"]
    assert "comprobante" not in " ".join(s.label for s in turn.suggestions)
    assert turn.suggestions[0].href == "/case/K-104233"
    assert [s.node for s in turn.trace][-4:] == ["plan", "act", "verify", "respond"]


def test_ac_04_block_card_that_times_out_on_every_retry_escalates_and_never_says_blocked(monkeypatch):
    # Only block_card is slow: it sleeps 5 s, far past this budget, while every other call answers at once. The budget is
    # generous (1 s) so a GC pause or a loaded runner cannot time out the handshake or an earlier call (flaky at 0.05 s).
    monkeypatch.setattr(intake, "TIMEOUT_S", 1.0)
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


CASE_UNSURE = "Apertura del caso: SIN CONFIRMAR. Pide que te llame una persona para revisarlo."
BLOCK_UNSURE = "Bloqueo de la tarjeta: SIN CONFIRMAR."
DENY = ToolError(code="DENY", policy_id="POL-DEFAULT-DENY", message="not allowed")
CALL = "Quiero hablar con una persona, " + EV_0001.lower()


@pytest.mark.parametrize("code", ["DENY", "NOT_FOUND"])
def test_ac_18_a_final_open_case_error_sends_no_block_and_says_the_planned_block_is_not_confirmed(code):
    """The plan promised the block, so the step not tried still gets its own not-confirmed line."""
    calls = []
    turn = Chat(mcp_transport=server(calls, open_case=ToolError(code=code, message="no"))).say(EV_0001, language="es")
    assert calls.count("open_case") == 1 and "block_card" not in calls
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "not_confirmed"), ("block_card", "not_confirmed")]
    assert turn.reply.splitlines()[-2:] == [CASE_UNSURE, BLOCK_UNSURE] and turn.decision == "escalate_unconfirmed_action"


EXPIRED = ToolError(code="SESSION_EXPIRED", message="expired")


def down_then_expired(args):
    """open_case unanswered once (the server may have written), then the session expired."""
    down_then_expired.n = getattr(down_then_expired, "n", 0) + 1
    return DOWN if down_then_expired.n == 1 else EXPIRED


@pytest.mark.parametrize("other", [{"action_id": "A-9A4D07E2C5B1"},           # request_call's action, with a V-
                                   {"product_id": "PRD-FIXTURE00002"}])       # the right action on another card
def test_ac_18_a_reading_of_another_action_never_verifies(other):
    other = {**fake.FIXTURES["get_product_status"], **other}
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
    if text == CALL:     # D-029: a call request plans no block, so there is no block line to answer
        assert [(a.tool, a.state) for a in turn.actions][:1] == [("open_case", "verified")]
        assert "block_card" not in [a.tool for a in turn.actions] and "Bloqueo de la tarjeta" not in turn.reply
        return
    assert [(a.tool, a.state) for a in turn.actions][:2] == [("open_case", "verified"), ("block_card", "not_confirmed")]
    # the planned block: no escalation on this turn (D-050), so the person on that case decides it, never "revisará"
    assert ("Bloqueo de la tarjeta: SIN CONFIRMAR. La persona a cargo del caso K-104233 decide el bloqueo."
            in turn.reply.splitlines()) and "revisará" not in turn.reply
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
    assert "Caso K-104233 aberto e verificado (verificação V-0C6A93F1B57D, 2026-06-01 15:04 UTC)." in turn.reply
    assert [s.id for s in turn.suggestions] == ["view_case", "add_info", "request_call"]


def test_ac_18_d_029_only_the_writes_decide_allowed_run():
    """D-029 (ADR 0024): the engine withholds the block on a call request: the graph opens the case, registers the
    call on it and never calls block_card."""
    calls = []
    turn = Chat(mcp_transport=server(calls)).say(CALL, language="es")
    assert record(turn)["decision"]["allowed_actions"] == ["open_case"] and "block_card" not in calls
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "verified"), ("request_call", "verified")]
    assert "Registré tu solicitud en el caso K-104233" in turn.reply


DUP = {**fake.FIXTURES["open_case"], "duplicate_of": "K-104233"}
OPEN_CASE = {"ok": {}, "DOWN": {"open_case": DOWN}, "DENY": {"open_case": DENY},
             "NOT_FOUND": {"open_case": ToolError(code="NOT_FOUND", message="no")},
             "SESSION_EXPIRED": {"open_case": EXPIRED}, "DOWN, then SESSION_EXPIRED": {"open_case": down_then_expired},
             "duplicate_of": {"open_case": DUP}, "duplicate_of, get_case DOWN": {"open_case": DUP, "get_case": DOWN}}
ACTIVE = {**fake.FIXTURES["get_product_status"], "status": "Active"}
BLOCK_CARD = {"ok": {}, "DOWN": {"block_card": DOWN}, "DENY": {"block_card": DENY},
              "post-condition missing": {"get_product_status": lambda a: ACTIVE if a.get("action_id") else None}}
ANSWERS = {"open_case": ("Apertura del caso: ", "abierto y verificado", "Este cargo ya está en tu caso"),
           "block_card": ("Bloqueo de la tarjeta: ", "bloqueada y verificada")}


@pytest.mark.parametrize("text", [EV_0001, CALL])
@pytest.mark.parametrize("block", list(BLOCK_CARD))
@pytest.mark.parametrize("opened", list(OPEN_CASE))
def test_ac_04_ac_18_the_reply_answers_every_planned_action_in_exactly_one_state(opened, block, text):
    """Invariant over a fault grid: each action decide() allowed has exactly one record and one line, in one of the
    four states; verified only with a V- id from a read of that action on that case or card; no line claims a block
    or promises a review that was not verified; each write is sent with one idempotency key, retries included."""
    seen = []
    down_then_expired.n = 0
    turn = Chat(mcp_transport=server(seen=seen, **OPEN_CASE[opened], **BLOCK_CARD[block])).say(text, language="es")
    allowed = record(turn)["decision"]["allowed_actions"]
    assert allowed == (["open_case"] if text == CALL else ["open_case", "block_card"])     # D-029: a call never blocks
    records = [a for a in turn.actions if a.tool != "request_call"]
    assert [a.tool for a in records] == allowed
    assert all(a.state in ("in_progress", "requested", "verified", "not_confirmed") for a in turn.actions)
    lines = turn.reply.splitlines()
    after = lines[lines.index("Esto es lo que voy a hacer:") + 1 + len(turn.plan):]   # what the turn did
    for a in records:
        said = [line for line in lines if line.startswith(ANSWERS[a.tool][0]) or any(
            mark in line for mark in ANSWERS[a.tool][1:])]
        assert len(said) == 1, (a.tool, said)
        assert ("SIN CONFIRMAR" in said[0]) == (a.state == "not_confirmed")
        if a.state == "verified":
            target = {"product_id": TRX["product_id"]} if a.tool == "block_card" else {"case_id": turn.case_id}
            assert a.verification_id.startswith("V-") and a.read_at
            assert any(name == intake.VERIFIED_WITH[a.tool] and args.get("action_id") == a.action_id
                       and target.items() <= args.items() for name, args in seen)
        else:
            assert a.verification_id is None
    verified = {a.tool for a in records if a.state == "verified"}
    assert verified == {tool for tool, holds in (("open_case", opened in ("ok", "duplicate_of")),     # the cell's oracle
                                                ("block_card", block == "ok" and opened in ("ok", "DOWN")))
                if holds and tool in allowed}
    assert ("bloqueada" in "\n".join(after)) == ("block_card" in verified)
    assert ("open_case" in verified) == (turn.case_id is not None)
    if turn.case_id is None:
        assert not any("revisará" in line or "K-104233" in line for line in after)
        assert not any(s.href and s.href.startswith("/case/") for s in turn.suggestions)
        assert text == CALL or "Hablar con una persona" in labels(turn)
    for tool in allowed:
        assert len({args["idempotency_key"] for name, args in seen if name == tool}) <= 1
    # block_card follows open_case only when it was accepted (not as a duplicate) or got no answer
    assert any(name == "block_card" for name, _ in seen) == ("block_card" in allowed and opened in ("ok", "DOWN"))
    assert not (text == CALL and "Pide que te llame" in turn.reply)   # never asks for the call it registers
    if "SESSION_EXPIRED" in opened:          # sign in again; "nothing changed" only if no attempt went unanswered
        assert turn.decision == "reauthenticate" and lines[-1].startswith("Necesito que verifiques tu sesión")
        assert ("No hice ningún cambio" in lines[-1]) == (opened == "SESSION_EXPIRED")
        assert [s.id for s in turn.suggestions] == ["reauthenticate", "talk_to_person"]
        assert not any(name == "request_call" for name, _ in seen) and "Pide que te llame" not in turn.reply
    elif opened == "duplicate_of":
        assert turn.decision == ("connect_person" if text == CALL else None)
    elif verified != set(allowed):
        assert turn.decision == "escalate_unconfirmed_action"


def test_ac_18_the_planned_steps_not_confirmed_are_said_in_portuguese():
    turn = Chat(mcp_transport=server(open_case=DENY)).say(EV_0001, language="pt")
    lines = turn.reply.splitlines()
    assert lines[-2].startswith("Abertura do caso: SEM CONFIRMAÇÃO.") and lines[-1] == "Bloqueio do cartão: SEM CONFIRMAÇÃO."
    assert [(a.tool, a.state) for a in turn.actions] == [("open_case", "not_confirmed"), ("block_card", "not_confirmed")]
