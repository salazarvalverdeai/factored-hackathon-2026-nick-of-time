"""Spec 01 §6.4.1 AC-09 (forwarded shapes, nothing else leaks) and AC-11 (the `writer` setting), on the store-backed api.
AC-10 (line grounding) is the graph's; the api only forwards what the graph released. Offline: fake Platform."""
from __future__ import annotations

import json

import pytest

from app import demo
from tests.test_spec05_api import START, Env, bearer

AT = START.isoformat()
TOOL = {"kind": "tool", "id": "t1", "step": "search_transaction", "title": "Buscando tu cargo", "status": "running",
        "at": AT}
DONE = {**TOOL, "status": "done", "summary": "Encontré el cargo", "cards": [
    {"type": "charge", "transaction_id": "TRX-1", "date": "2026-05-20", "amount": 120.5, "currency": "MXN",
     "merchant": "Tienda", "last4": "1234", "synthetic": False},
    {"type": "verdict", "headline": "Bloqueamos tu tarjeta", "actions": ["block"]},
    {"type": "action", "tool": "block_card", "state": "verified", "verification_id": "V-0123456789AB"},
    {"type": "deadline", "kind": "credit", "date": "2026-06-03", "source_label": "Banxico", "source_url": None},
    {"type": "case", "case_id": "CASE-1", "status": "new"}]}


def chunked(env: Env, chunks: list) -> Env:
    original = env.platform.stream

    def stream(thread_id, configurable, payload):
        for chunk in chunks:
            yield "progress", chunk                        # HttpPlatform names every custom chunk `progress`
        yield from original(thread_id, configurable, payload)
    env.platform.stream = stream
    return env


@pytest.fixture(autouse=True)
def _no_demo_run(monkeypatch):
    monkeypatch.setattr(demo, "new_run_id", lambda now: None)


def run(env: Env) -> str:
    env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    return env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={}).text


def events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_ac_09_tool_and_text_are_forwarded_in_order_in_the_6_4_1_shapes():
    got = events(run(chunked(Env(), [TOOL, DONE, {"kind": "text", "message_id": "m1", "delta": "Hola "}])))
    assert [n for n, _ in got] == ["tool", "tool", "text", "progress", "turn"]
    tools = [d for n, d in got if n == "tool"]
    assert [t["status"] for t in tools] == ["running", "done"] and tools[0]["id"] == tools[1]["id"]
    assert "kind" not in tools[0] and tools[0]["cards"] == [] and tools[0]["summary"] is None
    assert [c["type"] for c in tools[1]["cards"]] == ["charge", "verdict", "action", "deadline", "case"]
    assert tools[1]["cards"][2]["verification_id"] == "V-0123456789AB"
    assert [d for n, d in got if n == "text"] == [{"message_id": "m1", "delta": "Hola "}]


def test_ac_09_every_other_kind_chunk_or_field_is_dropped():
    leaky = {**DONE, "score": 72, "zone": "high", "policy_id": "POL-ZONE-HIGH", "args": {"customer_id": "C-1"},
             "cards": [{**DONE["cards"][0], "fraud_score": 72, "raw": {"x": 1}}]}
    bad = [{"kind": "debug", "prompt": "SYSTEM ..."}, {"kind": "state", "zone": "high"}, {"kind": "tool"},
           {**TOOL, "step": "evaluate_secret"}, {**TOOL, "status": "verified"},
           {**TOOL, "cards": [DONE["cards"][0]]},                                     # cards only on done
           {**DONE, "cards": [{"type": "action", "tool": "block_card", "state": "verified", "verification_id": None}]},
           {**DONE, "summary": "Regla POL-ZONE-HIGH aplicada"}, {**TOOL, "title": "fraud_score 72"},
           {"kind": "text", "message_id": "m", "delta": 5}, {"kind": "text", "delta": "x"}, "text", ["kind", "tool"]]
    got = events(run(chunked(Env(), [leaky, *bad])))
    assert [n for n, _ in got] == ["tool", "progress", "turn"]
    shown = got[0][1]
    assert set(shown) == {"id", "step", "title", "status", "summary", "cards", "at"}
    assert set(shown["cards"][0]) == {"type", "transaction_id", "date", "amount", "currency", "merchant", "last4",
                                      "synthetic"}
    for secret in ("POL-", "score", "zone", "customer_id", "SYSTEM", "debug", "raw"):
        assert secret not in json.dumps(shown), secret


def test_progress_items_still_work_and_a_result_claim_is_still_dropped():
    claim = {"step": "block_card", "label": "Listo", "state": "verified", "at": AT}
    got = events(run(chunked(Env(), [claim])))
    assert [n for n, _ in got] == ["progress", "turn"]                              # only the fake's in-progress item


def test_ac_11_writer_defaults_to_template_is_injected_and_changes_are_audited():
    env = Env()
    env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={})
    assert env.platform.calls[-1][0]["writer"] == "template"
    assert env.client.get("/api/console/settings", headers=bearer()).json()["writer"] == "template"
    assert env.client.put("/api/console/settings", json={"writer": "llm"}).status_code == 401
    assert env.client.put("/api/console/settings", json={"writer": "gpt"}, headers=bearer()).status_code in (400, 422)
    on = env.client.put("/api/console/settings", json={"writer": "llm"}, headers=bearer(sub="lead-1"))
    assert on.json()["writer"] == "llm"
    env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={})
    assert env.platform.calls[-1][0]["writer"] == "llm"
    env.client.put("/api/console/settings", json={"writer": "template"}, headers=bearer(sub="lead-2"))
    assert [(h["value"], h["actor"]) for h in env.store.setting_history("writer")] == [
        ("llm", "analyst:lead-1"), ("template", "analyst:lead-2")]
    assert env.store.setting_history("supervised_mode") == []                      # a writer change is not a supervised one


def test_ac_11_a_writer_sent_by_the_client_is_ignored():
    env = Env()
    env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    forged = {"input": {"writer": "llm"}, "writer": "llm", "config": {"configurable": {"writer": "llm"}}}
    env.client.post(f"/api/agent/threads/{thread}/runs/stream", json=forged)
    assert env.platform.calls[-1][0]["writer"] == "template"
    assert "writer" not in env.platform.calls[-1][1]["input"]
