"""Graph `dispute_intake` (spec 04 §4.1–§4.2), skeleton of task 04a (T1, T2): identity → greet → understand → route.

`route` runs spec 02 rules 1–4 (`engine.screen()`): reauthenticate/deny → refuse, connect_person → connect,
answer_status → status, a dispute → retrieve. Done here: identity, greet, understand (B0 rules arm and injection rules
in every arm; the LLM path of S1/S2 lands in T7, so no arm calls an LLM yet), route, refuse, connect (a general call
request only; T6 puts it on the active case and verifies it) and respond (templates and §4.5 chips). `retrieve` and
`status` are placeholders until T3 and T6: they call no tool and claim nothing. Tools are reached only through MCP
with the session of the run config (constitution #3); "today" comes from `config.today(mode)` (AC-27, ADR 0020).
Served as `dispute_intake_next` (langgraph.json) until it replaces the echo graph [assumption].
"""
# No `from __future__ import annotations`: the state types must resolve when the server loads this file by path.
import os
import uuid
from typing import Any, Optional, TypedDict

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from contracts.tools import CUSTOMER_TOOLS, ToolError
from nick_of_time import receipt as msg
from nick_of_time.config import resolve, today
from nick_of_time.contracts import TurnResult
from nick_of_time.nlu import load_nlu
from nick_of_time.policy import DecisionInput, PolicyEngine

ENGINE, NLU = PolicyEngine.load(), load_nlu("B0")
TIMEOUT_S = ENGINE.policies.reliability["tool_timeout_ms"] / 1000
DISPUTES = ("unrecognized_charge", "wrongful_charge")
# [assumption] until T3–T6: a press of these actions reads as this intent; confirm and choose_option keep the pending
# dispute. Pressing an action chip skips the classifier (AC-32).
ACTION_INTENT = {"request_call": "human_request", "send_summary": "status_inquiry",
                 "request_reevaluation": "status_inquiry", "verify_now": "status_inquiry"}
BRANCH = {"reauthenticate": "refuse", "deny": "refuse", "connect_person": "connect", "answer_status": "status"}


class InputState(TypedDict, total=False):   # spec 01 §6.4, as the echo graph
    messages: list[dict[str, Any]]
    language: Optional[str]
    action: Optional[dict[str, Any]]


OutputState = TypedDict("OutputState", {name: field.annotation for name, field in TurnResult.model_fields.items()},
                        total=False)


class Internal(TypedDict, total=False):     # spec 04 §4.1 fields outside TurnResult; kept on the thread
    session_id: str
    session_state: str
    arm: str
    case_id_in: Optional[str]
    today: str
    profile: Optional[dict[str, Any]]
    greet_pending: bool
    slots: dict[str, Any]
    injection_flagged: bool
    dispute_detected: bool
    active_case: Optional[bool]
    route: Optional[dict[str, Any]]         # rules 1–4 result; None = a dispute, go on
    branch: str
    body: list[str]
    row: Optional[str]                      # §4.5 row of this turn's chips
    language_last: Optional[str]            # the thread's language, kept when a request sends language null


State = TypedDict("State", {**InputState.__annotations__, **OutputState.__annotations__, **Internal.__annotations__},
                  total=False)
# Per-turn fields, cleared when a turn starts so nothing from the previous turn leaks into this one.
RESET = {"decision": None, "zone": None, "case_id": None, "actions": [], "denials": [], "guardrails_triggered": [],
         "body": [], "row": None, "route": None, "active_case": None, "greet_pending": False}


async def call(config: RunnableConfig, tool: str, **args: Any) -> BaseModel:
    """One MCP tool call with the session of the run config, never one from the text (constitution #3). Returns the
    tool's output model, or a ToolError for any failure (UNAVAILABLE for transport errors)."""
    settings = config["configurable"]
    try:
        transport = settings.get("mcp_transport") or StreamableHttpTransport(   # tests pass the fake server here
            os.environ["MCP_URL"], headers={"X-API-Key": os.environ.get("MCP_API_KEY", "")})
        async with Client(transport, timeout=TIMEOUT_S) as client:
            result = await client.call_tool(tool, {"session_id": settings["session_id"], **args}, raise_on_error=False)
        if result.is_error:
            return ToolError.model_validate(result.structured_content)
        return CUSTOMER_TOOLS[tool][1].model_validate(result.structured_content)
    except Exception as err:   # noqa: BLE001 — a failed call is a fact for the graph, never a crash
        return ToolError(code="UNAVAILABLE", message=type(err).__name__)


def identity(state: State, config: RunnableConfig) -> dict[str, Any]:
    """Session, mode and arm from the run config, injected by the api (spec 01 §6.4); never from the text."""
    settings = config.get("configurable") or {}
    if not settings.get("session_id"):
        raise ValueError("configurable.session_id is required; the api injects it (spec 01 §6.4)")
    if state.get("language") not in (None, "es", "pt"):
        raise ValueError(f"language must be es, pt or null, not {state.get('language')!r} (spec 01 §6.4)")
    arm = settings.get("arm") or "S0"       # [assumption] no arm → S0 (no LLM) until spec 15 names the default
    resolve(arm)                            # an unknown arm fails here
    mode = settings.get("mode") or "replay"
    today(mode)                             # an unknown mode fails here
    return {**RESET, "session_id": settings["session_id"], "arm": arm, "mode": mode,
            # [assumption] a missing session_state fails closed: unverified → reauthenticate (spec 02 rule 1)
            "session_state": settings.get("session_state") or "unverified", "case_id_in": settings.get("case_id"),
            "trace_id": str(config.get("run_id") or settings.get("run_id") or uuid.uuid4())}


async def greet(state: State, config: RunnableConfig) -> dict[str, Any]:
    """First turn of a verified session: the first name comes from get_customer_profile (AC-15)."""
    if state.get("profile") or state["session_state"] != "verified":
        return {}
    profile = await call(config, "get_customer_profile")
    if isinstance(profile, ToolError):
        return {}                           # no greeting without a name read from the tool; retried next turn
    return {"profile": profile.model_dump(mode="json"), "greet_pending": True}


def understand(state: State) -> dict[str, Any]:
    """Language, injection flag, intent and slots with the B0 rules arm; dates against the session's today."""
    profile = state.get("profile") or {}
    day = today(state["mode"], profile.get("country"))
    texts = [m.get("content", "") for m in state.get("messages") or [] if m.get("role", "user") == "user"]
    text, action = (texts[-1].strip() if texts else ""), state.get("action") or {}
    # [assumption] the thread's language: the request's, else the last turn's, else the first message's, else the
    # profile's. A customer who switches language mid-thread uses the web's language toggle.
    hint = state.get("language") or state.get("language_last")
    language = hint or profile.get("language") or "es"
    base = {"today": day.isoformat(), "language": language, "slots": {}, "injection_flagged": False,
            "intent": None, "intent_confidence": None, "dispute_detected": False}
    pending = state.get("intent") if state.get("intent") in DISPUTES else "unrecognized_charge"
    if action:                              # a pressed action chip or button skips the classifier (AC-32)
        intent = ACTION_INTENT.get(action.get("type"), pending)
        return {**base, "intent": intent, "intent_confidence": 1.0, "dispute_detected": intent in DISPUTES}
    if not text:
        return base
    reading = NLU.parse(text, hint, today=day)
    found = {"language": reading.language, "slots": reading.slots.model_dump(),
             "injection_flagged": reading.injection_flagged}
    chip = msg.offered_text_chip(text, state.get("suggestions") or [])
    if chip:                                # typed label = pressed text chip: routed by the pending question (AC-33)
        intent = msg.TEXT_CHIP_INTENT[chip] or pending
        return {**base, **found, "intent": intent, "intent_confidence": 1.0, "dispute_detected": intent in DISPUTES}
    return {**base, **found, "intent": reading.intent, "intent_confidence": reading.confidence,
            "dispute_detected": reading.dispute_detected}


async def route(state: State, config: RunnableConfig) -> dict[str, Any]:
    """Spec 02 rules 1–4 through `engine.screen()`; the engine, not the graph, picks the branch."""
    verified = state["session_state"] == "verified"
    if state.get("intent") is None and verified:
        return {"branch": "respond"}        # nothing to understand: the greeting, or a prompt to tell us more
    active = None
    if state.get("intent") == "status_inquiry" and state.get("dispute_detected") and verified:
        cases = await call(config, "list_my_cases")   # rule 3b needs to know whether a case is active
        if not isinstance(cases, ToolError):
            active = any(c.queue_status not in ("resolved", "closed") for c in cases.cases)
    decision = ENGINE.screen(DecisionInput(
        session_state=state["session_state"], intent=state.get("intent") or "out_of_scope",
        intent_confidence=float(state.get("intent_confidence") or 0), dispute_detected=state["dispute_detected"],
        injection_flagged=state["injection_flagged"],
        # [assumption] another customer's id or data is flagged by the injection rules (G-IN-01, spec 11); a separate
        # G-SES-02 detector, if any, comes with the tool-side check of spec 03.
        cross_customer=False, supervised_mode=False, active_case=active))
    if decision is None:
        return {"branch": "retrieve", "active_case": active}
    return {"branch": BRANCH[decision.decision], "route": decision.model_dump(mode="json"), "active_case": active,
            "decision": decision.decision, "guardrails_triggered": decision.guardrail_ids}


def refuse(state: State) -> dict[str, Any]:
    """DENY or re-authenticate with no data and a way forward; the denial is reported for policy_denials (AC-03)."""
    decision, rule = state["route"]["decision"], state["route"]["rule_ids"][-1]
    key = "refuse.deny" if decision == "deny" else (
        "connect.general_contact" if state.get("intent") == "human_request" else "refuse.reauthenticate")  # AC-28
    denial = {"policy_id": rule, "guardrail_id": ENGINE.policies.rules[rule].guardrail, "detail": decision}
    return {"body": [msg.text(key, state["language"])], "row": decision, "denials": [denial]}


async def connect(state: State, config: RunnableConfig) -> dict[str, Any]:
    """A general call request (spec 02 request_call, D-026): it stays "requested", as no read verifies it."""
    key = f"{state['session_id']}:none:request_call:{state['trace_id']}"
    out, language = await call(config, "request_call", idempotency_key=key), state["language"]
    if isinstance(out, ToolError):          # never refuse (AC-28) and never claim it (AC-18)
        label = msg.text("status.action_label.request_call", language)
        return {"body": [msg.text("status.action_not_confirmed", language, action_label=label)],
                "row": "connect_person"}
    when = out.expected_contact_by
    body = (msg.text("connect.requested", language, expected_contact_by=when.isoformat()) if when
            else msg.text("connect.requested_no_window", language))
    return {"body": [body], "row": "connect_person",
            "actions": [{"tool": "request_call", "action_id": out.action_id, "state": "requested"}]}


def retrieve(state: State) -> dict[str, Any]:
    """Placeholder until T3 (retrieve, decide, plan, clarify): asks what the charge is and acts on nothing."""
    return {"body": [msg.text("clarify.ask_what", state["language"])], "row": "ask_details"}


def status(state: State) -> dict[str, Any]:
    """Placeholder until T6: no reading yet, so it says it could not verify and states no status (AC-19)."""
    return {"body": [msg.text("status.read_failed", state["language"])], "row": "deny"}


def respond(state: State) -> dict[str, Any]:
    """The TurnResult from templates and §4.5 chips; clears the turn's input so the next turn starts clean."""
    language, profile, lines = state["language"], state.get("profile") or {}, []
    if state.get("greet_pending"):          # AC-15: name from the tool, three capabilities, a person reviews
        lines = [msg.text("greet.hello", language, first_name=profile["first_name"])] + [
            msg.text(f"greet.{key}", language) for key in ("capability_1", "capability_2", "capability_3",
                                                            "human_review")]
    row = state.get("row") or ("greet" if lines else "ask_details")
    body = state.get("body") or ([] if lines else [msg.text("clarify.ask_what", language)])
    branch = state.get("branch", "respond")
    nodes = ["identity", "greet", "understand", "route", *([branch] if branch != "respond" else []), "respond"]
    turn = TurnResult(
        reply="\n".join(lines + body), language=language, decision=state.get("decision"), intent=state.get("intent"),
        intent_confidence=state.get("intent_confidence"), case_id=state.get("case_id"),
        actions=state.get("actions") or [], suggestions=msg.suggestions(row, language, state.get("case_id")),
        guardrails_triggered=state.get("guardrails_triggered") or [], denials=state.get("denials") or [],
        mode=state["mode"], trace_id=state["trace_id"],
        trace=[{"node": n, "status": "deny" if n == "refuse" else "ok", "ms": 0} for n in nodes])
    return {**turn.model_dump(mode="json"), "messages": [], "action": None, "greet_pending": False,
            "language_last": language}


builder = StateGraph(State, input_schema=InputState, output_schema=OutputState)
for _node in (identity, greet, understand, route, refuse, connect, retrieve, status, respond):
    builder.add_node(_node.__name__, _node)
builder.add_edge(START, "identity")
builder.add_edge("identity", "greet")
builder.add_edge("greet", "understand")
builder.add_edge("understand", "route")
builder.add_conditional_edges("route", lambda state: state["branch"],
                              ["refuse", "connect", "retrieve", "status", "respond"])
for _node in ("refuse", "connect", "retrieve", "status"):
    builder.add_edge(_node, "respond")
builder.add_edge("respond", END)
graph = builder.compile(name="dispute_intake")   # Platform adds its own checkpointer; tests compile `builder` with one
