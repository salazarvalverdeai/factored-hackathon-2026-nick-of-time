"""Spec 02 T3 + T7 (task 02b): the regulatory clock, holiday calendars, clock.today(mode, country) and time zones."""
from __future__ import annotations

import copy
import inspect
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import date as D, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nick_of_time.policy import calendars, clock
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
    ("MX", "debit", {"charged_at": D(2026, 5, 31), "abroad": True}, D(2026, 6, 3), D(2026, 11, 28), [],
     "Banxico Circular 3/2012"),
    ("MX", "debit", {"charged_at": D(2026, 3, 2)}, None, D(2026, 7, 16), [], "LTOSF art. 23"),
    ("MX", "debit", {"charged_at": D(2026, 3, 2), "abroad": True}, None, D(2026, 11, 28), [], "LTOSF art. 23"),
    ("MX", "credit", {"charged_at": D(2026, 5, 31)}, D(2026, 6, 3), D(2026, 7, 16), [], "Banxico Circular 34/2010"),
    ("MX", "credit", {"charged_at": D(2026, 5, 31), "abroad": True}, D(2026, 6, 3), D(2026, 11, 28), [],
     "Banxico Circular 34/2010"),
    ("MX", "credit", {"charged_at": D(2026, 3, 2)}, None, D(2026, 7, 16), [], "LTOSF art. 23"),
    ("MX", "credit", {"charged_at": D(2026, 3, 2), "abroad": True}, None, D(2026, 11, 28), [], "LTOSF art. 23"),
    ("AR", "debit", {}, None, D(2026, 6, 16), [D(2026, 6, 15)], "BCRA"),
    ("AR", "credit", {"abroad": True}, None, D(2026, 6, 16), [D(2026, 6, 15)], "BCRA"),
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


@pytest.mark.parametrize("product", ["debit", "credit"])
@pytest.mark.parametrize("age, credited", [(0, True), (89, True), (90, True), (91, False), (200, False)])
def test_ac_03_mx_credit_only_for_a_claim_within_90_days_of_the_charge(product, age, credited):
    """AC-03 (ADR 0023, proposed): Circular 3/2012 art. 19 Bis 3 fr. II (debit) and Circular 34/2010 numeral 3.4 b)
    (credit); an older charge gets the LTOSF art. 23 ruling instead. Day 90 still qualifies [assumption]."""
    d = clock.deadline("MX", product, OPENED, charged_at=OPENED - timedelta(days=age))
    assert d.credit_deadline == (D(2026, 6, 3) if credited else None) and d.ruling_deadline == D(2026, 7, 16)


def test_ac_03_the_charge_date_is_local_near_midnight():
    """AC-03 + AC-16: 2026-03-03 05:30 UTC is 2026-03-02 23:30 in Mexico City, 91 days before the notice."""
    late = datetime(2026, 3, 3, 5, 30, tzinfo=timezone.utc)
    assert clock.deadline("MX", "debit", OPENED, charged_at=late).credit_deadline is None
    assert clock.deadline("MX", "debit", OPENED, charged_at=late + timedelta(hours=1)).credit_deadline == D(2026, 6, 3)


def test_ac_03_naive_times_are_rejected_and_utc_is_read_in_local_time():
    """Spec 01 §Time: timestamps are UTC. Live notice at 2026-10-06 05:30Z is Monday 2026-10-05 in Mexico City."""
    notice_day = clock.today("live", "MX", utc_now=datetime(2026, 10, 6, 5, 30, tzinfo=timezone.utc))
    assert notice_day == D(2026, 10, 5)
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.deadline("MX", "debit", notice_day, charged_at=datetime(2026, 10, 6, 5, 0))
    utc_charge = datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc)              # 23:00 the day before, local
    assert clock.deadline("MX", "debit", notice_day, charged_at=utc_charge).credit_deadline == D(2026, 10, 7)
    # Transaction.transaction_date may be the UTC date, one day ahead of the local notice date [assumption]
    assert clock.deadline("MX", "debit", notice_day, charged_at=D(2026, 10, 6)).credit_deadline == D(2026, 10, 7)


@pytest.mark.parametrize("before, credited", [(timedelta(hours=47, minutes=59), True), (timedelta(hours=48), True),
                                              (timedelta(hours=48, minutes=1), False)])
def test_ac_03_an_hours_window_is_exact_to_the_minute(before, credited):
    """AC-03 boundary 47:59 / 48:00 / 48:01 for an entry shaped `when_charged_within: {hours: 48}` (fr. I, theft or loss)."""
    p = Policies.model_validate(policies_with("regulatory_clock.MX.debit.0.when_charged_within", {"hours": 48}))
    noticed = datetime(2026, 6, 1, 16, 0, tzinfo=timezone.utc)                  # 10:00 in Mexico City
    d = clock.deadline("MX", "debit", OPENED, charged_at=noticed - before, noticed_at=noticed, policies=p)
    assert d.credit_deadline == (D(2026, 6, 3) if credited else None)
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.deadline("MX", "debit", OPENED, charged_at=noticed - before, noticed_at=noticed.replace(tzinfo=None),
                       policies=p)


def test_ac_03_a_charge_age_rule_needs_its_inputs():
    with pytest.raises(ValueError, match="charged_at"):
        clock.deadline("MX", "credit", OPENED)
    with pytest.raises(ValueError, match="after the notice"):
        clock.deadline("MX", "debit", OPENED, charged_at=D(2026, 6, 3))


NOTICES = [  # notice on a weekend or a holiday, through deadline(): country, product, opened_on, credit, ruling
    ("MX", "debit", D(2026, 5, 30), D(2026, 6, 2), D(2026, 7, 14)),       # Saturday
    ("MX", "credit", D(2026, 9, 16), D(2026, 9, 18), D(2026, 10, 31)),    # Independence Day
    ("AR", "debit", D(2026, 6, 15), None, D(2026, 6, 29))]                # Güemes Day


@pytest.mark.parametrize("country, product, opened_on, credit, ruling", NOTICES)
def test_ac_03_a_notice_on_a_weekend_or_holiday_counts_from_the_next_business_day(country, product, opened_on, credit,
                                                                                   ruling):
    d = clock.deadline(country, product, opened_on, charged_at=opened_on - timedelta(days=1))
    assert (d.credit_deadline, d.ruling_deadline) == (credit, ruling)


def test_ac_03_mx_credit_card_credit_skips_the_holiday():
    """AC-03 (ADR 0023): opened 2026-09-15, business day 1 is 09-17 (09-16 is a holiday), so the credit is 09-18;
    calendar days would give 09-17."""
    d = clock.deadline("MX", "credit", D(2026, 9, 15), charged_at=D(2026, 9, 14))
    assert d.credit_deadline == D(2026, 9, 18) and d.holidays_skipped == [D(2026, 9, 16)]


def test_ac_03_a_naive_datetime_is_rejected_for_every_country():
    """§4.3: charged_at and noticed_at are checked up front, even where no window reads them (AR has none)."""
    aware = datetime(2026, 5, 31, 12, tzinfo=timezone.utc)
    for kwargs in ({"charged_at": aware.replace(tzinfo=None)}, {"noticed_at": aware.replace(tzinfo=None)}):
        with pytest.raises(ValueError, match="timezone-aware"):
            clock.deadline("AR", "debit", OPENED, **kwargs)
    assert clock.deadline("AR", "debit", OPENED, charged_at=aware, noticed_at=aware).ruling_deadline == D(2026, 6, 16)


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
    old = clock.deadline("MX", "credit", D(2026, 12, 1), charged_at=D(2026, 6, 1))           # LTOSF, calendar days
    assert old.ruling_deadline == D(2027, 1, 15)
    fresh = clock.deadline("MX", "debit", D(2026, 12, 30), charged_at=D(2026, 12, 29))       # all or nothing
    assert (fresh.credit_deadline, fresh.ruling_deadline, fresh.rule_ids) == (None, None, ["POL-CLOCK-UNKNOWN"])


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
    assert {mondays(2)[0], mondays(3)[2], mondays(11)[2]} <= mx
    assert mx == {D(2026, m, d) for m, d in [(1, 1), (2, 2), (3, 16), (4, 2), (4, 3), (5, 1), (9, 16), (11, 2), (11, 16),
                                             (12, 12), (12, 25)]}
    assert set(clock.holidays("AR")[2026].holidays) == {D(2026, m, d) for m, d in [
        (1, 1), (2, 16), (2, 17), (3, 24), (4, 2), (4, 3), (5, 1), (5, 25), (6, 15), (6, 20), (7, 9), (8, 17), (10, 12),
        (11, 9), (11, 23), (12, 8), (12, 25)]}


INVALID = [
    ("ADR 0019 no source_url", "regulatory_clock.AR.any.0.source_url", None),
    ("ADR 0019 no verified_on", "regulatory_clock.AR.any.0.verified_on", None),
    ("ADR 0019 plain http", "regulatory_clock.MX.debit.0.source_url", "http://www.banxico.org.mx/"),
    ("AC-03 entry without a term", "regulatory_clock.AR.any.0.ruling", None),
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


def test_fr_01_holiday_files_are_validated_with_the_policies(monkeypatch, tmp_path):
    """FR-01: a missing or unverified holiday file fails at startup, not on the first deadline of a turn."""
    monkeypatch.setattr(calendars, "HOLIDAYS_DIR", tmp_path)
    calendars.holidays.cache_clear()
    real = Path(calendars.__file__).parent / "holidays"
    try:
        with pytest.raises(ValidationError, match="no holiday file"):
            Policies.model_validate(RAW)
        shutil.copy(real / "mx_2026.yaml", tmp_path)                 # MX alone is not enough: AR also counts business days
        calendars.holidays.cache_clear()
        with pytest.raises(ValidationError, match="regulatory_clock AR"):
            Policies.model_validate(RAW)
        shutil.copy(real / "ar_2026.yaml", tmp_path)
        calendars.holidays.cache_clear()
        Policies.model_validate(RAW)
        (tmp_path / "mx_2026.yaml").write_text("source: CNBV\nsource_url: http://dof.gob.mx/\nverified_on: 2026-10-04\n"
                                               "holidays: {2026-01-01: New Year}\n")
        calendars.holidays.cache_clear()
        with pytest.raises(ValidationError, match="holiday file of MX"):
            Policies.model_validate(RAW)
    finally:
        calendars.holidays.cache_clear()


def test_fr_01_a_holiday_outside_the_year_of_its_file_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(calendars, "HOLIDAYS_DIR", tmp_path)
    calendars.holidays.cache_clear()
    try:
        (tmp_path / "mx_2026.yaml").write_text("source: CNBV\nsource_url: https://dof.gob.mx/\nverified_on: 2026-10-04\n"
                                               "holidays: {2027-01-01: New Year}\n")
        with pytest.raises(ValueError, match="outside 2026"):
            calendars.holidays("MX")
        with pytest.raises(ValidationError, match="outside 2026"):
            Policies.model_validate(RAW)
    finally:
        calendars.holidays.cache_clear()


def test_ac_16_a_stale_demo_today_variable_only_warns(monkeypatch, caplog):
    """ADR 0020: the constant wins; a local .env with the superseded 2026-06-03 is logged, never used."""
    monkeypatch.setenv("DEMO_TODAY", "2026-06-03")
    with caplog.at_level(logging.WARNING, logger=clock.__name__):
        clock.warn_if_demo_today_env_differs()
    assert "DEMO_TODAY=2026-06-03 is ignored" in caplog.text and clock.today("replay", "MX") == D(2026, 6, 1)
    caplog.clear()
    monkeypatch.setenv("DEMO_TODAY", "2026-06-01")
    clock.warn_if_demo_today_env_differs()
    assert not caplog.records


def test_ac_16_importing_the_clock_with_a_stale_demo_today_warns():
    """ADR 0020: the warning fires at import time, not only when the function is called again."""
    packages = Path(clock.__file__).parents[2]
    env = {**os.environ, "DEMO_TODAY": "2026-06-03", "PYTHONPATH": f"{packages.parent}{os.pathsep}{packages}"}
    code = "from nick_of_time.policy import clock; print(clock.DEMO_TODAY)"
    run = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert run.stdout.strip() == "2026-06-01" and "DEMO_TODAY=2026-06-03 is ignored" in run.stderr
    env["DEMO_TODAY"] = "2026-06-01"
    assert subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                          check=True).stderr == ""
