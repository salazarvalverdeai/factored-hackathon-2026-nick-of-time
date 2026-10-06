"""Spec 01 AC-09 end to end, with spec 04 AC-38 and AC-40 (§6.4.1, ADR 0030): the `tool` and `text` chunks the real
graph writes reach the browser through the api's projection unchanged (the SSE event name carries `kind`), and
nothing internal leaks. The graph runs offline on the fake MCP with arm S0; the `llm` writer is a scripted fake client
(CLAUDE.md: never a real LLM in CI). Every custom chunk of the run is replayed through the store-backed api's
`progress_event` by a fake Platform, as `HttpPlatform` hands it over."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from app import demo
from contracts.tools import ToolError
from nick_of_time.events import ToolEvent
from tests.test_spec04_decide import candidates, server
from tests.test_spec04_graph import Chat
from tests.test_spec04_writer import EV_0001, Writer, rewrite, run
from tests.test_spec05_api import Env

# the api's projection lands with spec 01 §6.4.1's api side (PR #201); until both lanes meet, this file skips
stream_events = pytest.importorskip("app.stream_events")

POLICIES = Path(__file__).resolve().parents[1] / "contracts" / "policies.yaml"
CALL = "Quiero hablar con una persona, " + EV_0001.lower()
HELD = ToolError(code="DENY", message="POL-HUMAN-REQUEST holds the block", policy_id="POL-HUMAN-REQUEST")
# Spec 01 AC-09: no score, zone, policy or guardrail id, raw tool payload or prompt
INTERNAL = re.compile(r"score|\bPOL-|\bG-[A-Z]{3}-\d+|\bzone\b|\bzona\b|product_id|amount_usd|idempotency|"
                      r"features_used|customer_id|CLI-|PRD-", re.I)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "DEMO_TODAY", "MCP_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(demo, "new_run_id", lambda now: None)


def chunked(env: Env, chunks: list) -> Env:
    """A fake Platform whose stream first hands over `chunks`, each named `progress` as HttpPlatform names them."""
    original = env.platform.stream

    def stream(thread_id, configurable, payload):
        for chunk in chunks:
            yield "progress", chunk
        yield from original(thread_id, configurable, payload)
    env.platform.stream = stream
    return env


def events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def through_api(chunks: list[tuple[str, dict]]) -> tuple[list[dict], list[tuple[str, dict]]]:
    """The graph's custom chunks (as the graph wrote them) and the SSE events the api sent for them."""
    custom = [c for m, c in chunks if m == "custom"]
    sent = [(n, d) for n, d in events_of(custom) if n in ("tool", "text")]
    return custom, sent


def events_of(custom: list[dict]) -> list[tuple[str, dict]]:
    env = Env()
    env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    chunked(env, custom)
    return events(env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={}).text)


def forwarded_unchanged(chunks: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """AC-09: every `tool`/`text` chunk leaves, in order, as its own SSE event with the same body less `kind`."""
    custom, sent = through_api(chunks)
    expected = [(c["kind"], {k: v for k, v in c.items() if k != "kind"}) for c in custom
                if c.get("kind") in ("tool", "text")]
    assert sent == expected
    assert not INTERNAL.search(json.dumps([d for _, d in sent])), json.dumps(sent)
    return sent


def tools(sent: list[tuple[str, dict]]) -> list[ToolEvent]:
    return [ToolEvent.model_validate({"kind": "tool", **d}) for n, d in sent if n == "tool"]


def ends(sent) -> dict[str, ToolEvent]:
    return {e.step: e for e in tools(sent) if e.status != "running"}


def test_spec01_ac_09_spec04_ac_38_verified_block_and_case_reach_the_browser_unchanged():
    chunks, turn = run(Chat(mcp_transport=server(), mode="replay"), EV_0001)
    sent = forwarded_unchanged(chunks)
    done = ends(sent)
    assert {s: e.status for s, e in done.items()} == {"search_transaction": "done", "evaluate_policy": "done",
                                                      "open_case": "done", "block_card": "done"}
    actions = {c.tool: c for e in done.values() for c in e.cards if c.type == "action"}
    assert {t: (a.state, a.verification_id) for t, a in actions.items()} == {
        a.tool: (a.state, a.verification_id) for a in turn.actions if a.tool in actions}
    deadlines = [c for c in done["open_case"].cards if c.type == "deadline"]
    assert deadlines and all(c.source_url and c.source_url.startswith("https://") for c in deadlines)
    assert not [n for n, _ in sent if n == "text"]                      # AC-40: the template writer streams no text


def test_spec04_ac_38_a_refused_block_is_forwarded_failed_with_no_policy_id():
    chunks, turn = run(Chat(mcp_transport=server(block_card=HELD), mode="replay"), EV_0001)
    done = ends(forwarded_unchanged(chunks))
    assert done["block_card"].status == "failed" and done["block_card"].cards == []
    assert done["open_case"].status == "done"


def test_spec04_ac_38_a_multi_candidate_search_forwards_every_charge_card_synthetic_flag_included():
    many = candidates(2)
    many["candidates"][1]["synthetic"] = True
    chunks, _ = run(Chat(mcp_transport=server(search_transaction=many), mode="replay"), EV_0001)
    search = ends(forwarded_unchanged(chunks))["search_transaction"]
    assert [(c.transaction_id, c.synthetic, c.last4) for c in search.cards] == [
        (c["transaction_id"], c.get("synthetic", False), None) for c in many["candidates"]]


def test_spec04_ac_38_a_status_read_forwards_get_case_with_its_case_card():
    chat = Chat(mode="replay")
    run(chat, EV_0001)
    chunks, turn = run(chat, "¿Cómo va mi caso?")
    read = ends(forwarded_unchanged(chunks))["get_case"]
    assert next(c for c in read.cards if c.type == "case").case_id == turn.case_id


def test_spec04_ac_38_request_call_forwards_its_action_card():
    chunks, turn = run(Chat(mcp_transport=server(), mode="replay"), CALL)
    call = ends(forwarded_unchanged(chunks))["request_call"]
    record = next(a for a in turn.actions if a.tool == "request_call")
    action = next(c for c in call.cards if c.type == "action")
    assert (action.state, action.verification_id) == (record.state, record.verification_id)


def test_spec01_ac_09_the_llm_writer_text_chunks_reach_the_browser_unchanged():
    chat = Chat(mcp_transport=server(), mode="replay", writer="llm", writer_client=Writer(rewrite()))
    chunks, turn = run(chat, EV_0001)
    sent = forwarded_unchanged(chunks)
    text = [d for n, d in sent if n == "text"]
    assert text and {d["message_id"] for d in text} == {f"{turn.trace_id}:reply"}
    assert "".join(d["delta"] for d in text) == turn.reply


def test_spec01_ac_09_every_regulatory_source_url_passes_the_leak_filter():
    urls = list(_urls(yaml.safe_load(POLICIES.read_text())["regulatory_clock"]))
    assert len(urls) >= 6
    for url in urls:
        card = {"type": "deadline", "kind": "ruling", "date": "2026-07-15", "source_label": "Fuente", "source_url": url}
        event = {"kind": "tool", "id": "t:open_case", "step": "open_case", "title": "Caso", "status": "done",
                 "cards": [card], "at": "2026-06-01T15:04:11Z"}
        assert stream_events.project(event) == ("tool", {k: v for k, v in event.items() if k != "kind"}
                                                | {"summary": None}), url


def _urls(node):
    """Every `source_url` of the regulatory clock, however deep its entries nest."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "source_url" and value:
                yield value
            else:
                yield from _urls(value)
    elif isinstance(node, list):
        for item in node:
            yield from _urls(item)
