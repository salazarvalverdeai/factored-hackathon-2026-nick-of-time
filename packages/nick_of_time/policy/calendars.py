"""Business-day calendars (spec 02 §4.3): weekends plus each country's verified holidays/{cc}_{year}.yaml (ADR 0019).

Loaded and validated together with policies.yaml (FR-01), so a broken file fails at startup, not in the middle of a turn.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from nick_of_time.contracts import HTTPS_URL

HOLIDAYS_DIR = Path(__file__).parent / "holidays"


class CalendarNotCovered(LookupError):
    """A business-day count reached a year with no verified holiday file: no date is invented (AC-14)."""


class HolidayFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str = Field(min_length=1)
    source_url: str = Field(pattern=HTTPS_URL)
    verified_on: date
    holidays: dict[date, str]


@cache
def holidays(country: str) -> dict[int, HolidayFile]:
    """The country's verified holiday files by year."""
    files = {}
    for path in sorted(HOLIDAYS_DIR.glob(f"{country.lower()}_*.yaml")):
        year = int(path.stem.split("_")[1])
        files[year] = HolidayFile.model_validate(yaml.safe_load(path.read_text()))
        if any(day.year != year for day in files[year].holidays):
            raise ValueError(f"{path.name} lists a day outside {year}")
    return files


def is_business_day(country: str, day: date) -> bool:
    """Monday to Friday and not a holiday of the country."""
    calendar = holidays(country).get(day.year)
    if calendar is None:
        raise CalendarNotCovered(f"no verified {country} holiday file for {day.year}")
    return day.weekday() < 5 and day not in calendar.holidays


def walk(country: str, start: date, n: int) -> tuple[date, list[date]]:
    """The n-th business day after `start` and the weekday holidays skipped on the way."""
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
    return walk(country, start, n)[0]
