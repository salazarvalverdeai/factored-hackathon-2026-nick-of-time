"""Spec 03 T1: the real MCP app — API key (AC-06), session first (AC-02), injected faults (AC-05), and the gate's
denials (AC-12 mechanism), rate limits and audit. In-memory sessions and sinks: no network, no gold, no Postgres."""
from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import json
import sys
from pathlib import Path

import pytest
import yaml
from fastmcp import Client
from starlette.testclient import TestClient

from contracts import tools

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server import fake, gate, server  # noqa: E402
from tests.test_spec01_mcp_stub import ARGS  # noqa: E402

NOW = dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC)
KEY = "test-key-not-a-secret"
LIVE, CUSTOMER = "S-livesession00001", "CLI-EXAMPLE00001"


def _row(session_id: str, **extra) -> gate.SessionRow:
    base = {"session_id": session_id, "customer_id": CUSTOMER, "verified_at": NOW, "language": "es",
            "mode": "replay", "expires_at": NOW + dt.timedelta(minutes=15)}
    return gate.SessionRow(**{**base, **extra})


SESSIONS = {LIVE: _row(LIVE), "S-expiredsession01": _row("S-expiredsession01", expires_at=NOW),
            "S-unverifiedsess01": _row("S-unverifiedsess01", verified_at=None),
            "S-nocustomersess01": _row("S-nocustomersess01", customer_id=None),
            "S-faultysession001": _row("S-faultysession001", tool_faults=("block_card", "get_case"), run_id="EV:S0:1")}
BAD_SESSIONS = ["S-unknownsession01", "S-expiredsession01", "S-unverifiedsess01", "S-nocustomersess01", "bad", None]


class Harness:
    """A gate over SESSIONS whose handlers answer the fake's fixtures and remember the session they were given."""

    def __init__(self, handlers=None, limiter=None):
        self.calls, self.denials, self.audit = [], [], []
        limiter = limiter or gate.RateLimiter(clock=itertools.count(step=3601.0).__next__)   # a fresh window per call

        def fixture(call, args):
            self.calls.append((call.tool, call.session.customer_id, args))
            return fake.ANSWERS[call.tool]
        self.handlers = handlers if handlers is not None else {name: fixture for name in tools.CUSTOMER_TOOLS}
        self.gate = gate.Gate(SESSIONS, self.handlers, denials=self.denials.append, audit=self.audit.append,
                              limiter=limiter, now=lambda: NOW)

    def run(self, *calls):
        async def go():
            async with Client(server.build_server(self.gate)) as client:
                return [await client.call_tool(name, args, raise_on_error=False) for name, args in calls]
        return asyncio.run(go())


def _args(name, session_id=LIVE, **extra):
    """The fake's smallest valid input of the tool (spec 01 tests), under `session_id` (None: no session_id)."""
    key = {"idempotency_key": f"key:{name}"} if name in tools.VERIFIED_WITH else {}
    return {**({} if session_id is None else {"session_id": session_id}), **ARGS.get(name, {}), **key, **extra}


def _code(result):
    assert result.is_error and set(result.structured_content) <= set(tools.ToolError.model_fields)
    return tools.ToolError.model_validate(result.structured_content).code


@pytest.mark.parametrize("session_id", BAD_SESSIONS)
def test_ac_02_every_tool_answers_session_expired_with_no_data(session_id):
    h = Harness()
    results = h.run(*[(name, _args(name, session_id)) for name in tools.CUSTOMER_TOOLS],
                    ("search_transaction", _args("search_transaction", session_id, customer_id="CLI-EXAMPLE00002")))
    assert [_code(r) for r in results] == ["SESSION_EXPIRED"] * 17     # session first, before the arguments
    assert h.calls == [] and h.denials == []
    assert [e["outcome"] for e in h.audit] == ["SESSION_EXPIRED"] * 17


def test_ac_02_a_live_session_reaches_the_handler_with_its_own_customer_only():
    h = Harness()
    results = h.run(*[(name, _args(name)) for name in tools.CUSTOMER_TOOLS])
    for (name, (_, model_out)), result in zip(tools.CUSTOMER_TOOLS.items(), results):
        assert not result.is_error and model_out.model_validate(result.structured_content) == fake.ANSWERS[name]
    assert {customer for _, customer, _ in h.calls} == {CUSTOMER} and len(h.calls) == 16
    assert all("customer_id" not in type(args).model_fields for _, _, args in h.calls)


def test_ac_02_every_call_is_audited_with_trace_actor_and_input_hash():
    """G-OPS-02: actor, trace_id and an input hash, never the input itself; one entry per call, whatever the outcome."""
    h = Harness()
    text = "nunca compré en esa tienda"
    h.run(("add_case_info", _args("add_case_info", text=text)), ("get_case", _args("get_case", "S-unknownsession01")))
    ok, expired = h.audit
    assert (ok["outcome"], ok["actor"], ok["session_id"]) == ("ok", "agent", LIVE)
    assert expired["outcome"] == "SESSION_EXPIRED"
    assert ok["input_hash"] == gate.input_hash(_args("add_case_info", text=text)) and ok["trace_id"].startswith("mcp-")
    assert text not in json.dumps(h.audit) and set(ok) == set(expired)


def test_ac_05_an_injected_fault_answers_unavailable_before_the_arguments():
    h = Harness()
    faulty = "S-faultysession001"
    results = h.run(("block_card", _args("block_card", faulty)), ("get_case", _args("get_case", faulty, extra=1)),
                    ("get_product_status", _args("get_product_status", faulty)))
    assert [_code(r) for r in results[:2]] == ["UNAVAILABLE"] * 2 and not results[2].is_error
    assert [name for name, _, _ in h.calls] == ["get_product_status"] and h.denials == []
    assert [(e["outcome"], e["run_id"]) for e in h.audit] == [("UNAVAILABLE", "EV:S0:1")] * 2 + [("ok", "EV:S0:1")]


def test_ac_05_a_failing_or_missing_handler_answers_unavailable_never_an_exception():
    def boom(call, args):
        raise RuntimeError("db down")
    h = Harness(handlers={"get_case": boom, "list_my_cards": lambda call, args: fake.ANSWERS["get_case"]})
    results = h.run(("get_case", _args("get_case")), ("list_my_cards", _args("list_my_cards")),
                    ("open_case", _args("open_case")))           # wrong output model; no handler yet (03b–03d)
    assert [_code(r) for r in results] == ["UNAVAILABLE"] * 3
    broken = Harness()
    broken.gate._audit = lambda entry: 1 / 0                      # no audit, no answer (G-OPS-02)
    assert _code(broken.run(("list_my_cards", _args("list_my_cards")))[0]) == "UNAVAILABLE"


def test_ac_12_unexpected_arguments_are_denied_and_written_to_policy_denials():
    h = Harness()
    [result] = h.run(("search_transaction", _args("search_transaction", customer_id="CLI-EXAMPLE00002")))
    assert _code(result) == "DENY" and result.structured_content["policy_id"] == gate.DEFAULT_DENY
    assert result.structured_content["message"] == "Unexpected or invalid arguments: customer_id."
    [denial] = h.denials
    assert (denial.policy_id, denial.guardrail_id, denial.actor, denial.session_id) == (
        gate.DEFAULT_DENY, "G-TOOL-01", "agent", LIVE)
    assert denial.detail == {"tool": "search_transaction", "fields": ["customer_id"]} and h.calls == []
    assert denial.trace_id == h.audit[0]["trace_id"]


def test_ac_12_a_handler_deny_is_written_with_its_guardrail_its_rule_one_or_g_pol_01():
    h = Harness(handlers={"get_fraud_score": lambda call, args: gate.Deny("POL-CROSS-CUSTOMER"),
                          "block_card": lambda call, args: gate.Deny("POL-SUPERVISED", "G-TOOL-01"),
                          "open_case": lambda call, args: tools.ToolError(code="DENY", policy_id="POL-ZONE-MISMATCH",
                                                                          message="zone")})
    results = h.run(*[(name, _args(name)) for name in ("get_fraud_score", "block_card", "open_case")])
    assert [r.structured_content["policy_id"] for r in results] == ["POL-CROSS-CUSTOMER", "POL-SUPERVISED",
                                                                     "POL-ZONE-MISMATCH"]
    assert [d.guardrail_id for d in h.denials] == ["G-SES-02", "G-TOOL-01", "G-POL-01"]   # policies.yaml rules
    assert gate.DEFAULT_DENY in yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())["rules"]


def test_ac_12_rate_limits_per_session_deny_with_g_tool_01():
    """Spec 03 §6 [assumption]: 30 calls/min, 5 writes/min, 3 notifications/hour per session; only admitted calls
    count, and the windows slide."""
    clock = [0.0]
    limiter = gate.RateLimiter(clock=lambda: clock[0])
    admit = [limiter.admit(LIVE, "send_case_summary") for _ in range(4)]
    assert admit == [None, None, None, "notifications_per_hour"]
    assert [limiter.admit(LIVE, "block_card") for _ in range(3)] == [None, None, "writes_per_minute"]
    assert [limiter.admit(LIVE, "get_case") for _ in range(26)][-2:] == [None, "calls_per_minute"]
    assert limiter.admit("S-anothersession1", "get_case") is None               # per session
    clock[0] = 60.0
    assert (limiter.admit(LIVE, "block_card"), limiter.admit(LIVE, "send_case_summary")) == (None,
                                                                                            "notifications_per_hour")
    h = Harness(limiter=gate.RateLimiter(clock=lambda: 0.0))
    results = h.run(*[("block_card", _args("block_card"))] * 6)
    assert [r.is_error for r in results] == [False] * 5 + [True] and _code(results[-1]) == "DENY"
    assert h.denials[0].detail == {"tool": "block_card", "limit": "writes_per_minute"}


def test_ac_06_mcp_answers_401_without_a_valid_api_key():
    """[C] on the deployed URL; here the same app in-process: 401 without the key or with a wrong one, an open
    /health, and with the key a tool call over streamable HTTP that the audit files under its X-Trace-Id."""
    h = Harness()
    app = server.build_app(server.build_server(h.gate), KEY)
    hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
    accept = {"Accept": "application/json, text/event-stream"}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "list_my_cards", "arguments": _args("list_my_cards")}}
    with TestClient(app) as client:
        assert client.post("/mcp", json=hello, headers=accept).status_code == 401
        denied = client.post("/mcp", json=call, headers={**accept, "X-API-Key": KEY + "x"})
        assert (denied.status_code, denied.json()) == (401, {"error": "unauthorized"}) and h.audit == []
        assert client.get("/health").json() == {"status": "ok", "tools": 16}
        opened = client.post("/mcp", json=hello, headers={**accept, "X-API-Key": KEY})
        session = {**accept, "X-API-Key": KEY, "mcp-session-id": opened.headers["mcp-session-id"]}
        client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=session)
        answer = client.post("/mcp", json=call, headers={**session, "X-Trace-Id": "run-0001"})
    assert opened.status_code == answer.status_code == 200 and '"isError":false' in answer.text
    assert [(e["tool"], e["trace_id"], e["outcome"]) for e in h.audit] == [("list_my_cards", "run-0001", "ok")]
    with pytest.raises(RuntimeError, match="fail closed"):
        server.build_app(server.build_server(h.gate), "")
