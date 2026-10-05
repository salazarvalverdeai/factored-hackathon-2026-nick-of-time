"""Spec 03 T3: `compute_deadline` through the real gate over a tiny gold fixture written to tmp_path. The tool delegates
to `clock.deadline()` (spec 02 §4.3), so the expected dates come from the clock table itself plus a few pinned values.
No network, no Postgres, no LLM."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import polars as pl
import pytest

from contracts import tools
from nick_of_time.policy import clock, load_policies

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server import gate, reads  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402

NOW = dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC)
ANA, BRUNO = "CLI-ANA000000001", "CLI-BRUNO0000001"
COUNTRIES = {"CLI-ARG000000001": ("Argentina", "AR"), "CLI-COL000000001": ("Colombia", "CO"),
             "CLI-BRA000000001": ("Brasil", "BR"), "CLI-PER000000001": ("Perú", "PE"),
             "CLI-CHL000000001": ("Chile", "CL"), "CLI-URY000000001": ("Uruguay", None)}
NAMES = {ANA: "México", BRUNO: "México", **{c: name for c, (name, _) in COUNTRIES.items()}}
UNKNOWN = tools.ToolError(code="UNAVAILABLE", policy_id="POL-CLOCK-UNKNOWN", message=reads.NO_CLOCK.message)


def _trx(n, customer, day, ptype="Tarjeta Débito", where="same"):
    where = NAMES[customer].replace("Brasil", "Brazil") if where == "same" else where   # gold spells it "Brazil"
    return {"transaction_id": f"TRX-{n:020d}", "product_id": f"PRD-{customer[4:16]}", "customer_id": customer,
            "transaction_date": dt.datetime.combine(day, dt.time(12, 30)), "amount": 69.44, "currency": "USD",
            "amount_usd": 69.44, "merchant_name": "Uber", "transaction_status": "Approved", "product_type": ptype,
            "transaction_country": where, "fraud_score": 55.0}


MAY30, DAY90, DAY91 = dt.date(2026, 5, 30), dt.date(2026, 3, 3), dt.date(2026, 3, 2)    # days before 2026-06-01
TRX = [_trx(1, ANA, MAY30), _trx(2, ANA, MAY30, "Tarjeta Crédito"), _trx(3, ANA, DAY90), _trx(4, ANA, DAY91),
       _trx(5, ANA, MAY30, where="USA"), _trx(6, ANA, MAY30, where=None), _trx(7, BRUNO, MAY30),
       _trx(8, ANA, DAY90, "Tarjeta Crédito"), _trx(9, ANA, DAY91, "Tarjeta Crédito"),
       *(_trx(10 + i, customer, MAY30) for i, customer in enumerate(COUNTRIES))]
ID = {n: f"TRX-{n:020d}" for n in range(1, 20)}
FIRST = {customer: 10 + i for i, customer in enumerate(COUNTRIES)}


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("data") / "gold"
    root.mkdir()
    pl.DataFrame(TRX).write_parquet(root / "transactions_enriched.parquet")
    pl.DataFrame([{"customer_id": c, "first_name": "Ana", "country": k} for c, k in NAMES.items()]).write_parquet(
        root / "customers.parquet")
    return root


def _sid(customer, mode="replay"):
    return f"S-{mode[:4]}{customer[4:16]}"                       # 16 characters after "S-"


class Run:
    def __init__(self, gold_dir, utc_now=None, language="es"):
        self.denials, policies = [], load_policies()
        sessions = {_sid(customer, mode): gate.SessionRow(
            session_id=_sid(customer, mode), customer_id=customer, verified_at=NOW, language=language,
            mode=mode, expires_at=NOW + dt.timedelta(minutes=15)) for customer in NAMES for mode in ("replay", "live")}
        handlers = reads.read_handlers(Gold(gold_dir), policies, utc_now=utc_now and (lambda: utc_now))
        guardrails = {rule_id: rule.guardrail for rule_id, rule in policies.rules.items() if rule.guardrail}
        self.gate = gate.Gate(sessions, handlers, denials=self.denials.append, audit=lambda _: None, now=lambda: NOW,
                              guardrails=guardrails)

    def __call__(self, n, customer=ANA, mode="replay", tool="compute_deadline", **extra):
        session = _sid(customer, mode)
        return self.gate.call(tool, {"session_id": session, "transaction_id": ID[n], **extra}, "trace-test")


def _expected(country, product, opened_on, charged_on, abroad=False):
    found = clock.deadline(country, product, opened_on, abroad=abroad, charged_at=charged_on)
    if found.source_url is None:
        return UNKNOWN
    return tools.ComputeDeadlineOut(country=country, product=product, credit_deadline=found.credit_deadline,
                                    ruling_deadline=found.ruling_deadline, deadline_source=found.deadline_source,
                                    deadline_source_label=clock.source_label(found.deadline_source, "es"),
                                    source_url=found.source_url, verified_on=found.verified_on)


def test_t3_compute_deadline_answers_every_clock_row_from_the_session_customers_country(gold_dir):
    """Spec 03 §6 compute_deadline: country from the customer, product from the card type, opened on DEMO_TODAY;
    spec 02 AC-03 (MX debit and credit) and spec 02 AC-14 (a country without an entry)."""
    run, rows = Run(gold_dir), load_policies().regulatory_clock
    assert set(rows) <= {"MX"} | {code for _, code in COUNTRIES.values()}       # every row of the table is exercised
    for customer, (_, code) in COUNTRIES.items():
        out = run(FIRST[customer], customer)
        assert out == (_expected(code, "debit", clock.DEMO_TODAY, MAY30) if code else UNKNOWN), customer
        assert (code in rows) == isinstance(out, tools.ComputeDeadlineOut), customer
    mx_debit, mx_credit = run(1), run(2)
    assert (mx_debit.credit_deadline, mx_debit.ruling_deadline) == (dt.date(2026, 6, 3), dt.date(2026, 7, 16))
    assert mx_debit.deadline_source.startswith("Banxico Circular 3/2012") and mx_debit.verified_on == dt.date(2026, 10, 4)
    assert (mx_credit.product, mx_credit.credit_deadline) == ("credit", dt.date(2026, 6, 3))
    assert mx_credit.deadline_source.startswith("Banxico Circular 34/2010")
    assert run(FIRST["CLI-ARG000000001"], "CLI-ARG000000001").ruling_deadline == dt.date(2026, 6, 16)
    assert run(FIRST["CLI-COL000000001"], "CLI-COL000000001").ruling_deadline == dt.date(2026, 6, 24)


def test_t3_mx_provisional_credit_covers_charges_within_90_calendar_days_debit_and_credit(gold_dir):
    """Spec 02 AC-03 and ADR 0023: day 90 still qualifies; day 91 falls to LTOSF art. 23, a ruling date and no credit
    date."""
    run = Run(gold_dir)
    for day90, day91 in ((3, 4), (8, 9)):                                      # debit, then credit
        assert run(day90).credit_deadline == dt.date(2026, 6, 3)
        older = run(day91)
        assert (older.credit_deadline, older.ruling_deadline, older.deadline_source) == (
            None, dt.date(2026, 7, 16), "LTOSF art. 23")


def test_t3_a_charge_abroad_gets_the_abroad_ruling_term(gold_dir):
    """Spec 03 §6 `abroad` when transaction_country differs from the customer's; spec 02 AC-03 (180 days abroad)."""
    run = Run(gold_dir)
    assert run(5).ruling_deadline == dt.date(2026, 11, 28)                     # USA: 180 calendar days
    assert run(5) == _expected("MX", "debit", clock.DEMO_TODAY, MAY30, abroad=True)
    assert run(6).ruling_deadline == run(1).ruling_deadline == dt.date(2026, 7, 16)   # unknown place: not abroad
    assert run(FIRST["CLI-BRA000000001"], "CLI-BRA000000001").country == "BR"    # "Brazil" is the customer's own


def test_t3_a_country_without_a_verified_entry_gets_no_deadline_and_pol_clock_unknown(gold_dir):
    """Spec 02 AC-14 and §4.3: case opened, a person decides, no invented deadline; the error carries no date."""
    run = Run(gold_dir)
    for customer in ("CLI-URY000000001", *(c for c, (_, code) in COUNTRIES.items()
                                          if code and code not in load_policies().regulatory_clock)):
        out = run(FIRST[customer], customer)
        assert out == UNKNOWN and "20" not in out.message, customer
    assert run.denials == []                                                    # not a denial: nothing was refused


def test_t3_live_mode_opens_on_the_real_date_in_the_customers_time_zone(gold_dir):
    """ADR 0020: live uses the real date per country; replay stays on DEMO_TODAY whatever the real time."""
    late = Run(gold_dir, utc_now=dt.datetime(2026, 6, 2, 4, 30, tzinfo=dt.UTC))   # 22:30 on 06-01 in Mexico City
    argentina = "CLI-ARG000000001"                                               # 01:30 on 06-02 in Buenos Aires
    assert late(1, mode="live") == _expected("MX", "debit", dt.date(2026, 6, 1), MAY30)
    assert late(FIRST[argentina], argentina, "live") == _expected("AR", "debit", dt.date(2026, 6, 2), MAY30)
    assert late(FIRST[argentina], argentina) == _expected("AR", "debit", clock.DEMO_TODAY, MAY30)
    next_day = Run(gold_dir, utc_now=dt.datetime(2026, 6, 2, 6, 0, tzinfo=dt.UTC))   # 06-02 in Mexico City
    assert next_day(3, mode="live").credit_deadline is None                      # the charge is now 91 days old
    assert next_day(3).credit_deadline == dt.date(2026, 6, 3)                    # replay: still day 90


def test_ac_11_the_deadline_uses_only_the_session_customer_never_an_argument(gold_dir):
    run = Run(gold_dir)
    refused = run(1, customer_id=BRUNO)                                          # extra="forbid" in the gate
    assert (refused.code, refused.policy_id) == ("DENY", "POL-DEFAULT-DENY")
    probe, unknown = run(7), run.gate.call("compute_deadline", {"session_id": _sid(ANA),
                                                               "transaction_id": "TRX-" + "9" * 20}, "trace-test")
    assert probe == unknown == tools.ToolError(code="NOT_FOUND", message=reads.NOT_FOUND.message)   # Bruno's charge
    assert [(d.policy_id, d.guardrail_id) for d in run.denials] == [
        ("POL-DEFAULT-DENY", "G-TOOL-01"), ("POL-CROSS-CUSTOMER", "G-SES-02")]
    assert run(7, BRUNO).country == "MX"                                         # his own session sees it


def test_ac_20_a_converted_amount_never_moves_the_deadline(gold_dir):
    """Spec 03 §6 convert_amount: it never changes a deadline; the deadline tool takes no amount at all."""
    assert set(tools.ComputeDeadlineIn.model_fields) == {"session_id", "transaction_id"}
    run = Run(gold_dir)
    before = run(1)
    run.gate.call("convert_amount", {"session_id": _sid(ANA), "amount": 69.44, "currency": "USD"}, "t")
    assert run(1) == before and run(1, amount=1250).code == "DENY"
