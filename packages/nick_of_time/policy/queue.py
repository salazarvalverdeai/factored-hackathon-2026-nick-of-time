"""Analyst queue (spec 02 FR-06, AC-10, AC-11; task 02c): transition() for an analyst action, sla() for a case.

Pure and deterministic over `policies.yaml` `case_queue`: no network, database or clock ("today" is an argument, from
`clock.today(mode, country)`, AC-16). A case's status is its last event (append-only): transition() only says which
status the next `status_changed` event may carry; the caller appends it.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Literal, Optional, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict

from nick_of_time.contracts import ProductType, QueueStatus
from nick_of_time.policy.calendars import CalendarNotCovered, add_business_days
from nick_of_time.policy.clock import time_zone
from nick_of_time.policy.engine import Deny
from nick_of_time.policy.model import CountryCode, Policies, load_policies

__all__ = ["ANALYST_SOURCES", "ANALYST_TARGETS", "HUMAN_ACTOR", "Moved", "QueueCase", "Sla", "sla", "transition"]

HUMAN_ACTOR = re.compile(r"analyst:.*\S.*")             # a person signed in to the console (spec 01 store ACTOR)
# D-034: the status each analyst action moves a case to; an action not listed keeps the status. [assumption] `take`
# always moves to review (a person is looking at it): review is the only target D-034 allows from every source.
ANALYST_TARGETS: dict[str, QueueStatus] = {"take": "review", "resolve": "resolved", "close_case": "closed",
                                           "reopen_case": "review"}
ANALYST_SOURCES: dict[str, frozenset[str]] = {"take": frozenset({"new", "verification", "review"}),
                                              "reopen_case": frozenset({"resolved"})}       # D-034
KEEPS = frozenset({"approve_credit", "approve_block", "unblock_card", "request_customer_info", "mark_ambiguous"})
CHECKED = ["POL-QUEUE-TRANSITION"]                        # the rule an allowed move passed (AC-12)


class Moved(BaseModel):
    """An allowed analyst action: the status the case has after it (`status == previous` when it keeps it)."""
    model_config = ConfigDict(frozen=True)
    action: str
    previous: QueueStatus
    status: QueueStatus
    rule_ids: list[str]
    policies_version: int


def _deny(p: Policies, action: str, policy_id: str) -> Deny:
    return Deny(action=action, policy_id=policy_id, guardrail_id=p.rules[policy_id].guardrail, rule_ids=[policy_id],
                policies_version=p.version)


def transition(current: str, action: str, actor: str, *, policies: Optional[Policies] = None) -> Union[Moved, Deny]:
    """May `actor` run analyst `action` on a case in `current`, and which status follows (AC-10, D-034)?

    Every analyst action needs a person (`approval.close: human_only`, actors.analyst `executed_by: human_only`):
    `close_case` by anyone else is POL-CLOSE-HUMAN; [assumption] any other analyst action by a non-person is
    POL-DEFAULT-DENY. A closed case takes nothing; `take` and `reopen_case` start only from their D-034 sources; a move
    not in `case_queue.transitions` is POL-QUEUE-TRANSITION. An unknown action is POL-DEFAULT-DENY.
    """
    p = policies or load_policies()
    q = p.case_queue
    if current not in q.states:
        raise ValueError(f"unknown queue status {current!r}")
    if action not in ANALYST_TARGETS and action not in KEEPS:
        return _deny(p, action, "POL-DEFAULT-DENY")
    if not isinstance(actor, str) or not HUMAN_ACTOR.fullmatch(actor):
        return _deny(p, action, "POL-CLOSE-HUMAN" if action == "close_case" else "POL-DEFAULT-DENY")
    if current == "closed" or current not in ANALYST_SOURCES.get(action, q.states):
        return _deny(p, action, "POL-QUEUE-TRANSITION")
    target = ANALYST_TARGETS.get(action, current)
    if action in ANALYST_TARGETS and target not in q.transitions[current]:
        return _deny(p, action, "POL-QUEUE-TRANSITION")
    rules = [*CHECKED, "POL-CLOSE-HUMAN"] if action == "close_case" else CHECKED
    return Moved(action=action, previous=current, status=target, rule_ids=rules, policies_version=p.version)


class QueueCase(BaseModel):
    """What sla() reads from a case: its status, when it entered it (its last `status_changed`, or the opening),
    country, product and business opening date (`clock.today` at opening, D-023)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: QueueStatus
    status_since: AwareDatetime
    country: CountryCode                                  # 'mx' is an input error, never a silent normal priority
    product_type: ProductType
    opened_on: date


class Sla(BaseModel):
    """`rule_ids` name the `case_queue` keys behind each value (the queue SLAs have no POL- id; AC-12)."""
    model_config = ConfigDict(frozen=True)
    priority: Literal["normal", "high"]
    sla_due_at: Optional[datetime] = None
    alert_due_at: Optional[datetime] = None
    rule_ids: list[str] = []
    policies_version: int


def sla(case: QueueCase, *, today: date, policies: Optional[Policies] = None) -> Sla:
    """SLA due time of the case's status and, for a scope of `case_queue.deadline_sla` (MX debit), the priority and
    alert (AC-11): priority `high` from business day `raise_priority_on_business_day` after opening, alert due at the
    start (local midnight) of business day `alert_before_business_day`.

    [assumption] Statuses without `sla_hours` (new, resolved, closed) have no SLA due time; a case is "open" for the
    deadline SLA until it is resolved, and the SLA applies to every open MX debit case, as AC-11 reads, whether or not
    its charge got a credit deadline. A business-day count past the last holiday file gives priority `high` and no
    alert time (POL-CLOCK-UNKNOWN): an earlier escalation, never an invented date.
    """
    p = policies or load_policies()
    q, rules = p.case_queue, []
    hours = q.sla_hours.get(case.status)
    due = case.status_since + timedelta(hours=hours) if hours is not None else None
    if due is not None:
        rules.append(f"case_queue.sla_hours.{case.status}")
    priority, alert = "normal", None
    for name, rule in q.deadline_sla.items():
        scope = rule.applies_to
        if (scope.country, scope.product) != (case.country, case.product_type) or case.status in ("resolved", "closed"):
            continue
        rules.append(f"case_queue.deadline_sla.{name}")
        try:
            raise_on = add_business_days(case.country, case.opened_on, rule.raise_priority_on_business_day)
            alert_on = add_business_days(case.country, case.opened_on, rule.alert_before_business_day)
        except CalendarNotCovered:
            priority = "high"
            rules.append("POL-CLOCK-UNKNOWN")
            continue
        priority = "high" if today >= raise_on else priority
        alert = datetime.combine(alert_on, time(0), tzinfo=time_zone(case.country, p))
    return Sla(priority=priority, sla_due_at=due, alert_due_at=alert, rule_ids=rules, policies_version=p.version)
