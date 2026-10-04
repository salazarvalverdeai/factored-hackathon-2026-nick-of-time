"""api stub (spec 01 T3, AC-02, AC-06, AC-07): every route of §6.2 and §6.8 answers with fixtures validated by the
contract models in `nick_of_time.contracts`. No store, no agent: spec 05 replaces the fixtures route by route.

Customer routes serve customer projections only (D-013). The session lives server-side; the `not_session` cookie
carries only its id, and a `session_id` or `customer_id` in any request body is ignored (AC-06).
"""

import datetime as dt
import json
import os
from typing import Any, Literal, Optional

from fastapi import Body, Cookie, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from app import fixtures as fx
from nick_of_time import ids
from nick_of_time.contracts import (AnalystActionIn, AnalystActionOut, CaseSummary, CustomerCaseSummary,
                                    CustomerCaseView, CustomerTurn, FinalState, ProductView, Mode)

CONTRACT_VERSION = "1.1.0"
COOKIE = "not_session"
SESSION_TTL = dt.timedelta(minutes=30)

Code = Literal["DENY", "NOT_FOUND", "SESSION_EXPIRED", "UNAUTHENTICATED", "UNAVAILABLE", "INVALID"]


class ApiError(Exception):
    def __init__(self, status: int, code: Code, message: str, policy_id: Optional[str] = None):
        self.status, self.body = status, {"code": code, "policy_id": policy_id, "message": message}


def today(mode: str) -> dt.date:
    """clock.today(mode) for the stub (ADR 0020): replay is frozen, live is the real UTC date."""
    return fx.REPLAY_TODAY if mode == "replay" else dt.datetime.now(dt.timezone.utc).date()


def create_app(eval_mode: Optional[bool] = None) -> FastAPI:
    eval_on = os.getenv("EVAL_MODE", "").lower() == "true" if eval_mode is None else eval_mode
    app = FastAPI(title="Nick of Time api (stub)", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.sessions = {}            # session_id -> dict(customer_id, mode, verified, expires_at, run_id, arm, prefs)
    app.state.runs = []                # configurable of every proxied agent run (AC-06 evidence)
    app.state.supervised = True

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return JSONResponse(e.body, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, e: RequestValidationError):
        return JSONResponse({"code": "INVALID", "policy_id": None, "message": str(e.errors()[0]["msg"])}, 400)

    def now() -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)

    def session(request: Request, sid: Optional[str] = Cookie(None, alias=COOKIE)) -> dict:
        s = request.app.state.sessions.get(sid) if sid else None
        if s is None or not s["verified"] or s["customer_id"] is None:
            if s is not None and s["expires_at"] <= now():
                raise ApiError(401, "SESSION_EXPIRED", "Session expired: verify again")
            raise ApiError(401, "UNAUTHENTICATED", "No verified session")
        if s["expires_at"] <= now():
            raise ApiError(401, "SESSION_EXPIRED", "Session expired: verify again")
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
            raise ApiError(403, "DENY", "The case does not belong to this customer", "scope.only_own_products")
        return s

    # ---------- public ----------
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "stub", "contract_version": CONTRACT_VERSION,
                "git_sha": os.getenv("GIT_SHA", "stub"), "gold_version": "v1", "policies_version": 2,
                "platform_revision": None, "models": {"graph": os.getenv("BEDROCK_MODEL_GRAPH"),
                                                      "fast": os.getenv("BEDROCK_MODEL_FAST")},
                "prompt_hash": None, "classifier_version": None,
                "today": {m: today(m).isoformat() for m in ("replay", "live")}}

    @app.get("/api/demo/customers")
    def demo_customers():
        return fx.CUSTOMERS

    class SessionIn(BaseModel):
        customer_id: str
        mode: Mode = os.getenv("DEFAULT_SESSION_MODE", "live")  # type: ignore[assignment]

    @app.post("/api/sessions", status_code=201)
    def create_session(body: SessionIn, request: Request):
        if body.customer_id not in {c["customer_id"] for c in fx.CUSTOMERS}:
            raise ApiError(404, "NOT_FOUND", "Unknown customer")
        sid = ids.new_id("session")
        s = {"customer_id": body.customer_id, "mode": body.mode, "verified": False, "prefs": {},
             "expires_at": now() + SESSION_TTL}
        request.app.state.sessions[sid] = s
        return {"session_id": sid, "mode": s["mode"], "today": today(s["mode"]).isoformat(), "otp_demo": fx.OTP,
                "expires_at": s["expires_at"].isoformat()}

    class VerifyIn(BaseModel):
        otp: str

    @app.post("/api/sessions/{session_id}/verify")
    def verify(session_id: str, body: VerifyIn, request: Request, response: Response):
        s = request.app.state.sessions.get(session_id)
        if s is None:
            raise ApiError(404, "NOT_FOUND", "Unknown session")
        if s["expires_at"] <= now():
            raise ApiError(410, "SESSION_EXPIRED", "Session expired")
        if body.otp != fx.OTP:
            raise ApiError(401, "UNAUTHENTICATED", "Wrong code")
        s["verified"] = True
        response.set_cookie(COOKIE, session_id, httponly=True, samesite="lax", max_age=int(SESSION_TTL.total_seconds()))
        return {"verified": True, "expires_at": s["expires_at"].isoformat()}

    # ---------- agent proxy (stub: the echo of a fixture turn; client session_id/customer_id are dropped) ----------
    @app.post("/api/agent/threads")
    def agent_thread(s: dict = Depends(session)):
        return {"thread_id": "th-" + ids.new_id("event")}

    def _turn() -> CustomerTurn:
        return fx.turn_result().for_customer()

    @app.post("/api/agent/threads/{thread_id}/runs/stream")
    def agent_stream(thread_id: str, request: Request, payload: dict = Body(default={}),
                     sid: Optional[str] = Cookie(None, alias=COOKIE), s: dict = Depends(session)):
        # AC-06: the injected configurable comes from the cookie's session; the body's ids are never read.
        request.app.state.runs.append({"session_id": sid, "arm": s.get("arm"), "customer_id": s["customer_id"]})
        turn = _turn().model_copy(update={"mode": s["mode"]})
        events = [("progress", {"step": "block_card", "state": "in_progress"}), ("turn", turn.model_dump(mode="json"))]
        return StreamingResponse((f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events),
                                 media_type="text/event-stream")

    @app.get("/api/agent/threads/{thread_id}/state", response_model=CustomerTurn)
    def agent_state(thread_id: str, s: dict = Depends(session)):
        return _turn()

    # ---------- customer ----------
    @app.get("/api/notifications")
    def my_notifications(s: dict = Depends(session)):
        return fx.notifications()

    @app.get("/api/me/products", response_model=list[ProductView])
    def products(s: dict = Depends(session)):
        return fx.my_products()

    @app.get("/api/me/cases", response_model=list[CustomerCaseSummary])
    def cases(s: dict = Depends(session)):
        return fx.my_cases() if s["customer_id"] == fx.OWNER else []

    class PrefsIn(BaseModel):
        display_currency: Optional[str] = None
        language: Optional[Literal["es", "pt"]] = None

    @app.put("/api/me/preferences")
    def preferences(body: PrefsIn, s: dict = Depends(session)):
        s["prefs"].update(body.model_dump(exclude_none=True))     # `mode` is never writable (AC-07)
        return {"display_currency": None, "language": None, **s["prefs"]}

    @app.get("/api/cases/{case_id}", response_model=CustomerCaseView)
    def case(case_id: str, s: dict = Depends(own_case)):
        return fx.case_view(case_id, s["mode"], today(s["mode"])).for_customer()

    class InfoIn(BaseModel):
        text: str

    class CallIn(BaseModel):
        preferred_time: Optional[str] = None

    class ReevalIn(BaseModel):
        reason: str

    class EmailIn(BaseModel):
        email: str

    def _event() -> str:
        return ids.new_id("event")

    @app.post("/api/cases/{case_id}/info", status_code=201)
    def info(case_id: str, body: InfoIn, s: dict = Depends(own_case)):
        return {"event_id": _event()}

    @app.post("/api/cases/{case_id}/call-request", status_code=201)
    def call_request(case_id: str, s: dict = Depends(own_case), body: CallIn = Body(default=CallIn())):
        # D-008: the expected contact date is a raw YYYY-MM-DD or null; the stub has no contact policy, so null.
        return {"event_id": _event(), "expected_contact_by": None}

    @app.post("/api/cases/{case_id}/reevaluation", status_code=201)
    def reevaluation(case_id: str, body: ReevalIn, s: dict = Depends(own_case)):
        if fx.case_view().queue_status not in ("resolved", "closed"):
            raise ApiError(409, "DENY", "The case is still being worked on", "case_queue.reevaluation")
        return {"event_id": _event(), "case_id": case_id}

    @app.post("/api/cases/{case_id}/channels/telegram", status_code=201)
    def telegram(case_id: str, s: dict = Depends(own_case)):
        exp = now() + dt.timedelta(minutes=15)
        return {"deep_link": "https://t.me/nick_of_time_stub_bot?start=stub-token", "expires_at": exp.isoformat()}

    @app.post("/api/cases/{case_id}/channels/email", status_code=202)
    def email(case_id: str, body: EmailIn, s: dict = Depends(own_case)):
        if "@" not in body.email:
            raise ApiError(400, "INVALID", "Not an e-mail address")
        return {"confirmation_sent": True}

    @app.get("/api/channels/email/confirm", status_code=302)
    def email_confirm(token: str = Query(...)):
        if token != "stub-token":
            raise ApiError(410, "NOT_FOUND", "The link expired")
        return RedirectResponse(f"/case/{fx.CASE_ID}?email=confirmed", status_code=302)

    @app.post("/api/telegram/webhook")
    def telegram_webhook(update: dict = Body(default={}),
                         x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
        secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        if not secret or x_telegram_bot_api_secret_token != secret:
            raise ApiError(401, "UNAUTHENTICATED", "Bad webhook secret")
        return {"ok": True}

    @app.post("/api/resend/webhook")
    def resend_webhook(event: dict = Body(default={}), svix_signature: Optional[str] = Header(None)):
        if not os.getenv("RESEND_WEBHOOK_SECRET") or not svix_signature:   # real svix verification: spec 05
            raise ApiError(401, "UNAUTHENTICATED", "Bad webhook signature")
        return {"ok": True}

    # ---------- analyst console ----------
    @app.get("/api/console/cases", response_model=list[CaseSummary])
    def console_cases(status: Optional[str] = None, zone: Optional[str] = None, country: Optional[str] = None,
                      _: str = Depends(analyst)):
        row = fx.case_summary()
        keep = (status in (None, row.queue_status)) and (zone in (None, row.zone)) and (country in (None, row.country))
        return [row] if keep else []

    @app.get("/api/console/cases/{case_id}")
    def console_case(case_id: str, _: str = Depends(analyst)):
        if case_id not in fx.CASE_OWNERS:
            raise ApiError(404, "NOT_FOUND", "Case not found")
        view = fx.case_view(case_id)
        events = [{"event_id": "E-000000000001", "type": "case_opened", "actor": "agent", "created_at": fx.NOW.isoformat()}]
        return {"case": view.model_dump(mode="json"), "handoff": fx.HANDOFF,
                "events": events}

    @app.post("/api/cases/{case_id}/action", response_model=AnalystActionOut)
    def analyst_action(case_id: str, body: AnalystActionIn, _: str = Depends(analyst)):
        if case_id not in fx.CASE_OWNERS:
            raise ApiError(404, "NOT_FOUND", "Case not found")
        if body.case_id != case_id:
            raise ApiError(403, "DENY", "case_id in the body does not match the path")
        if body.action == "close_case":                    # a person closes, and only a resolved case
            raise ApiError(409, "DENY", "Only a resolved case can be closed", "case_queue.transitions")
        return AnalystActionOut(event_id=_event(), previous_status="verification", new_status="review",
                                notification_id=ids.new_id("notification"))

    def _settings() -> dict:
        return {"supervised_mode": app.state.supervised, "score_provider": "dataset", "policies_version": 2}

    class SettingsIn(BaseModel):
        supervised_mode: bool

    @app.get("/api/console/settings")
    def settings(_: str = Depends(analyst)):
        return _settings()

    @app.put("/api/console/settings")
    def put_settings(body: SettingsIn, _: str = Depends(analyst)):
        app.state.supervised = body.supervised_mode
        return _settings()

    @app.post("/api/console/demo/reset")
    def demo_reset(_: str = Depends(analyst)):
        return {"demo_transactions": 0, "sample_cases": 0}

    # ---------- evaluation hooks (only when EVAL_MODE=true; never in production) ----------
    if eval_on:
        class SeedIn(BaseModel):
            initial_state: dict[str, Any]
            run_id: str
            arm: str

        @app.post("/api/eval/seed")
        def eval_seed(body: SeedIn, request: Request):
            state = body.initial_state.get("session", "verified")
            if state not in ("verified", "expired", "none"):
                raise ApiError(400, "INVALID", "session must be verified, expired or none")
            sid, t = ids.new_id("session"), now()
            request.app.state.sessions[sid] = {
                "customer_id": None if state == "none" else body.initial_state.get("customer_id"),
                "mode": "replay", "verified": state == "verified", "prefs": {}, "run_id": body.run_id,
                "arm": body.arm, "expires_at": t - SESSION_TTL if state == "expired" else t + SESSION_TTL}
            return {"session_id": sid, "thread_id": "th-" + ids.new_id("event"), "run_id": body.run_id,
                    "arm": body.arm, "mode": "replay"}

        @app.get("/api/eval/final-state/{session_id}", response_model=FinalState)
        def eval_final_state(session_id: str, request: Request):
            s = request.app.state.sessions.get(session_id)
            if s is None or "run_id" not in s:
                raise ApiError(404, "NOT_FOUND", "Unknown eval session")
            return fx.final_state(s["run_id"], s["arm"])

    return app


app = create_app()
