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
import os
import re
import secrets
import uuid
from collections import deque
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import Body, Cookie, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from app import demo
from app.auth import AuthError, CognitoVerifier
from app.catalog import Catalog, FixtureCatalog, catalog_from_env
from app.main import (COOKIE, SESSION_TTL, AckOut, ApiError, CallIn, CallOut, ConsoleCaseOut, EmailIn,
                      EmailOut, EventOut, HealthOut, InfoIn, NotificationOut, PrefsIn, PrefsOut, ReevalIn, ReevalOut,
                      RecentTransactionOut, ScenarioOut, SessionIn, SessionOut, SettingsIn, SettingsOut,
                      SyntheticChargeIn, SyntheticChargeOut, TelegramOut,
                      ThreadOut, VerifyIn, VerifyOut, DemoCustomerOut, TIME_ZONES, _is_analyst_path, today)
from app.notify import ChannelFailed, HttpNotifier, Notifier, mask_chat, mask_email
from app.platform import HttpPlatform, Platform, PlatformError
from nick_of_time import CONTRACT_VERSION, ids
from nick_of_time.contracts import (AnalystActionIn, AnalystActionOut, CaseSummary, CaseView, CustomerCaseSummary,
                                    CustomerCaseView, CustomerReceipt, CustomerTurn, ProductView, ProgressItem,
                                    TurnResult)
from nick_of_time.policy import queue
from nick_of_time.policy.calendars import CalendarNotCovered, add_business_days
from nick_of_time.policy.clock import deadline
from nick_of_time.policy.engine import Deny
from nick_of_time.policy.model import load_policies
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
                    now=_now, link_key: Optional[str] = None) -> FastAPI:
    catalog = catalog or FixtureCatalog()
    policies = load_policies()
    tokens = LinkTokens(link_key or os.getenv("LINK_SIGNING_KEY"))      # a dedicated key (SSM), never a shared secret
    app = FastAPI(title="Nick of Time api", docs_url="/api/docs", redoc_url=None, swagger_ui_oauth2_redirect_url=None,
                  openapi_url="/api/openapi.json")
    app.state.store, app.state.runs, app.state.now = store, deque(maxlen=200), now
    app.state.charges = {}                          # session id -> its last synthetic charge (AC-19)
    notifier = notifier or HttpNotifier.from_env()

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
        return catalog.customers()

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
        """The §6.4 configurable, built here and nowhere else; the client's body never contributes to it."""
        return {"session_id": s["session_id"], "session_state": session_state(s), "mode": s["mode"], "arm": s["arm"],
                "case_id": None, "supervised_mode": supervised()}

    @app.post("/api/agent/threads", response_model=ThreadOut)
    def agent_thread(s: dict = Depends(known_session)):
        try:
            return {"thread_id": need_platform().create_thread(s["session_id"])}
        except PlatformError:
            raise ApiError(503, "UNAVAILABLE", "The agent is not available") from None

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    @app.post("/api/agent/threads/{thread_id}/runs/stream")
    def agent_stream(thread_id: str, request: Request, payload: dict = Body(default={}),
                     s: dict = Depends(own_thread)):
        config = run_config(s)
        request.app.state.runs.append(config)
        upstream = need_platform()

        def events():
            try:
                for event, data in upstream.stream(thread_id, config, payload):
                    if event == "progress":
                        yield _sse("progress", ProgressItem.model_validate(data).model_dump(mode="json"))
                    elif event == "turn":       # only the customer projection leaves the api (D-013)
                        yield _sse("turn", turn_of(data).for_customer().model_dump(mode="json"))
            except (PlatformError, ValueError):
                yield _sse("error", {"code": "UNAVAILABLE", "message": "The agent is not available"})

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
        last4 = {p["product_id"]: p["last4"] for p in catalog.products(s["customer_id"])}
        rows = [*run_charges(s["customer_id"], s["run_id"], s["mode"]),        # dated today: the newest
                *catalog.recent_transactions(s["customer_id"], today(s["mode"], s["country"]), limit)][:limit]
        return [{**{k: v for k, v in t.items() if k != "product_id"}, "last4": last4.get(t["product_id"])}
                for t in rows]

    @app.post("/api/sessions/{session_id}/synthetic-charge", status_code=201, response_model=SyntheticChargeOut)
    def synthetic_charge(session_id: str, body: SyntheticChargeIn, s: dict = Depends(session)):
        """Demo type C (AC-19): one synthetic charge [simulated] for a live demo session's own run, dated today in its
        currency, with the fixed synthetic score (D-027); never gold, replay or production, never a visitor's score."""
        if session_id != s["session_id"]:
            raise ApiError(404, "NOT_FOUND", "Unknown session")
        if s["mode"] != "live" or not is_demo_run(s["run_id"]):
            raise ApiError(403, "DENY", "Synthetic charges exist only in a live demo session")
        try:
            merchant = demo.clean_merchant(body.merchant)
        except ValueError as error:
            raise ApiError(422, "INVALID", str(error)) from None
        gate, cards = policies.amount_gate.by_country.get(s["country"]), catalog.products(s["customer_id"])
        if gate is None or not cards:
            raise ApiError(503, "UNAVAILABLE", "No card or currency for this customer")
        if body.amount > demo.CHARGE_MAX_USD * gate.usd_rate:
            raise ApiError(422, "INVALID", f"amount is above {demo.CHARGE_MAX_USD * gate.usd_rate:,.0f} {gate.currency}")
        now, last = app.state.now(), app.state.charges.get(s["session_id"])
        mine = store.demo_transactions(s["customer_id"], run_id=s["run_id"])
        if (last and now - last < demo.CHARGE_EVERY) or len(mine) >= demo.CHARGES_PER_SESSION:
            raise ApiError(429, "DENY", "One synthetic charge per minute, three per session")
        card = next((c for c in cards if c["status"] == "Active"), cards[0])
        row = store.add_demo_transaction(demo.synthetic_charge(
            customer_id=s["customer_id"], run_id=s["run_id"], card=card, amount=body.amount, currency=gate.currency,
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
        # [assumption] the graph writes its handoff card as the `handoff` of its `handoff_emitted` event; {} until then
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
