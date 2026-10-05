"""The gate every customer tool call passes (spec 03 §6 common rules, T1): session, fault, rate limit, schema, audit.

Order: the session row first (AC-02), then the session's injected faults (AC-05), then the per-session rate limits,
then the strict input model; only then the tool's handler, which receives the session row as the only source of
`customer_id` (constitution #3). Every outcome is a `ToolError` or the tool's `<Name>Out`, never an exception. Every
call is audited (G-OPS-02) and every DENY is written as a `policy_denials` row (spec 01 §6.5, G-POL-01).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol, Union

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from contracts.tools import CUSTOMER_TOOLS, VERIFIED_WITH, ToolError
from nick_of_time.contracts import CONTRACTS_DIR
from nick_of_time.ids import PATTERN

ACTOR = "agent"                 # every MCP call is made by the agent on the customer's behalf (G-OPS-02)
# [assumption] spec 03 §6 (G-TOOL-01, G-OPS-01): (name, tools it counts, max calls, window in seconds) per session.
# A write is any tool of VERIFIED_WITH (W and N); send_case_summary also counts as a notification.
LIMITS: tuple[tuple[str, Optional[frozenset[str]], int, float], ...] = (
    ("calls_per_minute", None, 30, 60.0),
    ("writes_per_minute", frozenset(VERIFIED_WITH), 5, 60.0),
    ("notifications_per_hour", frozenset({"send_case_summary"}), 3, 3600.0))
# [assumption] a rate-limit or schema DENY cites the default-deny rule (spec 02 §4.1) and G-TOOL-01.
DEFAULT_DENY = "POL-DEFAULT-DENY"
# A DENY whose handler names no guardrail cites its rule's (policies.yaml `rules:`), else G-POL-01 (spec 01 §6.5).
RULE_GUARDRAIL: dict[str, str] = {rule: entry["guardrail"] for rule, entry in yaml.safe_load(
    (CONTRACTS_DIR / "policies.yaml").read_text())["rules"].items() if entry.get("guardrail")}
EXPIRED = ToolError(code="SESSION_EXPIRED", message="The session expired or does not exist.")
UNAVAILABLE = ToolError(code="UNAVAILABLE", message="This tool is not available right now.")
log = logging.getLogger("nickoftime.mcp")


class SessionRow(BaseModel):
    """The `sessions` columns a tool needs (spec 01 §6.5); read on every call, never cached."""
    model_config = ConfigDict(frozen=True, extra="ignore")
    session_id: str
    customer_id: Optional[str]
    verified_at: Optional[AwareDatetime]
    expires_at: AwareDatetime
    language: str
    mode: Literal["replay", "live"]
    display_currency: Optional[str] = None
    tool_faults: tuple[str, ...] = ()
    run_id: Optional[str] = None
    arm: Optional[str] = None


class Sessions(Protocol):
    def get(self, session_id: str) -> Optional[SessionRow]: ...   # a dict of rows serves tests


class Denial(BaseModel):
    """A `policy_denials` row (spec 01 §6.5): actor `agent`, a guardrail id always (G-POL-01 when none is given)."""
    denial_id: str
    trace_id: str
    session_id: str
    actor: Literal["agent"] = ACTOR
    policy_id: str
    guardrail_id: str
    detail: dict[str, Any]
    run_id: Optional[str]
    created_at: AwareDatetime


@dataclass(frozen=True)
class Deny:
    """What a handler returns to refuse: the gate writes the denial row and answers `ToolError` DENY."""
    policy_id: str
    guardrail_id: Optional[str] = None             # None: the rule's guardrail, else G-POL-01
    message: str = "This action is not allowed."
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Call:
    """What a handler receives besides its validated input: `session.customer_id` is the only customer it may use."""
    tool: str
    session: SessionRow
    trace_id: str


Handler = Callable[[Call, BaseModel], Union[BaseModel, ToolError, Deny]]


class RateLimiter:
    """Sliding windows per session (LIMITS); only admitted calls count. One process holds the counts [assumption]."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._seen: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def admit(self, session_id: str, tool: str) -> Optional[str]:
        """None when the call fits every limit (and is counted); else the name of the limit it exceeds."""
        now, windows = self._clock(), []
        for name, tools, limit, seconds in LIMITS:
            if tools is not None and tool not in tools:
                continue
            seen = self._seen[(session_id, name)]
            while seen and seen[0] <= now - seconds:
                seen.popleft()
            if len(seen) >= limit:
                return name
            windows.append(seen)
        for seen in windows:
            seen.append(now)
        return None


def input_hash(arguments: Mapping[str, Any]) -> str:
    """G-OPS-02: the audit keeps a hash of the input, never the customer's text."""
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def log_audit(entry: dict[str, Any]) -> None:
    """The default audit sink: one JSON line per call on the `nickoftime.mcp.audit` logger [assumption]."""
    logging.getLogger("nickoftime.mcp.audit").info(json.dumps(entry, sort_keys=True))


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Gate:
    def __init__(self, sessions: Sessions, handlers: Mapping[str, Handler], *, denials: Callable[[Denial], None],
                 audit: Callable[[dict[str, Any]], None] = log_audit, limiter: Optional[RateLimiter] = None,
                 now: Callable[[], dt.datetime] = _utc_now) -> None:
        self._sessions, self._handlers, self._denials, self._audit = sessions, handlers, denials, audit
        self._limiter, self._now = limiter or RateLimiter(), now

    def call(self, tool: str, arguments: dict[str, Any], trace_id: str) -> Union[BaseModel, ToolError]:
        started, raw = time.perf_counter(), arguments.get("session_id")
        session_id = raw if isinstance(raw, str) and re.fullmatch(PATTERN["session"], raw) else None
        session: Optional[SessionRow] = None
        try:
            session = self._session(session_id)
            result = EXPIRED if session is None else self._guarded(tool, arguments, session, trace_id)
        except Exception:                                    # fail closed: no data, nothing reported as done
            log.exception("tool %s failed (trace %s)", tool, trace_id)
            result = UNAVAILABLE
        entry = {"at": self._now().isoformat(), "trace_id": trace_id, "actor": ACTOR, "tool": tool,
                 "session_id": session_id, "run_id": session.run_id if session else None,
                 "input_hash": input_hash(arguments), "outcome": result.code if isinstance(result, ToolError) else "ok",
                 "policy_id": result.policy_id if isinstance(result, ToolError) else None,
                 "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
        try:
            self._audit(entry)
        except Exception:                                    # no audit, no answer (G-OPS-02)
            log.exception("audit failed for tool %s (trace %s)", tool, trace_id)
            return UNAVAILABLE
        return result

    def _session(self, session_id: Optional[str]) -> Optional[SessionRow]:
        """AC-02: a missing, unverified, customer-less or expired session is no session."""
        row = self._sessions.get(session_id) if session_id else None
        if row is None or row.customer_id is None or row.verified_at is None or row.expires_at <= self._now():
            return None
        return row

    def _guarded(self, tool: str, arguments: dict[str, Any], session: SessionRow,
                 trace_id: str) -> Union[BaseModel, ToolError]:
        if tool in session.tool_faults:                      # AC-05, set only by the eval seed
            return UNAVAILABLE
        if (limit := self._limiter.admit(session.session_id, tool)) is not None:
            return self._deny(Deny(DEFAULT_DENY, "G-TOOL-01", "Too many requests in this session; try again later.",
                                   {"limit": limit}), session, trace_id, tool)
        model_in, model_out = CUSTOMER_TOOLS[tool]
        try:
            args = model_in.model_validate(arguments)        # extra="forbid": a customer_id argument is refused
        except ValidationError as error:
            fields = sorted({".".join(map(str, e["loc"]))[:64] for e in error.errors()})[:5]   # names, never values
            return self._deny(Deny(DEFAULT_DENY, "G-TOOL-01", f"Unexpected or invalid arguments: {', '.join(fields)}.",
                                   {"fields": fields}), session, trace_id, tool)
        handler = self._handlers.get(tool)
        if handler is None:                                  # [assumption] tasks 03b–03d register the handlers
            return UNAVAILABLE
        result = handler(Call(tool, session, trace_id), args)
        if isinstance(result, ToolError) and result.code == "DENY":
            result = Deny(result.policy_id or DEFAULT_DENY, message=result.message)
        if isinstance(result, Deny):
            return self._deny(result, session, trace_id, tool)
        if not isinstance(result, (model_out, ToolError)):
            raise TypeError(f"{tool} returned {type(result).__name__}, not {model_out.__name__}")
        return result

    def _deny(self, deny: Deny, session: SessionRow, trace_id: str, tool: str) -> ToolError:
        self._denials(Denial(denial_id=uuid.uuid4().hex, trace_id=trace_id, session_id=session.session_id,
                             policy_id=deny.policy_id,
                             guardrail_id=deny.guardrail_id or RULE_GUARDRAIL.get(deny.policy_id, "G-POL-01"),
                             detail={"tool": tool, **deny.detail},
                             run_id=session.run_id, created_at=self._now()))
        return ToolError(code="DENY", policy_id=deny.policy_id, message=deny.message)
