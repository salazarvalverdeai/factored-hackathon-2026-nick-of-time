"""The api on the store (spec 05): sessions, cases, analyst actions, notifications, channels and the agent proxy.

Same routes and response models as the spec 01 stub (`app.main`); state lives in a `Store` (Postgres in production,
`MemoryStore` in tests) instead of fixtures. What the constitution asks of this layer:
- `customer_id` comes only from the session row (#3); a `session_id`/`customer_id` in a body is never read.
- A case's status is its last event and no row is changed (#2, AC-02); the analyst's identity is the verified Cognito
  `sub` (AC-07) and an action runs through `policy.transition` before the store writes anything (AC-04).
- Customer views carry no score, zone, priority or policy ids (D-013); customer notifications never carry internals.
- Nothing here decides a dispute: it reads and records. A person closes (#6).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from collections import deque
from decimal import Decimal
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import Body, Cookie, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import ValidationError

from app import demo, persona
from app.auth import AuthError, CognitoVerifier
from app.catalog import Catalog, FixtureCatalog, catalog_from_env
from app.guard import install as install_guard
from app.main import (COOKIE, SESSION_TTL, AckOut, ApiError, CallIn, CallOut, ConsoleCaseOut, EmailIn,
                      EmailOut, EventOut, HealthOut, InfoIn, NotificationOut, PrefsIn, PrefsOut, ReevalIn, ReevalOut,
                      PersonaIn, PersonaOut, RecentTransactionOut, ScenarioOut, SessionIn, SessionOut, SettingsIn, SettingsOut,
                      SyntheticChargeIn, SyntheticChargeOut, TelegramOut,
                      ThreadOut, VerifyIn, VerifyOut, DemoCustomerOut, TIME_ZONES, _is_analyst_path, today)
from app.notify import ChannelFailed, HttpNotifier, Notifier, mask_chat, mask_email
from app.platform import HttpPlatform, Platform, PlatformError
from nick_of_time import CONTRACT_VERSION, ids, llm
from nick_of_time.contracts import (AnalystActionIn, AnalystActionOut, CaseSummary, CaseView, CustomerCaseSummary,
                                    CustomerCaseView, CustomerReceipt, CustomerTurn, ProductView, ProgressItem,
                                    Suggestion, TurnAction, TurnResult)
from nick_of_time.policy import queue
from nick_of_time.policy.calendars import CalendarNotCovered, add_business_days
from nick_of_time.policy.clock import deadline
from nick_of_time.policy.engine import Deny
from nick_of_time.policy.model import load_policies
from nick_of_time.llm.steps import over_day_cap
from nick_of_time.receipt import messages
from nick_of_time.store import CaseRecord, NewCase, Store, StoreError, is_demo_run

STATUS_LABEL = {"new": "Case opened", "verification": "Verifying the block", "review": "Under review by a person",
                "resolved": "Resolved", "closed": "Closed"}
EVENT_LABEL = {"case_opened": "Case opened", "card_blocked": "Card blocked", "block_verified": "Block verified",
               "assigned": "Assigned to a person", "customer_info_added": "Information added",
               "call_requested": "Call requested", "reevaluation_requested": "Re-evaluation requested",
               "related_case_opened": "Related case opened", "notification_sent": "Notification sent",
               "receipt_issued": "Receipt issued", "telegram_linked": "Telegram linked",
               "email_confirmed": "E-mail confirmed"}
NO_REASON_NEEDED = {"take", "approve_credit", "approve_block"}        # AnalystActionIn: reason required for the rest
TEMPLATE_EVENT = {"take": "in_review", "reopen_case": "in_review", "resolve": "resolved"}   # status change -> template
ZONE_ORDER = {"high": 0, "medium": 1, "human": 2}
TELEGRAM_TTL, EMAIL_TTL = dt.timedelta(minutes=15), dt.timedelta(hours=24)
# AC-22 (D-066): handoff reasons of an escalated turn, besides `escalate_unconfirmed_action`; the zone reasons are not
# here because `open_case` already writes their `review` (spec 03 §6, D-063)
ESCALATED_REASONS = frozenset({"tool_failure", "person_requested"})
DAILY_LLM_CAP_USD = 5.0    # [assumption] G-OPS-01 per day across every session; env DAILY_LLM_CAP_USD overrides it

log = logging.getLogger("nick_of_time.api")


class Denied(Exception):
    def __init__(self, verdict: Deny) -> None:
        self.verdict = verdict


def turn_of(raw: Any) -> TurnResult:
    """The graph's state as a TurnResult: LangGraph streams every channel (`messages`, …) and TurnResult forbids extras,
    so only its own fields are kept before validating (the customer projection is taken after)."""
    if not isinstance(raw, dict):
        raise ValueError("not a graph state")
    return TurnResult.model_validate({k: v for k, v in raw.items() if k in TurnResult.model_fields})


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _trace() -> str:
    return "tr-" + uuid.uuid4().hex[:16]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class LinkTokens:
    """Signed, stateless one-time tokens for the Telegram deep link and the e-mail confirmation (spec 13 AC-02/04).
    `hex(case|exp|extra)` + `x` + HMAC: only [0-9a-fx], so it fits Telegram's `start` parameter. Single use is enforced
    by the store (`once` for Telegram, the channel row's `linked` -> `confirmed` order for e-mail)."""

    def __init__(self, key: Optional[str]) -> None:
        self._key = key.encode() if key else None

    def make(self, kind: str, case_id: str, expires: dt.datetime, extra: str = "") -> str:
        if self._key is None:                       # not configured: no link can be issued, and none will validate
            raise ApiError(503, "UNAVAILABLE", "Channel links are not configured")
        body = f"{kind}|{case_id}|{int(expires.timestamp())}|{extra}".encode().hex()
        return f"{body}x{self._sign(body)}"

    def read(self, kind: str, token: str, now: dt.datetime) -> Optional[tuple[str, str]]:
        """(case_id, extra) of a valid, unexpired token of `kind`, else None."""
        body, sep, sig = token.partition("x")
        if self._key is None or not sep or not hmac.compare_digest(self._sign(body), sig):
            return None
        try:
            got_kind, case_id, exp, extra = bytes.fromhex(body).decode().split("|", 3)
            return (case_id, extra) if got_kind == kind and int(exp) > now.timestamp() else None
        except ValueError:
            return None

    def _sign(self, body: str) -> str:
        return hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()[:20]


def create_live_app(store: Store, *, catalog: Optional[Catalog] = None, verifier: Optional[CognitoVerifier] = None,
                    platform: Optional[Platform] = None, notifier: Optional[Notifier] = None,
                    now=_now, link_key: Optional[str] = None, persona_llm: Optional[llm.LLMClient] = None) -> FastAPI:
    catalog = catalog or FixtureCatalog()
    policies = load_policies()
    tokens = LinkTokens(link_key or os.getenv("LINK_SIGNING_KEY"))      # a dedicated key (SSM), never a shared secret
    app = FastAPI(title="Nick of Time api", docs_url="/api/docs", redoc_url=None, swagger_ui_oauth2_redirect_url=None,
                  openapi_url="/api/openapi.json")
    app.state.store, app.state.runs, app.state.now = store, deque(maxlen=200), now
    app.state.charges = {}                          # session id -> its last synthetic charge (AC-19)
    app.state.personas = persona.Budget()            # LLM openings per session and persona spend per day (AC-20)
    notifier = notifier or HttpNotifier.from_env()
    day_cap = float(os.getenv("DAILY_LLM_CAP_USD") or DAILY_LLM_CAP_USD)   # read once, at app creation
    install_guard(app, lambda: app.state.now())                     # per-IP and global hourly limits (AC-18)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, e: ApiError):
        policy = e.policy_id if _is_analyst_path(request.url.path) else None
        return JSONResponse({"code": e.code, "policy_id": policy, "message": e.message}, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, e: RequestValidationError):
        return JSONResponse({"code": "INVALID", "policy_id": None, "message": str(e.errors()[0]["msg"])}, 400)

    # ---------- sessions ----------
    def known_session(sid: Optional[str] = Cookie(None, alias=COOKIE)) -> dict:
        row = store.get_session(sid) if sid else None
        if row is None:
            raise ApiError(401, "UNAUTHENTICATED", "No session")
        c = catalog.customer(row.customer_id) if row.customer_id else None
        return {"session_id": row.session_id, "customer_id": row.customer_id, "mode": row.mode, "run_id": row.run_id,
                "arm": row.arm, "language": row.language, "verified_at": row.verified_at,
                "expires_at": row.expires_at, "country": c["country"] if c else None}

    def session_state(s: dict) -> Literal["verified", "expired", "unverified"]:
        if s["expires_at"] <= app.state.now():
            return "expired"
        return "verified" if s["verified_at"] and s["customer_id"] is not None else "unverified"

    def session(s: dict = Depends(known_session)) -> dict:
        state = session_state(s)
        if state == "expired":
            raise ApiError(401, "SESSION_EXPIRED", "Session expired: verify again")      # AC-01
        if state != "verified":
            raise ApiError(401, "UNAUTHENTICATED", "No verified session")
        return s

    def analyst(authorization: Optional[str] = Header(None)) -> str:
        """AC-07: the verified Cognito `sub`; no, malformed, forged or expired token -> 401."""
        if not authorization or not authorization.lower().startswith("bearer ") or not authorization[7:].strip():
            raise ApiError(401, "UNAUTHENTICATED", "Analyst token required")
        try:
            if verifier is None:
                raise AuthError("no verifier configured")
            return verifier.verify(authorization[7:].strip())
        except AuthError:
            raise ApiError(401, "UNAUTHENTICATED", "Invalid analyst token") from None

    def case_of(case_id: str, s: dict) -> CaseRecord:
        record = store.get_case(case_id, run_id=s["run_id"], customer_id=None)
        if record is None:
            raise ApiError(404, "NOT_FOUND", "Case not found")
        if record.customer_id != s["customer_id"]:               # the same row, another customer: DENY, audited
            store.add_denial(trace_id=_trace(), session_id=s["session_id"], actor="customer",
                             policy_id="POL-CROSS-CUSTOMER", guardrail_id="G-SES-02", run_id=s["run_id"],
                             detail={"case_id": case_id})
            raise ApiError(403, "DENY", "The case does not belong to this customer", "POL-CROSS-CUSTOMER")
        return record

    def own_case(case_id: str, s: dict = Depends(session)) -> CaseRecord:
        return case_of(case_id, s)

    # ---------- case projections (from the store; D-013) ----------
    def status_since(record: CaseRecord, events) -> dt.datetime:
        moves = [e.created_at for e in events if e.type == "status_changed"]
        return moves[-1] if moves else record.created_at

    def priority_of(record: CaseRecord, status: str, since: dt.datetime) -> queue.Sla:
        day = today(record.mode, record.country)
        try:
            return queue.sla(queue.QueueCase(status=status, status_since=since, country=record.country,
                                             product_type=record.product_type, opened_on=record.opened_on), today=day)
        except ValueError:                                       # a country the queue does not know: normal priority
            return queue.Sla(priority="normal", policies_version=policies.version)

    def summary(record: CaseRecord) -> CaseSummary:
        events, status = store.events(record.case_id), store.queue_status(record.case_id)
        sla = priority_of(record, status, status_since(record, events))
        return CaseSummary(case_id=record.case_id, country=record.country, queue_status=status,
                           credit_deadline=record.credit_deadline, ruling_deadline=record.ruling_deadline,
                           created_at=record.created_at, customer_id=record.customer_id, zone=record.zone,
                           sla_due_at=sla.sla_due_at, priority=sla.priority, tags=[])

    def last_payload(events, kind: str, key: str) -> Optional[dict]:
        found = [e.payload.get(key) for e in events if e.type == kind and isinstance(e.payload.get(key), dict)]
        return found[-1] if found else None

    def run_charges(customer_id: str, run_id: Optional[str], mode: str) -> list:
        """A live demo run's synthetic charges [simulated], newest first; none in replay or production (AC-19)."""
        if mode != "live" or not is_demo_run(run_id):
            return []
        return [demo.charge_view(r) for r in reversed(store.demo_transactions(customer_id, run_id=run_id))]

    def charge_of(record: CaseRecord) -> Optional[dict]:
        """The case's charge: gold's, else its demo run's synthetic charge (spec 03 AC-14)."""
        return catalog.transaction(record.transaction_id) or next(
            ({k: v for k, v in t.items() if k != "product_id"}
             for t in run_charges(record.customer_id, record.run_id, record.mode)
             if t["transaction_id"] == record.transaction_id), None)

    def view(record: CaseRecord) -> CaseView:
        txn = charge_of(record)
        if txn is None:
            raise ApiError(503, "UNAVAILABLE", "Transaction data unavailable")
        events, status = store.events(record.case_id), store.queue_status(record.case_id)
        since = status_since(record, events)
        sla = priority_of(record, status, since)
        last4 = next((p["last4"] for p in catalog.products(record.customer_id)
                      if p["product_id"] == record.product_id), None)
        receipt = None
        if (raw := last_payload(events, "receipt_issued", "receipt")) is not None:
            try:
                receipt = CustomerReceipt.model_validate(raw)
            except ValueError:
                receipt = None                                    # a receipt that fails its contract is never shown
        channels = [] if is_demo_run(record.run_id) else store.channels(record.customer_id)   # ADR 0026
        notes = [n for n in store.list_notifications(record.customer_id, run_id=record.run_id)
                 if n.case_id == record.case_id]
        deadline = min((d for d in (record.credit_deadline, record.ruling_deadline) if d), default=None)
        timeline = [{"event_id": e.event_id, "type": e.type, "created_at": e.created_at,
                     "label": STATUS_LABEL.get(e.payload.get("to", ""), "Status changed") if e.type == "status_changed"
                     else EVENT_LABEL.get(e.type, e.type)} for e in events if e.customer_visible]
        return CaseView(
            case_id=record.case_id, customer_id=record.customer_id, country=record.country, zone=record.zone,
            queue_status=status, credit_deadline=record.credit_deadline, ruling_deadline=record.ruling_deadline,
            created_at=record.created_at, sla_due_at=sla.sla_due_at, priority=sla.priority, tags=[],
            transaction=txn, product_last4=last4, status_label=STATUS_LABEL[status],
            taken_by_person=any(e.type in ("assigned", "analyst_action") for e in events),
            related_case_id=record.related_case_id, mode=record.mode, receipt=receipt, timeline=timeline,
            deadline_countdown_days=(deadline - today(record.mode, record.country)).days if deadline else None,
            deadline_source=record.deadline_source, deadline_source_url=record.deadline_source_url,
            deadline_verified_on=record.deadline_verified_on,
            channels={"telegram": any(c.channel == "telegram" and c.confirmed for c in channels),
                      "email": any(c.channel == "email" and c.confirmed for c in channels)},
            notifications=[{"notification_id": n.notification_id, "channel": n.channel,
                            "masked_address": n.masked_address, "delivery_status": n.delivery_status,
                            "created_at": n.created_at} for n in notes])

    # ---------- notifications ----------
    def log_notice(record: CaseRecord, event: str) -> Optional[tuple[str, str]]:
        """The in-app row (always, AC-01): (notification id, text). The outcome is a fixed label of `messages.yaml`
        `status.label`, never the analyst's free text (AC-08, never_send). No external send happens here, so it can run
        inside the action's transaction."""
        spec = policies.notifications["events"].get(event)
        if spec is None:
            return None
        customer = catalog.customer(record.customer_id) or {}
        label = messages()["status"]["label"]["resolved"][customer.get("language", "es")]
        text = spec["template"].format_map({"case_id": record.case_id, "outcome": label, "deadline": "—",
                                           "product_last4": "••••"})
        log = store.add_notification(record.case_id, event=event, channel="log", masked_address=None, text=text,
                                     trigger="auto", actor="system", trace_id=_trace())
        store.add_delivery(log.notification_id, "delivered")
        return log.notification_id, text

    def deliver(record: CaseRecord, event: str, text: str) -> None:
        """Telegram / e-mail on a confirmed channel the template lists (AC-01, AC-04), after the action committed. A
        failing channel leaves its row `failed` and changes nothing else (AC-07)."""
        spec = policies.notifications["events"][event]
        trace = _trace()
        if is_demo_run(record.run_id):        # a demo customer's channels belong to no visitor: in-app only (ADR 0026)
            return
        for ch in store.channels(record.customer_id):
            if ch.channel not in spec["channels"] or not ch.confirmed:
                continue
            masked = mask_chat(ch.address) if ch.channel == "telegram" else mask_email(ch.address)
            try:
                if ch.channel == "telegram":
                    provider = notifier.telegram(ch.address, text)
                else:
                    provider = notifier.email(ch.address, "Nick of Time", text)
                row = store.add_notification(record.case_id, event=event, channel=ch.channel, masked_address=masked,
                                             text=text, trigger="auto", actor="system", trace_id=trace,
                                             provider_message_id=provider)
                store.add_delivery(row.notification_id, "sent")
            except ChannelFailed as error:
                row = store.add_notification(record.case_id, event=event, channel=ch.channel, masked_address=masked,
                                             text=text, trigger="auto", actor="system", trace_id=trace)
                store.add_delivery(row.notification_id, "failed", {"error": str(error)})

    # ---------- public ----------
    @app.get("/api/health", response_model=HealthOut)
    def health():
        return {"status": "ok", "version": "live", "contract_version": CONTRACT_VERSION,
                "git_sha": os.getenv("GIT_SHA", "dev"), "gold_version": "v1", "policies_version": policies.version,
                "platform_revision": None,
                "models": {"graph": os.getenv("BEDROCK_MODEL_GRAPH"), "fast": os.getenv("BEDROCK_MODEL_FAST")},
                "prompt_hash": None, "classifier_version": None,
                "today": {m: today(m) for m in ("replay", "live")}}

    @app.get("/api/demo/customers", response_model=list[DemoCustomerOut])
    def demo_customers():
        """The picker names gold's first name, the one the agent greets with (spec 07 AC-07); built once per app."""
        if not hasattr(app.state, "demo_customers"):
            app.state.demo_customers = [
                {**c, "display_name": demo.picker_label(c["display_name"], catalog.first_name(c["customer_id"]))}
                for c in catalog.customers()]
        return app.state.demo_customers

    def demo_scenarios() -> list[dict]:
        """Built once per app (gold is read-only at runtime, ADR 0004); a customer gold does not serve is not listed."""
        if not hasattr(app.state, "scenarios"):
            customers = catalog.customers()
            built = demo.scenarios(customers, {c["customer_id"]: catalog.first_name(c["customer_id"]) for c in customers})
            app.state.scenarios = [s for s in built if s["customer_name"] is not None]
        return app.state.scenarios

    @app.get("/api/demo/scenarios", response_model=list[ScenarioOut])
    def scenarios(country: Optional[str] = None, language: Optional[Literal["es", "pt"]] = None):
        return [demo.public(s) for s in demo_scenarios()
                if country in (None, s["country"]) and language in (None, s["language"])]

    @app.post("/api/sessions", status_code=201, response_model=SessionOut)
    def create_session(body: SessionIn):
        try:
            name = demo.clean_name(body.display_name)
        except ValueError as error:
            raise ApiError(422, "INVALID", str(error)) from None
        if body.customer_id is not None:                         # the original picker, until the web uses scenarios
            if body.scenario or body.country:
                raise ApiError(422, "INVALID", "Send a scenario or a customer, not both")
            customer = catalog.customer(body.customer_id)
        else:                                                    # D-068: the customer is chosen here, never sent (#3)
            if body.language is None:
                raise ApiError(422, "INVALID", "language is required for a demo session")
            picked = demo.choose(demo_scenarios(), body.scenario, body.country, body.language)
            if picked is None:
                raise ApiError(404, "NOT_FOUND", "Unknown scenario")
            customer = catalog.customer(picked["customer_id"])
        if customer is None:
            raise ApiError(404, "NOT_FOUND", "Unknown customer")
        run_id = demo.new_run_id(app.state.now())               # every public session is isolated (ADR 0026)
        mode = body.mode or os.getenv("DEFAULT_SESSION_MODE") or "live"
        otp = os.getenv("OTP_FIXED") or f"{secrets.randbelow(10**6):06d}"            # mock OTP, shown on screen (ADR 0017)
        row = store.create_session(customer_id=customer["customer_id"], otp_hash=_sha(otp), run_id=run_id,
                                   expires_at=app.state.now() + SESSION_TTL, language=body.language or
                                   customer["language"], mode=mode, display_name=name,
                                   arm=os.getenv("DEFAULT_ARM") or None)   # demo sessions: S1 in prod; eval seeds set their own
        return {"session_id": row.session_id, "mode": mode, "today": today(mode, customer["country"]),
                "otp_demo": otp, "expires_at": row.expires_at}

    @app.post("/api/sessions/{session_id}/verify", response_model=VerifyOut)
    def verify(session_id: str, body: VerifyIn, response: Response):
        row = store.get_session(session_id)
        if row is None:
            raise ApiError(404, "NOT_FOUND", "Unknown session")
        if row.expires_at <= app.state.now():
            raise ApiError(410, "SESSION_EXPIRED", "Session expired")
        if not hmac.compare_digest(_sha(body.otp), row.otp_hash):
            raise ApiError(401, "UNAUTHENTICATED", "Wrong code")
        store.revise_session(session_id, verified_at=app.state.now())
        response.set_cookie(COOKIE, session_id, httponly=True, secure=True, samesite="lax",
                            max_age=int(SESSION_TTL.total_seconds()))
        return {"verified": True, "expires_at": row.expires_at}

    # ---------- agent proxy (AC-05) ----------
    def need_platform() -> Platform:
        if platform is None:
            raise ApiError(503, "UNAVAILABLE", "The agent is not available")
        return platform

    def own_thread(thread_id: str, s: dict = Depends(known_session)) -> dict:
        try:
            owner = need_platform().thread_session(thread_id)
        except PlatformError:
            raise ApiError(503, "UNAVAILABLE", "The agent is not available") from None
        if owner != s["session_id"]:                               # unknown or foreign: the same 404
            raise ApiError(404, "NOT_FOUND", "Thread not found")
        return s

    def supervised() -> bool:
        value = store.get_setting("supervised_mode")
        return bool(policies.approval.supervised_mode) if value is None else bool(value)

    def run_config(s: dict) -> dict:
        """The §6.4 configurable, built here and nowhere else; the client's body never contributes to it. The day's
        LLM spend is the sum of every `llm_calls` row since 00:00 UTC (any run: real money either way), which this api
        writes from each turn's usage; the graph compares it with the cap before calling (G-OPS-01, spec 04 §5)."""
        midnight = app.state.now().astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return {"session_id": s["session_id"], "session_state": session_state(s), "mode": s["mode"], "arm": s["arm"],
                "case_id": None, "supervised_mode": supervised(),
                "llm_day_spent_usd": float(store.llm_spend_since(midnight)), "llm_day_cap_usd": day_cap}

    def run_input(payload: dict, s: dict) -> dict:
        """The §6.4 input rebuilt from the body: only the customer's text and a valid chip press; the language is the
        session's (spec 01 AC-06), so nothing else a client sends (arm, mode, run_id, customer_id) reaches the graph."""
        raw = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        said = raw.get("messages") if isinstance(raw.get("messages"), list) else []
        texts = [m["content"] for m in said if isinstance(m, dict) and isinstance(m.get("content"), str)
                 and m.get("role", "user") in ("user", "human")]
        try:
            action = TurnAction.model_validate(raw["action"]).model_dump() if raw.get("action") else None
        except ValidationError:
            action = None
        return {"messages": [{"role": "user", "content": t} for t in texts],
                "language": s["language"] if s["language"] in ("es", "pt") else None, "action": action}

    def log_usage(turn: TurnResult, s: dict) -> None:
        """One `llm_calls` row per billed call of the turn (spec 04 AC-14, D-023), once per trace: a trace already
        written is skipped. A failed write never fails the turn."""
        try:
            if turn.usage and not store.list_llm_calls(run_id=s["run_id"], trace_id=turn.trace_id):
                for u in turn.usage:
                    store.add_llm_call(trace_id=turn.trace_id, provider=u.provider, model=u.model,
                                       tokens_in=u.tokens_in, tokens_out=u.tokens_out, latency_ms=u.latency_ms,
                                       cost_usd=u.cost_usd, run_id=s["run_id"])
        except StoreError as error:
            log.error("llm_calls write failed trace_id=%s error=%s", turn.trace_id, error)

    def record_handoff(turn: TurnResult, s: dict) -> None:
        """Spec 05 AC-21 (D-066, the writer is this api): a turn from Platform whose handoff card is for its own
        `case_id` appends one `handoff_emitted` `{handoff, handoff_reason?}` to that case, once per trace. The card is
        stored exactly as the graph returned it (constitution #5); the case must be the session's own customer's, in
        the session's run (#3, ADR 0026). AC-22: an escalated turn (an unconfirmed or failed action, a person request)
        whose case is still `new` also moves it to `review`; any other status is left alone. Best effort: a failed
        write is logged and never fails the turn."""
        card = turn.handoff
        if not card or not turn.case_id or card.get("case_id") != turn.case_id:
            return
        try:
            record = store.get_case(turn.case_id, run_id=s["run_id"], customer_id=s["customer_id"])
            if record is None:                           # not the session's case: nothing is written for it
                log.error("handoff for a case outside the session trace_id=%s", turn.trace_id)
                return
            reason = card.get("handoff_reason")
            if not any(e.type == "handoff_emitted" and e.trace_id == turn.trace_id for e in store.events(record.case_id)):
                store.append_event(record.case_id, "handoff_emitted", actor="agent", trace_id=turn.trace_id,
                                   payload={"handoff": card, **({"handoff_reason": reason} if reason else {})})
            escalated = turn.decision == "escalate_unconfirmed_action" or reason in ESCALATED_REASONS
            if escalated and store.queue_status(record.case_id) == "new":
                store.change_status(record.case_id, "review", on=today(record.mode, record.country), actor="agent",
                                    trace_id=turn.trace_id)
        except StoreError as error:
            log.error("handoff write failed trace_id=%s error=%s", turn.trace_id, error)

    def record_receipt(turn: TurnResult, raw: dict, s: dict) -> None:
        """Spec 05 AC-23: a turn from Platform whose receipt (built by the graph only once `get_case` verified the case,
        spec 04 §4.3) is for its own `case_id` appends one customer-visible `receipt_issued` `{receipt}` to the
        session's own case in the session's run, once per trace. The receipt is the graph's own dict, unchanged
        (constitution #5); the event notifies nobody (spec 13 notifies on status changes and verified actions). Best
        effort, as AC-21."""
        receipt = raw.get("receipt")
        if (turn.receipt is None or not isinstance(receipt, dict) or not turn.case_id
                or turn.receipt.case_id != turn.case_id):
            return
        try:
            record = store.get_case(turn.case_id, run_id=s["run_id"], customer_id=s["customer_id"])
            if record is None:                           # not the session's case: nothing is written for it
                log.error("receipt for a case outside the session trace_id=%s", turn.trace_id)
                return
            if not any(e.type == "receipt_issued" and e.trace_id == turn.trace_id for e in store.events(record.case_id)):
                store.append_event(record.case_id, "receipt_issued", actor="agent", trace_id=turn.trace_id,
                                   payload={"receipt": receipt})
        except StoreError as error:
            log.error("receipt write failed trace_id=%s error=%s", turn.trace_id, error)

    def log_turn(raw: dict, s: dict) -> TurnResult:
        """The api's bookkeeping of a turn from Platform (never from the client): its usage, its handoff card and its
        receipt. Returns the validated turn."""
        turn = turn_of(raw)
        log_usage(turn, s)
        record_handoff(turn, s)
        record_receipt(turn, raw, s)
        return turn

    def reconcile(thread_id: str, s: dict) -> None:
        """A stream that ended without a logged turn (client gone, Platform failure): log the usage, the handoff and the
        receipt of the thread's latest state if its trace is not written yet (the same dedupe), best effort."""
        try:
            raw = need_platform().state(thread_id)
            if raw is not None:
                log_turn(raw, s)
        except Exception as error:  # noqa: BLE001 — bookkeeping only, never the turn's failure
            log.error("usage reconcile failed thread=%s error=%s", thread_id, type(error).__name__)

    @app.post("/api/agent/threads", response_model=ThreadOut)
    def agent_thread(s: dict = Depends(known_session)):
        try:
            return {"thread_id": need_platform().create_thread(s["session_id"])}
        except PlatformError:
            raise ApiError(503, "UNAVAILABLE", "The agent is not available") from None

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    def progress_event(data: Any) -> Optional[str]:
        """Spec 04 AC-17: a step label from the run's custom stream leaves only as an in-progress ProgressItem; any
        other chunk (not a ProgressItem, or one claiming a result, constitution #4) is dropped, never failing the turn."""
        try:
            item = ProgressItem.model_validate(data)
        except ValueError:
            return None
        return _sse("progress", item.model_dump(mode="json")) if item.state == "in_progress" else None

    def unavailable_turn(s: dict, trace_id: str) -> str:
        """A normal `turn` for a Platform failure (customer text from messages.yaml, nothing internal)."""
        lang, msgs = s.get("language") or "es", messages()
        turn = CustomerTurn(
            reply=msgs["system"]["agent_unavailable"][lang], language=lang, mode=s["mode"], trace_id=trace_id,
            suggestions=[Suggestion(id="retry", label=msgs["system"]["retry_chip"][lang], kind="text"),
                         Suggestion(id="talk_to_person", label=msgs["suggest"]["talk_to_person"][lang], kind="action",
                                    action={"type": "request_call"})])
        return _sse("turn", turn.model_dump(mode="json"))

    @app.post("/api/agent/threads/{thread_id}/runs/stream")
    def agent_stream(thread_id: str, request: Request, payload: dict = Body(default={}),
                     s: dict = Depends(known_session)):
        trace_id = _trace()
        try:
            owner = need_platform().thread_session(thread_id)
        except (PlatformError, ApiError) as error:           # Platform down before the run: a turn, not a 503
            log.error("platform unavailable (thread check) trace_id=%s error=%s", trace_id, error)
            return StreamingResponse(iter([unavailable_turn(s, trace_id)]), media_type="text/event-stream")
        if owner != s["session_id"]:                               # unknown or foreign: the same 404
            raise ApiError(404, "NOT_FOUND", "Thread not found")
        config, payload = run_config(s), {"input": run_input(payload, s)}
        request.app.state.runs.append(config)
        upstream = need_platform()

        def events():
            turned = False
            try:
                for event, data in upstream.stream(thread_id, config, payload):
                    if event == "progress" and (item := progress_event(data)):
                        yield item
                    elif event == "turn":       # only the customer projection leaves the api (D-013)
                        turn = log_turn(data, s)
                        turned = True
                        yield _sse("turn", turn.for_customer().model_dump(mode="json"))
            except (PlatformError, ValueError) as error:
                log.error("platform stream failed trace_id=%s error=%s", trace_id, error)
                turned = None
            finally:
                if not turned:              # the run may have billed calls anyway: log them from the thread's state
                    reconcile(thread_id, s)
            if not turned:                  # failed, dropped mid-run or ended with no turn
                if turned is not None:
                    log.error("platform run ended without a turn trace_id=%s", trace_id)
                yield unavailable_turn(s, trace_id)

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/agent/threads/{thread_id}/state", response_model=CustomerTurn)
    def agent_state(thread_id: str, s: dict = Depends(own_thread)):
        if session_state(s) != "verified":
            session(s)
        try:
            raw = need_platform().state(thread_id)
            if raw is None:
                raise ApiError(404, "NOT_FOUND", "No turn yet")
            return turn_of(raw).for_customer()
        except (PlatformError, ValueError):
            raise ApiError(503, "UNAVAILABLE", "The agent is not available") from None

    # ---------- customer ----------
    @app.get("/api/notifications", response_model=list[NotificationOut])
    def my_notifications(s: dict = Depends(session)):
        return [{"notification_id": n.notification_id, "case_id": n.case_id, "event": n.event, "channel": n.channel,
                 "masked_address": n.masked_address, "text": n.text, "delivery_status": n.delivery_status,
                 "created_at": n.created_at}
                for n in store.list_notifications(s["customer_id"], run_id=s["run_id"])]

    @app.get("/api/sessions/{session_id}/recent-transactions", response_model=list[RecentTransactionOut])
    def recent_transactions(session_id: str, limit: int = Query(10, ge=1, le=20), s: dict = Depends(session)):
        """D-068: the session's own customer's latest card transactions up to its `today`, for the visitor to pick;
        only the session in the cookie, and no score or label (D-013, constitution #7)."""
        if session_id != s["session_id"]:
            raise ApiError(404, "NOT_FOUND", "Unknown session")
        return recent(s, limit)

    def recent(s: dict, limit: int) -> list[dict]:
        last4 = {p["product_id"]: p["last4"] for p in catalog.products(s["customer_id"])}
        rows = [*run_charges(s["customer_id"], s["run_id"], s["mode"]),        # dated today: the newest
                *catalog.recent_transactions(s["customer_id"], today(s["mode"], s["country"]), limit)][:limit]
        return [{**{k: v for k, v in t.items() if k != "product_id"}, "last4": last4.get(t["product_id"])}
                for t in rows]

    @app.post("/api/demo/persona", response_model=PersonaOut)
    def demo_persona(body: PersonaIn, s: dict = Depends(session)):
        """Demo type D (AC-20): a suggested opening in the session language about one of the session's recent charges,
        written by S1 (Haiku 4.5) in the character's voice, else the fixed template; billed calls go to llm_calls."""
        if not is_demo_run(s["run_id"]):
            raise ApiError(403, "DENY", "Personas exist only in a demo session")
        try:
            name = demo.clean_name(body.display_name) or store.get_session(s["session_id"]).display_name
        except ValueError as error:
            raise ApiError(422, "INVALID", str(error)) from None
        charge = next((t for t in recent(s, 20) if body.transaction_id in (None, t["transaction_id"])), None)
        if charge is None:
            raise ApiError(404, "NOT_FOUND", "No such transaction in this session")
        language, message = s["language"], None
        if not hasattr(app.state, "persona_llm"):
            app.state.persona_llm = persona_llm or persona.default_client()
        client, user = app.state.persona_llm, persona.payload(language, body.character, name, charge)
        cost, config, now = (persona.estimate(client, user) if client else None), run_config(s), app.state.now()
        # G-OPS-01 (AC-18): every run's llm_calls today plus this call's worst case under the daily cap, and the
        # persona's own share of it, so persona traffic never pushes agent turns to S0
        if (cost is not None and not over_day_cap({"configurable": config}, cost)
                and app.state.personas.admit(s["session_id"], now, cost, float(config["llm_day_cap_usd"]))):
            message, result = persona.generate(client, user)
            if message and not persona.acceptable(message, language, body.character, charge):
                message = None                                  # a suggestion outside the rules: the template
            if result is not None:
                spent = result.cost_usd or 0.0
                app.state.personas.spend(now, spent)
                store.add_llm_call(trace_id="persona-" + uuid.uuid4().hex[:16], provider=result.provider, model=result.model,
                                   tokens_in=result.tokens_in, tokens_out=result.tokens_out,
                                   latency_ms=result.latency_ms, cost_usd=Decimal(str(spent)), run_id=s["run_id"])
        return {"message": message or persona.template(language, name, charge), "language": language,
                "source": "llm" if message else "template", "character": body.character,
                "transaction_id": charge["transaction_id"], "synthetic": bool(charge.get("synthetic"))}

    @app.post("/api/sessions/{session_id}/synthetic-charge", status_code=201, response_model=SyntheticChargeOut)
    def synthetic_charge(session_id: str, body: SyntheticChargeIn, s: dict = Depends(session)):
        """Demo type C (AC-19): one synthetic charge [simulated] for a live demo session's own run, dated today in its
        currency, with the fixed synthetic score (D-027); never gold, replay or production, never a visitor's score."""
        if session_id != s["session_id"]:
            raise ApiError(404, "NOT_FOUND", "Unknown session")
        if s["mode"] != "live" or not is_demo_run(s["run_id"]):
            raise ApiError(403, "DENY", "Synthetic charges exist only in a live demo session")
        gate = policies.amount_gate.by_country.get(s["country"])
        if gate is None:                                       # PE, CL: no amount gate, no currency for a demo charge
            raise ApiError(422, "INVALID", "Test charges are not supported in this country's demo")
        try:
            merchant, amount = demo.clean_merchant(body.merchant), demo.charge_amount(body.amount, gate.high)
        except ValueError as error:
            raise ApiError(422, "INVALID", str(error)) from None
        # the card the run may still charge: its overlay status (a block this run made), else gold's
        cards = [c for c in catalog.products(s["customer_id"]) if (getattr(
            store.product_status(c["product_id"], run_id=s["run_id"]), "status", None) or c["status"]) == "Active"]
        if not cards:
            raise ApiError(409, "INVALID", "No active card in this demo session")
        now, card = app.state.now(), cards[0]
        with store.serialize(f"synthetic-charge:{s['run_id']}"):    # the count and the insert, one at a time
            last, mine = app.state.charges.get(s["session_id"]), store.demo_transactions(s["customer_id"],
                                                                                          run_id=s["run_id"])
            if (last and now - last < demo.CHARGE_EVERY) or len(mine) >= demo.CHARGES_PER_SESSION:
                raise ApiError(429, "DENY", "One synthetic charge per minute, three per session")
            row = store.add_demo_transaction(demo.synthetic_charge(
                customer_id=s["customer_id"], run_id=s["run_id"], card=card, amount=amount, currency=gate.currency,
                usd_rate=gate.usd_rate, merchant=merchant, generated_at=now,
                local_now=now.astimezone(ZoneInfo(TIME_ZONES.get(s["country"], "UTC"))),
                taken=lambda i: catalog.transaction(i) is not None or any(r.transaction_id == i for r in mine)))
            app.state.charges = {k: v for k, v in app.state.charges.items() if now - v < demo.CHARGE_EVERY}
            app.state.charges[s["session_id"]] = now
        return {**{k: v for k, v in demo.charge_view(row).items() if k != "product_id"}, "last4": card["last4"]}

    @app.get("/api/me/products", response_model=list[ProductView])
    def products(s: dict = Depends(session)):
        out = []
        for p in catalog.products(s["customer_id"]):
            override = store.product_status(p["product_id"], run_id=s["run_id"])
            out.append(ProductView(product_id=p["product_id"], type=p["type"], last4=p["last4"],
                                   status=override.status if override else p["status"],
                                   verification_id=override.verification_id if override else None,
                                   read_at=app.state.now()))
        return out

    @app.get("/api/me/cases", response_model=list[CustomerCaseSummary])
    def cases(s: dict = Depends(session)):
        out = []
        for r in store.list_cases(s["customer_id"], run_id=s["run_id"]):
            events = store.events(r.case_id)
            last4 = next((p["last4"] for p in catalog.products(r.customer_id) if p["product_id"] == r.product_id), None)
            out.append(CustomerCaseSummary(
                case_id=r.case_id, status_label=STATUS_LABEL[store.queue_status(r.case_id)],
                credit_deadline=r.credit_deadline, ruling_deadline=r.ruling_deadline, product_last4=last4,
                related_case_id=r.related_case_id, updated_at=events[-1].created_at if events else r.created_at))
        return out

    @app.put("/api/me/preferences", response_model=PrefsOut)
    def preferences(body: PrefsIn, s: dict = Depends(session)):
        row = store.revise_session(s["session_id"], language=body.language, display_currency=body.display_currency)
        return {"display_currency": row.display_currency, "language": row.language}      # `mode` is never writable

    @app.get("/api/cases/{case_id}", response_model=CustomerCaseView)
    def case(record: CaseRecord = Depends(own_case)):
        return view(record).for_customer()

    def write_event(record: CaseRecord, kind: str, payload: dict) -> str:
        try:
            event = store.append_event(record.case_id, kind, actor="customer", trace_id=_trace(),
                                       payload={"action_id": ids.new_id("action"), **payload})
        except StoreError as error:
            raise ApiError(409, "DENY", str(error)) from None
        return event.event_id

    @app.post("/api/cases/{case_id}/info", status_code=201, response_model=EventOut)
    def info(body: InfoIn, record: CaseRecord = Depends(own_case)):
        if not body.text.strip():
            raise ApiError(400, "INVALID", "Empty text")
        return {"event_id": write_event(record, "customer_info_added", {"text": body.text})}

    @app.post("/api/cases/{case_id}/call-request", status_code=201, response_model=CallOut)
    def call_request(record: CaseRecord = Depends(own_case), body: CallIn = Body(default=CallIn())):
        days = policies.contact.callback_within_business_days if policies.contact else None            # D-008: the tool computes it, never the LLM
        by = None
        if days:
            try:
                by = add_business_days(record.country, today(record.mode, record.country), days)
            except CalendarNotCovered:
                by = None                                                 # no date is promised
        return {"event_id": write_event(record, "call_requested", {"preferred_time": body.preferred_time,
                                                                    "expected_contact_by": by.isoformat() if by else None}),
                "expected_contact_by": by}

    @app.post("/api/cases/{case_id}/reevaluation", status_code=201, response_model=ReevalOut)
    def reevaluation(body: ReevalIn, record: CaseRecord = Depends(own_case)):
        status = store.queue_status(record.case_id)
        if status not in ("resolved", "closed"):
            raise ApiError(409, "DENY", "already_in_progress", "POL-REEVAL-WINDOW")
        day = today(record.mode, record.country)
        if status == "resolved":
            # [assumption] POL-REEVAL-WINDOW has no `window_days` in policies.yaml yet (lead), so only the status gates.
            try:       # AC-19: the case goes back to review, with the customer's reason as the event
                store.change_status(record.case_id, "review", on=day, actor="customer", trace_id=_trace(),
                                    reason=body.reason)
            except StoreError as error:
                raise ApiError(409, "DENY", str(error)) from None
            return {"event_id": write_event(record, "reevaluation_requested", {"reason": body.reason}),
                    "case_id": record.case_id}
        again = next((c for c in store.list_cases(record.customer_id, run_id=record.run_id)
                      if c.related_case_id == record.case_id and store.queue_status(c.case_id) != "closed"), None)
        if again is not None:                                     # a double click returns the case already opened
            return {"event_id": store.events(again.case_id)[0].event_id, "case_id": again.case_id}
        txn = charge_of(record)
        if txn is None:
            raise ApiError(503, "UNAVAILABLE", "Transaction data unavailable")
        # A closed case is not reopened by the customer: a related case is opened (§6.3) with the deadlines of the new
        # notice, derived by the clock and never copied from the old case (the countdown would run backwards).
        clock = deadline(record.country, record.product_type, day, charged_at=dt.date.fromisoformat(str(txn["date"])),
                         policies=policies)
        facts = record.model_dump(include=set(NewCase.model_fields)) | {
            "related_case_id": record.case_id, "trace_id": _trace(), "opened_on": day,
            "credit_deadline": clock.credit_deadline, "ruling_deadline": clock.ruling_deadline,
            "deadline_source": clock.deadline_source, "deadline_source_url": clock.source_url,
            "deadline_verified_on": clock.verified_on}
        try:
            fresh = store.create_case(NewCase(**facts), actor="customer", action_id=ids.new_id("action"))
        except StoreError as error:
            raise ApiError(409, "DENY", str(error)) from None
        return {"event_id": store.events(fresh.case_id)[0].event_id, "case_id": fresh.case_id}

    def no_demo_channel(record: CaseRecord, s: dict) -> None:
        """ADR 0026: a demo customer is shared by every visitor, so a demo run links no Telegram chat or inbox."""
        if is_demo_run(record.run_id):
            store.add_denial(trace_id=_trace(), session_id=s["session_id"], actor="customer",
                             policy_id="POL-DEFAULT-DENY", run_id=s["run_id"], detail={"case_id": record.case_id})
            raise ApiError(403, "DENY", "Telegram and e-mail are off in the demo; this page shows every update",
                           "POL-DEFAULT-DENY")

    @app.post("/api/cases/{case_id}/channels/telegram", status_code=201, response_model=TelegramOut)
    def telegram(record: CaseRecord = Depends(own_case), s: dict = Depends(session)):
        no_demo_channel(record, s)
        expires = app.state.now() + TELEGRAM_TTL
        bot = os.getenv("TELEGRAM_BOT_NAME", "nick_of_time_bot")
        return {"deep_link": f"https://t.me/{bot}?start={tokens.make('tg', record.case_id, expires)}",
                "expires_at": expires}

    @app.post("/api/cases/{case_id}/channels/email", status_code=202, response_model=EmailOut)
    def email(body: EmailIn, record: CaseRecord = Depends(own_case), s: dict = Depends(session)):
        no_demo_channel(record, s)
        address = body.email.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
            raise ApiError(400, "INVALID", "Not an e-mail address")
        # AC-04: only the address the customer typed, and it is used only once they confirm it.
        store.add_channel_event(record.case_id, "email", address, "linked", actor="customer", trace_id=_trace())
        link = (os.getenv("PUBLIC_URL", "").rstrip("/") + "/api/channels/email/confirm?token="
                + tokens.make("em", record.case_id, app.state.now() + EMAIL_TTL, address))
        try:
            notifier.email(address, "Confirma tu correo", f"Confirma tu correo para recibir novedades de tu caso: {link}")
            return {"confirmation_sent": True}
        except ChannelFailed:
            return {"confirmation_sent": False}

    @app.get("/api/channels/email/confirm", status_code=302)
    def email_confirm(token: str = Query(...)):
        got = tokens.read("em", token, app.state.now())
        if got is None:
            raise ApiError(410, "DENY", "The link expired")
        case_id, address = got
        try:
            store.add_channel_event(case_id, "email", address, "confirmed", actor="customer", trace_id=_trace())
        except StoreError:
            raise ApiError(410, "DENY", "The link expired") from None
        return RedirectResponse(f"/case/{case_id}?email=confirmed", status_code=302)

    def _secret_ok(expected: Optional[str], given: Optional[str]) -> bool:
        return bool(expected and given) and hmac.compare_digest(expected.encode(), given.encode())

    @app.post("/api/telegram/webhook", response_model=AckOut)
    def telegram_webhook(update: dict = Body(default={}),
                         x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
        # AC-03 (spec 13): a wrong secret or an expired token answers 401 and processes nothing.
        if not _secret_ok(os.getenv("TELEGRAM_WEBHOOK_SECRET"), x_telegram_bot_api_secret_token):
            raise ApiError(401, "UNAUTHENTICATED", "Bad webhook secret")
        message = update.get("message") or {}
        text, chat = str(message.get("text") or ""), (message.get("chat") or {}).get("id")
        if not text.startswith("/start ") or chat is None:
            return {"ok": True}                                  # anything but a link request is ignored
        token = text[7:].strip()
        got = tokens.read("tg", token, app.state.now())
        record = store.get_case(got[0], run_id=None, customer_id=None) if got else None
        if record is None:
            raise ApiError(401, "UNAUTHENTICATED", "Invalid or expired token")
        try:
            result = store.once(token, action="telegram_link", customer_id=None, run_id=None,
                                arguments={"chat_id": str(chat)},
                                write=lambda: {"channel_id": store.add_channel_event(
                                    record.case_id, "telegram", str(chat), "linked", actor="system",
                                    trace_id=_trace()).channel_id})
        except StoreError:
            raise ApiError(401, "UNAUTHENTICATED", "Invalid or expired token") from None
        if not result.replayed:
            try:
                notifier.telegram(str(chat), "✓ Telegram vinculado a tu caso.")
            except ChannelFailed:
                pass                                              # the link is stored either way
        return {"ok": True}

    @app.post("/api/resend/webhook", response_model=AckOut)
    def resend_webhook(event: dict = Body(default={}), svix_signature: Optional[str] = Header(None)):
        # [assumption] presence check only; svix signature verification arrives with the Resend account (spec 13 T4)
        if not os.getenv("RESEND_WEBHOOK_SECRET") or not svix_signature:
            raise ApiError(401, "UNAUTHENTICATED", "Bad webhook signature")
        return {"ok": True}

    # ---------- analyst console ----------
    @app.get("/api/console/cases", response_model=list[CaseSummary])
    def console_cases(status: Optional[str] = None, zone: Optional[str] = None, country: Optional[str] = None,
                      _: str = Depends(analyst)):
        rows = [summary(r) for r in store.list_all_cases(run_id=None, demo_runs=True)]
        rows = [r for r in rows if status in (None, r.queue_status) and zone in (None, r.zone)
                and country in (None, r.country)]
        far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)                  # §6.2: SLA due first, then zone
        return sorted(rows, key=lambda r: (r.sla_due_at or far, ZONE_ORDER[r.zone]))

    @app.get("/api/console/cases/{case_id}", response_model=ConsoleCaseOut)
    def console_case(case_id: str, _: str = Depends(analyst)):
        record = store.get_case(case_id, run_id=None, customer_id=None, demo_runs=True)
        if record is None:
            raise ApiError(404, "NOT_FOUND", "Case not found")
        events = store.events(case_id)
        # AC-21: the api writes the graph's handoff card as the `handoff` of a `handoff_emitted` event; {} until then
        return {"case": view(record), "handoff": last_payload(events, "handoff_emitted", "handoff") or {},
                "events": [{"event_id": e.event_id, "type": e.type, "actor": e.actor, "created_at": e.created_at}
                           for e in events]}

    @app.post("/api/cases/{case_id}/action", response_model=AnalystActionOut)
    def analyst_action(case_id: str, body: AnalystActionIn, sub: str = Depends(analyst)):
        record = store.get_case(case_id, run_id=None, customer_id=None, demo_runs=True)
        if record is None:
            raise ApiError(404, "NOT_FOUND", "Case not found")
        if body.case_id != case_id:
            raise ApiError(403, "DENY", "case_id in the body does not match the path")
        if body.action not in NO_REASON_NEEDED and not (body.reason or "").strip():
            raise ApiError(400, "INVALID", "A reason is required for this action")
        actor = f"analyst:{sub}"
        request = body.model_copy(update={"actor_id": sub})        # AC-07: the identity is the token's, not the body's

        sends: list[tuple[str, str]] = []

        def write() -> dict:
            verdict = queue.transition(store.queue_status(case_id), body.action, actor, policies=policies)
            if isinstance(verdict, Deny):                          # AC-04: nothing is written
                raise Denied(verdict)
            new = verdict.status if verdict.status != verdict.previous else None
            out = store.record_analyst_action(request, new_status=new, on=today(record.mode, record.country),
                                              trace_id=_trace())
            event = TEMPLATE_EVENT.get(body.action) if new else None
            note = log_notice(record, event) if event else None
            sends.append((event, note[1])) if note else None
            return out.model_copy(update={"notification_id": note[0] if note else None}).model_dump(mode="json")

        try:
            result = store.once(body.idempotency_key, action=f"analyst:{body.action}", customer_id=None, run_id=None,
                                arguments={"case_id": case_id, "action": body.action, "reason": body.reason,
                                           "actor": sub}, write=write)
        except Denied as denied:
            v = denied.verdict
            store.add_denial(trace_id=_trace(), session_id=None, actor=actor, policy_id=v.policy_id,
                             guardrail_id=v.guardrail_id, run_id=record.run_id,
                             detail={"case_id": case_id, "action": body.action})
            raise ApiError(409, "DENY", f"{body.action} is not allowed from the current status",
                           v.policy_id) from None
        except StoreError as error:
            raise ApiError(409, "DENY", str(error)) from None
        if not result.replayed:
            for event, text in sends:                              # after the transaction: a send never rolls it back
                deliver(record, event, text)
        return result.result

    def _settings() -> dict:
        return {"supervised_mode": supervised(), "score_provider": os.getenv("SCORE_PROVIDER", "dataset"),
                "policies_version": policies.version}

    @app.get("/api/console/settings", response_model=SettingsOut)
    def settings(_: str = Depends(analyst)):
        return _settings()

    @app.put("/api/console/settings", response_model=SettingsOut)
    def put_settings(body: SettingsIn, sub: str = Depends(analyst)):
        store.record_setting("supervised_mode", body.supervised_mode, actor=f"analyst:{sub}")   # AC-06: audited
        return _settings()

    return app


def from_env() -> FastAPI:
    """The production wiring: Postgres from DATABASE_URL, Cognito from COGNITO_*, Platform from LANGGRAPH_API_URL, gold
    from GOLD_PATH."""
    from nick_of_time.store.postgres import PostgresStore
    return create_live_app(PostgresStore(os.environ["DATABASE_URL"]), catalog=catalog_from_env(),
                           verifier=CognitoVerifier.from_env(),
                           platform=HttpPlatform.from_env())
