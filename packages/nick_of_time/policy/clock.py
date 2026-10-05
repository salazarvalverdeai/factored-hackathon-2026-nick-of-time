"""Regulatory clock (spec 02 §4.3, §6; ADRs 0019, 0020): "today" per mode, business days per country, legal deadlines.

Pure and deterministic. The system clock is read only by `_system_now()`, and only in live mode (AC-16). A deadline is a
function of the opening date, never of "today": callers compute it once at opening and store it (spec 03 AC-16). No
amount enters here, so the amount tier can never move a deadline (AC-06).
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from nick_of_time.contracts import Mode
from nick_of_time.policy.calendars import CalendarNotCovered, add_business_days, holidays, is_business_day, walk
from nick_of_time.policy.model import ChargeWindow, Policies, Term, load_policies

__all__ = ["DEMO_TODAY", "CalendarNotCovered", "Deadline", "add_business_days", "deadline", "holidays",
           "is_business_day", "time_zone", "today"]

DEMO_TODAY = date(2026, 6, 1)          # replay "today" (ADR 0020): a Monday, the day after the gold ends
UNKNOWN = "POL-CLOCK-UNKNOWN"
log = logging.getLogger(__name__)


def warn_if_demo_today_env_differs() -> None:
    """The constant wins (reproducible evaluation, ADR 0020); a stale DEMO_TODAY in a local .env only gets a warning."""
    value = os.environ.get("DEMO_TODAY")
    if value and value != DEMO_TODAY.isoformat():
        log.warning("DEMO_TODAY=%s is ignored: replay uses %s (ADR 0020)", value, DEMO_TODAY)


warn_if_demo_today_env_differs()


class Deadline(BaseModel):
    """Result of `deadline()`; both dates are null with POL-CLOCK-UNKNOWN when there is no verified entry."""
    model_config = ConfigDict(frozen=True)
    country: str
    product: str
    opened_on: date
    credit_deadline: Optional[date] = None
    ruling_deadline: Optional[date] = None
    deadline_source: Optional[str] = None
    source_url: Optional[str] = None
    verified_on: Optional[date] = None
    calendar: dict[Literal["credit", "ruling"], Literal["business", "calendar"]] = {}
    holidays_skipped: list[date] = []
    extendable_once: bool = False
    rule_ids: list[str] = []
    policies_version: int


def _system_now() -> datetime:
    """The only read of the system clock in the policy package; live mode only (AC-16)."""
    return datetime.now(timezone.utc)


def time_zone(country: str, policies: Optional[Policies] = None) -> ZoneInfo:
    entry = (policies or load_policies()).countries.get(country)
    return ZoneInfo(entry.time_zone if entry else "UTC")     # [assumption] unknown country: UTC; it gets no deadline


def today(mode: Mode, country: str, *, utc_now: Optional[datetime] = None,
          policies: Optional[Policies] = None) -> date:
    """`DEMO_TODAY` in replay; in live, the real date in the country's time zone (ADR 0020)."""
    if mode == "replay":
        return DEMO_TODAY
    if mode != "live":
        raise ValueError(f"unknown mode {mode!r}")
    now = utc_now or _system_now()
    if now.tzinfo is None:
        raise ValueError("utc_now must be timezone-aware")
    return now.astimezone(time_zone(country, policies)).date()


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:            # spec 01 §Time: timestamps are UTC; a naive one is ambiguous, never guessed
        raise ValueError("charged_at and noticed_at must be timezone-aware datetimes, or charged_at a date")
    return moment


def _charge_in_window(window: ChargeWindow, tz: ZoneInfo, opened_on: date, charged_at: date | datetime | None,
                      noticed_at: Optional[datetime]) -> bool:
    if charged_at is None:
        raise ValueError("this country's deadline depends on the charge's age: pass charged_at")
    if window.days is not None:          # calendar days between local dates; the last day counts [assumption]
        if isinstance(charged_at, datetime):
            age = opened_on - _aware(charged_at).astimezone(tz).date()
        else:                            # a bare date may be the UTC date, one day ahead of the local notice date
            age = opened_on - charged_at
            age = timedelta(0) if age == timedelta(days=-1) else age      # [assumption] same day, the earlier deadline
        limit = timedelta(days=window.days)
    else:
        if noticed_at is None or not isinstance(charged_at, datetime):
            raise ValueError("an hours window needs the charge and notice times")
        age, limit = _aware(noticed_at) - _aware(charged_at), timedelta(hours=window.hours)
    if age < timedelta(0):
        raise ValueError("the charge is after the notice")
    return age <= limit


def _add(country: str, start: date, term: Term) -> tuple[date, list[date]]:
    if term.calendar == "calendar":
        return start + timedelta(days=term.days), []
    return walk(country, start, term.days)


def deadline(country: str, product: str, opened_on: date, *, abroad: bool = False,
             charged_at: date | datetime | None = None, noticed_at: Optional[datetime] = None,
             policies: Optional[Policies] = None) -> Deadline:
    """Legal deadlines of a case opened on `opened_on` (the notice date), from the first applicable verified entry.

    `charged_at` (an aware datetime, or a date) is required when the entry depends on the charge's age (MX). No
    verified entry, or a business-day term past the last holiday file → no date at all and POL-CLOCK-UNKNOWN (AC-14).
    """
    p = policies or load_policies()
    base = dict(country=country, product=product, opened_on=opened_on, policies_version=p.version)
    by_product = p.regulatory_clock.get(country, {})
    rows = by_product.get(product, by_product.get("any", ())) if product in ("debit", "credit") else ()
    tz = time_zone(country, p)
    entry = next((e for e in rows if e.when_charged_within is None
                  or _charge_in_window(e.when_charged_within, tz, opened_on, charged_at, noticed_at)), None)
    if entry is None:
        return Deadline(**base, rule_ids=[UNKNOWN])
    terms = {"credit": entry.credit, "ruling": entry.ruling_abroad if abroad and entry.ruling_abroad else entry.ruling}
    terms = {name: term for name, term in terms.items() if term}
    try:
        dates = {name: _add(country, opened_on, term) for name, term in terms.items()}
    except CalendarNotCovered:
        return Deadline(**base, rule_ids=[UNKNOWN])
    return Deadline(**base, credit_deadline=dates.get("credit", (None,))[0],
                    ruling_deadline=dates.get("ruling", (None,))[0], deadline_source=entry.source,
                    source_url=entry.source_url, verified_on=entry.verified_on,
                    calendar={name: term.calendar for name, term in terms.items()},
                    holidays_skipped=sorted({d for _, skipped in dates.values() for d in skipped}),
                    extendable_once=entry.extendable_once)
