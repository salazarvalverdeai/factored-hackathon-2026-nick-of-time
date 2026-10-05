"""INT1 harness (spec 04 §10): the `dispute_intake` graph against the REAL MCP server, in-process and offline.

The app is the one `python -m mcp_server` serves (`mcp_server.__main__.build`: API-key middleware, gate, every tool
module on main) over a real store and a gold folder. The graph reaches it exactly as on Platform: `intake.call` builds a
`StreamableHttpTransport` from `MCP_URL` and `MCP_API_KEY` in the environment. The only change is the hop: the httpx
client is given an ASGI transport bound to the app, so no socket is opened (tests/conftest.py blocks them).

- Store: MemoryStore through the entry point's own `open_store` with the explicit dev flag (`MCP_DEV_MEMORY_STORE=1`),
  or PostgresStore in a throwaway schema when `TEST_DATABASE_URL` is set (`-m postgres`).
- Gold: a folder given by the test (a tiny fixture built from an eval case, or `GOLD_PATH`).
- Session: a verified row seeded in the store for the case's customer, as the api does after the OTP (spec 01 §6.5).
- LLM: none. The graph runs arm S0 (rules), so no provider is ever called.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import functools
import json
import os
import re
import secrets
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional
from unittest import mock

import httpx2
import polars as pl
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langgraph.checkpoint.memory import InMemorySaver

from contracts.tools import CUSTOMER_TOOLS, ToolError
from nick_of_time.contracts import TurnResult
from nick_of_time.ids import GOLD_PATTERN

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps/agent"), str(ROOT / "apps/mcp")]
from agent import intake  # noqa: E402
from mcp_server import __main__ as entry  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402

KEY = "int1-dummy-key-not-a-secret-0123456789"     # >= 32 characters: the server refuses a shorter one
MCP_URL = "http://mcp.int.local/mcp"                 # never resolved: the ASGI transport answers it in-process
# The policy's per-call budget (800 ms) is for the network; an in-process DuckDB read over the full gold on a loaded
# runner can exceed it, which would turn a read into a spurious UNAVAILABLE. Same widening as the fake harness.
BUDGET_S = 30.0
SCHEMA_SQL = ROOT / "packages/nick_of_time/store/schema.sql"


@functools.lru_cache(maxsize=4)
def cached_gold(path: str) -> Gold:
    """One DuckDB load per gold folder for the whole test session (the full gold takes seconds)."""
    return Gold(Path(path))


def asgi_factory(app: Any):
    """An `McpHttpClientFactory` whose client sends every request to `app` in-process (no socket)."""
    def factory(headers: Optional[dict[str, str]] = None, timeout: Any = None, auth: Any = None,
                follow_redirects: bool = True, **_: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers=headers, auth=auth,
                                  timeout=timeout or httpx2.Timeout(30.0), follow_redirects=follow_redirects)
    return factory


class LocalMCP:
    """The real MCP app over `store` and `gold`, served on one event loop that the graph's turns share.

    The streamable HTTP session manager runs once per app and lives in its own task (anyio's task group must exit in
    the task that entered it), so `start()` / `close()` bracket every turn of a test."""

    def __init__(self, gold: Path, store: Any, backend: str, env: dict[str, str]) -> None:
        self.gold, self.store, self.backend = Path(gold), store, backend
        self.env = {"MCP_API_KEY": KEY, "GOLD_PATH": str(gold), **env}
        with mock.patch.object(entry, "open_store", lambda _env: (store, backend)), \
                mock.patch.object(entry, "Gold", lambda path: cached_gold(str(path))):
            self.app = entry.build(self.env)          # the entry point's own wiring: key, gold, store, tool modules
        self.runner, self._stop, self._task = asyncio.Runner(), None, None

    def start(self) -> "LocalMCP":
        self.runner.run(self._start())
        return self

    async def _start(self) -> None:
        ready, self._stop = asyncio.Event(), asyncio.Event()

        async def serve() -> None:
            async with self.app.router.lifespan_context(self.app):
                ready.set()
                await self._stop.wait()
        self._task = asyncio.get_running_loop().create_task(serve())
        await ready.wait()

    def close(self) -> None:
        async def stop() -> None:
            self._stop.set()
            await self._task
        try:
            self.runner.run(stop())
        finally:
            self.runner.close()

    def run(self, coro):
        return self.runner.run(coro)

    @contextmanager
    def wired(self) -> Iterator[None]:
        """The graph's MCP client config as on Platform (MCP_URL, MCP_API_KEY), with the hop made in-process."""
        def transport(url: str, headers: Optional[dict[str, str]] = None, **kwargs: Any) -> StreamableHttpTransport:
            assert url == MCP_URL, url
            return StreamableHttpTransport(url, headers=headers, httpx_client_factory=asgi_factory(self.app), **kwargs)
        with mock.patch.dict(os.environ, {"MCP_URL": MCP_URL, "MCP_API_KEY": KEY}), \
                mock.patch.object(intake, "StreamableHttpTransport", transport), \
                mock.patch.object(intake, "TIMEOUT_S", BUDGET_S):
            yield

    def tool(self, name: str, session_id: str, **args: Any):
        """One direct tool call through the same HTTP app and key (for the test's own cross-checks)."""
        async def go():
            transport = StreamableHttpTransport(MCP_URL, headers={"X-API-Key": KEY},
                                                httpx_client_factory=asgi_factory(self.app))
            async with Client(transport, timeout=BUDGET_S) as client:
                result = await client.call_tool(name, {"session_id": session_id, **args}, raise_on_error=False)
            model = ToolError if result.is_error else CUSTOMER_TOOLS[name][1]
            return model.model_validate(result.structured_content)
        return self.run(go())


def seed_session(store: Any, customer_id: str, language: str, run_id: str, *, mode: str = "replay",
                 tool_faults: tuple[str, ...] = ()) -> str:
    """A verified 15-minute session for the case's customer, as the api writes it after the OTP (spec 01 §6.5);
    `tool_faults` as the eval seed sets them for a tool_failure case (spec 03 AC-05)."""
    now = dt.datetime.now(dt.UTC)
    return store.create_session(customer_id=customer_id, otp_hash="int1-not-an-otp", language=language, mode=mode,
                                expires_at=now + dt.timedelta(minutes=15), verified_at=now, run_id=run_id,
                                arm="S0", tool_faults=tool_faults).session_id


class Chat:
    """One thread of the graph (with a checkpointer, as Platform keeps it) against a started LocalMCP."""

    def __init__(self, mcp: LocalMCP, session_id: str, thread: str, **settings: Any) -> None:
        self.mcp = mcp
        self.graph = intake.builder.compile(checkpointer=InMemorySaver())
        # spec 01 §6.4: what the api injects; Platform adds thread_id and run_id to the configurable itself
        self.config = {"configurable": {"session_id": session_id, "session_state": "verified", "mode": "replay",
                                        "arm": "S0", "thread_id": thread, **settings}}

    def say(self, text: Optional[str] = None, language: Optional[str] = None,
            action: Optional[dict[str, Any]] = None, run_id: bool = True) -> TurnResult:
        """One turn; `run_id=False` runs it as a bare `ainvoke` with no run id in the config (not Platform)."""
        payload = {"messages": [{"role": "user", "content": text}] if text else [], "language": language,
                   "action": action}
        with self.mcp.wired():
            run = {"run_id": str(uuid.uuid4())} if run_id else {}   # a new Platform run per turn
            config = {**self.config, "configurable": {**self.config["configurable"], **run}}
            out = self.mcp.run(self.graph.ainvoke(payload, config))
        return TurnResult.model_validate(out)


def gate_drops(turn: TurnResult) -> int:
    """How many facts respond's grounding gate dropped this turn (G-OUT-01), from its trace step."""
    detail = (turn.trace[-1].detail or "") if turn.trace and turn.trace[-1].node == "respond" else ""
    return int(detail.split()[1]) if detail.startswith("G-OUT-01: ") else 0


# ---------- stores ----------
@contextmanager
def memory_store() -> Iterator[tuple[Any, str]]:
    """The entry point's in-memory store, selected only by the explicit dev flag."""
    yield entry.open_store({entry.MEMORY_FLAG: "1"})


@contextmanager
def postgres_store(url: str) -> Iterator[tuple[Any, str]]:
    """The entry point's PostgresStore (DATABASE_URL) in a fresh schema of TEST_DATABASE_URL, dropped afterwards."""
    import psycopg

    schema = "int1_" + secrets.token_hex(4)
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f"create schema {schema}")
        try:
            admin.execute(f"set search_path to {schema}")
            admin.execute(SCHEMA_SQL.read_text())
            sep = "&" if "?" in url else "?"
            store, backend = entry.open_store({"DATABASE_URL": f"{url}{sep}options=-csearch_path%3D{schema}"})
            try:
                yield store, backend
            finally:
                store.close()
        finally:
            admin.execute(f"drop schema {schema} cascade")


# ---------- gold ----------
CARD = {"debit": "Tarjeta Débito", "credit": "Tarjeta Crédito"}
COUNTRY_NAME = {"MX": "México", "AR": "Argentina", "CO": "Colombia", "BR": "Brasil", "PE": "Perú", "CL": "Chile"}


def fixture_gold(folder: Path, case: dict[str, Any], *, first_name: str = "Ana", product_type: str = "debit",
                 last4: str = "4417") -> Path:
    """A tiny gold folder with just the case's customer, card and transactions (initial_state.fixtures), in the
    columns `Gold` and `GoldCards` read. [assumption] Fields an eval fixture leaves out get a neutral value: the first
    name, the card type (debit unless the fixture says), its last 4, status Approved and the charge made at home."""
    state, country = case["initial_state"], case["country"]
    customer = state["customer_id"]
    # a malformed id would make the tools refuse the call (schema DENY, UNAVAILABLE) and a test fail for the wrong reason
    bad = [f"{kind} {value!r}" for kind, value in
           [("customer", customer), *[(k, item.get(f"{k}_id")) for item in state["fixtures"]
                                      for k in ("transaction", "product")]]
           if not (isinstance(value, str) and re.fullmatch(GOLD_PATTERN[kind], value))]
    if bad:
        raise ValueError(f"fixture ids outside the gold shapes (nick_of_time.ids.GOLD_PATTERN): {', '.join(bad)}")
    folder.mkdir(parents=True, exist_ok=True)
    trx, products = [], {}
    for item in state["fixtures"]:
        kind = item.get("product_type", product_type)
        products[item["product_id"]] = kind
        day = dt.date.fromisoformat(item["transaction_date"])
        trx.append({"transaction_id": item["transaction_id"], "product_id": item["product_id"], "customer_id": customer,
                    "transaction_date": dt.datetime.combine(day, dt.time(10)), "amount": float(item["amount"]),
                    "currency": item["currency"], "amount_usd": float(item["amount"]) if item["currency"] == "USD"
                    else None, "merchant_name": item.get("merchant"), "transaction_status": "Approved",
                    "fraud_score": item.get("fraud_score"), "product_type": CARD[kind],
                    "transaction_country": COUNTRY_NAME[country]})
    pl.DataFrame(trx, schema_overrides={"amount_usd": pl.Float64, "merchant_name": pl.Utf8,
                                        "fraud_score": pl.Float64}).write_parquet(
        folder / "transactions_enriched.parquet")
    pl.DataFrame([{"customer_id": customer, "first_name": first_name, "country": COUNTRY_NAME[country]}]).write_parquet(
        folder / "customers.parquet")
    pl.DataFrame([{"product_id": pid, "customer_id": customer, "product_type": CARD[kind],
                   "product_number": f"5{secrets.randbelow(10**11):011d}{last4}", "product_status": "Active"}
                  for pid, kind in products.items()]).write_parquet(folder / "products.parquet")
    (folder / "manifest.json").write_text(json.dumps({"dataset": "int1_fixture", "version": 0}))
    return folder
