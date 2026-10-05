"""Spec 04 AC-17 (task PROG): the progress stream. The graph streams one customer label per step as a LangGraph custom
event, in the thread's language, and the api forwards each as `event: progress` before the one `event: turn`. Offline:
fake MCP (FastMCP in-memory), no LLM (arm S0), Platform replayed through httpx.MockTransport."""
from __future__ import annotations

import asyncio
import json
import re

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from app.platform import HttpPlatform
from nick_of_time.contracts import CONTRACTS_DIR, ProgressItem, TurnResult
from tests.test_spec04_decide import server
from tests.test_spec04_graph import Chat, intake
from tests.test_spec05_api import HTTPS, env  # noqa: F401 — the api fixture

EV_0001 = "No reconozco un cargo de 1250 USD en TIENDA X"        # MX, debit, score 72 (high), replay
EV_0001_PT = "Não reconheço uma cobrança de 1250 USD na TIENDA X"
STEPS = ["reading_account", "reading_message", "searching", "deciding", "opening_case", "blocking_card", "verifying",
         "writing"]
LABELS = yaml.safe_load((CONTRACTS_DIR / "messages.yaml").read_text(encoding="utf-8"))["progress"]
# Constitution #4: a label says what is attempted, never a result. Words that would claim one, per language.
RESULT_WORDS = {
    "es": r"bloquead[oa]s?|list[oa]s?|hech[oa]s?|abiert[oa]s?|verificad[oa]s?|confirmad[oa]s?|registrad[oa]s?|"
          r"complet[oa]d?[oa]?s?|termin(é|ado|ada)|qued[óo]|ya|éxito|exitos[oa]|resuelt[oa]|enviad[oa]|listo",
    "pt": r"bloquead[oa]s?|pront[oa]s?|feit[oa]s?|abert[oa]s?|verificad[oa]s?|confirmad[oa]s?|registrad[oa]s?|"
          r"conclu[íi]d[oa]s?|termin(ei|ado|ada)|ficou|já|sucesso|resolvid[oa]|enviad[oa]",
}
INTERNAL = re.compile(r"_|\b(?:mcp|tool|policy|pol-|score|zona|zone|node|graph|llm|bedrock)\b", re.I)


def stream(chat: Chat, text: str, language) -> list[tuple[str, dict]]:
    """One turn as Platform runs it: stream_mode custom + values, in arrival order."""
    payload = {"messages": [{"role": "user", "content": text}], "language": language, "action": None}

    async def run():
        return [(mode, chunk) async for mode, chunk in chat.graph.astream(payload, chat.config,
                                                                        stream_mode=["custom", "values"])]
    return asyncio.run(run())


def progress(chunks) -> list[ProgressItem]:
    return [ProgressItem.model_validate(chunk) for mode, chunk in chunks if mode == "custom"]


@pytest.mark.parametrize("language, text", [("es", EV_0001), ("pt", EV_0001_PT)])
def test_ac_17_ev_0001_streams_one_label_per_step_in_order_in_the_session_language(language, text):
    chunks = stream(Chat(mcp_transport=server(), mode="replay"), text, language)
    items = progress(chunks)
    assert [i.step for i in items] == STEPS
    assert [i.label for i in items] == [LABELS[step][language] for step in STEPS]
    assert all(i.state == "in_progress" for i in items)                     # never verified mid-run (constitution #4)
    assert chunks[-1][0] == "values"                                         # the turn comes after every label
    turn = TurnResult.model_validate({k: v for k, v in chunks[-1][1].items() if k in TurnResult.model_fields})
    assert turn.decision == "block_and_open_case" and [a.state for a in turn.actions] == ["verified", "verified"]


def test_ac_17_a_status_question_streams_its_own_step_in_the_threads_language():
    chat = Chat(mcp_transport=server(), mode="replay")
    stream(chat, EV_0001_PT, "pt")
    items = progress(stream(chat, "Como está meu caso?", None))        # language null: the thread's, pt
    assert [i.step for i in items] == ["reading_message", "checking_status", "writing"]
    assert items[1].label == LABELS["checking_status"]["pt"]


def test_ac_17_a_node_run_outside_a_stream_emits_nothing_and_does_not_fail():
    assert intake.progress({"language": "pt"}, "writing") is None


@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_17_no_label_claims_a_result_or_names_an_internal_term(language):
    deny = re.compile(rf"\b(?:{RESULT_WORDS[language]})\b", re.I)
    assert set(STEPS) | {"checking_status", "requesting_call"} == set(LABELS)
    for step, leaf in LABELS.items():
        label = leaf[language]
        assert label.endswith("…") and not deny.search(label) and not INTERNAL.search(label), (step, label)


def platform_sse(chunks) -> str:
    """The graph's stream as LangGraph Platform sends it: a metadata event, then `custom` and `values` events."""
    events = [("metadata", {"run_id": "r-1"})] + [(mode, chunk) for mode, chunk in chunks]
    return "".join(f"event: {e}\ndata: {json.dumps(d, default=str)}\n\n" for e, d in events)


def test_ac_17_the_api_forwards_each_label_as_progress_then_exactly_one_turn(env):  # noqa: F811
    chunks = stream(Chat(mcp_transport=server(), mode="replay"), EV_0001, "es")
    extra = [("custom", {"note": "not a progress item"}),                    # another custom chunk: dropped
             ("custom", {"step": "block_card", "label": "Tarjeta bloqueada", "state": "verified",
                         "at": "2026-06-01T15:04:00Z"})]                     # a result claim mid-run: dropped
    sse = platform_sse(chunks[:2] + extra + chunks[2:])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/threads" and request.method == "POST":
            return httpx.Response(200, json={"thread_id": "T-1"})
        if request.url.path == "/threads/T-1":
            return httpx.Response(200, json={"metadata": {"session_id": env.sid}})
        assert json.loads(request.content)["stream_mode"] == ["custom", "values"]
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    from app.main import create_app
    env.sid = env.login()
    platform = HttpPlatform("https://platform.example", "k", transport=httpx.MockTransport(handler))
    app = create_app(store=env.store, platform=platform, notifier=env.notifier, now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser:
        browser.cookies.set("not_session", env.sid)
        thread = browser.post("/api/agent/threads").json()["thread_id"]
        run = browser.post(f"/api/agent/threads/{thread}/runs/stream", json={"input": {"messages": []}})
    assert run.status_code == 200
    events = re.findall(r"event: (\w+)\ndata: (.*)\n\n", run.text)
    assert [e for e, _ in events] == ["progress"] * len(STEPS) + ["turn"]
    assert [json.loads(d)["label"] for _, d in events[:-1]] == [LABELS[step]["es"] for step in STEPS]
    assert json.loads(events[-1][1])["decision"] == "block_and_open_case"
