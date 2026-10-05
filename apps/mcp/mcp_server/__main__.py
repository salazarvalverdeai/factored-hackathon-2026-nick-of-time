"""Entry point of the real MCP server (spec 03 T8): `python -m mcp_server [--host H] [--port P]`.

Everything comes from the environment, which deploy writes from SSM (spec 06 FR-09): `MCP_API_KEY` (checked first; the
server refuses to start without one of 32+ characters and never logs it), `DATABASE_URL` (the Postgres store; the
in-memory store only with `MCP_DEV_MEMORY_STORE=1`, never by default), `GOLD_PATH` (gold mounted read-only) and
`GOLD_VERSION` (else the gold manifest's version). One uvicorn worker: the rate limiter's counts live in one process.
The read handlers (task 03b) are wired here; the other tool modules are imported when present (OPTIONAL_MODULES), so
the server keeps starting while they merge, and a tool without a handler answers UNAVAILABLE (the gate).
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import logging
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Optional

from starlette.applications import Starlette

from contracts.tools import CUSTOMER_TOOLS
from mcp_server import server
from mcp_server.gate import DenialRow, Gate, Handler, SessionRow
from mcp_server.gold import Gold
from mcp_server.reads import read_handlers
from nick_of_time.policy import load_policies

# Tasks 03c (writes, case reads) and 03d1 (follow-ups, notifications). A module either fills `server.HANDLERS` when
# imported or defines `<name>_handlers(...)` functions whose parameters are named after DEPENDENCIES and that return
# {tool name: handler}. [assumption] a module that fails to import is logged and skipped: its tools stay UNAVAILABLE.
OPTIONAL_MODULES = ("writes", "case_reads", "followups", "notify")
DEPENDENCIES = ("gold", "policies", "store", "channels", "guardrails")
MEMORY_FLAG = "MCP_DEV_MEMORY_STORE"
log = logging.getLogger("nickoftime.mcp")


class StoreSessions:
    """The gate's `Sessions` over the store: the row is read fresh on every call (spec 03 AC-02)."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def get(self, session_id: str) -> Optional[SessionRow]:
        record = self._store.get_session(session_id)
        return SessionRow.model_validate(record.model_dump()) if record else None


def store_denials(store: Any) -> Callable[[DenialRow], None]:
    """The gate's denial sink: one `policy_denials` row per DENY (spec 03 AC-12)."""
    def write(row: DenialRow) -> None:
        store.add_denial(trace_id=row.trace_id, session_id=row.session_id, actor=row.actor, policy_id=row.policy_id,
                         guardrail_id=row.guardrail_id, detail=row.detail, run_id=row.run_id)
    return write


def open_store(env: Mapping[str, str]) -> tuple[Any, str]:
    if url := env.get("DATABASE_URL", "").strip():
        from nick_of_time.store.postgres import PostgresStore    # psycopg is imported only when used
        return PostgresStore(url), "postgres"
    if env.get(MEMORY_FLAG, "").strip().lower() in ("1", "true", "yes"):
        from nick_of_time.store.memory import MemoryStore
        log.warning("%s is set: in-memory store, local development only", MEMORY_FLAG)
        return MemoryStore(), "memory"
    raise RuntimeError(f"DATABASE_URL is not set: the MCP server does not start without a store ({MEMORY_FLAG}=1 "
                       "selects the in-memory store for local development)")


def gold_version(path: Path, env: Mapping[str, str]) -> Optional[str]:
    """`GOLD_VERSION` as deploy sets it, else `v<version>` from the gold manifest, else None."""
    if version := env.get("GOLD_VERSION", "").strip():
        return version
    try:
        return f"v{json.loads((path / 'manifest.json').read_text())['version']}"
    except (OSError, ValueError, KeyError, TypeError):
        return None


def optional_handlers(deps: Mapping[str, Any], modules: tuple[str, ...] = OPTIONAL_MODULES) -> dict[str, Handler]:
    found: dict[str, Handler] = {}
    for name in modules:
        qualified = f"{__package__}.{name}"
        try:
            module = importlib.import_module(qualified)
        except ModuleNotFoundError as error:
            if error.name == qualified:
                log.info("tool module %s is not present yet", name)
            else:
                log.error("tool module %s failed to import: %s", name, type(error).__name__)
            continue
        except Exception as error:                               # its tools stay UNAVAILABLE
            log.error("tool module %s failed to import: %s", name, type(error).__name__)
            continue
        for attr, factory in vars(module).items():
            if not (attr.endswith("_handlers") and inspect.isfunction(factory) and factory.__module__ == qualified):
                continue
            params = inspect.signature(factory).parameters.values()
            missing = [p.name for p in params if p.default is p.empty and p.name not in deps]
            if missing:
                log.error("%s.%s needs %s: skipped", name, attr, ", ".join(missing))
                continue
            try:
                found.update(factory(**{p.name: deps[p.name] for p in params if p.name in deps}))
            except Exception as error:
                log.error("%s.%s failed: %s", name, attr, type(error).__name__)
    return found


def build(env: Mapping[str, str] = os.environ) -> Starlette:
    """The gated app, or RuntimeError before anything is loaded when the key, the store or gold is missing."""
    api_key = server._key(env.get("MCP_API_KEY", ""))              # fail closed first; the key is never logged
    if not (gold_path := env.get("GOLD_PATH", "").strip()):
        raise RuntimeError("GOLD_PATH is not set: the MCP server does not start without gold")
    store, backend = open_store(env)
    policies, gold = load_policies(), Gold(Path(gold_path))
    guardrails = {rule_id: rule.guardrail for rule_id, rule in policies.rules.items() if rule.guardrail}
    deps = {"gold": gold, "policies": policies, "store": store, "channels": store.channels, "guardrails": guardrails}
    extra = optional_handlers(deps)                                  # imports may also fill server.HANDLERS
    handlers = {**read_handlers(gold, policies, channels=store.channels), **server.HANDLERS, **extra}
    handlers = {tool: handler for tool, handler in handlers.items() if tool in CUSTOMER_TOOLS}
    gate = Gate(StoreSessions(store), handlers, denials=store_denials(store), guardrails=guardrails)
    health = {"gold_version": gold_version(Path(gold_path), env), "policies_version": policies.version,
              "store": backend, "handlers": len(handlers)}
    log.info("MCP server ready: %s", json.dumps(health))
    return server.build_app(server.build_server(gate, info=health), api_key)


def main(argv: Optional[list[str]] = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(prog="python -m mcp_server", description="Nick of Time MCP server (spec 03)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(build(), host=args.host, port=args.port, workers=1, proxy_headers=True)


if __name__ == "__main__":
    main()
