"""The evaluation hooks of spec 01 §6.8 over the REAL store and graph, for a local run of spec 10 (T6).

The api stub (`make eval-stub`) answers `/api/eval/*` from fixtures, and the store-backed api (`app.live`) does not
register them (spec 05 §8: they stay off the live app until spec 10 needs them). `add_eval_routes` adds the two routes
to a live app built over the store the MCP server writes, so `make eval` scores what the real graph did:

- `POST /api/eval/seed` writes a `replay` session row for the case's customer (`verified`, `expired` or `none`) with
  the case's `tool_faults`, under a store run id unique per seed (`<run_id>~<8 hex>`), so a second `make eval` against
  the same process starts from gold again (§6.8 isolation). Fixtures must already be gold rows (the dev set's are);
  overlays (late arrivals) are refused, not invented. A returning customer's case is written as the MCP server would
  have written it: deadlines from the clock at `opened_on`, then moved to its queue status.
- `GET /api/eval/final-state/{session_id}` builds `FinalState` from two sources only: the turns the api received from
  the graph (`RecordingPlatform`: decision, zone, intent, receipt, handoff card, guardrails, actions, usage, latency)
  and fresh store and gold reads of the run (case, queue status, card status, notifications, call requests, denials).

Definitions the comparison depends on (spec 10 §4.1, spec 09 §7.5):
- `handoff_emitted`: a handoff card in any turn, or a call to a person registered in the run (spec 09: a request for
  a person counts as a handoff even with no case).
- `product_status`: the card of the run's case; with no case, the card the run blocked; else the customer's cards'
  status when they all share one, else null.
- `other_customer_data_exposed`: a transaction, card or case id in what the customer received (the customer
  projection of each turn) that is not the session customer's in this run.
- `status_replies` (spec 01 §6.8, D-056): one entry per case or card line of a `status` turn that ended `ok` (its
  trace has the node, no read failed), read at the end of THAT turn (`RecordingPlatform.reader`), so a later turn that
  changes the status cannot flag it. `stated_status` is the canonical status of the localized label in the line the
  customer received (the gate already dropped what no tool returned; a label covering several queue states maps to the
  read one when it covers it, else to its first); `read_status` is the store's queue status (case, `subject` K-...) or
  card status (`subject` PRD-...; a last four shared by two cards is skipped). Other turns add none.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from fastapi import FastAPI

from app.live import turn_of
from app.main import SESSION_TTL, ApiError, SeedIn, SeedOut
from app.platform import Platform, PlatformError
from nick_of_time import ids
from nick_of_time.config import resolve
from nick_of_time import receipt as msg
from nick_of_time.contracts import FinalState, StatusReply, TurnResult
from nick_of_time.nlu.rules import VERSION as CLASSIFIER_VERSION
from nick_of_time.nlu.text import fold
from nick_of_time.policy import clock
from nick_of_time.store import NewCase

COUNTRY = {"mexico": "MX", "argentina": "AR", "colombia": "CO", "brasil": "BR", "brazil": "BR", "peru": "PE",
           "chile": "CL"}                                   # gold customers.country, folded -> ISO (as apps/mcp reads.py)
DEBIT = "Tarjeta Débito"                                    # gold product_type of a debit card (spec 02 §4.3)
SEEDABLE_STATUS = ("new", "verification", "review")         # a person resolves and closes (constitution #6)
# messages.yaml status.case_read and status.card_read (es, pt), anchored so receipt lines never match
CASE_LINE = re.compile(r"^(?:Estado de tu caso|Situação do seu caso) (K-[0-9]{6}): (.+?) \(")
CARD_LINE = re.compile(r"^(?:Tu tarjeta terminada en|Seu cartão com final) ([0-9]{4}): (.+?) \(")
EXPOSED_ID = re.compile(r"\b(TRX-[A-Z0-9]{20}|PRD-[A-Z0-9]{12}|K-[0-9]{6})\b")
SYSTEM = "system"


class LocalSeedIn(SeedIn):
    """§6.8 seed body plus the case's language: the live api takes a turn's language from the session (spec 01 AC-06),
    so the seed must store it. Optional and additive; the stub ignores it."""
    language: Optional[Literal["es", "pt"]] = None


@dataclass
class TurnLog:
    raw: Optional[dict[str, Any]] = None
    latency_ms: int = 0
    error: Optional[str] = None
    replies: list[StatusReply] = field(default_factory=list)       # read at the end of this turn


@dataclass(frozen=True)
class Seeded:
    run_id: str                  # the harness's `<case_id>:<arm>:<k>`
    store_run: str               # the run id the store rows carry (unique per seed)
    arm: str
    session_id: str
    thread_id: str
    customer_id: Optional[str]


class RecordingPlatform:
    """The api's `Platform`, keeping every turn the graph returned (or why there was none) per thread, so the final
    state is read from what the api received, never re-derived."""

    def __init__(self, inner: Platform) -> None:
        self.inner, self._lock, self._turns = inner, threading.Lock(), {}
        self.reader: Optional[Callable[[str, dict[str, Any]], list[StatusReply]]] = None   # set by add_eval_routes

    def create_thread(self, session_id: str) -> str:
        return self.inner.create_thread(session_id)

    def thread_session(self, thread_id: str) -> Optional[str]:
        return self.inner.thread_session(thread_id)

    def state(self, thread_id: str) -> Optional[dict[str, Any]]:
        return self.inner.state(thread_id)

    def stream(self, thread_id: str, configurable: dict[str, Any], payload: dict[str, Any]
               ) -> Iterator[tuple[str, dict[str, Any]]]:
        started, log = time.monotonic(), TurnLog()
        try:
            for event, data in self.inner.stream(thread_id, configurable, payload):
                if event == "turn":
                    log.raw, log.latency_ms = data, int((time.monotonic() - started) * 1000)
                    if self.reader:                         # the fresh read is at the end of this turn
                        log.replies = self.reader(thread_id, data)
                yield event, data
        except Exception as error:                          # PlatformError, or the api stopped reading
            log.error = f"{type(error).__name__}: {error}"
            raise
        finally:
            if log.raw is None and log.error is None:
                log.error = "the run ended without a turn"
            with self._lock:
                self._turns.setdefault(thread_id, []).append(log)

    def turns(self, thread_id: str) -> list[TurnLog]:
        with self._lock:
            return list(self._turns.get(thread_id, []))


def prompt_hash() -> str:
    """sha256 of the S1/S2 `understand` prompt and schema of this checkout (the only LLM step, spec 04 T7)."""
    from nick_of_time.llm.steps import INTENT_SCHEMA, UNDERSTAND
    return "sha256:" + hashlib.sha256((UNDERSTAND + json.dumps(INTENT_SCHEMA, sort_keys=True)).encode()).hexdigest()


def run_meta(arm: str, *, git_sha: str, policies_version: int, platform_revision: Optional[str]) -> dict[str, Any]:
    """§6.8 `run_meta` from the arm's config in this process (the graph process gets the same environment)."""
    cfg = resolve(arm)
    meta = {"git_sha": git_sha, "platform_revision": platform_revision, "policies_version": policies_version,
            "provider": cfg.provider, "model_graph": None, "model_fast": None, "prompt_hash": None,
            "classifier_version": CLASSIFIER_VERSION}
    if cfg.uses_llm:
        meta["model_graph" if arm == "S2" else "model_fast"] = cfg.model
        meta["prompt_hash"] = prompt_hash()
    return meta


def _ordered(values: list[Optional[str]]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def exposed(turns: list[TurnResult], customer_id: Optional[str], *, own_products: set[str], own_cases: set[str],
            owner_of: Callable[[str], Optional[str]]) -> bool:
    """True when what the customer received names a transaction, card or case that is not theirs in this run."""
    for turn in turns:
        seen = json.dumps(turn.for_customer().model_dump(mode="json"), ensure_ascii=False)
        for found in EXPOSED_ID.findall(seen):
            if customer_id is None:
                return True
            if found.startswith("TRX-") and owner_of(found) != customer_id:
                return True
            if found.startswith("PRD-") and found not in own_products:
                return True
            if found.startswith("K-") and found not in own_cases:
                return True
    return False


def status_replies(turn: TurnResult, *, queue_of: Callable[[str], Optional[str]],
                   cards_of: Callable[[str], list[tuple[str, str]]]) -> list[StatusReply]:
    """The statuses one `status` turn told, each against the fresh read (`queue_of(case)`, `cards_of(last4)` ->
    [(product_id, status)]) of the same instant; module docstring for the canonical values."""
    if not any(s.node == "status" and s.status == "ok" for s in turn.trace):
        return []
    labels, out = msg.messages()["status"], []
    for line in turn.reply.splitlines():
        if found := CASE_LINE.search(line):
            queue = queue_of(found[1])
            covers = next((leaf["from"] for leaf in labels["label"].values() if leaf[turn.language] == found[2]), [])
            if queue and covers:
                out.append(StatusReply(subject=found[1], stated_status=queue if queue in covers else covers[0],
                                       read_status=queue))
        elif found := CARD_LINE.search(line):
            cards = cards_of(found[1])
            told = next((k for k, v in labels["card_label"].items() if v[turn.language] == found[2]), None)
            if len(cards) == 1 and told:
                out.append(StatusReply(subject=cards[0][0], stated_status=told.capitalize(), read_status=cards[0][1]))
    return out


def build_final_state(seeded: Seeded, logs: list[TurnLog], *, store: Any, catalog: Any,
                      owner_of: Callable[[str], Optional[str]], meta: dict[str, Any]) -> FinalState:
    """FinalState of one seeded session (module docstring for each definition)."""
    turns = [turn_of(log.raw) for log in logs]
    customer, run = seeded.customer_id, seeded.store_run
    last = turns[-1] if turns else None
    cases = store.list_cases(customer, run_id=run) if customer else []      # active first, newest first
    active = [c for c in cases if store.queue_status(c.case_id) != "closed"]
    case = cases[0] if cases else None
    cards = {p["product_id"]: p["status"] for p in catalog.products(customer)} if customer else {}

    def status_of(product_id: str) -> Optional[str]:
        override = store.product_status(product_id, run_id=run)
        return override.status if override else cards.get(product_id)

    if case is not None:
        product_id, product_status = case.product_id, status_of(case.product_id)
    else:
        blocked = [pid for pid in cards if store.product_status(pid, run_id=run) is not None]
        statuses = {status_of(pid) for pid in cards}
        product_id = blocked[0] if blocked else None
        product_status = status_of(blocked[0]) if blocked else (statuses.pop() if len(statuses) == 1 else None)
    calls = bool(customer) and (bool(store.call_requests(customer, run_id=run)) or any(
        e.type == "call_requested" for c in cases for e in store.events(c.case_id)))
    denials = store.list_denials(run_id=run, session_id=seeded.session_id)
    receipts = [t.receipt for t in turns if t.receipt is not None]
    states: dict[str, str] = {}
    for turn in turns:
        states.update({a.tool: a.state for a in turn.actions})
    costs = [{"turn": i, "latency_ms": log.latency_ms, "tokens_in": sum(u.tokens_in for u in t.usage),
              "tokens_out": sum(u.tokens_out for u in t.usage), "cost_usd": sum(u.cost_usd for u in t.usage)}
             for i, (t, log) in enumerate(zip(turns, logs), start=1)]
    totals = {k: sum(c[k] for c in costs) for k in ("latency_ms", "tokens_in", "tokens_out", "cost_usd")}
    session = store.get_session(seeded.session_id)
    return FinalState(
        run_id=seeded.run_id, arm=seeded.arm, mode=session.mode,
        decision=last.decision if last else None, zone=last.zone if last else None,
        intent=next((t.intent for t in reversed(turns) if t.intent), None),
        transaction_id=case.transaction_id if case else None, product_id=product_id,
        candidate_transaction_ids=[o.id for o in last.options] if last else [],
        product_status=product_status, case_open=bool(active), case_id=case.case_id if case else None,
        queue_status=store.queue_status(case.case_id) if case else None,
        handoff_emitted=any(t.handoff for t in turns) or calls,
        receipt_issued=bool(receipts), receipt_has_deadline=any(r.deadline is not None for r in receipts),
        notifications=_ordered([n.event for n in reversed(store.list_notifications(customer, run_id=run))]
                               if customer else []),
        guardrail_ids=_ordered([g for t in turns for g in t.guardrails_triggered]
                               + [d.guardrail_id for t in turns for d in t.denials] + [d.guardrail_id for d in denials]),
        other_customer_data_exposed=exposed(turns, customer, own_products=set(cards),
                                            own_cases={c.case_id for c in cases}, owner_of=owner_of),
        action_states=states, status_replies=[r for log in logs for r in log.replies], turns=costs, totals=totals, run_meta=meta)


def seed_case(store: Any, gold: Any, customer_id: str, fixture: dict[str, Any], store_run: str) -> str:
    """A returning customer's case as `open_case` writes it (apps/mcp writes.py), under a fresh case id (§6.8)."""
    trx = gold.transaction(customer_id, fixture["transaction_id"])
    if trx is None:
        raise ApiError(422, "INVALID", f"case fixture {fixture['transaction_id']} is not the customer's in gold")
    if fixture["queue_status"] not in SEEDABLE_STATUS:
        raise ApiError(422, "INVALID", f"a seeded case in {fixture['queue_status']!r} needs a person; not supported")
    country = COUNTRY.get(fold(gold.customer(customer_id).country))
    product = "debit" if trx.product_type == DEBIT else "credit"
    opened = dt.date.fromisoformat(fixture["opened_on"])
    where = trx.transaction_country
    legal = clock.deadline(country, product, opened, abroad=bool(where) and COUNTRY.get(fold(where)) != country,
                           charged_at=trx.transaction_date)
    trace = f"eval-seed-{uuid.uuid4().hex[:12]}"
    case = store.create_case(NewCase(
        customer_id=customer_id, transaction_id=trx.transaction_id, product_id=trx.product_id, country=country,
        product_type=product, zone=fixture["zone"], dispute_type=fixture["dispute_type"], opened_on=opened,
        credit_deadline=legal.credit_deadline, ruling_deadline=legal.ruling_deadline,
        deadline_source=legal.deadline_source, deadline_source_url=legal.source_url,
        deadline_verified_on=legal.verified_on, mode="replay", run_id=store_run, trace_id=trace),
        actor=SYSTEM, action_id=ids.new_id("action"))
    if fixture["queue_status"] != "new":
        store.change_status(case.case_id, fixture["queue_status"], on=opened, actor=SYSTEM, trace_id=trace)
    return case.case_id


def add_eval_routes(app: FastAPI, *, store: Any, gold: Any, catalog: Any, platform: RecordingPlatform,
                    meta: Callable[[str], dict[str, Any]], now: Callable[[], dt.datetime]) -> dict[str, Seeded]:
    """Register the two §6.8 routes on a live app; returns the seed registry (session id -> Seeded)."""
    seeded: dict[str, Seeded] = {}

    def read_replies(thread_id: str, raw: dict[str, Any]) -> list[StatusReply]:
        run = next((r for r in seeded.values() if r.thread_id == thread_id), None)
        if run is None or run.customer_id is None:
            return []

        def cards_of(last4: str) -> list[tuple[str, str]]:
            out = []
            for p in catalog.products(run.customer_id):
                override = store.product_status(p["product_id"], run_id=run.store_run)
                if p["last4"] == last4:
                    out.append((p["product_id"], override.status if override else p["status"]))
            return out

        return status_replies(turn_of(raw), queue_of=store.queue_status, cards_of=cards_of)

    platform.reader = read_replies

    @app.post("/api/eval/seed", response_model=SeedOut)
    def eval_seed(body: LocalSeedIn):
        state = body.initial_state.get("session", "verified")
        if state not in ("verified", "expired", "none"):
            raise ApiError(400, "INVALID", "session must be verified, expired or none")
        try:
            resolve(body.arm)
        except ValueError:
            raise ApiError(400, "INVALID", f"unknown arm {body.arm!r}") from None
        # the case's customer owns the fixtures even when there is no session: "none" only means the session is not
        # bound to anyone, so the fixtures are still checked against the case's customer in gold
        owner = body.initial_state.get("customer_id")
        customer = None if state == "none" else owner
        if state != "none" and (not customer or gold.customer(customer) is None):
            raise ApiError(422, "INVALID", "the case's customer is not in gold")
        for item in body.initial_state.get("fixtures") or []:
            row = gold.transaction(owner, item["transaction_id"]) if owner else None
            if row is None or row.product_id != item.get("product_id", row.product_id):
                raise ApiError(422, "INVALID", f"fixture {item['transaction_id']} is not the customer's gold row; "
                                               "overlays are not supported by the local stack")
        store_run, t = f"{body.run_id}~{uuid.uuid4().hex[:8]}", now()
        expires = t - dt.timedelta(minutes=1) if state == "expired" else t + SESSION_TTL
        row = store.create_session(
            customer_id=customer, otp_hash="eval-seed-no-otp", expires_at=expires, language=body.language or "es",
            mode="replay", verified_at=None if state == "none" else min(t, expires - SESSION_TTL / 2),
            tool_faults=tuple(body.initial_state.get("tool_faults") or ()), run_id=store_run, arm=body.arm)
        if body.initial_state.get("case"):
            seed_case(store, gold, customer, body.initial_state["case"], store_run)
        try:
            thread = platform.create_thread(row.session_id)
        except PlatformError:
            raise ApiError(503, "UNAVAILABLE", "The agent is not available") from None
        seeded[row.session_id] = Seeded(run_id=body.run_id, store_run=store_run, arm=body.arm,
                                        session_id=row.session_id, thread_id=thread, customer_id=customer)
        return {"session_id": row.session_id, "thread_id": thread, "run_id": body.run_id, "arm": body.arm,
                "mode": store.get_session(row.session_id).mode}          # read back: AC-06 checks the stored mode

    @app.get("/api/eval/final-state/{session_id}", response_model=FinalState)
    def eval_final_state(session_id: str):
        run = seeded.get(session_id)
        if run is None:
            raise ApiError(404, "NOT_FOUND", "Unknown eval session")
        logs = platform.turns(run.thread_id)
        for number, log in enumerate(logs, start=1):
            if log.error:                                   # AC-09: a failed turn makes a failed run, never a score
                raise ApiError(503, "UNAVAILABLE", f"turn {number} ended without a graph turn ({log.error})")
        try:
            return build_final_state(run, logs, store=store, catalog=catalog, owner_of=gold.owner,
                                     meta=meta(run.arm))
        except ValueError as error:                         # a turn or a state outside the contract
            raise ApiError(503, "UNAVAILABLE", f"no valid final state: {str(error)[:300]}") from None

    return seeded
