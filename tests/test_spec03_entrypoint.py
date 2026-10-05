"""Spec 03 T8: the entry point `python -m mcp_server` — fail closed without the key, the store or gold (AC-06), 401/200
on /mcp, a /health without secrets, the read handlers wired over the store's sessions and denials (AC-02, AC-12), and
optional tool modules that may be absent. In-memory store and a tiny gold fixture: no network, no Postgres, no LLM."""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

import polars as pl
import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server import __main__ as entry  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402
from mcp_server.reads import read_handlers  # noqa: E402
from nick_of_time.policy import load_policies  # noqa: E402
from nick_of_time.store.memory import MemoryStore  # noqa: E402

KEY = "test-key-not-a-secret-0123456789abcdef"
DB_URL = "postgresql://user:not-a-real-password@db:5432/x"
CUSTOMER = "CLI-ENTRYPOINT0001"
ACCEPT = {"Accept": "application/json, text/event-stream"}
HELLO = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}


@pytest.fixture(scope="module")
def gold(tmp_path_factory):
    root = tmp_path_factory.mktemp("gold") / "v1"
    root.mkdir()
    pl.DataFrame([{"transaction_id": "TRX-1", "product_id": "PRD-1", "customer_id": CUSTOMER,
                   "transaction_date": dt.datetime(2026, 5, 30, 10), "amount": 120.0, "currency": "MXN",
                   "amount_usd": 6.67, "merchant_name": "Tienda", "transaction_status": "Approved",
                   "fraud_score": 61.0, "product_type": "Tarjeta Crédito",
                   "transaction_country": "México"}]).write_parquet(
        root / "transactions_enriched.parquet")
    pl.DataFrame([{"customer_id": CUSTOMER, "first_name": "Ana", "country": "Mexico"}]).write_parquet(
        root / "customers.parquet")
    (root / "manifest.json").write_text(json.dumps({"dataset": "latam_bank_gold", "version": 1}))
    return root


def _env(gold, **extra):
    return {"MCP_API_KEY": KEY, "GOLD_PATH": str(gold), "MCP_DEV_MEMORY_STORE": "1", **extra}


def _app(gold, monkeypatch, store=None, **extra):
    store = store or MemoryStore()
    monkeypatch.setattr(entry, "open_store", lambda env: (store, "memory"))
    return entry.build(_env(gold, **extra)), store


@pytest.mark.parametrize("key", [None, "", "a" * 31])
def test_ac_06_the_server_refuses_to_start_without_a_valid_api_key(gold, key):
    env = {name: value for name, value in _env(gold, MCP_API_KEY=key).items() if value is not None}
    with pytest.raises(RuntimeError, match="fail closed") as refused:
        entry.build(env)
    assert KEY not in str(refused.value)


def test_ac_06_without_a_store_or_gold_it_refuses_to_start_and_memory_needs_the_explicit_flag(gold):
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        entry.build({"MCP_API_KEY": KEY, "GOLD_PATH": str(gold)})
    with pytest.raises(RuntimeError, match="GOLD_PATH"):
        entry.build({"MCP_API_KEY": KEY, "MCP_DEV_MEMORY_STORE": "1"})
    assert entry.open_store({"MCP_DEV_MEMORY_STORE": "1"})[1] == "memory"
    with pytest.raises(RuntimeError):
        entry.open_store({"MCP_DEV_MEMORY_STORE": "0"})


def test_ac_06_mcp_answers_401_without_the_key_and_200_with_it(gold, monkeypatch):
    app, _ = _app(gold, monkeypatch)
    with TestClient(app) as client:
        assert client.post("/mcp", json=HELLO, headers=ACCEPT).status_code == 401
        assert client.post("/mcp", json=HELLO, headers={**ACCEPT, "X-API-Key": "wrong"}).status_code == 401
        assert client.post("/mcp", json=HELLO, headers={**ACCEPT, "X-API-Key": KEY}).status_code == 200


def test_t8_health_reports_versions_and_handlers_without_secrets(gold, monkeypatch):
    app, _ = _app(gold, monkeypatch, DATABASE_URL=DB_URL)
    with TestClient(app) as client:
        body = client.get("/health").text
    health = json.loads(body)
    reads = read_handlers(Gold(gold), load_policies())                   # grows as 03b adds read tools (PR #120)
    assert {k: health[k] for k in ("status", "tools", "gold_version", "store")} == {
        "status": "ok", "tools": 16, "gold_version": "v1", "store": "memory"}
    assert health["policies_version"] == load_policies().version
    assert len(reads) <= health["handlers"] <= 16                        # 03c / 03d1 modules add theirs when merged
    modules = health["modules"]
    assert sorted(modules["loaded"] + modules["absent"]) == sorted(entry.OPTIONAL_MODULES)
    assert KEY not in body and "not-a-real-password" not in body and str(gold) not in body
    assert entry.gold_version(gold, {"GOLD_VERSION": "v7"}) == "v7"
    assert entry.gold_version(gold / "missing", {}) is None


def test_ac_02_ac_12_read_handlers_run_over_the_store_sessions_and_denials(gold, monkeypatch):
    store = MemoryStore()
    now = dt.datetime.now(dt.UTC)
    session = store.create_session(customer_id=CUSTOMER, otp_hash="h", expires_at=now + dt.timedelta(minutes=15),
                                   language="es", mode="replay", verified_at=now)
    app, _ = _app(gold, monkeypatch, store=store)

    def call(client, headers, name, **args):
        body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args}}
        return client.post("/mcp", json=body, headers=headers).text

    with TestClient(app) as client:
        opened = client.post("/mcp", json=HELLO, headers={**ACCEPT, "X-API-Key": KEY})
        headers = {**ACCEPT, "X-API-Key": KEY, "mcp-session-id": opened.headers["mcp-session-id"]}
        client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers)
        profile = call(client, headers, "get_customer_profile", session_id=session.session_id)
        expired = call(client, headers, "get_customer_profile", session_id="S-unknownsession01")
        denied = call(client, headers, "get_fraud_score", session_id=session.session_id, transaction_id="TRX-1",
                      customer_id="CLI-OTHER")
    assert '"first_name":"Ana"' in profile and '"isError":false' in profile
    assert "SESSION_EXPIRED" in expired
    assert "DENY" in denied
    [row] = store.list_denials(run_id=None)
    assert (row.session_id, row.policy_id, row.guardrail_id) == (session.session_id, "POL-DEFAULT-DENY", "G-TOOL-01")


def _modules(monkeypatch, **fakes):
    """Fake tool modules: a module object, an exception to raise on import, or absent when not named."""
    real_import = importlib.import_module

    def fake_import(name, *args):
        short = name.removeprefix("mcp_server.")
        if short in fakes:
            if isinstance(fakes[short], BaseException):
                raise fakes[short]
            return fakes[short]
        if name.startswith("mcp_server.") and short not in ("gold", "reads", "gate", "server"):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real_import(name, *args)
    monkeypatch.setattr(importlib, "import_module", fake_import)


def _module(name, factory):
    module = types.ModuleType(f"mcp_server.{name}")
    factory.__module__ = module.__name__
    setattr(module, factory.__name__, factory)
    return module


def test_t8_present_tool_modules_register_and_absent_ones_are_skipped(monkeypatch):
    def demo_handlers(gold, store, unused=None):
        return {"get_case": lambda call, args: (gold, store)}
    _modules(monkeypatch, present=_module("present", demo_handlers))
    found, loaded, absent = entry.optional_handlers({"gold": "G", "store": "S"}, ("absent", "present"))
    assert list(found) == ["get_case"] and found["get_case"](None, None) == ("G", "S")
    assert (loaded, absent) == (["present"], ["absent"])


def test_t8_a_broken_tool_module_stops_startup(monkeypatch, gold):
    def needs_handlers(clock):
        return {}

    def failing_handlers(gold):
        raise ValueError("boom")

    def unknown_handlers(gold):
        return {"wire_money": lambda call, args: None}
    inner = ModuleNotFoundError("No module named 'missing_dep'", name="missing_dep")
    cases = {"broken": ImportError("a bug"), "inner": inner, "needs": _module("needs", needs_handlers),
             "failing": _module("failing", failing_handlers), "unknown": _module("unknown", unknown_handlers)}
    _modules(monkeypatch, **cases)
    for name in cases:
        with pytest.raises(RuntimeError, match=name):
            entry.optional_handlers({"gold": "G"}, (name,))
    monkeypatch.setattr(entry.optional_handlers, "__defaults__", (("broken",),))
    with pytest.raises(RuntimeError, match="broken"):
        _app(gold, monkeypatch)


def test_t8_entry_point_runs_one_worker_and_the_image_runs_the_real_server(monkeypatch):
    ran = {}
    monkeypatch.setattr(entry, "build", lambda: "app")
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda app, **kw: ran.update(app=app, **kw)))
    entry.main(["--port", "8123"])
    assert ran == {"app": "app", "host": "0.0.0.0", "port": 8123, "workers": 1}
    dockerfile = (ROOT / "apps/mcp/Dockerfile").read_text()
    assert '"-m", "mcp_server", "--host"' in dockerfile and "mcp_server.fake" not in dockerfile.split("CMD")[-1]
    assert '"mcp_server.fake"' in (ROOT / "infra/compose.dev.yml").read_text()
