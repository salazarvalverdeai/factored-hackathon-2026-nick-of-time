"""Graph `dispute_intake` (spec 04 §4.1–§4.2), tasks 04a (T1, T2), 04b (T3), 04c (T4), 04d (T5) and 04e (T6).

identity → greet → understand → route. `route` runs spec 02 rules 1–4 (`engine.screen()`): reauthenticate/deny →
refuse, connect_person → connect, answer_status → status, a dispute → retrieve → decide. `decide` runs
`engine.decide()` on tool facts only and the graph follows its result: ask → clarify, deny → refuse, a case to open
(or confirm) → plan, a call with no case to open → connect. `plan` states the numbered steps; in confirm it stops
there, otherwise act runs the writes decide() allowed and verify reads each post-condition (T4). understand reads with
the B0 rules arm first in every arm. `status` re-reads cards or
cases in every turn that asks (AC-19) and `connect` registers the call where the decision says, on the active case or
a general one (AC-28; task 04e). `respond` builds the receipt and the handoff card from tool results, and the
grounding gate drops any fact no tool returned (G-OUT-01, task 04d). S1/S2 (task 04f, `nick_of_time.llm.steps`):
`understand` asks the LLM below τ in a verified session, and the reply stays template text (rewording waits for spec
15's `word` gate); any LLM failure runs the step as S0, and the run returns its usage and denials (AC-14). Tools are reached only through MCP
with the session of the run config (constitution #3); "today" comes from `config.today(mode)` (AC-27, ADR 0020).
Served as `dispute_intake` in langgraph.json (D-048 applied); the echo graph stays as `dispute_intake_echo`. Each
step streams its customer progress label as a LangGraph custom event while the run is in progress (AC-17).
"""
# No `from __future__ import annotations`: the state types must resolve when the server loads this file by path.
import asyncio
import functools
import inspect
import json
import logging
import os
import re
import uuid
from datetime import date, timezone
from typing import Annotated, Any, Optional, TypedDict

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from contracts.tools import CUSTOMER_TOOLS, VERIFIED_WITH, ToolError
from nick_of_time import receipt as msg
from nick_of_time.config import check_prices, now, resolve, today
from nick_of_time.llm import steps as arms
from nick_of_time.contracts import ProgressItem, TurnResult
from nick_of_time.events import TextChunk, ToolEvent
from nick_of_time.ids import new_id
from nick_of_time.llm import writer as wording
from nick_of_time.receipt import build
from nick_of_time.nlu import load_nlu
from nick_of_time.nlu.rules import detect_language
from nick_of_time.nlu.text import fold
from nick_of_time.policy import DecisionInput, PolicyDecision, PolicyEngine

ENGINE, NLU = PolicyEngine.load(), load_nlu("B0")
try:    # D-058: logged, not raised, so S0 and the echo graph on the same server stay up; that turn runs as S0
    check_prices()
except ValueError as err:
    logging.getLogger(__name__).error("%s: S1/S2 turns run as S0 until a price is configured", err)
TIMEOUT_S = ENGINE.policies.reliability["tool_timeout_ms"] / 1000
RETRIES = ENGINE.policies.reliability["tool_retries"]
MAX_OPTIONS = ENGINE.policies.clarify.max_candidate_transactions
TAU = ENGINE.policies.clarify.intent_confidence_min   # τ (spec 11 AC-07): the LLM is asked only below it
DISPUTES = ("unrecognized_charge", "wrongful_charge")
# D-067 [assumption]: amount and date name a charge (the search filters on them); a merchant only when EVERY content
# word of the slot (more than 2 letters, not a stop word, a currency code or a generic word) is a word of the one
# candidate's merchant (the search keeps null-merchant rows, and gold merchants share generic words: "Mercado Central"
# never names "Laboratorio Central"); a slot with no content word names nothing; a currency never names a charge.
CURRENCY_CODES = {"usd", "mxn", "cop", "ars", "brl", "pen", "clp"}
STOP_WORDS = {"del", "los", "las", "una", "uno", "unos", "unas", "con", "com", "por", "para", "dos", "das", "uma",
              "the", "and", "que", "mas", "muy", "este", "esta", "ese", "esa", "esse", "essa", "cargo", "cobro",
              "cobranca"}
GENERIC_WORDS = {"tienda", "central", "super", "servicio", "servicios", "centro", "comercial", "store", "shop", "loja",
                 "pago", "pagos", "compra"}
CLOSED = ("resolved", "closed")             # queue states of a case that is no longer active
# [assumption] until T3–T6: a press of these actions reads as this intent; confirm and choose_option keep the pending
# dispute. Pressing an action chip skips the classifier (AC-32).
ACTION_INTENT = {"request_call": "human_request", "send_summary": "status_inquiry",
                 "request_reevaluation": "status_inquiry", "verify_now": "status_inquiry"}
BRANCH = {"reauthenticate": "refuse", "deny": "refuse", "connect_person": "connect", "answer_status": "status"}
# [assumption] a typed yes or no (or a confirm chip's label) answers the confirm question only right after it was asked.
CONFIRM_WORDS = {"si": True, "sim": True, "si, continua": True, "sim, continue": True, "no": False, "nao": False,
                 "no es ese cargo": False, "nao e essa cobranca": False}
# D-067 [assumption]: the card of a charge the customer did not name (rows confirm_charge and confirm_call) is
# confirmed only by its chip, a tap on the card, or a typed reply that, folded and without punctuation, EQUALS one of
# these; anything longer ("Sí, quiero hablar con alguien", "Sí, el de Amazon") goes to the classifier as any message.
CHARGE_WORDS = {**{said: True for said in ("si", "si es ese", "si es ese cargo", "correcto", "ese es", "ese mismo",
                                           "sim", "sim e essa cobranca", "e essa", "essa mesma", "correto")},
                **{said: False for said in ("no", "no es ese cargo", "nao", "nao e essa cobranca")}}
# Another customer's data (spec 02 rule 2, POL-CROSS-CUSTOMER / G-SES-02), on folded text: a data word, then "of" a
# third party. The graph sets cross_customer; the nlu injection rules stay as they are (spec 11).
_DATA = (r"(?:saldo|cuentas?|contas?|tarjetas?|cartao|cartoes|transacc\w*|transac\w*|movimientos?|movimentos?"
         r"|extracto|extrato|datos|dados)")
# Precision over recall: own possession or a dispute in the text means the customer reports their own charge.
OWN_OR_DISPUTE = re.compile(r"\b(?:en|no|na|de|da|do) (?:mi|meu|minha) (?:tarjeta|cuenta|cartao|conta|extracto|extrato)\b"
                            r"|\bno (?:lo |la )?reconozco|\bnao reconhec|\bno autorice|\bnao autorizei|\bno hice"
                            r"|\bnao fiz|\bcobr\w*\b|\badicional\b")
_THIRD = (r"(?:otr[oa]|outr[oa]) (?:cliente|persona|pessoa|usuari[oa]|titular)|cliente (?:(?:n[o°º]\.?|numero|#) ?)?\d{3,}"
          r"|(?:cliente )?cli-[a-z0-9]{12}"     # EV-0116: a customer id of the gold shape (ids.GOLD_PATTERN)
          r"|(?:mi|minha|meu) (?:esposa|esposo|marido|mujer|hij[oa]|filh[oa]|madre|padre|mama|papa|mae|pai|herman[oa]"
          r"|irma|irmao|novi[oa]|namorad[oa]|pareja|amig[oa]|jefe|chefe|vecin[oa]|vizinh[oa])")
CROSS_CUSTOMER = re.compile(rf"\b{_DATA}\b(?: \w+){{0,4}}? (?:de|del|da|do) (?:la |el |o |a )?(?:{_THIRD})\b")
# D-085 (spec 04 AC-42): the fixed labels of these text chips, typed or pressed, in ES or PT and offered or not, ask
# to see the latest charges: the graph searches with no slot and lists them as cards, with no classifier.
RECENT_CHIPS = ("show_recent", "dont_remember_amount")


class InputState(TypedDict, total=False):   # spec 01 §6.4, as the echo graph
    messages: list[dict[str, Any]]
    language: Optional[str]
    action: Optional[dict[str, Any]]


OutputState = TypedDict("OutputState", {name: field.annotation for name, field in TurnResult.model_fields.items()},
                        total=False)


def keep(old: Optional[list], new: Optional[list]) -> list:
    """Reducer of `seen`: a node adds the tool results it read; None (RESET) clears them when a turn starts."""
    return [] if new is None else [*(old or []), *new]


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
    other_language: bool                    # G-IN-03: a clear non-ES/PT sentence, answered by rule in route
    cross_customer: bool
    dispute_detected: bool
    active_case: Optional[bool]
    route: Optional[dict[str, Any]]         # rules 1–4 result; None = a dispute, go on
    branch: str
    body: list[str]
    row: Optional[str]                      # §4.5 row of this turn's chips
    language_last: Optional[str]            # the last turn's language (D-087), kept when a request sends language null
    session_language: Optional[str]         # the session language the last turn saw (D-087: a toggle wins over language_last)
    answer: Optional[dict[str, Any]]        # this turn's answer to a confirm question or an option card (task 04b)
    candidates: list[dict[str, Any]]        # search_transaction's last candidates
    selected_transaction: Optional[dict[str, Any]]   # the one candidate, with product_type and last4 of its card
    customer_confirmed: Optional[bool]      # about selected_transaction; None whenever it changes
    unnamed: bool                           # the one candidate came from a search no slot narrowed (D-067)
    listed: bool                            # this turn's search had no amount, date or merchant: the latest charges
    dispute_intent: Optional[str]           # the last dispute intent read: what a confirm or option answer goes on with
    score: Optional[dict[str, Any]]         # get_fraud_score of the selected transaction
    display: Optional[dict[str, Any]]       # convert_amount of it; None without a verified rate (AC-25)
    existing_case: Optional[dict[str, Any]]  # an active case on the selected transaction, read with get_case (AC-23)
    clarification_turns: int                # clarification questions already sent (spec 02 rule 5b)
    decision_record: Optional[dict[str, Any]]   # D-046: {node, input, decision} for the auditor's A1 (spec 18)
    next_node: str                          # where decide sends the turn
    read_failed: Optional[str]              # the read retrieve or status could not do this turn (its tool), or None
    path: list[str]                         # nodes run after route, for the trace
    writes: dict[str, Any]                  # act's accepted write results by tool, and `errors` codes (task 04c)
    unconfirmed: list[str]                  # tools whose action ended not_confirmed this turn, for the trace
    readings: dict[str, Any]                # verify's post-condition reads by write tool (task 04d)
    seen: Annotated[list, keep]             # the other tool results of the turn the reply states, for grounding
    llm_spent_usd: float                    # the conversation's LLM spend, for the G-OPS-01 cap (task 04f)
    llm_notes: dict[str, str]               # LLM step → "S1: ok" or "S1 -> S0: <reason>", for the trace
    llm_alerts: list[str]                   # guardrails the LLM step triggered (G-OPS-01)

State = TypedDict("State", {**InputState.__annotations__, **OutputState.__annotations__, **Internal.__annotations__},
                  total=False)
# Per-turn fields, cleared when a turn starts so nothing from the previous turn leaks into this one.
RESET = {"decision": None, "zone": None, "case_id": None, "actions": [], "denials": [], "guardrails_triggered": [],
         "body": [], "row": None, "route": None, "active_case": None, "greet_pending": False, "plan": [], "options": [],
         "answer": None, "decision_record": None, "path": [], "read_failed": None, "writes": {},
         "unconfirmed": [], "readings": {}, "seen": None, "usage": [], "llm_notes": {}, "llm_alerts": [],
         "listed": False}
WRITING = {"open_case": "opening_case", "block_card": "blocking_card"}   # act's progress key per write (AC-17)


def progress(state: State, key: str) -> None:
    """AC-17: the step's customer label (messages.yaml progress.<key>, in the thread's language) as a LangGraph custom
    stream event, which the api forwards as `event: progress`. It says what is being attempted, never a result
    (constitution #4); outside a run (a node called directly) it does nothing."""
    try:
        write = get_stream_writer()
    except RuntimeError:
        return
    language = (state.get("language") or state.get("language_last") or (state.get("profile") or {}).get("language")
                or "es")
    write(ProgressItem(step=key, label=msg.text(f"progress.{key}", language), state="in_progress",
                       at=now()).model_dump(mode="json"))


def tool_event(state: State, step: str, status: str, summary: Optional[str] = None,
               cards: Optional[list[dict[str, Any]]] = None) -> None:
    """Spec 04 AC-38 (spec 01 §6.4.1, ADR 0030): one `tool` event of the turn's `step` on the custom stream, `running`
    when the call starts, then one `done` or `failed` with the same id. Title and summary are `messages.yaml tool.*`
    text; `cards` are built by the caller from tool results only. In every writer mode; nothing outside a run."""
    try:
        write = get_stream_writer()
    except RuntimeError:
        return
    language = (state.get("language") or state.get("language_last") or (state.get("profile") or {}).get("language")
                or "es")
    event = ToolEvent(id=f"{state.get('trace_id') or 'run'}:{step}", step=step, status=status,
                      title=msg.text(f"tool.{step}.title", language), at=now(), cards=cards or [],
                      summary=msg.text(f"tool.{step}.{summary}", language) if summary else None)
    write(event.model_dump(mode="json"))


def charge_card(trx: dict[str, Any]) -> dict[str, Any]:
    """A `charge` card from search_transaction's row (and get_product_status's last4 when read)."""
    return {"type": "charge", "transaction_id": trx["transaction_id"], "date": str(trx["transaction_date"]),
            "amount": trx["amount"], "currency": trx["currency"], "merchant": trx.get("merchant"),
            "last4": trx.get("last4"), "synthetic": bool(trx.get("synthetic"))}


def case_cards(case: dict[str, Any], keys: tuple[str, ...] = ("ruling_deadline", "credit_deadline")) -> list[dict]:
    """The `case` card and one `deadline` card per stored deadline, from a get_case reading only."""
    label = case.get("deadline_source_label") or case.get("deadline_source")
    return [{"type": "case", "case_id": case["case_id"], "status": case.get("queue_status")},
            *({"type": "deadline", "kind": key.split("_")[0], "date": str(case[key]), "source_label": label,
               "source_url": case.get("deadline_source_url")} for key in keys if case.get(key) and label)]


async def call(config: RunnableConfig, tool: str, **args: Any) -> BaseModel:
    """One MCP tool call with the session of the run config, never one from the text (constitution #3). Returns the
    tool's output model, or a ToolError for any failure (UNAVAILABLE for transport errors)."""
    settings = config["configurable"]
    try:
        transport = settings.get("mcp_transport")   # tests pass a server object; a URL string is never honoured
        if not transport or isinstance(transport, str):
            # spec 03 §6: X-Trace-Id is the turn's trace_id, which `traced` hands the node from the state (INT1)
            trace = settings.get("trace_id")
            transport = StreamableHttpTransport(os.environ["MCP_URL"], headers={
                "X-API-Key": os.environ.get("MCP_API_KEY", ""), **({"X-Trace-Id": trace} if trace else {})})
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
    texts = [m.get("content", "") for m in state.get("messages") or [] if m.get("role", "user") == "user"]
    said = texts[-1].strip() if texts and not state.get("action") else ""
    progress({**state, "language": turn_language(state, said)}, "reading_account")     # D-087: the turn's language
    profile = await call(config, "get_customer_profile")
    if isinstance(profile, ToolError):
        return {}                           # no greeting without a name read from the tool; retried next turn
    return {"profile": profile.model_dump(mode="json"), "greet_pending": True}


async def understand(state: State, config: RunnableConfig) -> dict[str, Any]:
    """Language, injection flag, intent and slots with the B0 rules arm; dates against the session's today. Below τ,
    S1/S2 ask the LLM for intent and slots, only in a verified session and never for a flagged or cross-customer
    message; if it fails, B0 stands. D-071: right after the ask_intent or the confirm question, a reply that names no
    charge (no amount, date or merchant) is about the charge shown, so `retrieve` keeps it (spec 04 AC-36)."""
    out = await understood(state, config)
    intent = out.get("intent")
    return {**out, "dispute_intent": intent if intent in DISPUTES else state.get("dispute_intent")}


async def understood(state: State, config: RunnableConfig) -> dict[str, Any]:
    """The turn's understanding (see `understand`)."""
    profile = state.get("profile") or {}
    day = today(state["mode"], profile.get("country"))
    texts = [m.get("content", "") for m in state.get("messages") or [] if m.get("role", "user") == "user"]
    text, action = (texts[-1].strip() if texts else ""), state.get("action") or {}
    language = turn_language(state, text if not action else "")
    # before any LLM call: the first label comes within 1 s (§5), in the turn's language (D-087)
    progress({**state, "language": language}, "reading_message")
    hint = language
    base = {"today": day.isoformat(), "language": language, "session_language": session_language(state), "slots": {},
            "injection_flagged": False,
            "cross_customer": False, "other_language": False, "intent": None, "intent_confidence": None, "dispute_detected": False}
    # the dispute being clarified: the last turn's, else the last dispute read (D-071), else an unrecognized charge
    pending = (state.get("intent") if state.get("intent") in DISPUTES
               else state.get("dispute_intent") or "unrecognized_charge")
    if action:                              # a pressed action chip or button skips the classifier (AC-32)
        kind, value = action.get("type"), action.get("value")
        answer = {"confirm": value == "yes"} if kind == "confirm" else {"option": value} if kind == "choose_option" else None
        call = call_confirmed(state, answer)
        intent = "human_request" if call else ACTION_INTENT.get(kind, pending)
        return {**base, "intent": intent, "intent_confidence": 1.0, "dispute_detected": intent in DISPUTES or call,
                "answer": answer}
    if not text:
        return base
    offered = {s.get("id") for s in state.get("suggestions") or []}
    # D-071: the question the last reply asked about the charge it showed (AC-36)
    keep = "confirm" if "confirm_yes" in offered else "intent" if offered & msg.INTENT_CHIPS else None
    # D-067: the card's rows take only an exact closed-list reply; the medium-zone confirm row keeps CONFIRM_WORDS
    said = (CHARGE_WORDS.get(" ".join(re.findall(r"\w+", fold(text)))) if "confirm_charge" in offered
            else CONFIRM_WORDS.get(fold(text).strip(" .!¡?¿")) if "confirm_yes" in offered else None)
    if said is not None:
        answer = {"confirm": said}
        return {**base, "intent": "human_request" if call_confirmed(state, answer) else pending,
                "intent_confidence": 1.0, "dispute_detected": True, "answer": answer}
    if label := recent_label(text):         # D-085 (AC-42): list the latest charges, by rule, no classifier
        return {**base, "language": hint or label, "intent": pending, "intent_confidence": 1.0,
                "dispute_detected": True, "answer": {"recent": True}}
    reading = NLU.parse(text, hint, today=day)
    found = {"language": reading.language, "slots": reading.slots.model_dump(),
             "injection_flagged": reading.injection_flagged, "other_language": reading.other_language,
             "cross_customer": bool(CROSS_CUSTOMER.search(fold(text))) and not OWN_OR_DISPUTE.search(fold(text))}
    if found["other_language"]:             # G-IN-03 stays as it was: the session language, plus English once
        found["language"] = base["language"] = session_language(state)
    chip =msg.offered_text_chip(text, state.get("suggestions") or [])
    if chip:                                # typed label = pressed text chip: routed by the pending question (AC-33)
        intent = msg.TEXT_CHIP_INTENT[chip] or pending
        return {**base, **found, "intent": intent, "intent_confidence": 1.0, "dispute_detected": intent in DISPUTES,
                **kept(keep, found["slots"])}
    heard, extra = (None, {})
    if reading.confidence < TAU and state["session_state"] == "verified" and not (
            found["other_language"] or found["injection_flagged"] or found["cross_customer"]):
        heard, extra = await arms.understand(state, config, text, day.isoformat(), TAU)
    if heard:                               # D-020: dispute words the rules saw still count
        heard["dispute_detected"] = heard["dispute_detected"] or reading.dispute_detected
        if heard["intent"] == "human_request" and reading.intent != "human_request":
            heard["intent"] = reading.intent    # D-065 [assumption]: no call on an LLM-only reading; the turn asks

    out = {**base, **found, "intent": reading.intent, "intent_confidence": reading.confidence,
           "dispute_detected": reading.dispute_detected, **(heard or {}), **extra}
    return {**out, **kept(keep, out["slots"])}


def session_language(state: State) -> str:
    """The session's language: the request's (the api sends the session's, spec 01 §6.4), else the last turn's, else
    the profile's. It stays the default and the language of notifications; the graph never rewrites it (D-087)."""
    return (state.get("language") or state.get("language_last") or (state.get("profile") or {}).get("language")
            or "es")


def turn_language(state: State, text: str) -> str:
    """D-087 (lead, 2026-10-06; spec 04 AC-43): the turn follows the language of the customer's last message when its
    words tell ES from PT (`detect_language` with no hint, at least 2 words of one language and more than of the
    other [assumption], so "ok" or a lone shared word never switches); a message they do not tell apart, or a chip
    press with no text, keeps the last turn's language [assumption], else the session's. Another language is G-IN-03's (the session
    language, set by the caller). A session language changed since the last turn (the web's toggle) wins over it."""
    session = session_language(state)
    last = state.get("language_last") if state.get("session_language") in (None, session) else None
    return detect_language(text, None, default=last or session, min_words=2) if text else last or session


def recent_label(text: str) -> Optional[str]:
    """D-085 (AC-42): the language of the RECENT_CHIPS label that `text` equals (case, accents, spacing and end
    punctuation ignored, as AC-33), or None."""
    def same(said: str) -> str:
        return " ".join(fold(said).strip(" ¿?¡!.").split())
    return next((language for chip in RECENT_CHIPS for language in ("es", "pt")
                 if same(text) == same(msg.text(f"suggest.{chip}", language))), None)


def kept(keep: Optional[str], slots: dict[str, Any]) -> dict[str, Any]:
    """D-071 (AC-36): the answer that keeps the charge shown, when the last reply asked about it (`keep`) and this
    message names no charge of its own (a currency alone names none, D-067); else nothing."""
    named = any((slots or {}).get(key) for key in ("amount", "date", "merchant"))
    return {"answer": {"keep": keep}} if keep and not named else {}


def call_confirmed(state: State, answer: Optional[dict[str, Any]]) -> bool:
    """D-067: the last turn was a call request with an unnamed charge (a general call and its card) and this answer
    confirms that card, so the turn goes on as that call request with the charge (D-029: the case opens, no block)."""
    trx = state.get("selected_transaction") or {}
    return bool(state.get("intent") == "human_request" and state.get("unnamed") and trx) and answer in (
        {"confirm": True}, {"option": trx.get("transaction_id")})


def unconfirmed(state: State) -> bool:
    """D-067: the one candidate is a charge the customer did not name and has not confirmed yet."""
    return bool(state.get("unnamed") and state.get("selected_transaction") and state.get("customer_confirmed") is not True)


def names(slots: dict[str, Any], trx: dict[str, Any]) -> bool:
    """D-067: whether the turn's slots name this candidate (see CURRENCY_CODES): an amount or a date, or a merchant
    slot whose every content word is a word of the candidate's non-null merchant (accents and case ignored)."""
    if slots.get("amount") or slots.get("date"):
        return True
    said = {word for word in re.findall(r"\w+", fold(slots.get("merchant") or "")) if len(word) > 2}
    said -= CURRENCY_CODES | STOP_WORDS | GENERIC_WORDS
    return bool(said) and said <= set(re.findall(r"\w+", fold(trx.get("merchant") or "")))


async def route(state: State, config: RunnableConfig) -> dict[str, Any]:
    """Spec 02 rules 1–4 through `engine.screen()`; the engine, not the graph, picks the branch."""
    verified = state["session_state"] == "verified"
    if state.get("intent") is None and verified:
        return {"branch": "respond"}        # nothing to understand: the greeting, or a prompt to tell us more
    if state.get("other_language") and verified and not (state["injection_flagged"] or state["cross_customer"]):
        # G-IN-03 [assumption]: by rule, no LLM, no case; the session language plus English once, the usual chips
        return {"branch": "respond", "body": [msg.text("refuse.other_language", state["language"])],
                "row": "other_language", "guardrails_triggered": ["G-IN-03"]}
    active = None
    if state.get("intent") == "status_inquiry" and state.get("dispute_detected") and verified:
        cases = await call(config, "list_my_cases")   # rule 3b needs to know whether a case is active
        if not isinstance(cases, ToolError):
            active = any(c.queue_status not in ("resolved", "closed") for c in cases.cases)
    understood = {**state, "active_case": active, "selected_transaction": None, "candidates": [], "score": None,
                  "customer_confirmed": None}          # this turn's reading only: no transaction facts read yet
    decision = ENGINE.screen(inputs := decision_input(understood))
    if decision is None:
        return {"branch": "retrieve", "active_case": active}
    return {"branch": BRANCH[decision.decision], "active_case": active, **outcome("route", inputs, decision)}


def decision_input(state: State) -> DecisionInput:
    """The understood turn plus tool facts only: candidates, score, amount and card come from MCP results, the country
    from get_customer_profile, never from the text (constitution #3, spec 02 FR-03)."""
    trx, score = state.get("selected_transaction") or {}, state.get("score") or {}
    # [assumption] supervised_mode is not passed to the graph yet; policies.yaml approval.supervised_mode still applies
    return DecisionInput(
        session_state=state["session_state"], intent=state.get("intent") or "out_of_scope",
        intent_confidence=float(state.get("intent_confidence") or 0), dispute_detected=state["dispute_detected"],
        injection_flagged=state["injection_flagged"], cross_customer=state["cross_customer"], supervised_mode=False,
        active_case=state.get("active_case"), clarification_turns=state.get("clarification_turns") or 0,
        candidates=1 if trx else len(state.get("candidates") or []), score=score.get("score"),
        score_source=score.get("source"), amount=trx.get("amount"), currency=trx.get("currency"),
        country=(state.get("profile") or {}).get("country"), product_type=trx.get("product_type"),
        customer_confirmed=state.get("customer_confirmed"))


def outcome(node: str, inputs: DecisionInput, decision: PolicyDecision) -> dict[str, Any]:
    """The policy result on the turn, with the pair the auditor's A1 re-runs (D-046, spec 18 §6)."""
    return {"route": decision.model_dump(mode="json"), "decision": decision.decision, "zone": decision.zone,
            "guardrails_triggered": decision.guardrail_ids,
            "decision_record": {"node": node, "input": inputs.model_dump(mode="json"),
                                "decision": decision.model_dump(mode="json")}}


def refuse(state: State) -> dict[str, Any]:
    """DENY or re-authenticate with no data and a way forward; the denial is reported for policy_denials (AC-03)."""
    decision, rules = state["route"]["decision"], state["route"]["rule_ids"]
    key = "refuse.deny" if decision == "deny" else (
        "connect.general_contact" if state.get("intent") == "human_request" else "refuse.reauthenticate")  # AC-28
    # an injection that also asks for another customer's data is logged under both rules (EV-0116)
    denied = rules if rules[0] == "POL-INJECTION" else rules[-1:]
    denials = [{"policy_id": rule, "guardrail_id": ENGINE.policies.rules[rule].guardrail, "detail": decision}
               for rule in denied]
    return {"body": [msg.text(key, state["language"])], "row": decision, "denials": denials,
            "path": state["path"] + ["refuse"]}


async def connect(state: State, config: RunnableConfig) -> dict[str, Any]:
    """A call request where spec 02 `request_call` says (AC-28, never refused), on the case `call_case` picks. A call on
    a case is read back with get_case: "verified" only with the read's V- id, else it stays "requested" (AC-18); a
    general call stays "requested" (D-026). Actions and lines already set this turn stay."""
    language, before, done, path = state["language"], state.get("body") or [], state.get("actions") or [], state["path"]
    progress(state, "requesting_call")
    case = await call_case(state, config)
    key = f"{state['session_id']}:{case or 'none'}:request_call:{state['trace_id']}"
    tool_event(state, "request_call", "running")
    out = await call(config, "request_call", idempotency_key=key, **({"case_id": case} if case else {}))
    if isinstance(out, ToolError):          # never refuse (AC-28), never claim it (AC-18): say it failed, offer a retry
        tool_event(state, "request_call", "failed", "failed")
        # [assumption] the graph's own id for an attempt the tool never accepted; no tool returned one
        return {"body": [*before, msg.text("connect.request_failed", language)], "row": "connect_failed",
                "actions": [*done, {"tool": "request_call", "action_id": new_id("action"), "state": "not_confirmed"}],
                "path": path + ["connect"]}
    record = {"tool": "request_call", "action_id": out.action_id, "state": "requested"}
    seen = [out.model_dump(mode="json")]
    cards: list[dict[str, Any]] = []
    if out.case_id:                         # [assumption] one read, no retries: unread, it stays "requested"
        read = await call(config, "get_case", case_id=out.case_id, action_id=out.action_id)
        if not isinstance(read, ToolError) and read.verification_id and read.action_id == out.action_id:
            record |= {"state": "verified", "verification_id": read.verification_id,
                       "read_at": read.read_at.isoformat()}
            seen.append(read.model_dump(mode="json"))
            cards = case_cards(read.model_dump(mode="json"), ())
    tool_event(state, "request_call", "done", record["state"],
               [{"type": "action", "tool": "request_call", "state": record["state"],
                 "verification_id": record.get("verification_id")}, *cards])
    when, suffix = out.expected_contact_by, "_case" if out.case_id else ""
    body = (msg.text(f"connect.requested{suffix}", language, case_id=out.case_id, expected_contact_by=when.isoformat())
            if when else msg.text(f"connect.requested{suffix}_no_window", language, case_id=out.case_id))
    turn = {"body": [*before, body], "row": "connect_person_case" if out.case_id else "connect_person",
            "actions": [*done, record], "path": path + ["connect"], **({"case_id": out.case_id} if out.case_id else {}),
            "seen": seen}
    if state.get("intent") == "human_request" and unconfirmed(state):   # D-067: the charge's card, still to confirm
        trx = state["selected_transaction"]
        turn |= {"body": [*turn["body"], msg.text("clarify.confirm_call", language)], "row": "confirm_call",
                 "options": [{"id": trx["transaction_id"], "label": msg.option_label(trx)}]}
    return turn


async def call_case(state: State, config: RunnableConfig) -> Optional[str]:
    """The case for the call (spec 04 `connect`): `general` → none (rule 5b); `opened_case` → the case set this turn
    (opened and verified, or the active case on the charge, AC-23), else none; `active_or_general` → the customer's
    active case, read now with list_my_cases, else none (a general request)."""
    where, opened = (state.get("route") or {}).get("request_call") or "active_or_general", state.get("case_id")
    if where == "general" or unconfirmed(state):    # D-067: an unnamed charge's call is never on another case
        return None
    if where == "opened_case":
        # [assumption] no verified case for this charge → a general request, never another charge's active case
        verified = all(a["state"] == "verified" for a in state.get("actions") or [] if a["tool"] == "open_case")
        return opened if opened and verified else None
    cases = await call(config, "list_my_cases")
    if isinstance(cases, ToolError):        # [assumption] cases unread: a general request, still registered (AC-28)
        return None
    active = [c.case_id for c in cases.cases if c.queue_status not in CLOSED]
    # [assumption] the case the web's case page names (configurable.case_id) when it is active, else the first active
    return state["case_id_in"] if state.get("case_id_in") in active else next(iter(active), None)


async def retrieve(state: State, config: RunnableConfig) -> dict[str, Any]:
    """Finds the customer's transaction with search_transaction; for exactly one, reads its card, score, display
    amount and any active case on it. A confirm answer keeps what the customer was shown; an option card picks one of
    the candidates shown, never an id the tool did not return. A failed search or card read is not a missing charge:
    the turn says the read failed and goes to respond, with no decision and no clarification turn counted."""
    answer, path, slots = state.get("answer") or {}, state["path"] + ["retrieve"], None
    if "confirm" in answer and state.get("selected_transaction"):
        return {"path": path, "customer_confirmed": answer["confirm"]}
    if answer.get("keep") and state.get("selected_transaction"):     # D-071: about the charge shown (AC-36)
        return {"path": path}
    if "option" in answer:                  # "none", or an id never shown: identify it again
        candidates = [c for c in state.get("candidates") or [] if c["transaction_id"] == answer["option"]]
    elif not state["dispute_detected"] and not any((state.get("slots") or {}).values()):
        candidates = []                     # [assumption] nothing reported ("hola" below τ): ask, search nothing
    else:                                   # D-085 (AC-42): a request for the latest charges searches with no slot
        slots = {} if answer.get("recent") else state.get("slots") or {}
        query = {"amount": float(slots["amount"]) if slots.get("amount") else None, "currency": slots.get("currency"),
                 "approx_date": slots.get("date"), "merchant": slots.get("merchant")}
        progress(state, "searching")
        tool_event(state, "search_transaction", "running")
        found = await call(config, "search_transaction", **{k: v for k, v in query.items() if v is not None})
        if isinstance(found, ToolError):
            tool_event(state, "search_transaction", "failed", "failed")
            return unread(path, "search_transaction", state["language"])
        candidates = [c.model_dump(mode="json") for c in found.candidates]
        if len(candidates) != 1:            # one candidate: done once its card is read, with its last4 (AC-38)
            tool_event(state, "search_transaction", "done", "found_many" if candidates else "found_none",
                       [charge_card(c) for c in candidates])
    fresh = {"path": path, "candidates": candidates, "selected_transaction": None, "customer_confirmed": None,
             "score": None, "display": None, "existing_case": None,
             "unnamed": slots is not None and len(candidates) == 1 and not names(slots, candidates[0]),
             "listed": slots is not None and not any(slots.get(key) for key in ("amount", "date", "merchant"))}
    if len(candidates) != 1:
        return fresh
    trx = candidates[0]
    card, score, fx, cases = await asyncio.gather(
        call(config, "get_product_status", product_id=trx["product_id"]),
        call(config, "get_fraud_score", transaction_id=trx["transaction_id"]),
        call(config, "convert_amount", amount=trx["amount"], currency=trx["currency"]), call(config, "list_my_cases"))
    searched = slots is not None
    if isinstance(card, ToolError):         # [assumption] no card type, no decision: product_type is never guessed
        if searched:
            tool_event(state, "search_transaction", "done", "found_one", [charge_card(trx)])
        return unread(path, "get_product_status", state["language"])
    if searched:
        tool_event(state, "search_transaction", "done", "found_one", [charge_card({**trx, "last4": card.last4})])
    return {**fresh, "selected_transaction": {**trx, "product_type": card.type, "last4": card.last4},
            # a failed score read is a null score: zone human (POL-SCORE-NULL)
            "score": None if isinstance(score, ToolError) else score.model_dump(mode="json"),
            "display": None if isinstance(fx, ToolError) or not fx.converted else fx.converted.model_dump(mode="json"),
            "existing_case": await active_case_on(config, cases, trx["transaction_id"])}


def unread(path: list[str], tool: str, language: str) -> dict[str, Any]:
    """The read could not be done (no data, nothing claimed): say so and offer a retry and a person. [assumption] No
    tool_failure handoff: spec 02 has no input for it (follow-up for the lead)."""
    return {"path": path, "read_failed": tool, "body": [msg.text("clarify.read_failed", language)], "row": "read_failed"}


async def active_case_on(config: RunnableConfig, cases: BaseModel, transaction_id: str) -> Optional[dict[str, Any]]:
    """The active case on this transaction, read with get_case (AC-23). A failed read finds none: open_case still
    answers the existing case as duplicate_of and writes nothing (spec 03 AC-15)."""
    if isinstance(cases, ToolError):
        return None
    for item in cases.cases:
        if item.queue_status in ("resolved", "closed"):
            continue
        case = await call(config, "get_case", case_id=item.case_id)
        if not isinstance(case, ToolError) and case.transaction.transaction_id == transaction_id:
            return case.model_dump(mode="json", include={"case_id", "credit_deadline", "ruling_deadline",
                                                          "deadline_source", "deadline_source_label"})
    return None


def decide(state: State) -> dict[str, Any]:
    """spec 02 `engine.decide()` on the turn's tool facts; the graph runs whatever it returns, never a rule of its own.
    [assumption] D-067: a charge the customer did not name (one candidate of a search no slot narrowed) is not yet
    identified, so the engine sees no transaction until the customer confirms it: it asks (clarify shows the card)."""
    progress(state, "deciding")
    tool_event(state, "evaluate_policy", "running")
    unnamed = unconfirmed(state)
    facts = {**state, "selected_transaction": None, "candidates": [], "score": None} if unnamed else state
    decision = ENGINE.decide(inputs := decision_input(facts))
    tool_event(state, "evaluate_policy", "done", "done", [verdict_card(decision, state["language"])])
    record = outcome("decide", inputs, decision)
    if unnamed:                             # the trace says why the record shows no candidate (D-046)
        record["decision_record"]["note"] = "D-067: one candidate the customer did not name, held until confirmed"
    opens = "open_case" in decision.allowed_actions or decision.decision == "confirm"
    nxt = {"ask": "clarify", "deny": "refuse"}.get(decision.decision) or (
        ("duplicate" if state.get("existing_case") else "plan") if opens else call_or_respond(state, decision))
    exhausted = decision.handoff_reason == "clarification_exhausted"                      # rule 5b (AC-13)
    return {**record, "next_node": nxt, "path": state["path"] + ["decide"],
            "clarification_turns": (state.get("clarification_turns") or 0) if decision.decision == "ask" else 0,
            "body": [msg.text("clarify.exhausted", state["language"])] if exhausted else []}


def verdict_card(decision: PolicyDecision, language: str) -> dict[str, Any]:
    """The `verdict` card: the decision in customer words (messages.yaml verdict.*) and the labels of the actions it
    allows; no score, zone or rule id (spec 01 §6.4.1)."""
    labels = msg.messages()["status"]["action_label"]
    return {"type": "verdict", "headline": msg.text(f"verdict.{decision.decision}", language),
            "actions": [labels[a][language] for a in decision.allowed_actions if a in labels]}


def plan(state: State) -> dict[str, Any]:
    """Numbered steps before acting (AC-16), from the decision's allowed actions and handoff; in the confirm state it
    asks before anything is done (AC-11). The amount is the tool's exact amount, plus convert_amount's (AC-25)."""
    trx, policy, language = state["selected_transaction"], state["route"], state["language"]
    confirm = policy["decision"] == "confirm"
    keys = ["step_open_case" if trx["merchant"] else "step_open_case_no_merchant"]
    keys += ["step_block_card", "step_verify"] if "block_card" in policy["allowed_actions"] else []
    keys += ["step_deadline", *(["step_person"] if policy["handoff_reason"] or confirm else [])]
    facts = {"amount": msg.amount_text(trx["amount"]), "currency": trx["currency"], "merchant": trx["merchant"],
             "last4": trx["last4"]}
    steps = [msg.text(f"plan.{key}", language, step_n=n, **facts) for n, key in enumerate(keys, 1)]
    fx = state.get("display")
    shown = [msg.text("receipt.transaction_display", language, display_amount=fx["amount"],
                      display_currency=fx["currency"], rate=fx["rate"], rate_source=fx["rate_source"],
                      as_of=fx["as_of"])] if fx and fx["currency"] != trx["currency"] else []
    ask = [msg.text("plan.confirm_ask", language)] if confirm else []
    return {"plan": steps, "body": [msg.text("plan.intro", language), *steps, *shown, *ask],
            "row": "confirm" if confirm else None, "path": state["path"] + ["plan"]}


async def attempt(config: RunnableConfig, tool: str, **args: Any) -> tuple[BaseModel, bool]:
    """One tool call retried on UNAVAILABLE (a timeout or a transport error) up to reliability.tool_retries times with
    the same arguments, so a write's retry carries the same idempotency key and the server writes once (spec 01 §6.3).
    A DENY, NOT_FOUND or SESSION_EXPIRED answer is final and never retried. Also says whether any attempt went
    unanswered, since the server may then have written."""
    unanswered = False
    for _ in range(RETRIES + 1):
        out = await call(config, tool, **args)
        if not (isinstance(out, ToolError) and out.code == "UNAVAILABLE"):
            break
        unanswered = True
    return out, unanswered


async def act(state: State, config: RunnableConfig) -> dict[str, Any]:
    """Runs only what decide() allowed, in spec 03's order (Q3): open_case first, then block_card when allowed_actions
    lists it (D-029: the engine, never the graph, decides whether a call request blocks). The idempotency key is
    session:transaction:action:run. Every allowed action gets exactly one record, so verify answers every step the plan
    promised: a write the tool accepted is "requested" until verify reads it; one never answered, or not tried, gets a
    graph-minted id and "not_confirmed" (§4.1). block_card follows an open_case error only when it was UNAVAILABLE
    (the case may exist; the server re-checks it, spec 03 AC-10). Nothing is told to the customer here."""
    trx, policy, writes, actions = state["selected_transaction"], state["route"], {"errors": {}, "unanswered": []}, []
    planned = {"open_case": {"transaction_id": trx["transaction_id"], "dispute_type": dispute_type(state),
                             "zone": policy["zone"]},
               "block_card": {"product_id": trx["product_id"],
                              "reason": "high_zone_dispute" if policy["zone"] == "high" else "confirmed_dispute"}}
    for tool in [t for t in planned if t in policy["allowed_actions"]]:
        if tool == "block_card" and ((writes.get("open_case") or {}).get("duplicate_of")
                                     or writes["errors"].get("open_case") not in (None, "UNAVAILABLE")):
            # [assumption] no block on an existing case (as AC-23) nor after a final open_case error; still recorded
            actions.append({"tool": tool, "action_id": new_id("action"), "state": "not_confirmed"})
            break
        # run = the LangGraph run id (trace_id); policies.yaml's template has no run part (follow-up for the lead)
        key = f"{state['session_id']}:{trx['transaction_id']}:{tool}:{state['trace_id']}"
        progress(state, WRITING[tool])
        tool_event(state, tool, "running")  # done after verify reads it back (AC-38), failed here
        out, unanswered = await attempt(config, tool, idempotency_key=key, **planned[tool])
        writes["unanswered"] += [tool] if unanswered else []
        if isinstance(out, ToolError):
            actions.append({"tool": tool, "action_id": new_id("action"), "state": "not_confirmed"})
            writes["errors"][tool] = out.code
            # D-043: an open call request holds the block (POL-HUMAN-REQUEST): a person decides it after the call
            held = tool == "block_card" and out.code == "DENY" and out.policy_id == "POL-HUMAN-REQUEST"
            writes["held"] = writes.get("held") or held
            tool_event(state, tool, "failed", "held" if held else "failed")
            continue
        writes[tool] = out.model_dump(mode="json")
        actions.append({"tool": tool, "action_id": out.action_id, "state": "requested"})
    return {"writes": writes, "actions": actions, "path": state["path"] + ["act"]}


def dispute_type(state: State) -> str:
    """The case's dispute type. [assumption] A call request that reports a charge opens an unrecognized_charge case."""
    return state["intent"] if state.get("intent") in DISPUTES else "unrecognized_charge"


async def verify(state: State, config: RunnableConfig) -> dict[str, Any]:
    """Post-condition reads (constitution #4): each accepted write is read with its VERIFIED_WITH tool and its
    action_id, retried up to reliability.tool_retries times; "verified" only when the read returns that action with a
    V- id (and Blocked for block_card, D-025). Otherwise "not_confirmed", with its own line: the turn escalates with
    escalate_unconfirmed_action and never says the action was done (AC-04, AC-18). The case id is given out only once
    get_case verified it, so connect puts a call on it only then (§4.2)."""
    trx, language, writes, done, readings = state["selected_transaction"], state["language"], state["writes"], [], {}
    progress(state, "verifying")
    expired = "SESSION_EXPIRED" in writes["errors"].values()   # any write or read, as open_case's (task 04d)
    for action in state["actions"]:
        tool, reading, target = action["tool"], None, {}
        if action["state"] == "requested":
            target = {"case_id": writes[tool]["case_id"]} if tool == "open_case" else {"product_id": trx["product_id"]}
            for _ in range(RETRIES + 1):
                reading = await call(config, VERIFIED_WITH[tool], action_id=action["action_id"], **target)
                if holds(tool, action["action_id"], target, reading) or (
                        isinstance(reading, ToolError) and reading.code != "UNAVAILABLE"):
                    break
            expired |= isinstance(reading, ToolError) and reading.code == "SESSION_EXPIRED"
        if reading is not None and holds(tool, action["action_id"], target, reading):
            readings[tool] = reading.model_dump(mode="json")
            done.append({**action, "state": "verified", "verification_id": reading.verification_id,
                         "read_at": readings[tool]["read_at"]})
        else:
            done.append({**action, "state": "not_confirmed"})
        if action["state"] == "requested":  # the write act started: its one done, from the reading only (AC-38)
            last = done[-1]
            cards = [{"type": "action", "tool": tool, "state": last["state"],
                      "verification_id": last.get("verification_id")}]
            if tool == "open_case" and tool in readings:
                cards += case_cards(sourced(readings[tool]), ("ruling_deadline", "credit_deadline")
                                    if dispute_type(state) == "unrecognized_charge" else ("ruling_deadline",))
            tool_event(state, tool, "done", last["state"], cards)
    case, calls, held = readings.get("open_case"), state["route"]["request_call"], writes.get("held")
    # D-043: a block the open call request holds is not done, but it is no tool failure and does not escalate
    unconfirmed = [a["tool"] for a in done if a["state"] == "not_confirmed" and not (held and a["tool"] == "block_card")]
    lines = verified_lines(case, readings.get("block_card"), writes.get("open_case"), language, dispute_type(state))
    duplicate = bool(case and (writes.get("open_case") or {}).get("duplicate_of"))
    lines += [unconfirmed_line(tool, case, calls or expired, duplicate, language) for tool in unconfirmed]
    lines += [msg.text("act.block_held", language,
                       action_label=msg.text("status.action_label.block_card", language))] if held else []
    reads = {"readings": readings, "seen": list(readings.values()), "path": state["path"] + ["verify"]}
    if expired:     # sign in again (spec 02 rule 1); "nothing changed" only when nothing may have been written
        maybe = writes["unanswered"] or any(tool in writes for tool in ("open_case", "block_card"))   # accepted
        lines.append(msg.text("act.sign_in" if maybe else "refuse.reauthenticate", language))
        return {"actions": done, "unconfirmed": unconfirmed, "body": [*state["body"], *lines],
                "row": "reauthenticate_case" if case else "reauthenticate", "decision": "reauthenticate",
                "case_id": case["case_id"] if case else None, **reads}
    row = ("case_active" if duplicate else ("escalate_unconfirmed" if case else "case_unconfirmed") if unconfirmed
           else "block_held" if held else "receipt" if state["route"]["decision"] == "block_and_open_case"
           else "handoff")
    # a duplicate_of case reports as the duplicate node does (D-050); any other unconfirmed action escalates
    decision = ({"decision": "connect_person" if calls else None} if duplicate else
                {"decision": "escalate_unconfirmed_action"} if unconfirmed else {})
    return {"actions": done, "unconfirmed": unconfirmed, "body": [*state["body"], *lines], "row": row,
            "case_id": case["case_id"] if case else None, **reads, **decision}


def unconfirmed_line(tool: str, case: Optional[dict[str, Any]], quiet: bool, duplicate: bool, language: str) -> str:
    """The line of an action not confirmed. With a verified case a person reviews it (status.action_not_confirmed),
    but on a duplicate_of case, which does not escalate (D-050), the person on that case decides the block; with no
    verified case no line promises a review [assumption]: the case line asks for a call unless the turn registers one
    or asks to sign in (`quiet`)."""
    label = msg.text(f"status.action_label.{tool}", language)
    if tool == "open_case" and not quiet:
        return msg.text("act.case_not_confirmed", language)
    if duplicate:
        return msg.text("act.decided_on_case", language, action_label=label, case_id=case["case_id"])
    if case:
        return msg.action_line(tool, "not_confirmed", language)
    return msg.text("act.not_confirmed", language, action_label=label)


def holds(tool: str, action_id: str, target: dict[str, str], reading: BaseModel) -> bool:
    """The write's post-condition, from the read only: the same action with a V- id, on the same case or card."""
    if isinstance(reading, ToolError) or reading.action_id != action_id or not reading.verification_id:
        return False
    if tool == "block_card":
        return reading.product_id == target["product_id"] and reading.status == "Blocked"
    return reading.case_id == target["case_id"]


def sourced(case: dict[str, Any]) -> dict[str, Any]:
    """DLANG: a customer line names the deadline's source by the label get_case returned in the session's language,
    never a translation of the agent's (constitution #5); a case read with no label keeps its stored source."""
    return {**case, "deadline_source": case.get("deadline_source_label") or case.get("deadline_source")}


def verified_lines(case: Optional[dict[str, Any]], card: Optional[dict[str, Any]], opened: Optional[dict[str, Any]],
                   language: str, dispute: str = "unrecognized_charge") -> list[str]:
    """What verify confirmed, from the verifying reads only (ADR 0016): the case with its V- id and stored deadlines,
    and the card blocked with its V- id. Nothing for an action that is not verified. D-030 (ADR 0023 item 5): the
    credit date only for an unrecognized charge; a wrongful charge shows the ruling date."""
    lines = []
    if case:
        lines.append(msg.text("duplicate.case_exists", language, case_id=case["case_id"])
                     if (opened or {}).get("duplicate_of") else
                     msg.text("act.case_opened", language, case_id=case["case_id"],
                              verification_id=case["verification_id"], verified_at=build.stamp(case["read_at"])))
        facts = {**sourced(case), "source_url": case["deadline_source_url"], "verified_on": case["deadline_verified_on"]}
        keys = ("ruling_deadline", "credit_deadline") if dispute == "unrecognized_charge" else ("ruling_deadline",)
        lines += [msg.text(f"receipt.{key}", language, **facts) for key in keys
                  if case.get(key)] or [msg.text("receipt.deadline_unknown", language)]
    if card:
        lines.append(msg.text("receipt.card_blocked", language, last4=card["last4"],
                              verification_id=card["verification_id"], verified_at=build.stamp(card["read_at"])))
    return lines


def duplicate(state: State) -> dict[str, Any]:
    """AC-23: the charge already has an active case, so nothing is opened; the case id and its stored deadlines come
    from get_case. [assumption] No new write either (no block): the person on that case decides."""
    case, language = state["existing_case"], state["language"]
    lines = [msg.text("duplicate.case_exists", language, case_id=case["case_id"])]
    lines += [msg.text(f"status.{key}", language, **sourced(case)) for key in ("ruling_deadline", "credit_deadline")
              if case.get(key)] or [msg.text("status.deadline_unknown", language)]
    # [assumption] D-050: the turn reports decision null, since nothing the decision called for was run; a call request
    # reports connect_person, as only the call is run. The engine's decision stays in the trace (D-046).
    return {"body": lines, "row": "case_active", "case_id": case["case_id"], "path": state["path"] + ["duplicate"],
            "decision": "connect_person" if state["route"]["request_call"] else None}


def clarify(state: State) -> dict[str, Any]:
    """Rule 5: one question, nothing done. Up to max_candidate_transactions candidates become option cards; otherwise
    it asks for the details. A charge the customer did not name is one card with the confirm chips (D-067). A declined
    confirm answers plan.declined and clears the selection (D-039). D-071: one charge the customer named, asked about
    because the intent is below τ, is one card with the ask_intent chips (AC-35); an unclear reply to the confirm
    question keeps the charge and asks it again with the confirm chips (AC-36). D-085: a search with no amount, date or
    merchant that found several charges lists the latest max_candidate_transactions of them as cards (the tool ranks
    them most recent first), with the ask_recent row; a list the customer can pick from counts no clarification turn
    (AC-42)."""
    candidates, language = state.get("candidates") or [], state["language"]
    declined = state.get("customer_confirmed") is False
    if not declined and (state.get("answer") or {}).get("keep") == "confirm" and state.get("selected_transaction"):
        return {"body": [msg.text("clarify.confirm_again", language)], "row": "confirm",
                "clarification_turns": (state.get("clarification_turns") or 0) + 1,
                "path": state["path"] + ["clarify"]}
    listing = not declined and bool(state.get("listed")) and len(candidates) > 1
    if listing:                             # only the cards shown can be picked (an option never shown finds none)
        shown = candidates[:MAX_OPTIONS]
        return {"body": [msg.text("clarify.pick_one", language)], "row": "ask_recent", "candidates": shown,
                "options": [{"id": c["transaction_id"], "label": msg.option_label(c)} for c in shown],
                "clarification_turns": state.get("clarification_turns") or 0, "path": state["path"] + ["clarify"]}
    shown = [] if declined or len(candidates) > MAX_OPTIONS else candidates
    # D-067: a charge the customer did not name is shown as a card and confirmed (confirm chips) before anything is done
    unnamed = bool(shown) and unconfirmed(state)
    # D-071: one named charge and still an ask: the intent is what is unclear, so the chips state it
    intent = len(shown) == 1 and not unnamed and bool(state.get("selected_transaction"))
    key = ("plan.declined" if declined else "clarify.confirm_one" if unnamed else "clarify.ask_intent" if intent
           else "clarify.pick_one" if shown else "clarify.ask_what")
    row = ("confirm_charge" if unnamed else "ask_intent" if intent else "ask_options" if shown
           else "ask_details")
    return {"body": [msg.text(key, language)], "row": row,
            "options": [{"id": c["transaction_id"], "label": msg.option_label(c)} for c in shown],
            "clarification_turns": (state.get("clarification_turns") or 0) + 1, "path": state["path"] + ["clarify"],
            **({"selected_transaction": None, "customer_confirmed": None} if declined else {})}


def call_or_respond(state: State, decision: Optional[PolicyDecision] = None) -> str:
    """connect only when the decision sets request_call (rule 3a, rule 5b, AC-28), else respond. After plan, act →
    verify run before it."""
    wanted = decision.request_call if decision else (state.get("route") or {}).get("request_call")
    return "connect" if wanted else "respond"


# [assumption] a status question that names a card and no case reads the cards; any other reads the cases.
CARD_WORDS = re.compile(r"\b(?:tarjetas?|cartao|cartoes)\b")
CASE_WORDS = re.compile(r"\b(?:casos?|reclamos?|reclamac\w*|disputas?|contestac\w*)\b")


async def status(state: State, config: RunnableConfig) -> dict[str, Any]:
    """answer_status (spec 02 rule 3b): reads the system again in this turn, never from memory or the thread (AC-19),
    and answers with tool facts only and the time of the reading (AC-06). A failed read says so and states no status."""
    progress(state, "checking_status")
    texts = [fold(m.get("content", "")) for m in state.get("messages") or [] if m.get("role", "user") == "user"]
    said = texts[-1] if texts else ""
    # a question that names both reads both, cards first (task 04d); the last read sets the row and the case
    reads = [card_status] * bool(CARD_WORDS.search(said)) + [case_status] * (
        bool(CASE_WORDS.search(said)) or not CARD_WORDS.search(said))
    parts = [await read(state, config) for read in reads]
    if len(parts) == 2 and sum(bool(part.get("read_failed")) for part in parts) == 1:   # name the read that failed
        parts = [{"body": [msg.text("status.read_failed_" + ("cards" if part["read_failed"] == "list_my_cards"
                                                            else "case"), state["language"])]}
                 if part.get("read_failed") else part for part in parts]
    merged = {key: value for part in parts for key, value in part.items()}
    return {**merged, "body": [line for part in parts for line in part["body"]],
            "seen": [fact for part in parts for fact in part.get("seen", [])], "path": state["path"] + ["status"]}


async def card_status(state: State, config: RunnableConfig) -> dict[str, Any]:
    """Each card's status from list_my_cards, read now (at most 3 lines, spec 04 §5)."""
    language, cards = state["language"], await call(config, "list_my_cards")
    if isinstance(cards, ToolError):
        return status_unread("list_my_cards", language)
    lines = [msg.text("status.card_read", language, last4=card.last4, read_at=stamp(card.read_at),
                      card_label=msg.text(f"status.card_label.{card.status.lower()}", language))
             for card in cards.cards[:3]]
    return {"body": lines or [msg.text("status.no_cards", language, read_at=stamp(cards.read_at))], "row": "card_status",
            "seen": [cards.model_dump(mode="json")]}


async def case_status(state: State, config: RunnableConfig) -> dict[str, Any]:
    """One case read now with get_case: status label, stored deadlines and the next step (AC-06). The case is the one
    the web's case page names (configurable.case_id), else the first active, else the latest [assumption]."""
    language, cases = state["language"], await call(config, "list_my_cases")
    if isinstance(cases, ToolError):
        return status_unread("list_my_cases", language)
    seen = [cases.model_dump(mode="json")]
    if not cases.cases:
        return {"body": [msg.text("status.no_cases", language, read_at=stamp(cases.read_at))], "row": "status_none",
                "seen": seen}
    ids = [c.case_id for c in cases.cases]
    target = state["case_id_in"] if state.get("case_id_in") in ids else next(
        (c.case_id for c in cases.cases if c.queue_status not in CLOSED), ids[0])
    tool_event(state, "get_case", "running")
    case = await call(config, "get_case", case_id=target)
    if isinstance(case, ToolError):
        tool_event(state, "get_case", "failed", "failed")
        return status_unread("get_case", language)
    facts, active = sourced(case.model_dump(mode="json")), case.queue_status not in CLOSED
    tool_event(state, "get_case", "done", "done", case_cards(facts))
    lines = [msg.text("status.case_read", language, case_id=case.case_id, read_at=stamp(case.read_at),
                      status_label=status_label(case.queue_status, language) or case.status_label)]
    lines += [msg.text(f"status.{key}", language, **facts) for key in ("ruling_deadline", "credit_deadline")
              if facts.get(key)] or ([msg.text("status.deadline_unknown", language)] if active else [])
    lines.append(msg.text("receipt.what_a_person_does" if active else "status.case_done", language))
    # F-010 [assumption]: a status question with dispute words (D-020) also offers to report another charge
    row = "case_active" if active and not state.get("dispute_detected") else "case_done"
    return {"body": lines, "row": row, "case_id": case.case_id, "seen": [*seen, facts]}


def status_label(queue_status: str, language: str) -> Optional[str]:
    """The localized label of a queue state (messages.yaml status.label and its `from` list), or None."""
    return next((leaf[language] for leaf in msg.messages()["status"]["label"].values()
                 if queue_status in leaf["from"]), None)


def stamp(read_at: Any) -> str:
    """The time of a reading as shown (AC-19): the tool's read_at in UTC, to the minute [assumption]."""
    return read_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def status_unread(tool: str, language: str) -> dict[str, Any]:
    """The read failed: say it could not verify, state no status, offer a retry and a person (AC-19)."""
    return {"body": [msg.text("status.read_failed", language)], "row": "status_failed", "read_failed": tool}


async def respond(state: State, config: RunnableConfig) -> dict[str, Any]:
    """The TurnResult from templates and §4.5 chips, with the run's usage and denials (AC-14); clears the turn's input
    so the next turn starts clean. With `configurable.writer = llm` (ADR 0030, spec 04 AC-37, AC-39) the §4.6 writer
    words the gated template lines and picks the chips, streamed as `text` chunks; with `template` (the default) the
    reply, chips and stream are what they were before it (AC-40)."""
    progress(state, "writing")
    language, profile, lines = state["language"], state.get("profile") or {}, []
    if state.get("greet_pending"):          # AC-15: name from the tool, three capabilities, a person reviews
        lines = [msg.text("greet.hello", language, first_name=profile["first_name"])] + [
            msg.text(f"greet.{key}", language) for key in ("capability_1", "capability_2", "capability_3",
                                                            "human_review")]
    row = state.get("row") or ("greet" if lines else "ask_details")
    body = state.get("body") or ([] if lines else [msg.text("clarify.ask_what", language)])
    nodes = ["identity", "greet", "understand", "route", *(state.get("path") or []), "respond"]
    record, facts = state.get("decision_record") or {}, tool_facts(state)
    # §4.3 grounding (AC-05): a line stating an id, date or number no tool returned is dropped and logged (G-OUT-01)
    kept = [line for line in lines + body if not build.bad(line, facts)]
    receipt, handoff, dropped = papers(state, facts)
    dropped += len(lines) + len(body) - len(kept)
    # [assumption] nothing left to say: the line that states nothing it could not verify
    kept = kept or [msg.text("status.read_failed", language)]
    usage, notes, extra_alerts, chosen = list(state.get("usage") or []), dict(state.get("llm_notes") or {}), [], None
    if ((config.get("configurable") or {}).get("writer") or "template") == "llm":
        worded = await write_reply(state, config, kept, facts, row)
        kept, chosen, dropped = worded.lines, worded.chips, dropped + worded.dropped
        usage += [worded.usage] if worded.usage else []
        notes["respond"], extra_alerts = worded.note, worded.alerts
    alerts = [build.ALERT] * bool(dropped) + [a for a in [*(state.get("llm_alerts") or []), *extra_alerts]
                                              if a not in (state.get("guardrails_triggered") or [])]
    turn = TurnResult(
        reply="\n".join(kept), language=language,
        decision=state.get("decision"), intent=state.get("intent"), receipt=receipt, handoff=handoff,
        intent_confidence=state.get("intent_confidence"), case_id=state.get("case_id"), zone=state.get("zone"),
        plan=state.get("plan") or [], options=state.get("options") or [],
        actions=state.get("actions") or [],
        suggestions=msg.suggestions(row, language, state.get("case_id"), chosen),
        guardrails_triggered=[*(state.get("guardrails_triggered") or []), *alerts], denials=state.get("denials") or [],
        mode=state["mode"], trace_id=state["trace_id"], usage=usage,
        trace=[step(n, record, state.get("read_failed"), state.get("unconfirmed"), dropped, notes) for n in nodes])
    return {**turn.model_dump(mode="json"), "messages": [], "action": None, "greet_pending": False,
            "language_last": language, "llm_spent_usd": state.get("llm_spent_usd") or 0.0}


async def write_reply(state: State, config: RunnableConfig, lines: list[str], facts: list[Any],
                      row: str) -> wording.Worded:
    """The §4.6 writer on the turn's gated template lines (AC-37): each released text delta leaves as a spec 01 §6.4.1
    `text` chunk; the chips it may pick are the row's allowed set (AC-39). Its spend counts toward the daily cap only,
    not the conversation's S1 budget [assumption]; its usage row goes to `llm_calls` as every billed call (AC-14)."""
    language, case_id = state["language"], state.get("case_id")
    try:
        write = get_stream_writer()
    except RuntimeError:
        write = None
    message_id = f"{state['trace_id']}:reply"

    def emit(delta: str) -> None:
        if write:
            write(TextChunk(message_id=message_id, delta=delta).model_dump(mode="json"))

    allowed = msg.allowed(row, case_id)
    chips = [{"id": c, "label": msg.chip(c, language, case_id).label} for c in allowed]
    texts = [m.get("content", "") for m in state.get("messages") or [] if m.get("role", "user") == "user"]
    cards, shown = on_cards(state)
    return await wording.word(
        config, lines, facts, language=language, first_name=(state.get("profile") or {}).get("first_name"),
        chips=chips, person=next((c for c in allowed if c in msg.PERSON), None), emit=emit,
        score=(state.get("score") or {}).get("score"), transcript=texts, cards=cards, shown=shown,
        over_cap=lambda estimate: arms.over_day_cap(config, estimate))


SHOWN_KEYS = frozenset({"verification_id", "read_at", "verified_at", "deadline_source", "deadline_source_label",
                        "deadline_source_url", "source_url", "verified_on", "deadline_verified_on"})


def on_cards(state: State) -> tuple[list[str], list[str]]:
    """What the turn's cards (spec 01 §6.4.1 `tool` events, the receipt) show beside the writer's text: their names for
    the writer, and the strings it need not repeat (verification ids and times, deadline sources, links, verified-on
    dates). The case id and the deadline dates are not among them: the text states them once (spec 04 §4.6)."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in SHOWN_KEYS and isinstance(value, (str, date)):
                    found.append(str(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk([state.get("actions"), state.get("readings"), state.get("seen"), state.get("writes")])
    names = (["charge"] * bool(state.get("selected_transaction")) + ["case id and status"] * bool(state.get("case_id"))
             + ["action verification ids and times"] * any(wording.VERIFICATION.fullmatch(s) for s in found)
             + ["deadlines with their legal source and link"] * any("://" in s for s in found))
    return names, found


def tool_facts(state: State) -> list[Any]:
    """Every tool result of the turn the customer may see (the score never: notifications.never_send)."""
    writes = {k: v for k, v in (state.get("writes") or {}).items() if k not in ("errors", "unanswered", "held")}
    found = [state.get(key) for key in ("profile", "candidates", "selected_transaction", "display", "existing_case")]
    return [fact for fact in [*found, writes, *(state.get("seen") or [])] if fact]


def papers(state: State, facts: list[Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    """The receipt (a case get_case verified this turn) and the handoff card (a case open_case returned this turn),
    built and gated by `build.papers` against the same tool results as the reply; and how many facts were dropped."""
    writes, readings = state.get("writes") or {}, state.get("readings") or {}
    if not writes.get("open_case") or not state.get("selected_transaction"):
        return None, None, 0
    return build.papers({
        "trx": state["selected_transaction"], "opened": writes["open_case"], "case": readings.get("open_case"),
        "card": readings.get("block_card"), "display": state.get("display"), "actions": state.get("actions") or [],
        "held": bool(writes.get("held")), "dispute": dispute_type(state), "route": state.get("route") or {},
        "decision": state.get("decision"), "score": state.get("score"), "language": state["language"],
        "mode": state["mode"], "trace_id": state["trace_id"], "intent_confidence": state.get("intent_confidence"),
        "guardrails": state.get("guardrails_triggered") or []}, facts)


def step(node: str, record: dict[str, Any], read_failed: Optional[str], unconfirmed: Optional[list[str]] = None,
         dropped: int = 0, notes: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """A trace step: the decision record on the node that decided (D-046); a failed read as not_confirmed on the node
    that tried it (retrieve or status), the actions verify could not confirm on verify, on respond how many facts
    the grounding gate dropped (G-OUT-01), and on understand its LLM arm, or its fall back to S0 as an error (§5)."""
    if node == "respond" and dropped:
        return {"node": node, "status": "error", "ms": 0, "detail": f"G-OUT-01: {dropped} ungrounded fact(s) dropped"}
    if llm := (notes or {}).get(node):      # understand's LLM arm, respond's writer
        return {"node": node, "status": "error" if " -> " in llm else "ok", "ms": 0, "detail": llm}
    if node in ("retrieve", "status") and read_failed:
        return {"node": node, "status": "error", "ms": 0, "detail": f"{read_failed}: not_confirmed"}
    if node == "verify" and unconfirmed:
        return {"node": node, "status": "error", "ms": 0, "detail": ", ".join(unconfirmed) + ": not_confirmed"}
    return {"node": node, "status": "deny" if node == "refuse" else "ok", "ms": 0,
            "detail": json.dumps(record, sort_keys=True) if node == record.get("node") else None}


def traced(node):
    """A node after identity that takes the run config gets the turn's `trace_id` in it, so `call` sends the state's
    trace id as X-Trace-Id: one id for every tool call of the turn, also on a run with no run_id (spec 03 §6, INT1)."""
    if node is identity or "config" not in inspect.signature(node).parameters:
        return node

    def with_trace(state: State, config: RunnableConfig) -> RunnableConfig:
        return {**config, "configurable": {**(config.get("configurable") or {}), "trace_id": state.get("trace_id")}}

    if inspect.iscoroutinefunction(node):
        @functools.wraps(node)
        async def run_async(state: State, config: RunnableConfig) -> dict[str, Any]:
            return await node(state, with_trace(state, config))
        return run_async

    @functools.wraps(node)
    def run(state: State, config: RunnableConfig) -> dict[str, Any]:
        return node(state, with_trace(state, config))
    return run


builder = StateGraph(State, input_schema=InputState, output_schema=OutputState)
for _node in (identity, greet, understand, route, refuse, connect, retrieve, decide, plan, act, verify, duplicate, clarify,
              status, respond):
    builder.add_node(_node.__name__, traced(_node))
builder.add_edge(START, "identity")
builder.add_edge("identity", "greet")
builder.add_edge("greet", "understand")
builder.add_edge("understand", "route")
builder.add_conditional_edges("route", lambda state: state["branch"],
                              ["refuse", "connect", "retrieve", "status", "respond"])
builder.add_conditional_edges("retrieve", lambda state: "respond" if state.get("read_failed") else "decide",
                              ["decide", "respond"])
builder.add_conditional_edges("decide", lambda state: state["next_node"],
                              ["clarify", "refuse", "plan", "duplicate", "connect", "respond"])
builder.add_conditional_edges("plan", lambda state: "respond" if state["route"]["decision"] == "confirm" else "act",
                              ["act", "respond"])
builder.add_edge("act", "verify")
builder.add_conditional_edges("verify", lambda state: "respond" if state["row"] == "reauthenticate"
                              else call_or_respond(state), ["connect", "respond"])
builder.add_conditional_edges("duplicate", call_or_respond, ["connect", "respond"])
for _node in ("refuse", "connect", "clarify", "status"):
    builder.add_edge(_node, "respond")
builder.add_edge("respond", END)
graph = builder.compile(name="dispute_intake")   # Platform adds its own checkpointer; tests compile `builder` with one
