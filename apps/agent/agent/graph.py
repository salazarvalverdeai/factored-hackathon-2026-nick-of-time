"""Echo graph `dispute_intake` (spec 01 §6.4, T5, AC-04): the graph's input and output without its logic.

Every turn answers a valid `TurnResult` that echoes the customer's last message and carries the sample receipt
[simulated], so the api, the web and the harness can build against the real I/O before spec 04. No LLM, no tools, no
network. `configurable.session_id` is required, as the api always injects it; `configurable.mode` defaults to replay.
Served by `langgraph.json` as `dispute_intake_echo` (D-048: `dispute_intake` is the real graph, `agent.intake`); locally `PYTHONPATH=.:packages langgraph dev`.
"""
# No `from __future__ import annotations`: the state types must resolve when the server loads this file by path.
import uuid
from typing import Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from nick_of_time.contracts import TurnResult, sample_receipt


class InputState(TypedDict, total=False):
    messages: list[dict[str, Any]]    # [{"role": "user", "content": str}]
    language: Optional[str]           # "es" | "pt" | None
    action: Optional[dict[str, Any]]  # a chip or button press: {"type": …, "value": …}


OutputState = TypedDict("OutputState", {name: field.annotation for name, field in TurnResult.model_fields.items()},
                        total=False)
State = TypedDict("State", {**InputState.__annotations__, **OutputState.__annotations__}, total=False)

TEXT = {   # customer-facing, so ES/PT
    "es": {"reply": "Recibí tu mensaje (respuesta de prueba): {text}", "view": "Ver mi caso",
           "summary": "Enviarme el comprobante", "call": "Que me llame una persona"},
    "pt": {"reply": "Recebi sua mensagem (resposta de teste): {text}", "view": "Ver meu caso",
           "summary": "Enviar-me o comprovante", "call": "Quero que uma pessoa me ligue"},
}


def echo(state: State, config: RunnableConfig) -> dict[str, Any]:
    settings = config.get("configurable") or {}
    if not settings.get("session_id"):
        raise ValueError("configurable.session_id is required; the api injects it (spec 01 §6.4)")
    language = state.get("language") or "es"
    if language not in TEXT:
        raise ValueError(f"language must be es, pt or null, not {language!r} (spec 01 §6.4)")
    messages, action = state.get("messages") or [], state.get("action") or {}
    text = messages[-1].get("content", "") if messages else action.get("type", "")
    receipt, words = sample_receipt(), TEXT[language]
    turn = TurnResult(
        reply=words["reply"].format(text=text), language=language, case_id=receipt.case_id, receipt=receipt,
        suggestions=[
            {"id": "view_case", "label": words["view"], "kind": "link", "href": f"/case/{receipt.case_id}"},
            {"id": "send_summary", "label": words["summary"], "kind": "action", "action": {"type": "send_summary"}},
            {"id": "request_call", "label": words["call"], "kind": "action", "action": {"type": "request_call"}}],
        mode=settings.get("mode") or "replay",
        trace=[{"node": "echo", "status": "ok", "ms": 0}],
        trace_id=str(config.get("run_id") or settings.get("run_id") or uuid.uuid4()),
    )
    return turn.model_dump(mode="json")


_builder = StateGraph(State, input_schema=InputState, output_schema=OutputState)
_builder.add_node("echo", echo)
_builder.add_edge(START, "echo")
_builder.add_edge("echo", END)
graph = _builder.compile(name="dispute_intake")
