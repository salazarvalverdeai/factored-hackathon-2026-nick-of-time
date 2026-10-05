"""Spec 02 T3 + T7 (task 02b): the regulatory clock, holiday calendars, clock.today(mode, country) and time zones."""
from __future__ import annotations

import copy
import inspect
import re
from datetime import date as D, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nick_of_time.policy import clock
from nick_of_time.policy.model import POLICIES_PATH, Policies, load_policies

RAW = yaml.safe_load(POLICIES_PATH.read_text())
OPENED = clock.DEMO_TODAY                                   # Monday 2026-06-01 (ADR 0020)
VERIFIED = D(2026, 10, 4)


def policies_with(path: str, value) -> dict:
    raw = copy.deepcopy(RAW)
    *parents, key = path.split(".")
    node = raw
    for name in parents:
        node = node[int(name)] if isinstance(node, list) else node[name]
    if isinstance(node, list):
        key = int(key)
    if value is None:
        del node[key]
    else:
        node[key] = value
    return raw


def boom():
    raise AssertionError("the system clock was read")


ROWS = [  # country, product, kwargs, credit_deadline, ruling_deadline, weekday holidays skipped, source
    ("MX", "debit", {"charged_at": D(2026, 5, 31)}, D(2026, 6, 3), D(2026, 7, 16), [], "Banxico Circular 3/2012"),
    ("MX", "debit", {"charged_at": D(2026, 3, 2)}, None, D(2026, 7, 16), [], "LTOSF art. 23"),
    ("MX", "debit", {"charged_at": D(2026, 3, 2), "abroad": True}, None, D(2026, 11, 28), [], "LTOSF art. 23"),
    ("MX", "credit", {}, None, D(2026, 7, 16), [], "LTOSF art. 23"),
    ("MX", "credit", {"abroad": True}, None, D(2026, 11, 28), [], "LTOSF art. 23"),
    ("AR", "debit", {}, D(2026, 6, 16), D(2026, 6, 16), [D(2026, 6, 15)], "BCRA"),
    ("AR", "credit", {"abroad": True}, D(2026, 6, 16), D(2026, 6, 16), [D(2026, 6, 15)], "BCRA"),
]


@pytest.mark.parametrize("country, product, kwargs, credit, ruling, skipped, source", ROWS,
                         ids=[f"{r[0]}-{r[1]}-{i}" for i, r in enumerate(ROWS)])
def test_ac_03_every_country_and_product_row_from_the_demo_date(country, product, kwargs, credit, ruling, skipped,
                                                                 source):
    """AC-03: opened on Monday 2026-06-01; business days skip weekends and the country's 2026 holidays."""
    d = clock.deadline(country, product, OPENED, **kwargs)
    assert (d.credit_deadline, d.ruling_deadline, d.holidays_skipped) == (credit, ruling, skipped)
    assert d.deadline_source.startswith(source) and d.source_url.startswith("https://") and d.verified_on == VERIFIED
    assert d.rule_ids == [] and d.policies_version == 2 and not d.extendable_once


@pytest.mark.parametrize("age, credited", [(0, True), (89, True), (90, True), (91, False), (200, False)])
def test_ac_03_mx_debit_credit_only_for_a_claim_within_90_days_of_the_charge(age, credited):
    """AC-03 as verified in T3: art. 19 Bis 3 fr. II; an older charge gets the LTOSF art. 23 ruling instead."""
    d = clock.deadline("MX", "debit", OPENED, charged_at=OPENED - timedelta(days=age))
    assert d.credit_deadline == (D(2026, 6, 3) if credited else None) and d.ruling_deadline == D(2026, 7, 16)


def test_ac_03_the_charge_date_is_local_near_midnight():
    """AC-03 + AC-16: 2026-03-03 05:30 UTC is 2026-03-02 23:30 in Mexico City, 91 days before the notice."""
    late = datetime(2026, 3, 3, 5, 30, tzinfo=timezone.utc)
    assert clock.deadline("MX", "debit", OPENED, charged_at=late).credit_deadline is None
    assert clock.deadline("MX", "debit", OPENED, charged_at=late + timedelta(hours=1)).credit_deadline == D(2026, 6, 3)


@pytest.mark.parametrize("before, credited", [(timedelta(hours=47, minutes=59), True), (timedelta(hours=48), True),
                                              (timedelta(hours=48, minutes=1), False)])
def test_ac_03_an_hours_window_is_exact_to_the_minute(before, credited):
    """AC-03 boundary 47:59 / 48:00 / 48:01 for an entry shaped `when_charged_within: {hours: 48}` (fr. I, theft or loss)."""
    p = Policies.model_validate(policies_with("regulatory_clock.MX.debit.0.when_charged_within", {"hours": 48}))
    noticed = datetime(2026, 6, 1, 16, 0, tzinfo=timezone.utc)                  # 10:00 in Mexico City
    charged = datetime(2026, 6, 1, 10, 0) - before                               # naive = local time
    d = clock.deadline("MX", "debit", OPENED, charged_at=charged, noticed_at=noticed, policies=p)
    assert d.credit_deadline == (D(2026, 6, 3) if credited else None)


def test_ac_03_a_charge_age_rule_needs_its_inputs():
    with pytest.raises(ValueError, match="charged_at"):
        clock.deadline("MX", "debit", OPENED)
    with pytest.raises(ValueError, match="after the notice"):
        clock.deadline("MX", "debit", OPENED, charged_at=D(2026, 6, 2))


ADD = [("MX", D(2026, 6, 1), 1, D(2026, 6, 2)),       # D-008
       ("MX", D(2026, 5, 29), 1, D(2026, 6, 1)),      # Friday → Monday
       ("MX", D(2026, 5, 30), 2, D(2026, 6, 2)),      # notice on a Saturday
       ("MX", D(2026, 4, 1), 2, D(2026, 4, 7)),       # Holy Thursday and Good Friday, then the weekend
       ("MX", D(2026, 9, 15), 1, D(2026, 9, 17)),     # Independence Day
       ("MX", D(2026, 11, 13), 2, D(2026, 11, 18)),   # Revolution Day, third Monday of November
       ("AR", D(2026, 11, 6), 1, D(2026, 11, 10)),    # papal visit Monday (Decreto 1103/2026)
       ("AR", D(2026, 3, 20), 1, D(2026, 3, 23))]     # a "día no laborable" counts [assumption, conservative]


@pytest.mark.parametrize("country, start, n, expected", ADD)
def test_ac_03_add_business_days_skips_weekends_and_holidays(country, start, n, expected):
    assert clock.add_business_days(country, start, n) == expected


@pytest.mark.parametrize("n", [0, -1, 1.5, True])
def test_d008_add_business_days_needs_a_positive_integer(n):
    with pytest.raises(ValueError):
        clock.add_business_days("MX", OPENED, n)


@pytest.mark.parametrize("country, product", [("PE", "debit"), ("CL", "credit"), ("XX", "debit"), ("MX", "prepaid"),
                                              ("AR", "any")])
def test_ac_14_no_verified_entry_means_no_deadline(country, product):
    d = clock.deadline(country, product, OPENED, charged_at=D(2026, 5, 31))
    assert (d.credit_deadline, d.ruling_deadline, d.deadline_source, d.source_url) == (None, None, None, None)
    assert d.rule_ids == ["POL-CLOCK-UNKNOWN"] and "POL-CLOCK-UNKNOWN" in RAW["rules"]


def test_ac_14_no_business_day_is_invented_past_the_verified_calendar():
    with pytest.raises(clock.CalendarNotCovered):
        clock.add_business_days("MX", D(2026, 12, 31), 1)
    assert clock.deadline("AR", "debit", D(2026, 12, 21)).rule_ids == ["POL-CLOCK-UNKNOWN"]
    assert clock.deadline("MX", "credit", D(2026, 12, 1)).ruling_deadline == D(2027, 1, 15)   # calendar days


def test_ac_06_no_amount_reaches_the_clock_and_a_deadline_never_reads_today(monkeypatch):
    """AC-06 and spec 03 AC-16: the deadline depends on the opening date only, so the stored value never changes."""
    assert not {"amount", "currency", "tier", "today", "mode"} & set(inspect.signature(clock.deadline).parameters)
    monkeypatch.setattr(clock, "_system_now", boom)
    first = clock.deadline("MX", "debit", OPENED, charged_at=D(2026, 5, 31))
    assert clock.deadline("MX", "debit", OPENED, charged_at=D(2026, 5, 31)) == first


def test_ac_16_replay_is_the_demo_date_and_never_reads_the_system_clock(monkeypatch):
    monkeypatch.setattr(clock, "_system_now", boom)
    assert {clock.today("replay", c) for c in ("MX", "CO", "AR", "BR", "XX")} == {D(2026, 6, 1)}
    with pytest.raises(ValueError):
        clock.today("demo", "MX")


@pytest.mark.parametrize("utc, country, local", [
    (datetime(2026, 10, 5, 4, 30, tzinfo=timezone.utc), "MX", D(2026, 10, 4)),   # 22:30 the day before
    (datetime(2026, 10, 5, 4, 30, tzinfo=timezone.utc), "CO", D(2026, 10, 4)),   # 23:30
    (datetime(2026, 10, 5, 4, 30, tzinfo=timezone.utc), "AR", D(2026, 10, 5)),   # 01:30
    (datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc), "MX", D(2026, 10, 5)),    # 00:00 exactly
    (datetime(2026, 10, 5, 2, 59, tzinfo=timezone.utc), "BR", D(2026, 10, 4))])  # 23:59
def test_ac_16_live_is_the_real_date_in_the_country_time_zone(monkeypatch, utc, country, local):
    assert clock.today("live", country, utc_now=utc) == local
    monkeypatch.setattr(clock, "_system_now", lambda: utc)
    assert clock.today("live", country) == local
    with pytest.raises(ValueError):
        clock.today("live", country, utc_now=utc.replace(tzinfo=None))


def test_ac_16_only_system_now_reads_the_system_clock():
    reads = re.compile(r"datetime\.now\(|date\.today\(|time\.time\(|datetime\.utcnow\(")
    hits = {p.name: len(reads.findall(p.read_text())) for p in Path(clock.__file__).parent.glob("*.py")}
    assert hits.pop("clock.py") == 1 and not any(hits.values())


def test_ac_16_time_zones_follow_spec_section_4_4():
    zones = {c: v["time_zone"] for c, v in RAW["countries"].items()}
    assert zones == {"MX": "America/Mexico_City", "CO": "America/Bogota", "AR": "America/Argentina/Buenos_Aires",
                     "PE": "America/Lima", "CL": "America/Santiago", "BR": "America/Sao_Paulo"}


def test_ac_03_holiday_files_cite_their_source_and_cover_2026():
    """ADR 0019: every country with business-day terms has a verified 2026 file; Monday rules are recomputed here."""
    for country in RAW["regulatory_clock"]:
        f = clock.holidays(country)[2026]
        assert f.source_url.startswith("https://") and f.verified_on == VERIFIED
    mondays = lambda month: [d for d in (D(2026, month, x) for x in range(1, 29)) if d.weekday() == 0]
    mx = set(clock.holidays("MX")[2026].holidays)
    assert {mondays(2)[0], mondays(3)[2], mondays(11)[2]} <= mx and len(mx) == 11


INVALID = [
    ("ADR 0019 no source_url", "regulatory_clock.AR.any.0.source_url", None),
    ("ADR 0019 no verified_on", "regulatory_clock.AR.any.0.verified_on", None),
    ("ADR 0019 plain http", "regulatory_clock.MX.debit.0.source_url", "http://www.banxico.org.mx/"),
    ("AC-03 entry without a term", "regulatory_clock.MX.credit.0.ruling", None),
    ("AC-03 window in hours and days", "regulatory_clock.MX.debit.0.when_charged_within", {"hours": 48, "days": 90}),
    ("AC-03 unknown product", "regulatory_clock.MX.prepaid", []),
    ("AC-16 unknown time zone", "countries.MX.time_zone", "America/Mexico_Cty"),
    ("AC-16 clock country without zone", "countries.AR", None),
    ("D-008 fractional", "contact.callback_within_business_days", 1.5),
    ("D-008 boolean", "contact.callback_within_business_days", True),
    ("D-008 zero", "contact.callback_within_business_days", 0),
]


@pytest.mark.parametrize("case, path, value", INVALID, ids=[c[0] for c in INVALID])
def test_ac_14_an_unverified_or_malformed_clock_fails_at_startup(case, path, value):
    with pytest.raises(ValidationError):
        Policies.model_validate(policies_with(path, value))


def test_d008_contact_window_is_one_business_day_and_optional():
    assert load_policies().contact.callback_within_business_days == 1
    assert Policies.model_validate(policies_with("contact", None)).contact is None
