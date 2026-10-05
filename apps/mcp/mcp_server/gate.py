"""The gate every customer tool call passes (spec 03 §6 common rules, T1): session, fault, rate limit, schema, audit.

Order: session (AC-02), injected faults (AC-05), per-session rate limits, strict input model, then the handler, whose
only source of `customer_id` is the session row (constitution #3). Every outcome is a `ToolError` or the tool's
`<Name>Out`, never an exception; every call is audited (G-OPS-02) and every DENY is a `policy_denials` row (AC-12).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import sys
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from contracts.tools import CUSTOMER_TOOLS, VERIFIED_WITH, ToolError
from nick_of_time.ids import PATTERN

ACTOR = "agent"                 # every MCP call is made by the agent on the customer's behalf (G-OPS-02)
# [assumption] spec 03 §6 (G-TOOL-01, G-OPS-01): (name, tools it counts, max calls, window in seconds) per session.
# A write is any tool of VERIFIED_WITH (W and N). D-041 (lead): the notification limit is per session, as AC-21 says.
LIMITS: tuple[tuple[str, Optional[frozenset[str]], int, float], ...] = (
    ("calls_per_minute", None, 30, 60.0),
    ("writes_per_minute", frozenset(VERIFIED_WITH), 5, 60.0),
    ("notifications_per_hour", frozenset({"send_case_summary"}), 3, 3600.0))
# D-040 (lead): a rate-limit or schema DENY cites the default-deny rule (spec 02 §4.1) and G-TOOL-01.
DEFAULT_DENY = "POL-DEFAULT-DENY"
FIELD_NAME = re.compile(r"[a-z_][a-z0-9_]{0,31}")   # a refused key outside it is recorded as <unexpected>
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
    display_name: Optional[str] = None               # a demo visitor's typed name (ADR 0026)


class Sessions(Protocol):
    def get(self, session_id: str) -> Optional[SessionRow]: ...   # a dict of rows serves tests


class DenialRow(BaseModel):
    """A `policy_denials` row (spec 01 §6.5): actor `agent`, a guardrail id always (G-POL-01 when none is given).
    [assumption] It moves to the store's `policy_denials` accessor (task 01g part 2) once that merges."""
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
    """A refusal: written as a `policy_denials` row, answered as `ToolError` DENY."""
    policy_id: str
    guardrail_id: str
    message: str
    detail: dict[str, Any]


@dataclass(frozen=True)
class Call:
    """What a handler receives besides its validated input: `session.customer_id` is the only customer it may use."""
    tool: str
    session: SessionRow
    trace_id: str


Handler = Callable[[Call, BaseModel], Union[BaseModel, ToolError]]


class RateLimiter:
    """Sliding windows per session (LIMITS); only admitted calls count, and an emptied window is dropped. One process
    holds the counts [assumption]; a lock makes check-and-count atomic when the gate runs in worker threads."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock, self._lock = clock, threading.Lock()
        self._seen: dict[tuple[str, str], deque[float]] = {}

    def admit(self, session_id: str, tool: str) -> Optional[str]:
        """None when the call fits every limit (and is counted); else the limit it exceeds."""
        with self._lock:
            now, windows = self._clock(), []
            for name, tools, limit, seconds in LIMITS:
                if tools is not None and tool not in tools:
                    continue
                key = (session_id, name)
                seen = self._seen.pop(key, deque())
                while seen and seen[0] <= now - seconds:
                    seen.popleft()
                if seen:
                    self._seen[key] = seen
                if len(seen) >= limit:
                    return name
                windows.append((key, seen))
            for key, seen in windows:
                seen.append(now)
                self._seen[key] = seen
            return None


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def input_hash(arguments: Mapping[str, Any]) -> str:
    """G-OPS-02: the audit keeps a hash of the input, never the customer's text."""
    return _sha256(json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str))


def stdout_audit(entry: dict[str, Any]) -> None:
    """The default audit sink (D-040): one JSON line per call on stdout, flushed, so a failed write raises and the
    call answers UNAVAILABLE (no audit, no answer)."""
    sys.stdout.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _failed(what: str, tool: str, error: Exception, trace_id: str) -> None:
    """Log the exception type only: its message may carry input values (AC-11); the traceback only at DEBUG."""
    log.error("%s %s failed: %s (trace %s)", what, tool, type(error).__name__, trace_id,
              exc_info=log.isEnabledFor(logging.DEBUG))


class Gate:
    def __init__(self, sessions: Sessions, handlers: Mapping[str, Handler], *, denials: Callable[[DenialRow], None],
                 audit: Callable[[dict[str, Any]], None] = stdout_audit, limiter: Optional[RateLimiter] = None,
                 now: Callable[[], dt.datetime] = _utc_now, guardrails: Optional[Mapping[str, str]] = None) -> None:
        """`guardrails`: rule id → its guardrail (policies.yaml `rules.<id>.guardrail`), cited by a handler's DENY or
        probe denial (AC-12); a rule without one cites G-POL-01."""
        self._sessions, self._handlers, self._denials, self._audit = sessions, handlers, denials, audit
        self._limiter, self._now, self._guardrails = limiter or RateLimiter(), now, dict(guardrails or {})

    def call(self, tool: str, arguments: dict[str, Any], trace_id: str) -> Union[BaseModel, ToolError]:
        started, raw = time.perf_counter(), arguments.get("session_id")
        session_id = raw if isinstance(raw, str) and re.fullmatch(PATTERN["session"], raw) else None
        session: Optional[SessionRow] = None
        try:
            session = self._session(session_id)
            result = EXPIRED if session is None else self._guarded(tool, arguments, session, trace_id)
        except Exception as error:                           # fail closed: no data, nothing reported as done
            _failed("tool", tool, error, trace_id)
            result = UNAVAILABLE
        # [assumption] the session id is a 15-minute bearer handle with the API key, so the audit keeps its hash
        entry = {"at": self._now().isoformat(), "trace_id": trace_id, "actor": ACTOR, "tool": tool,
                 "session_hash": _sha256(session_id) if session_id else None,
                 "run_id": session.run_id if session else None, "input_hash": input_hash(arguments),
                 "outcome": result.code if isinstance(result, ToolError) else "ok",
                 "policy_id": result.policy_id if isinstance(result, ToolError) else None,
                 "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
        try:
            self._audit(entry)
        except Exception as error:                           # no audit, no answer (G-OPS-02)
            _failed("audit of", tool, error, trace_id)
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
            fields = sorted({".".join(_name(part, model_in) for part in e["loc"]) for e in error.errors()})[:5]
            return self._deny(Deny(DEFAULT_DENY, "G-TOOL-01", f"Unexpected or invalid arguments: {', '.join(fields)}.",
                                   {"fields": fields}), session, trace_id, tool)
        handler = self._handlers.get(tool)
        if handler is None:                                  # [assumption] tasks 03b–03d register the handlers
            return UNAVAILABLE
        result = handler(Call(tool, session, trace_id), args)
        if isinstance(result, ToolError) and result.code == "DENY":     # the rule's guardrail, else G-POL-01 (T4)
            policy_id = result.policy_id or DEFAULT_DENY
            return self._deny(Deny(policy_id, self._guardrails.get(policy_id, "G-POL-01"), result.message, {}), session,
                              trace_id, tool)
        if isinstance(result, ToolError) and result.code == "NOT_FOUND" and result.policy_id:
            # a refusal answered as not found (a cross-customer probe, D-052): logged as a denial with its
            # rule's guardrail, its policy id never shown; best-effort, since UNAVAILABLE here would be an oracle
            try:
                self._deny(Deny(result.policy_id, self._guardrails.get(result.policy_id, "G-POL-01"), result.message,
                                {}), session, trace_id, tool)
            except Exception as error:
                _failed("denial of", tool, error, trace_id)
            return result.model_copy(update={"policy_id": None})
        if not isinstance(result, (model_out, ToolError)):
            raise TypeError(f"{tool} returned {type(result).__name__}, not {model_out.__name__}")
        return result

    def _deny(self, deny: Deny, session: SessionRow, trace_id: str, tool: str) -> ToolError:
        self._denials(DenialRow(denial_id=uuid.uuid4().hex, trace_id=trace_id, session_id=session.session_id,
                                policy_id=deny.policy_id, guardrail_id=deny.guardrail_id,
                                detail={"tool": tool, **deny.detail}, run_id=session.run_id, created_at=self._now()))
        return ToolError(code="DENY", policy_id=deny.policy_id, message=deny.message)


def _name(part: Any, model_in: type[BaseModel]) -> str:
    """A refused argument's name as the error and the denial row show it: a model field or a plain lower-case name;
    any other key (a card number, an instruction) is input too, so it shows as <unexpected>."""
    if isinstance(part, int) or part in model_in.model_fields or FIELD_NAME.fullmatch(str(part)):
        return str(part)
    return "<unexpected>"
