"""Real MCP server (spec 03 T1): the 16 customer tools behind the `X-API-Key` middleware and the gate.

Each tool publishes its `contracts/tools.py` schemas and runs through `gate.Gate` (session, fault, rate limit, schema,
audit). The tool handlers land with tasks 03b–03d in `HANDLERS`; until then a tool answers `UNAVAILABLE`. `/health` is
the only route without the key, and it returns no data. [assumption] T8 adds the entry point (MCP_API_KEY from SSM,
one uvicorn worker) over the in-memory store; the Postgres backend and its `sessions` and `policy_denials` accessors are
task 01g's. The fake stays the compose service until then.
"""
from __future__ import annotations

import hmac
import re
import uuid
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from fastmcp.tools.base import Tool, ToolResult
from pydantic import PrivateAttr
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

from contracts.tools import CUSTOMER_TOOLS, ToolError
from mcp_server.gate import Gate, Handler

HANDLERS: dict[str, Handler] = {}       # tool name → handler, filled by tasks 03b–03d
OPEN_PATHS = frozenset({"/health"})
TRACE_ID = re.compile(r"[\w.:-]{1,128}", re.ASCII)   # [assumption] a header outside it is replaced, not logged
MIN_KEY_LENGTH = 32


class CustomerTool(Tool):
    """A contract tool: the input schema of `<Name>In`, the output schema of `<Name>Out`, answered by the gate."""
    _gate: Gate = PrivateAttr()

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        trace_id = get_http_headers().get("x-trace-id", "")        # the graph's run id (spec 03 §6)
        if not TRACE_ID.fullmatch(trace_id):
            trace_id = f"mcp-{uuid.uuid4().hex}"                    # [assumption] a call without one still gets one
        result = self._gate.call(self.name, arguments, trace_id)   # sync: short store reads; T5 measures (AC-13)
        if isinstance(result, ToolError):                          # returned, never raised (spec 03 §6)
            return ToolResult(content=result.model_dump_json(), structured_content=result.model_dump(), is_error=True)
        return ToolResult(structured_content=result.model_dump(mode="json"))


def build_server(gate: Gate) -> FastMCP:
    server = FastMCP("nick-of-time-mcp")
    for name, (model_in, model_out) in CUSTOMER_TOOLS.items():
        tool = CustomerTool(name=name, description=f"{name} (spec 03 §6)", parameters=model_in.model_json_schema(),
                            output_schema=model_out.model_json_schema())
        tool._gate = gate
        server.add_tool(tool)

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "tools": len(CUSTOMER_TOOLS)})

    return server


class ApiKeyMiddleware:
    """AC-06: every HTTP request but OPEN_PATHS needs `X-API-Key` equal to MCP_API_KEY, else 401 with no data."""

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self.app, self._key = app, _key(api_key).encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "lifespan" and scope["path"] not in OPEN_PATHS:     # any other scope fails closed
            given = dict(scope["headers"]).get(b"x-api-key", b"")
            if not hmac.compare_digest(given, self._key):
                if scope["type"] == "http":
                    await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                else:
                    await WebSocketClose(1008)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_app(server: FastMCP, api_key: str) -> Starlette:
    """The streamable HTTP app at `/mcp` (spec 01 §6.3), behind the API key."""
    return server.http_app(path="/mcp", middleware=[Middleware(ApiKeyMiddleware, api_key=_key(api_key))])


def _key(api_key: str) -> str:
    """A key shorter than MIN_KEY_LENGTH once stripped refuses to start: an empty one would match no header."""
    key = (api_key or "").strip()
    if len(key) < MIN_KEY_LENGTH:
        raise RuntimeError(f"MCP_API_KEY needs at least {MIN_KEY_LENGTH} characters: the server does not start "
                           "without it (fail closed)")
    return key

