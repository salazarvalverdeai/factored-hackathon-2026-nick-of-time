"""Regulatory clock (spec 02 §4.3, §6; ADRs 0019, 0020): "today" per mode, business days per country, legal deadlines.

Pure and deterministic. The system clock is read only by `_system_now()`, and only in live mode (AC-16). A deadline is a
function of the opening date, never of "today": callers compute it once at opening and store it (spec 03 AC-16). No
amount enters here, so the amount tier can never move a deadline (AC-06).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import cache
from pathlib import Path
from typing import Literal, Optional
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field

from nick_of_time.contracts import HTTPS_URL, Mode
from nick_of_time.policy.model import ChargeWindow, Policies, Term, load_policies

DEMO_TODAY = date(2026, 6, 1)          # replay "today" (ADR 0020): a Monday, the day after the gold ends
HOLIDAYS_DIR = Path(__file__).parent / "holidays"
UNKNOWN = "POL-CLOCK-UNKNOWN"


class CalendarNotCovered(LookupError):
    """A business-day count reached a year with no verified holiday file: no date is invented (AC-14)."""


class HolidayFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str = Field(min_length=1)
    source_url: str = Field(pattern=HTTPS_URL)
    verified_on: date
    holidays: dict[date, str]


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


@cache
def holidays(country: str) -> dict[int, HolidayFile]:
    """The country's verified holiday files by year, from holidays/{cc}_{year}.yaml."""
    files = {}
    for path in sorted(HOLIDAYS_DIR.glob(f"{country.lower()}_*.yaml")):
        year = int(path.stem.split("_")[1])
        files[year] = HolidayFile.model_validate(yaml.safe_load(path.read_text()))
        if any(day.year != year for day in files[year].holidays):
            raise ValueError(f"{path.name} lists a day outside {year}")
    return files


def is_business_day(country: str, day: date) -> bool:
    """Monday to Friday and not a holiday of the country (spec 02 §4.3)."""
    calendar = holidays(country).get(day.year)
    if calendar is None:
        raise CalendarNotCovered(f"no verified {country} holiday file for {day.year}")
    return day.weekday() < 5 and day not in calendar.holidays


def _walk(country: str, start: date, n: int) -> tuple[date, list[date]]:
    if type(n) is not int or n < 1:
        raise ValueError("n must be a positive integer")
    day, skipped = start, []
    while n:
        day += timedelta(days=1)
        if is_business_day(country, day):
            n -= 1
        elif day.weekday() < 5:
            skipped.append(day)
    return day, skipped


def add_business_days(country: str, start: date, n: int) -> date:
    """The n-th business day after `start` (D-008: MX 2026-06-01 + 1 → 2026-06-02). Raises CalendarNotCovered."""
    return _walk(country, start, n)[0]


def _local(moment: datetime, tz: ZoneInfo) -> datetime:
    return moment.astimezone(tz) if moment.tzinfo else moment.replace(tzinfo=tz)   # naive = local time [assumption]


def _charge_in_window(window: ChargeWindow, tz: ZoneInfo, opened_on: date, charged_at: date | datetime | None,
                      noticed_at: Optional[datetime]) -> bool:
    if charged_at is None:
        raise ValueError("this country's deadline depends on the charge's age: pass charged_at")
    if window.days is not None:          # calendar days between local dates; the last day counts [assumption]
        charged_on = _local(charged_at, tz).date() if isinstance(charged_at, datetime) else charged_at
        age, limit = opened_on - charged_on, timedelta(days=window.days)
    else:
        if noticed_at is None or not isinstance(charged_at, datetime):
            raise ValueError("an hours window needs the charge and notice times")
        age, limit = _local(noticed_at, tz) - _local(charged_at, tz), timedelta(hours=window.hours)
    if age < timedelta(0):
        raise ValueError("the charge is after the notice")
    return age <= limit


def _add(country: str, start: date, term: Term) -> tuple[date, list[date]]:
    if term.calendar == "calendar":
        return start + timedelta(days=term.days), []
    return _walk(country, start, term.days)


def deadline(country: str, product: str, opened_on: date, *, abroad: bool = False,
             charged_at: date | datetime | None = None, noticed_at: Optional[datetime] = None,
             policies: Optional[Policies] = None) -> Deadline:
    """Legal deadlines of a case opened on `opened_on` (the notice date), from the first applicable verified entry.

    `charged_at` is required when the entry depends on the charge's age (MX debit); a naive time is the country's local
    time. No verified entry or calendar → both dates null and POL-CLOCK-UNKNOWN (AC-14).
    """
    p = policies or load_policies()
    base = dict(country=country, product=product, opened_on=opened_on, policies_version=p.version)
    by_product = p.regulatory_clock.get(country, {})
    rows = by_product.get(product, by_product.get("any", [])) if product in ("debit", "credit") else []
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
