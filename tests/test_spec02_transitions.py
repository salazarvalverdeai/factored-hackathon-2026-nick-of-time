"""Spec 02 T4 — queue.transition() for analyst actions (AC-10, D-034) and queue.sla() (AC-11), over case_queue."""
from __future__ import annotations

import copy
import itertools
from datetime import date, datetime, timezone
from typing import get_args
from zoneinfo import ZoneInfo

import pytest
import yaml
from pydantic import ValidationError

from contracts.tools import AnalystActionIn
from nick_of_time.policy import Deny, Moved, Policies, QueueCase, sla, transition
from nick_of_time.policy import clock
from nick_of_time.policy.model import POLICIES_PATH

RAW = yaml.safe_load(POLICIES_PATH.read_text())
STATES = ["new", "verification", "review", "resolved", "closed"]
ACTIONS = list(get_args(AnalystActionIn.model_fields["action"].annotation))
ANALYST = "analyst:a-17"
NOT_A_PERSON = ["agent", "customer", "system", "analyst:", "analyst:   ", "Analyst:a-17", ""]
X = "POL-QUEUE-TRANSITION"
# D-034 written out by hand: the status after each moving action, X = denied. Every other action keeps the status.
MOVES = {
    "new":          {"take": "review", "resolve": X, "close_case": X, "reopen_case": X},
    "verification": {"take": "review", "resolve": "resolved", "close_case": X, "reopen_case": X},
    "review":       {"take": "review", "resolve": "resolved", "close_case": X, "reopen_case": X},
    "resolved":     {"take": X, "resolve": X, "close_case": "closed", "reopen_case": "review"},
}


def expected(current: str, action: str) -> str:
    if current == "closed":
        return X                                          # D-034: nothing on a closed case
    return MOVES[current].get(action, current)


@pytest.mark.parametrize("current,action", list(itertools.product(STATES, ACTIONS)))
def test_ac_10_an_analyst_action_moves_only_as_d034_and_case_queue_allow(current, action):
    """AC-10, AC-12: every status × analyst action, against D-034; an allowed result cites its rule and version."""
    result, want = transition(current, action, ANALYST), expected(current, action)
    if want == X:
        assert isinstance(result, Deny) and result.policy_id == X and result.guardrail_id == "G-POL-01"
    else:
        assert isinstance(result, Moved) and (result.previous, result.status) == (current, want)
        assert "POL-QUEUE-TRANSITION" in result.rule_ids
        assert want == current or want in RAW["case_queue"]["transitions"][current]
    assert result.policies_version == RAW["version"]


@pytest.mark.parametrize("actor", NOT_A_PERSON)
@pytest.mark.parametrize("current", STATES)
def test_ac_10_close_by_a_non_human_actor_is_denied_with_pol_close_human(actor, current):
    """AC-10: close requested by anyone but a signed-in person → POL-CLOSE-HUMAN, before the status is looked at."""
    result = transition(current, "close_case", actor)
    assert isinstance(result, Deny) and result.policy_id == "POL-CLOSE-HUMAN" and result.rule_ids == ["POL-CLOSE-HUMAN"]


@pytest.mark.parametrize("action", [a for a in ACTIONS if a != "close_case"])
@pytest.mark.parametrize("actor", ["agent", "system", "analyst: "])
def test_ac_10_no_analyst_action_runs_without_a_person(actor, action):
    """AC-10 [assumption]: every other analyst action by a non-person is denied by default (actors.analyst human_only)."""
    result = transition("review", action, actor)
    assert isinstance(result, Deny) and result.policy_id == "POL-DEFAULT-DENY"


def test_ac_10_a_person_closing_a_resolved_case_cites_both_rules():
    """AC-10, AC-12: the allowed close names the transition rule and the person rule it passed."""
    result = transition("resolved", "close_case", ANALYST)
    assert isinstance(result, Moved) and result.status == "closed"
    assert result.rule_ids == ["POL-QUEUE-TRANSITION", "POL-CLOSE-HUMAN"]


@pytest.mark.parametrize("action", ["delete_case", "approve_refund", "", "RESOLVE"])
def test_ac_10_an_unknown_action_is_denied_by_default(action):
    """AC-10, AC-05: an action the analyst api does not list is POL-DEFAULT-DENY."""
    result = transition("review", action, ANALYST)
    assert isinstance(result, Deny) and result.policy_id == "POL-DEFAULT-DENY"


@pytest.mark.parametrize("current", ["open", "Closed", "", "ambiguous"])
def test_ac_10_an_unknown_status_is_an_input_error(current):
    """AC-10: a status outside case_queue.states is never guessed."""
    with pytest.raises(ValueError, match="unknown queue status"):
        transition(current, "resolve", ANALYST)


@pytest.mark.parametrize("path,value,error", [
    (("transitions", "closed"), ["review"], "nothing leaves closed"),
    (("transitions", "review"), ["resolved", "closed"], "only a resolved case can be closed"),
    (("states",), ["new", "review", "resolved", "closed"], "every queue status"),
    (("transitions", "ambiguous"), ["review"], "Input should be"),
    (("sla_hours", "review"), 0, "sla_hours.review must be positive"),
    (("deadline_sla", "mx_debit", "raise_priority_on_business_day"), 2, "priority must rise before the alert"),
    (("deadline_sla", "mx_debit", "applies_to", "product"), "prepaid", "Input should be"),
])
def test_ac_10_the_loader_refuses_a_queue_that_breaks_a_firm_rule(path, value, error):
    """AC-10, FR-01, FR-06: a broken case_queue fails at startup, not at transition time."""
    raw = copy.deepcopy(RAW)
    node = raw["case_queue"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValidationError, match=error):
        Policies.model_validate(raw)


# ---------- sla() (AC-11) ----------
MX = ZoneInfo("America/Mexico_City")


def case(status="verification", country="MX", product="debit", opened=date(2026, 6, 1), since=None) -> QueueCase:
    since = since or datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)
    return QueueCase(status=status, status_since=since, country=country, product_type=product, opened_on=opened)


@pytest.mark.parametrize("opened,today,priority,alert", [
    (date(2026, 6, 1), date(2026, 6, 1), "normal", date(2026, 6, 3)),     # Monday: day 1 Tue, day 2 Wed
    (date(2026, 6, 1), date(2026, 6, 2), "high", date(2026, 6, 3)),
    (date(2026, 6, 1), date(2026, 6, 3), "high", date(2026, 6, 3)),
    (date(2026, 6, 5), date(2026, 6, 7), "normal", date(2026, 6, 9)),     # Friday: the weekend does not count
    (date(2026, 6, 5), date(2026, 6, 8), "high", date(2026, 6, 9)),
    (date(2026, 9, 15), date(2026, 9, 16), "normal", date(2026, 9, 18)),  # 09-16 is a MX bank holiday (CNBV 2026)
    (date(2026, 9, 15), date(2026, 9, 17), "high", date(2026, 9, 18)),
])
def test_ac_11_a_mx_debit_case_rises_on_business_day_1_and_alerts_before_day_2(opened, today, priority, alert):
    """AC-11: priority high from business day 1 after opening; the alert is due at the start of business day 2 in the
    country's time zone (case_queue.deadline_sla.mx_debit, §4.3)."""
    result = sla(case(opened=opened), today=today)
    assert result.priority == priority
    assert result.alert_due_at == datetime.combine(alert, datetime.min.time(), tzinfo=MX)
    assert "case_queue.deadline_sla.mx_debit" in result.rule_ids and result.policies_version == RAW["version"]


@pytest.mark.parametrize("country,product,status", [("MX", "credit", "review"), ("CO", "debit", "review"),
                                                    ("AR", "credit", "verification"), ("MX", "debit", "resolved"),
                                                    ("MX", "debit", "closed")])
def test_ac_11_other_scopes_and_finished_cases_keep_normal_priority(country, product, status):
    """AC-11 [assumption]: only an open (not resolved or closed) case in a deadline_sla scope rises or alerts."""
    result = sla(case(status=status, country=country, product=product), today=date(2026, 6, 30))
    assert (result.priority, result.alert_due_at) == ("normal", None)


@pytest.mark.parametrize("status,due", [("verification", datetime(2026, 6, 1, 19, tzinfo=timezone.utc)),
                                        ("review", datetime(2026, 6, 2, 15, tzinfo=timezone.utc)),
                                        ("new", None), ("resolved", None), ("closed", None)])
def test_ac_11_the_sla_due_time_follows_sla_hours_of_the_status(status, due):
    """AC-11, FR-06: sla_due_at = when the case entered its status + case_queue.sla_hours (verification 4 h, review
    24 h); none for a status without an entry."""
    result = sla(case(status=status, country="CO"), today=date(2026, 6, 1))
    assert result.sla_due_at == due
    assert (f"case_queue.sla_hours.{status}" in result.rule_ids) == (due is not None)


def test_ac_11_past_the_last_holiday_file_it_escalates_and_invents_no_alert_time():
    """AC-11, AC-14: no 2027 MX calendar → priority high now, no alert date, POL-CLOCK-UNKNOWN."""
    result = sla(case(opened=date(2026, 12, 31)), today=date(2026, 12, 31))
    assert (result.priority, result.alert_due_at) == ("high", None) and "POL-CLOCK-UNKNOWN" in result.rule_ids


def test_ac_13_queue_results_are_deterministic_and_never_read_the_clock(monkeypatch):
    """AC-13, AC-16: same input, same output; the system clock is never read (today is an argument)."""
    monkeypatch.setattr(clock, "_system_now", lambda: pytest.fail("the queue read the system clock"))
    first = [sla(case(), today=clock.today("replay", "MX")).model_dump(), transition("review", "resolve", ANALYST)]
    second = [sla(case(), today=clock.today("replay", "MX")).model_dump(), transition("review", "resolve", ANALYST)]
    assert first == second
