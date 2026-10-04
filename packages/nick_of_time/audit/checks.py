"""Checks A3–A7 of spec 18 §4.1. Each returns one `Finding` with the exact facts it compared (expected vs observed)."""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Literal, Optional

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from nick_of_time.contracts import (CONTRACTS_DIR, ActionRecord, ActionState, CustomerReceipt, QueueStatus,
                                    StatusReply)

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
    """The database's own read of an action at the end of the turn, and when the action was requested."""
    model_config = ConfigDict(frozen=True)
    action_id: str
    state: ActionState
    verification_id: Optional[str] = None
    requested_at: AwareDatetime


def check_actions(shown: Iterable[ActionRecord], db: Iterable[ActionRead], *,
                  receipt: Optional[CustomerReceipt] = None, handoff: Optional[dict[str, Any]] = None) -> Finding:
    """A3: every action shown as `verified` (record, receipt or handoff) was read after its request; the db agrees.

    Each claim is normalised to (key, action_id, verification_id, read time, timed). The handoff carries no read time,
    so only the database comparison applies to it.
    """
    claims: list[tuple[str, str, Optional[str], Optional[dt.datetime], bool]] = [
        (a.action_id, a.action_id, a.verification_id, a.read_at, True) for a in shown if a.state == "verified"]
    claims += [(f"receipt:{a.action_id}", a.action_id, a.verification_id, a.verified_at, True)
               for a in (receipt.actions if receipt else []) if a.state == "verified"]
    claims += [(f"handoff:{a['action_id']}", a["action_id"], a.get("verification_id"), None, False)
               for a in (handoff or {}).get("actions", []) if a.get("verified")]
    reads = {r.action_id: r for r in db}
    problems: dict[str, str] = {}
    for key, action_id, verification_id, read_at, timed in claims:
        r = reads.get(action_id)
        if r is None:
            problems[key] = "no database read"
        elif r.state != "verified" or r.verification_id != verification_id:
            problems[key] = f"database says {r.state} {r.verification_id}"
        elif timed and (read_at is None or read_at < r.requested_at):
            problems[key] = "post-condition not read after the request"
    return _finding("A3", "critical", problems, "every verified action read after its request and confirmed by the db",
                    applicable=bool(claims))


# ---------- A4 grounding ----------
_ID = re.compile(r"\b[A-Z]{1,4}-[A-Z0-9]{6,20}\b")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUM = re.compile(r"\d[\d.,]*\d|\d")


def _number(m: str) -> str:
    """Locale-aware amount: a last separator with 1-2 digits after it is the decimal mark, groups of 3 are thousands.

    "R$ 1.250,00" = 1250, "$ 1.250.000" = 1250000, "1,5" = 1.5, "1,250.00" = 1250, "0.125" = 0.125.
    """
    seps = [i for i, c in enumerate(m) if c in ".,"]
    if seps:
        head, tail = m[:seps[-1]], m[seps[-1] + 1:]
        if len(tail) <= 2 or head == "0":
            m = re.sub(r"[.,]", "", head) + "." + tail
        else:
            m = re.sub(r"[.,]", "", m)
    return format(Decimal(m).normalize(), "f")


def _numbers(text: str) -> list[str]:
    out = []
    for m in _NUM.findall(_DATE.sub(" ", _ID.sub(" ", text))):
        try:
            out.append(_number(m))
        except InvalidOperation:
            out.append(m)
    return out


def _tokens(text: str) -> set[str]:
    """The ids, dates and numbers (normalised) a text states."""
    return set(_ID.findall(text)) | set(_DATE.findall(text)) | set(_numbers(text))


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


# generated by us, free policy text or classifier output, not read from a tool: never a grounded fact
_UNGROUNDED_KEYS = frozenset({"intent_confidence", "guardrails_triggered", "ts", "receipt_id", "issued_at",
                              "verified_at", "verified_on", "case_url", "source_url", "deadline_source", "trace_id",
                              "language", "mode", "label", "zone"})


def check_grounding(tool_results: Iterable[Any], *, reply: str = "", receipt: Optional[CustomerReceipt] = None,
                    handoff: Optional[dict[str, Any]] = None, policy_facts: Iterable[str] = ()) -> Finding:
    """A4: every number, date and id in the reply, receipt and handoff appears in a tool result or the policy.

    Statuses are checked by A5, not here.
    """
    known: set[str] = set()
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
_MONEY = re.compile(r"(?:\b[A-Z]{3}|\$)\s*\d[\d.,]*|\d[\d.,]*\s*\b[A-Z]{3}\b")
_MIN_UTTERANCE = 20


def _luhn(digits: str) -> bool:
    total = sum(sum(divmod(int(d) * (1 + i % 2), 10)) for i, d in enumerate(reversed(digits)))
    return total % 10 == 0


def _has_card(text: str) -> bool:
    return any(13 <= len(d := re.sub(r"\D", "", m.group())) <= 19 and _luhn(d) for m in _CARD.finditer(text))


def _states_score(text: str, score: float) -> bool:
    """The score appears as a number (any locale format) that is not an amount, date or id."""
    return format(Decimal(str(score)).normalize(), "f") in _numbers(_MONEY.sub(" ", text))


def check_privacy(surfaces: dict[str, str], *, score: Optional[float] = None, policy_ids: Iterable[str] = (),
                  transcript: Iterable[str] = (), other_customer_ids: Iterable[str] = (),
                  other_customer_data_exposed: bool = False) -> Finding:
    """A6: what the customer sees holds no other customer, internals or card data.

    The transcript rule applies to notification surfaces only (spec 18 A6, `never_send`), as word-bounded matches of
    utterances of at least 20 characters. A surface is a notification when its name starts with "notification".
    """
    utterances = {t for t in transcript if len(t) >= _MIN_UTTERANCE}
    problems: dict[str, list[str]] = {}
    for name, text in surfaces.items():
        hit = [f"policy_id:{s}" for s in sorted(set(policy_ids)) if s in text]
        if name.startswith("notification"):
            hit += [f"transcript:{u}" for u in sorted(utterances) if re.search(rf"(?<!\w){re.escape(u)}(?!\w)", text)]
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
    return actor.startswith("analyst:")


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
