"""api stub (spec 01 T3, AC-02, AC-06, AC-07): every route of §6.2 and §6.8 answers with fixtures validated by the
contract models in `nick_of_time.contracts`. No store, no agent: spec 05 replaces the fixtures route by route.

Customer routes serve customer projections only (D-013). The session lives server-side; the `not_session` cookie
carries only its id, and a `session_id` or `customer_id` in any request body is ignored (AC-06). Every route declares a
`response_model` with `extra="forbid"`, so `/api/docs` is the contract and a stray field fails loudly.
"""

import datetime as dt
import hmac
import json
import os
import uuid
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import Body, Cookie, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app import fixtures as fx
from nick_of_time import CONTRACT_VERSION, ids
from nick_of_time.contracts import (AnalystActionIn, AnalystActionOut, CaseSummary, CaseView, CustomerCaseSummary,
                                    CustomerCaseView, CustomerTurn, FinalState, Mode, ProductView, ProgressItem,
                                    Suggestion)

COOKIE = "not_session"
SESSION_TTL = dt.timedelta(minutes=fx.SESSION_TTL_MINUTES)       # policies.yaml identity.session_ttl_minutes
TIME_ZONES = {"MX": "America/Mexico_City", "AR": "America/Argentina/Buenos_Aires", "BR": "America/Sao_Paulo",
              "CO": "America/Bogota"}

Code = Literal["DENY", "NOT_FOUND", "SESSION_EXPIRED", "UNAUTHENTICATED", "UNAVAILABLE", "INVALID"]


class ApiError(Exception):
    def __init__(self, status: int, code: Code, message: str, policy_id: Optional[str] = None):
        self.status, self.code, self.message, self.policy_id = status, code, message, policy_id


def today(mode: str, country: Optional[str] = None) -> dt.date:
    """clock.today(mode, country) for the stub (ADR 0020): replay is DEMO_TODAY, live is the date in the customer's
    country time zone. [assumption] a live call without a country falls back to UTC."""
    if mode == "replay":
        return dt.date.fromisoformat(os.getenv("DEMO_TODAY") or fx.REPLAY_TODAY.isoformat())
    return dt.datetime.now(ZoneInfo(TIME_ZONES.get(country or "", "UTC"))).date()


# ---------- response models (extra="forbid"): the shapes of spec 01 §6.2 and §6.8 ----------
class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorOut(Out):
    code: Code
    policy_id: Optional[str]
    message: str


class HealthOut(Out):
    status: str
    version: str
    contract_version: str
    git_sha: str
    gold_version: str
    policies_version: int
    platform_revision: Optional[str]
    models: dict[str, Optional[str]]
    prompt_hash: Optional[str]
    classifier_version: Optional[str]
    today: dict[str, dt.date]


class DemoCustomerOut(Out):
    customer_id: str
    display_name: str
    country: str
    segment: str
    scenario: str
    language: Literal["es", "pt"]


class SessionOut(Out):
    session_id: str
    mode: Mode
    today: dt.date
    otp_demo: str
    expires_at: dt.datetime


class VerifyOut(Out):
    verified: bool
    expires_at: dt.datetime


class ThreadOut(Out):
    thread_id: str


class NotificationOut(Out):
    notification_id: str
    case_id: str
    event: str
    channel: Literal["log", "telegram", "email"]
    masked_address: Optional[str]
    text: str
    delivery_status: Literal["queued", "sent", "delivered", "bounced", "failed"]
    created_at: dt.datetime


class PrefsOut(Out):
    display_currency: Optional[str]
    language: Optional[Literal["es", "pt"]]


class EventOut(Out):
    event_id: str


class CallOut(EventOut):
    expected_contact_by: Optional[dt.date]          # D-008


class ReevalOut(EventOut):
    case_id: str


class TelegramOut(Out):
    deep_link: str
    expires_at: dt.datetime


class EmailOut(Out):
    confirmation_sent: bool


class AckOut(Out):
    ok: bool


class CaseEventOut(Out):
    event_id: str
    type: str
    actor: str
    created_at: dt.datetime


class ConsoleCaseOut(Out):
    case: CaseView
    handoff: dict[str, Any]                         # checked against handoff.schema.json in the tests
    events: list[CaseEventOut]


class SettingsOut(Out):
    supervised_mode: bool
    score_provider: str
    policies_version: int


class ResetOut(Out):
    demo_transactions: int
    sample_cases: int


class SeedOut(Out):
    session_id: str
    thread_id: str
    run_id: str
    arm: str
    mode: Literal["replay"]


class SessionIn(BaseModel):
    customer_id: Optional[str] = None                # the original picker; a demo session names a scenario instead
    mode: Optional[Mode] = None                      # default: DEFAULT_SESSION_MODE, else live
    # demo session (D-068, ADR 0026): the customer behind the scenario is chosen server-side, never sent
    display_name: Optional[str] = None               # checked by app.demo.clean_name (422 when not a plain name)
    language: Optional[Literal["es", "pt"]] = None   # required for a demo session
    country: Optional[Literal["MX", "CO", "AR"]] = None
    scenario: Optional[str] = None                   # a scenario_id of GET /api/demo/scenarios, or "auto"


class ScenarioOut(Out):
    scenario_id: str
    title: str
    country: str
    language: Literal["es", "pt"]
    segment: str
    customer_name: Optional[str]                     # gold's synthetic first name, the default greeting name
    cases: list[str]                                 # spec 09 dev/sample case ids for this customer, never held-out
    tags: list[str]


class RecentTransactionOut(Out):
    transaction_id: str
    date: dt.date
    amount: float
    currency: str
    merchant: Optional[str]                          # null in some gold rows: the chip then names no merchant
    last4: Optional[str]                             # the card's last 4, for a customer with several cards
    synthetic: bool = False                          # a live demo run's synthetic charge [simulated] (AC-19)


class SyntheticChargeIn(BaseModel):
    amount: float = Field(gt=0)                      # in the currency of the customer's country
    merchant: str                                    # checked by app.demo.clean_merchant (422 when not a plain name)


class SyntheticChargeOut(Out):
    transaction_id: str
    date: dt.date
    amount: float
    currency: str
    merchant: str
    last4: Optional[str]
    synthetic: Literal[True] = True
    label: Literal["[simulated]"] = "[simulated]"


class VerifyIn(BaseModel):
    otp: str


class PrefsIn(BaseModel):
    display_currency: Optional[str] = None
    language: Optional[Literal["es", "pt"]] = None


class InfoIn(BaseModel):
    text: str


class CallIn(BaseModel):
    preferred_time: Optional[str] = None


class ReevalIn(BaseModel):
    reason: str


class EmailIn(BaseModel):
    email: str


class SettingsIn(BaseModel):
    supervised_mode: bool


class SeedIn(BaseModel):
    initial_state: dict[str, Any]
    run_id: str
    arm: str


def _is_analyst_path(path: str) -> bool:
    return path.startswith("/api/console") or path.endswith("/action")


def create_app(eval_mode: Optional[bool] = None, store: Any = None, **deps: Any) -> FastAPI:
    """The fixture stub of spec 01, or, with a `store` (or DATABASE_URL set), the store-backed api of spec 05
    (`app.live`); `deps` are its optional seams (catalog, verifier, platform, notifier, now, link_key)."""
    if store is not None:
        from app.live import create_live_app
        return create_live_app(store, **deps)
    if os.getenv("DATABASE_URL"):
        from app.live import from_env
        return from_env()
    eval_on = os.getenv("EVAL_MODE", "").lower() == "true" if eval_mode is None else eval_mode
    app = FastAPI(title="Nick of Time api (stub)", docs_url="/api/docs", redoc_url=None, swagger_ui_oauth2_redirect_url=None, openapi_url="/api/openapi.json")
    app.state.sessions = {}            # session_id -> dict(customer_id, country, mode, verified, expires_at, arm, prefs)
    app.state.threads = {}             # thread_id -> session_id (a thread belongs to the session that created it)
    app.state.runs = []                # configurable of every proxied agent run (AC-06 evidence)
    app.state.policy_denials = []      # policy ids stay server-side; customer error bodies carry null (D-013)
    app.state.supervised = True

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, e: ApiError):
        analyst = _is_analyst_path(request.url.path)
        if e.policy_id and not analyst:
            app.state.policy_denials.append({"policy_id": e.policy_id, "path": request.url.path})
        return JSONResponse({"code": e.code, "policy_id": e.policy_id if analyst else None, "message": e.message},
                            status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, e: RequestValidationError):
        return JSONResponse({"code": "INVALID", "policy_id": None, "message": str(e.errors()[0]["msg"])}, 400)

    def now() -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)

    def known_session(request: Request, sid: Optional[str] = Cookie(None, alias=COOKIE)) -> dict:
        s = request.app.state.sessions.get(sid) if sid else None
        if s is None:
            raise ApiError(401, "UNAUTHENTICATED", "No session")
        return {**s, "session_id": sid, "_row": s}

    def session_state(s: dict) -> Literal["verified", "expired", "unverified"]:
        if s["expires_at"] <= now():
            return "expired"
        return "verified" if s["verified"] and s["customer_id"] is not None else "unverified"

    def session(s: dict = Depends(known_session)) -> dict:
        """Data routes: only a verified, unexpired session passes (401 SESSION_EXPIRED / UNAUTHENTICATED)."""
        state = session_state(s)
        if state == "expired":
            raise ApiError(401, "SESSION_EXPIRED", "Session expired: verify again")
        if state != "verified":
            raise ApiError(401, "UNAUTHENTICATED", "No verified session")
        return s

    def analyst(authorization: Optional[str] = Header(None)) -> str:
        # [assumption] stub accepts any non-empty bearer token; the Cognito JWT check lands with spec 17 / 05.
        if not authorization or not authorization.lower().startswith("bearer ") or not authorization[7:].strip():
            raise ApiError(401, "UNAUTHENTICATED", "Analyst token required")
        return "analyst-stub"

    def own_case(case_id: str, s: dict = Depends(session)) -> dict:
        owner = fx.CASE_OWNERS.get(case_id)
        if owner is None:
            raise ApiError(404, "NOT_FOUND", "Case not found")
        if owner != s["customer_id"]:
            raise ApiError(403, "DENY", "The case does not belong to this customer", "POL-CROSS-CUSTOMER")
        return s

    def own_thread(thread_id: str, s: dict = Depends(known_session)) -> dict:
        if app.state.threads.get(thread_id) != s["session_id"]:        # unknown or foreign: the same 404
            raise ApiError(404, "NOT_FOUND", "Thread not found")
        return s

    def run_config(s: dict) -> dict:
        """The §6.4 configurable, built here and nowhere else; the client's body never contributes to it."""
        return {"session_id": s["session_id"], "session_state": session_state(s), "mode": s["mode"],
                "arm": s.get("arm"), "case_id": None}

    def new_thread(sid: str) -> str:
        tid = str(uuid.uuid4())
        app.state.threads[tid] = sid
        return tid

    # ---------- public ----------
    @app.get("/api/health", response_model=HealthOut)
    def health():
        return {"status": "ok", "version": "stub", "contract_version": CONTRACT_VERSION,
                "git_sha": os.getenv("GIT_SHA", "stub"), "gold_version": "v1",
                "policies_version": fx.POLICIES_VERSION, "platform_revision": None,
                "models": {"graph": os.getenv("BEDROCK_MODEL_GRAPH"), "fast": os.getenv("BEDROCK_MODEL_FAST")},
                "prompt_hash": None, "classifier_version": None,
                # [assumption] one `live` value: the UTC date; sessions use their customer's country time zone
                "today": {m: today(m) for m in ("replay", "live")}}

    @app.get("/api/demo/customers", response_model=list[DemoCustomerOut])
    def demo_customers():
        return fx.CUSTOMERS

    @app.post("/api/sessions", status_code=201, response_model=SessionOut)
    def create_session(body: SessionIn, request: Request):
        customer = next((c for c in fx.CUSTOMERS if c["customer_id"] == body.customer_id), None)
        if customer is None:
            raise ApiError(404, "NOT_FOUND", "Unknown customer")
        mode = body.mode or os.getenv("DEFAULT_SESSION_MODE") or "live"
        sid = ids.new_id("session")
        s = {"customer_id": body.customer_id, "country": customer["country"], "mode": mode, "verified": False,
             "prefs": {}, "expires_at": now() + SESSION_TTL}
        request.app.state.sessions[sid] = s
        return {"session_id": sid, "mode": mode, "today": today(mode, s["country"]), "otp_demo": fx.OTP,
                "expires_at": s["expires_at"]}

    @app.post("/api/sessions/{session_id}/verify", response_model=VerifyOut)
    def verify(session_id: str, body: VerifyIn, request: Request, response: Response):
        s = request.app.state.sessions.get(session_id)
        if s is None:
            raise ApiError(404, "NOT_FOUND", "Unknown session")
        if s["expires_at"] <= now():
            raise ApiError(410, "SESSION_EXPIRED", "Session expired")
        if body.otp != fx.OTP:
            raise ApiError(401, "UNAUTHENTICATED", "Wrong code")
        s["verified"] = True
        response.set_cookie(COOKIE, session_id, httponly=True, secure=True, samesite="lax",
                            max_age=int(SESSION_TTL.total_seconds()))
        return {"verified": True, "expires_at": s["expires_at"]}

    # ---------- agent proxy (stub: the echo of a fixture turn; client session_id/customer_id are dropped) ----------
    # [assumption] (pending the lead) 401 only for a missing or unknown cookie. A known session in any state is
    # forwarded with session_state verified|expired|unverified, and the graph decides `reauthenticate` (spec 02 AC-07).
    @app.post("/api/agent/threads", response_model=ThreadOut)
    def agent_thread(s: dict = Depends(known_session)):
        return {"thread_id": new_thread(s["session_id"])}

    def _turn(s: dict) -> CustomerTurn:
        turn = fx.turn_result().for_customer().model_copy(update={"mode": s["mode"]})
        if session_state(s) != "verified":                 # the stub's stand-in for the graph's reauthenticate rule
            # No data: no case, receipt or action claim. The line is the session line of messages.yaml (spec 04 §4.5).
            lang = next((c["language"] for c in fx.CUSTOMERS if c["customer_id"] == s["customer_id"]), "es")
            chips = fx.MESSAGES["suggest"]
            turn = turn.model_copy(update={
                "decision": "reauthenticate", "case_id": None, "receipt": None, "language": lang,
                "intent": None, "denials": [], "guardrails_triggered": ["G-SES-01"],
                "reply": fx.MESSAGES["connect"]["general_contact"][lang],
                "suggestions": [      # [assumption] the link goes to "/" (the verify screen); labels from messages.yaml
                    Suggestion(id="reauthenticate", label=chips["reauthenticate"][lang], kind="link", href="/"),
                    Suggestion(id="talk_to_person", label=chips["talk_to_person"][lang], kind="action",
                               action={"type": "request_call"})]})
        return turn

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    @app.post("/api/agent/threads/{thread_id}/runs/stream")
    def agent_stream(thread_id: str, request: Request, payload: dict = Body(default={}),
                     s: dict = Depends(own_thread)):
        # AC-06: the configurable comes from the cookie's session; the body (including config.configurable) is never read.
        request.app.state.runs.append(run_config(s))
        events = [("turn", _turn(s).model_dump(mode="json"))]
        if session_state(s) == "verified":                 # a reauthenticate turn has no action, so no progress event
            progress = ProgressItem(step="block_card", label="Bloqueando la tarjeta", state="in_progress", at=now())
            events.insert(0, ("progress", progress.model_dump(mode="json")))
        return StreamingResponse((_sse(e, d) for e, d in events), media_type="text/event-stream")

    @app.get("/api/agent/threads/{thread_id}/state", response_model=CustomerTurn)
    def agent_state(thread_id: str, s: dict = Depends(own_thread)):
        # Not forwarded: an expired session gets no thread data (G-SES-01), the same 401 as the data routes.
        if session_state(s) != "verified":
            session(s)
        return _turn(s)

    # ---------- customer ----------
    @app.get("/api/notifications", response_model=list[NotificationOut])
    def my_notifications(s: dict = Depends(session)):
        return fx.notifications() if s["customer_id"] == fx.OWNER else []

    @app.get("/api/me/products", response_model=list[ProductView])
    def products(s: dict = Depends(session)):
        return fx.my_products() if s["customer_id"] == fx.OWNER else []

    @app.get("/api/me/cases", response_model=list[CustomerCaseSummary])
    def cases(s: dict = Depends(session)):
        return fx.my_cases() if s["customer_id"] == fx.OWNER else []

    @app.put("/api/me/preferences", response_model=PrefsOut)
    def preferences(body: PrefsIn, s: dict = Depends(session)):
        s["_row"]["prefs"].update(body.model_dump(exclude_none=True))     # `mode` is never writable (AC-07)
        return {"display_currency": None, "language": None, **s["_row"]["prefs"]}

    @app.get("/api/cases/{case_id}", response_model=CustomerCaseView)
    def case(case_id: str, s: dict = Depends(own_case)):
        return fx.case_view(case_id, s["mode"], today(s["mode"], s["country"])).for_customer()

    def _event() -> str:
        return ids.new_id("event")

    @app.post("/api/cases/{case_id}/info", status_code=201, response_model=EventOut)
    def info(case_id: str, body: InfoIn, s: dict = Depends(own_case)):
        return {"event_id": _event()}

    @app.post("/api/cases/{case_id}/call-request", status_code=201, response_model=CallOut)
    def call_request(case_id: str, s: dict = Depends(own_case), body: CallIn = Body(default=CallIn())):
        # D-008: the expected contact date is a raw YYYY-MM-DD or null; the stub has no contact policy, so null.
        return {"event_id": _event(), "expected_contact_by": None}

    @app.post("/api/cases/{case_id}/reevaluation", status_code=201, response_model=ReevalOut)
    def reevaluation(case_id: str, body: ReevalIn, s: dict = Depends(own_case)):
        if fx.case_view(case_id).queue_status not in ("resolved", "closed"):
            raise ApiError(409, "DENY", "already_in_progress", "POL-REEVAL-WINDOW")
        return {"event_id": _event(), "case_id": case_id}

    @app.post("/api/cases/{case_id}/channels/telegram", status_code=201, response_model=TelegramOut)
    def telegram(case_id: str, s: dict = Depends(own_case)):
        return {"deep_link": "https://t.me/nick_of_time_stub_bot?start=stub-token",
                "expires_at": now() + dt.timedelta(minutes=15)}

    @app.post("/api/cases/{case_id}/channels/email", status_code=202, response_model=EmailOut)
    def email(case_id: str, body: EmailIn, s: dict = Depends(own_case)):
        if "@" not in body.email:
            raise ApiError(400, "INVALID", "Not an e-mail address")
        return {"confirmation_sent": True}

    @app.get("/api/channels/email/confirm", status_code=302)
    def email_confirm(token: str = Query(...)):
        if token != "stub-token":
            # [assumption] the error enum has no "expired link" code; DENY with the 410 status says it
            raise ApiError(410, "DENY", "The link expired")
        return RedirectResponse(f"/case/{fx.CASE_ID}?email=confirmed", status_code=302)

    def _secret_ok(expected: Optional[str], given: Optional[str]) -> bool:
        return bool(expected and given) and hmac.compare_digest(expected.encode(), given.encode())

    @app.post("/api/telegram/webhook", response_model=AckOut)
    def telegram_webhook(update: dict = Body(default={}),
                         x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
        if not _secret_ok(os.getenv("TELEGRAM_WEBHOOK_SECRET"), x_telegram_bot_api_secret_token):
            raise ApiError(401, "UNAUTHENTICATED", "Bad webhook secret")
        return {"ok": True}

    @app.post("/api/resend/webhook", response_model=AckOut)
    def resend_webhook(event: dict = Body(default={}), svix_signature: Optional[str] = Header(None)):
        # [assumption] the stub only checks that a signature is present; real svix verification: spec 05
        if not os.getenv("RESEND_WEBHOOK_SECRET") or not svix_signature:
            raise ApiError(401, "UNAUTHENTICATED", "Bad webhook signature")
        return {"ok": True}

    # ---------- analyst console ----------
    @app.get("/api/console/cases", response_model=list[CaseSummary])
    def console_cases(status: Optional[str] = None, zone: Optional[str] = None, country: Optional[str] = None,
                      _: str = Depends(analyst)):
        row = fx.case_summary()
        keep = (status in (None, row.queue_status)) and (zone in (None, row.zone)) and (country in (None, row.country))
        return [row] if keep else []

    @app.get("/api/console/cases/{case_id}", response_model=ConsoleCaseOut)
    def console_case(case_id: str, _: str = Depends(analyst)):
        if case_id not in fx.CASE_OWNERS:
            raise ApiError(404, "NOT_FOUND", "Case not found")
        events = [{"event_id": "E-000000000001", "type": "case_opened", "actor": "agent", "created_at": fx.NOW}]
        return {"case": fx.case_view(case_id), "handoff": fx.HANDOFF, "events": events}

    @app.post("/api/cases/{case_id}/action", response_model=AnalystActionOut)
    def analyst_action(case_id: str, body: AnalystActionIn, _: str = Depends(analyst)):
        if case_id not in fx.CASE_OWNERS:
            raise ApiError(404, "NOT_FOUND", "Case not found")
        if body.case_id != case_id:
            raise ApiError(403, "DENY", "case_id in the body does not match the path")
        status = fx.case_view(case_id).queue_status
        if body.action == "close_case":                    # a person closes, and only a resolved case
            if status != "resolved":
                raise ApiError(409, "DENY", "Only a resolved case can be closed", "case_queue.transitions")
            return AnalystActionOut(event_id=_event(), previous_status=status, new_status="closed",
                                    notification_id=ids.new_id("notification"))
        return AnalystActionOut(event_id=_event(), previous_status=status, new_status="review",
                                notification_id=ids.new_id("notification"))

    def _settings() -> dict:
        return {"supervised_mode": app.state.supervised, "score_provider": "dataset",
                "policies_version": fx.POLICIES_VERSION}

    @app.get("/api/console/settings", response_model=SettingsOut)
    def settings(_: str = Depends(analyst)):
        return _settings()

    @app.put("/api/console/settings", response_model=SettingsOut)
    def put_settings(body: SettingsIn, _: str = Depends(analyst)):
        app.state.supervised = body.supervised_mode
        return _settings()

    @app.post("/api/console/demo/reset", response_model=ResetOut)
    def demo_reset(_: str = Depends(analyst)):
        return {"demo_transactions": 0, "sample_cases": 0}

    # ---------- evaluation hooks (only when EVAL_MODE=true; never in production) ----------
    if eval_on:
        @app.post("/api/eval/seed", response_model=SeedOut)
        def eval_seed(body: SeedIn, request: Request):
            state = body.initial_state.get("session", "verified")
            if state not in ("verified", "expired", "none"):
                raise ApiError(400, "INVALID", "session must be verified, expired or none")
            sid, t = ids.new_id("session"), now()
            mode = "replay"                                # ADR 0020: seeded sessions are always replay
            cid = None if state == "none" else body.initial_state.get("customer_id")
            country = next((c["country"] for c in fx.CUSTOMERS if c["customer_id"] == cid), None)
            request.app.state.sessions[sid] = {
                "customer_id": cid, "country": country, "mode": mode, "verified": state == "verified",
                "prefs": {}, "run_id": body.run_id, "arm": body.arm,
                "expires_at": t - SESSION_TTL if state == "expired" else t + SESSION_TTL}
            return {"session_id": sid, "thread_id": new_thread(sid), "run_id": body.run_id, "arm": body.arm,
                    "mode": request.app.state.sessions[sid]["mode"]}

        @app.get("/api/eval/final-state/{session_id}", response_model=FinalState)
        def eval_final_state(session_id: str, request: Request):
            s = request.app.state.sessions.get(session_id)
            if s is None or "run_id" not in s:
                raise ApiError(404, "NOT_FOUND", "Unknown eval session")
            return fx.final_state(s["run_id"], s["arm"])

    return app


app = create_app()
