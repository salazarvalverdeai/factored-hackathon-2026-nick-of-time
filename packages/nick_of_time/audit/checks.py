"""Checks A3–A7 of spec 18 §4.1. Each returns one `Finding` with the exact facts it compared (expected vs observed)."""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Any, Iterable, Literal, Optional

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from nick_of_time.contracts import CONTRACTS_DIR, ActionRecord, CustomerReceipt, QueueStatus, StatusReply
from nick_of_time.ids import GOLD_PATTERN, PATTERN
from nick_of_time.store import WRITE_EVENTS, WRITE_TOOL, Store

Severity = Literal["critical", "high", "medium", "low"]
FindingStatus = Literal["passed", "finding", "not_applicable"]
TRANSITIONS: dict[str, list[str]] = yaml.safe_load((CONTRACTS_DIR / "policies.yaml").read_text())[
    "case_queue"]["transitions"]


class Finding(BaseModel):
    """One check result: its status (AC-06), what was expected and what was observed; `observed` is {} when clean."""
    model_config = ConfigDict(frozen=True)
    check_id: str
    severity: Severity
    status: FindingStatus
    expected: Any
    observed: Any


def _finding(check_id: str, severity: Severity, problems: Any, expected: Any, applicable: bool = True) -> Finding:
    status: FindingStatus = "finding" if problems else "passed" if applicable else "not_applicable"
    return Finding(check_id=check_id, severity=severity, status=status, expected=expected, observed=problems or {})


# ---------- A3 actions ----------
class ActionRead(BaseModel):
    """One `action_verified` case event (D-025): the verifying read minted `verification_id` at `read_at`.

    `requested_at` is the `created_at` of the write event (one of `WRITE_EVENTS`, six types) with the same `action_id`.
    `tools` are the tools that may have made that write (`WRITE_TOOL`; a `case_opened` of a case with a
    `related_case_id` also comes from `request_reevaluation`, spec 03 AC-19). That the read was the write's
    `VERIFIED_WITH` read is a store invariant (`record_verification`), not re-checked here: `action_verified` carries
    no read name yet.
    """
    model_config = ConfigDict(frozen=True)
    action_id: str
    verification_id: str
    read_at: AwareDatetime
    requested_at: AwareDatetime
    tools: frozenset[str] = frozenset()


def reads_from_store(store: Store, action_ids: Iterable[str], *, customer_id: str,
                    run_id: Optional[str]) -> list[ActionRead]:
    """One `ActionRead` per `action_verified` event of each action a turn showed (D-025), in `read_at` order.

    `action_ids` is the union of the action ids of the TurnResult `actions[]`, `receipt.actions` and `handoff.actions`.
    `customer_id` is the session's customer (constitution #3): an action of another customer's case yields no reads.
    `requested_at` is the `created_at` of the action's write event (`WRITE_EVENTS`), found with `store.action_write`;
    the events come from `store.verifications`. An action with no write of that customer in `run_id` yields none,
    so a claim that cites it is a finding.
    """
    # TODO(01g): the store adds `read` to the `action_verified` payload; then check it against `VERIFIED_WITH` here.
    reads: list[ActionRead] = []
    for action_id in dict.fromkeys(action_ids):
        write = store.action_write(action_id, run_id=run_id, customer_id=customer_id)
        if write is None or write.type not in WRITE_EVENTS:
            continue
        tools = {WRITE_TOOL[write.type]}
        case = store.get_case(write.case_id, run_id=run_id, customer_id=customer_id)
        if write.type == "case_opened" and case is not None and case.related_case_id:
            tools.add("request_reevaluation")
        reads += [ActionRead(action_id=action_id, verification_id=e.payload["verification_id"],
                             read_at=e.payload["read_at"], requested_at=write.created_at,
                             tools=frozenset(tools))
                  for e in store.verifications(write.case_id, action_id, run_id=run_id)]
    return reads


def check_actions(shown: Iterable[ActionRecord], reads: Iterable[ActionRead], *,
                  receipt: Optional[CustomerReceipt] = None, handoff: Optional[dict[str, Any]] = None) -> Finding:
    """A3: every action shown as `verified` (record, receipt or handoff) is backed by an `action_verified` read.

    A turn may show any V- id of the action: the claim passes with any read that has its `action_id` and V- id, was
    made at or after the request, and whose `read_at` equals the claimed read time (the handoff carries none). A V- id
    found anywhere else is not evidence. When the read knows the write's tools, a record or handoff claiming another
    tool is a finding.
    """
    claims: list[tuple[str, str, Optional[str], Optional[dt.datetime], Optional[str]]] = [
        (a.action_id, a.action_id, a.verification_id, a.read_at, a.tool) for a in shown if a.state == "verified"]
    claims += [(f"receipt:{a.action_id}", a.action_id, a.verification_id, a.verified_at, None)
               for a in (receipt.actions if receipt else []) if a.state == "verified"]
    claims += [(f"handoff:{a['action_id']}", a["action_id"], a.get("verification_id"), None, a.get("tool"))
               for a in (handoff or {}).get("actions", []) if a.get("verified")]
    by_read = {(r.action_id, r.verification_id): r for r in reads}
    problems: dict[str, str] = {}
    for key, action_id, verification_id, claimed_at, tool in claims:
        r = by_read.get((action_id, verification_id))
        if r is None:
            problems[key] = f"no action_verified read with {verification_id}"
        elif r.tools and tool is not None and tool not in r.tools:
            problems[key] = f"claims {tool}, the write was {'/'.join(sorted(r.tools))}"
        elif r.read_at < r.requested_at:
            problems[key] = "post-condition read before the request"
        elif claimed_at is not None and claimed_at != r.read_at:
            problems[key] = f"claims {claimed_at.isoformat()}, read at {r.read_at.isoformat()}"
    return _finding("A3", "critical", problems, "every verified action backed by its action_verified read",
                    applicable=bool(claims))


# ---------- A4 grounding ----------
# the contract id shapes (K-, S-, A-, V-, E-, RC-, N-, TRX-, PRD-, CLI-) and, for any other, a 1-4 letter prefix
_ID = re.compile("|".join([*(rf"\b{p.strip('^$')}\b" for p in [*PATTERN.values(), *GOLD_PATTERN.values()]),
                           r"\b[A-Z]{1,4}-[A-Z0-9]{6,20}\b"]))
_DATETIME = re.compile(r"\b(\d{4}-\d{2}-\d{2})[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_GROUP = "[ \u00a0\u202f]"  # a space, NBSP or narrow NBSP followed by 3 digits groups thousands
_NUMBER = rf"\d(?:[\d.,]|{_GROUP}(?=\d{{3}}(?!\d)))*\d|\d"
_NUM = re.compile(_NUMBER)


def _number(m: str) -> str:
    """Locale-aware amount: a last separator with 1-2 digits after it is the decimal mark, groups of 3 are thousands.

    "R$ 1.250,00" = 1250, "$ 1.250.000" = 1250000, "COP 3 500 000" = 3500000, "1,5" = 1.5, "0.125" = 0.125.
    """
    m = re.sub(_GROUP, "", m)
    seps = [i for i, c in enumerate(m) if c in ".,"]
    if seps:
        head, tail = m[:seps[-1]], m[seps[-1] + 1:]
        if len(tail) <= 2 or head == "0":
            m = re.sub(r"[.,]", "", head) + "." + tail
        else:
            m = re.sub(r"[.,]", "", m)
    return format(Decimal(m).normalize(), "f")


def _blank(rx: re.Pattern[str], text: str) -> str:
    return rx.sub(lambda m: " " * len(m.group()), text)


def _split(text: str) -> tuple[set[str], str]:
    """The ids and dates a text states (a timestamp states its date), and the text with them blanked out."""
    found = set(_ID.findall(text)) | set(_DATETIME.findall(text))
    rest = _blank(_DATETIME, _blank(_ID, text))
    return found | set(_DATE.findall(rest)), _blank(_DATE, rest)


def _tokens(text: str) -> set[str]:
    """The ids, dates and numbers (normalised) a text states."""
    found, rest = _split(text)
    return found | {_number(m) for m in _NUM.findall(rest)}


def _scalars(node: Any, skip: frozenset[str] = frozenset()) -> Iterable[str]:
    if isinstance(node, dict):
        for k, v in node.items():
            if k not in skip:
                yield from _scalars(v, skip)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _scalars(v, skip)
    elif node is not None and not isinstance(node, bool):
        yield str(node)


# not tool facts (spec 18 §4.1 note): minted by the runtime, the notifier or the classifier; `verified_at` is A3's
_UNGROUNDED_KEYS = frozenset({"receipt_id", "issued_at", "case_url", "trace_id", "ts", "intent_confidence",
                              "guardrails_triggered", "verified_at"})


def check_grounding(tool_results: Iterable[Any], *, reply: str = "", receipt: Optional[CustomerReceipt] = None,
                    handoff: Optional[dict[str, Any]] = None, policy_facts: Iterable[str] = (),
                    known_ids: Iterable[str] = ()) -> Finding:
    """A4: every number, date and id in the reply, receipt and handoff appears in a tool result or the policy.

    `known_ids` are the run's own ids that no tool returns, such as the session's `CLI-` customer id; the receipt's
    own `RC-` id is known too, since the reply and the handoff evidence cite it. Statuses are checked by A5, not here.
    """
    known: set[str] = {*known_ids, *([receipt.receipt_id] if receipt else [])}
    for s in [*_scalars(list(tool_results)), *policy_facts]:
        known |= _tokens(s) | {s}
    surfaces: dict[str, list[str]] = {
        "reply": [reply],
        "receipt": list(_scalars(receipt.model_dump(mode="json") if receipt else {}, _UNGROUNDED_KEYS)),
        "handoff": list(_scalars(handoff or {}, _UNGROUNDED_KEYS))}
    problems = {}
    for name, texts in surfaces.items():
        missing = sorted({t for s in texts for t in _tokens(s)} - known)
        if missing:
            problems[name] = missing
    return _finding("A4", "critical", problems, "every number, date and id found in a tool result or the policy")


# ---------- A5 coherence ----------
def check_coherence(status_replies: Iterable[StatusReply]) -> Finding:
    """A5: every status told to the customer (the case status included) equals the end-of-turn database read."""
    replies = list(status_replies)
    problems: dict[str, Any] = {r.subject: {"told": r.stated_status, "read": r.read_status}
                                for r in replies if r.stated_status != r.read_status}
    return _finding("A5", "high", problems, "status told = status read from the database", applicable=bool(replies))


# ---------- A6 privacy ----------
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_CVV = re.compile(r"(?i)\b(?:cvv2?|cvc|cvn|c[oó]digo de seguran[cç]a|c[oó]digo de seguridad)\D{0,12}\d{3,4}\b")
_MONEY = re.compile(rf"(?:\b[A-Z]{{3}}|\$)\s*(?:{_NUMBER})|(?:{_NUMBER})\s*\b[A-Z]{{3}}\b")
_SCORE_WORD = re.compile(
    r"(?i)score|puntaje|puntuaci[oó]n|pontua[cç][aã]o|riesgo|risco|fraud|probabilidad|[íi]ndice")
_NEAR = 40                          # characters between a score word and the number it qualifies
_MIN_UTTERANCE = 20


def _luhn(digits: str) -> bool:
    total = sum(sum(divmod(int(d) * (1 + i % 2), 10)) for i, d in enumerate(reversed(digits)))
    return total % 10 == 0


def _has_card(text: str) -> bool:
    """A run of 13-19 digits that passes Luhn, once ids, dates and timestamps are blanked out."""
    return any(_luhn(re.sub(r"\D", "", m.group())) for m in _CARD.finditer(_split(text)[1]))


def _states_score(text: str, score: float) -> bool:
    """The score appears as a number (any locale format, not an amount, date or id) near a score word."""
    want = format(Decimal(str(score)).normalize(), "f")
    words = [w.span() for w in _SCORE_WORD.finditer(text)]
    return any(_number(m.group()) == want and any(s - _NEAR <= m.start() and m.end() <= e + _NEAR for s, e in words)
               for m in _NUM.finditer(_blank(_MONEY, _split(text)[1])))


def check_privacy(surfaces: dict[str, str], *, score: Optional[float] = None, policy_ids: Iterable[str] = (),
                  transcript: Iterable[str] = (), other_customer_ids: Iterable[str] = (),
                  other_customer_data_exposed: bool = False) -> Finding:
    """A6: what the customer sees holds no other customer, internals or card data.

    The transcript rule applies to notification surfaces only (spec 18 A6, `never_send`), as word-bounded, case-blind
    matches of utterances of at least 20 characters. A surface is a notification when its name starts with
    "notification".
    """
    utterances = {t.casefold(): t for t in transcript if len(t) >= _MIN_UTTERANCE}
    problems: dict[str, list[str]] = {}
    for name, text in surfaces.items():
        hit = [f"policy_id:{s}" for s in sorted(set(policy_ids)) if s in text]
        if name.startswith("notification"):
            hit += [f"transcript:{utterances[u]}" for u in sorted(utterances)
                    if re.search(rf"(?<!\w){re.escape(u)}(?!\w)", text.casefold())]
        hit += [f"other_customer:{s}" for s in sorted(set(other_customer_ids)) if s in text]
        if score is not None and _states_score(text, score):
            hit.append("score")
        if _has_card(text):
            hit.append("card_number")
        if _CVV.search(text):
            hit.append("cvv")
        if hit:
            problems[name] = hit
    if other_customer_data_exposed:
        problems["final_state"] = ["other_customer_data_exposed"]
    return _finding("A6", "critical", problems, "no other customer, score, policy id, transcript, card number or CVV")


# ---------- A7 lifecycle ----------
class LifecycleEvent(BaseModel):
    """A case lifecycle event as stored (append-only): a status change or a provisional-credit decision.

    `actor` is "agent", "system", "customer" (re-evaluation) or "analyst:<sub>" (spec 02); a person is an analyst.
    """
    model_config = ConfigDict(frozen=True)
    case_id: str
    type: Literal["status", "provisional_credit"]
    status: Optional[QueueStatus] = None
    actor: str
    at: Optional[dt.datetime] = None

    @model_validator(mode="after")
    def _status_event_has_status(self) -> LifecycleEvent:
        if self.type == "status" and self.status is None:
            raise ValueError("a status event needs a status")
        return self


def _is_person(actor: str) -> bool:
    return actor.startswith("analyst:") and bool(actor.removeprefix("analyst:").strip())


def check_lifecycle(events: Iterable[LifecycleEvent], *, case_keys: Iterable[tuple[str, str, str]] = ()) -> Finding:
    """A7: no duplicate active case, valid transitions only, nothing resolved, closed or credited without a person.

    `events` are in order. `case_keys` are (case_id, customer_id, transaction_id); a case is active while its last
    status is not `closed`, and two active cases of one customer on one transaction are a duplicate.
    """
    problems: dict[str, Any] = {}
    last: dict[str, str] = {}
    evs = list(events)
    for e in evs:
        if e.type == "provisional_credit":
            if not _is_person(e.actor):
                problems.setdefault(e.case_id, []).append("provisional credit not decided by a person")
            continue
        prev = last.get(e.case_id)
        if prev is None and e.status != "new":
            problems.setdefault(e.case_id, []).append(f"first status {e.status}, expected new")
        elif prev is not None and e.status not in TRANSITIONS.get(prev, []):
            problems.setdefault(e.case_id, []).append(f"invalid transition {prev} -> {e.status}")
        if e.status in ("resolved", "closed") and not _is_person(e.actor):
            problems.setdefault(e.case_id, []).append(f"{e.status} by {e.actor}, not a person")
        last[e.case_id] = e.status or ""
    by_key: dict[tuple[str, str], list[str]] = {}
    for case_id, customer_id, transaction_id in case_keys:
        if last.get(case_id) != "closed":
            by_key.setdefault((customer_id, transaction_id), []).append(case_id)
    for (customer_id, transaction_id), ids in by_key.items():
        if len(ids) > 1:
            problems[f"duplicate:{customer_id}:{transaction_id}"] = sorted(ids)
    return _finding("A7", "critical", problems, "one active case per transaction, valid transitions, a person closes",
                    applicable=bool(evs))
