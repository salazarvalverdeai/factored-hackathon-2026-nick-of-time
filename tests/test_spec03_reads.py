"""Spec 03 T2/T3: the gold loader and the read tools (search, profile, score, convert) through the real gate, over a
tiny gold fixture written to tmp_path. No network, no Postgres, no LLM; data/gold_eval is never opened."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastmcp import Client

from contracts import tools
from nick_of_time.policy import load_policies

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server import gate, reads, server  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402

NOW = dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC)
ANA, BRUNO, CARLA = "CLI-ANA000000001", "CLI-BRUNO0000001", "CLI-CARLA0000001"     # MX, MX, AR
S_ANA, S_BRUNO, S_CARLA, S_LIVE = "S-anareplay0000001", "S-brunoreplay00001", "S-carlareplay00001", "S-analive000000001"


def _trx(n, customer, day, amount, currency="USD", merchant=None, status="Approved", ptype="Tarjeta Crédito",
         amount_usd=None, score=55.0):
    return {"transaction_id": f"TRX-{n:020d}", "product_id": f"PRD-{customer[4:16]}", "customer_id": customer,
            "transaction_date": dt.datetime(2026, 4, 30, 12, 30) + dt.timedelta(days=day), "amount": amount, "currency": currency,
            "amount_usd": amount_usd, "merchant_name": merchant, "transaction_status": status, "product_type": ptype,
            "fraud_score": score, "is_fraud": True}         # is_fraud planted: the loader must never select it


TRX = [_trx(1, ANA, 30, 69.44, merchant="Tienda Don José"), _trx(2, BRUNO, 30, 69.44, merchant="Tienda Don José"),
       _trx(3, ANA, 20, 1234.567, merchant=None, score=None), _trx(4, ANA, 29, 69.44, status="Declined"),
       _trx(5, ANA, 28, 69.44, status="Reversed"), _trx(6, ANA, 27, 69.44, ptype="Cuenta Ahorro"),
       _trx(7, ANA, 33, 500.0, merchant="Farmacia Salud"), _trx(8, ANA, 25, 69.10, merchant="Uber"),
       _trx(9, ANA, 26, 70.80, merchant="Uber"), _trx(10, ANA, 24, 69.44, status="Pending", merchant="Uber"),
       _trx(11, ANA, 1, 11.11), _trx(12, CARLA, 30, 35000.0, "ARS", "Super Ahorro"),
       _trx(13, ANA, 23, 69.44, merchant="Uber")]


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    (root / "gold").mkdir()
    pl.DataFrame(TRX, schema_overrides={"amount_usd": pl.Float64}).write_parquet(root / "gold/transactions_enriched.parquet")
    pl.DataFrame([{"customer_id": c, "first_name": f, "last_name": "Pérez", "document_number": "DOC-SECRET",
                   "email": f"{f.lower()}.perez@example.com", "mobile_phone": "+525512345678", "address": "Calle 1",
                   "country": k} for c, f, k in ((ANA, "Ana", "México"), (BRUNO, "Bruno", "México"),
                                                 (CARLA, "Carla", "Argentina"))]).write_parquet(
        root / "gold/customers.parquet")
    (root / "gold_eval").mkdir()
    labels = root / "gold_eval/transaction_labels.parquet"
    pl.DataFrame({"transaction_id": ["TRX-x"], "is_fraud": [True]}).write_parquet(labels)
    os.chmod(labels, 0)                                  # opening it would fail the load
    yield root
    os.chmod(labels, 0o600)


class Run:
    def __init__(self, gold_dir, denials=None, **kwargs):
        def row(sid, customer, **extra):
            return gate.SessionRow(**{"session_id": sid, "customer_id": customer, "verified_at": NOW, "language": "es",
                                      "mode": "replay", "expires_at": NOW + dt.timedelta(minutes=15), **extra})
        sessions = {S_ANA: row(S_ANA, ANA), S_BRUNO: row(S_BRUNO, BRUNO, display_currency="USD"),
                    S_CARLA: row(S_CARLA, CARLA), S_LIVE: row(S_LIVE, ANA, mode="live")}
        self.denials, policies = [], load_policies()
        handlers = reads.read_handlers(Gold(gold_dir / "gold"), policies, **kwargs)
        guardrails = {rule_id: rule.guardrail for rule_id, rule in policies.rules.items() if rule.guardrail}
        self.gate = gate.Gate(sessions, handlers, denials=denials or self.denials.append, audit=lambda _: None,
                              now=lambda: NOW, guardrails=guardrails)

    def raw(self, tool, session=S_ANA, **args):
        async def go():
            async with Client(server.build_server(self.gate)) as client:
                return await client.call_tool(tool, {"session_id": session, **args}, raise_on_error=False)
        return asyncio.run(go())

    def __call__(self, tool, session=S_ANA, **args):
        result = self.raw(tool, session, **args)
        model = tools.ToolError if result.is_error else tools.CUSTOMER_TOOLS[tool][1]
        return model.model_validate(result.structured_content)


def _ids(out):
    return [int(c.transaction_id[4:]) for c in out.candidates]


def test_ac_01_search_returns_only_the_session_customers_transactions(gold_dir):
    run = Run(gold_dir)
    assert _ids(run("search_transaction", amount=69.44, approx_date="2026-05-30", window_days=0)) == [1]
    assert _ids(run("search_transaction", S_BRUNO, amount=69.44, approx_date="2026-05-30", window_days=0,
                    merchant=f"tienda don jose de {ANA}")) == [2]
    assert run("search_transaction", amount=69.44, customer_id=BRUNO).code == "DENY"    # never an argument (AC-02)


def test_ac_01_another_customers_transaction_is_not_found_and_logged_never_leaked(gold_dir):
    run = Run(gold_dir)
    probe = run("get_fraud_score", transaction_id=TRX[1]["transaction_id"])               # Bruno's, from Ana
    unknown = run("get_fraud_score", transaction_id="TRX-" + "9" * 20)
    assert probe == unknown == tools.ToolError(code="NOT_FOUND", message=reads.NOT_FOUND.message)
    assert [(d.policy_id, d.guardrail_id, d.session_id) for d in run.denials] == [
        ("POL-CROSS-CUSTOMER", "G-SES-02", S_ANA)]


def test_ac_01_a_failing_denial_sink_still_gives_a_probe_the_unknown_ids_answer(gold_dir):
    def broken(row):
        raise OSError("policy_denials is down")
    run = Run(gold_dir, denials=broken)                  # UNAVAILABLE here would reveal that the id exists
    probe, unknown = (run.raw("get_fraud_score", transaction_id=trx) for trx in (TRX[1]["transaction_id"],
                                                                                 "TRX-" + "9" * 20))
    assert probe.is_error and probe.structured_content == unknown.structured_content
    assert probe.content[0].text == unknown.content[0].text and "NOT_FOUND" in probe.content[0].text


def test_ac_01_the_score_comes_from_gold_as_dataset_never_synthetic_in_replay(gold_dir):
    run = Run(gold_dir)
    assert run("get_fraud_score", transaction_id=TRX[0]["transaction_id"]) == tools.GetFraudScoreOut(
        transaction_id=TRX[0]["transaction_id"], score=55.0, source="dataset", version="gold-v1")
    assert run("get_fraud_score", transaction_id=TRX[2]["transaction_id"]).score is None    # a null stays null


def test_ac_07_pesos_match_a_usd_charge_through_the_policy_rate_within_2_percent(gold_dir):
    run = Run(gold_dir)                                  # 69.44 USD × 18.0 = 1,249.92 MXN
    for said, currency in ((1250, "MXN"), (1250, None), (1249.92 * 1.019, "MXN"), (69.44, "USD")):
        assert 1 in _ids(run("search_transaction", amount=said, currency=currency, approx_date="2026-05-30",
                             window_days=0)), (said, currency)
    for said, currency in ((1249.92 * 1.021, "MXN"), (1250, "USD"), (1250, "ARS")):
        assert _ids(run("search_transaction", amount=said, currency=currency, approx_date="2026-05-30",
                        window_days=0)) == [], (said, currency)
    assert _ids(run("search_transaction", S_CARLA, amount=100, currency="USD")) == []     # ARS charge, not converted


def test_ac_08_cards_approved_or_pending_in_the_window_never_after_today_at_most_4_ranked(gold_dir):
    run = Run(gold_dir)
    out = run("search_transaction", amount=69.44, approx_date="2026-05-28", window_days=7)
    assert _ids(out) == [1, 10, 13, 8]                   # gap, then date distance; 9 is the 5th, cut by the cap;
    #                                                      4/5/6 excluded, 7 after today
    assert {c.transaction_status for c in out.candidates} == {"Approved", "Pending"}
    assert _ids(run("search_transaction", approx_date="2026-06-02", window_days=1)) == []   # 7 is after today
    assert _ids(run("search_transaction", amount=11.11)) == []             # no date: the last 30 days only
    assert _ids(run("search_transaction", amount=11.11, approx_date="2026-05-01")) == [11]
    assert _ids(run("search_transaction", amount=1234.567, approx_date="2026-05-20", window_days=0)) == [3]


def test_ac_08_merchant_is_accent_insensitive_and_a_null_merchant_still_matches(gold_dir):
    run = Run(gold_dir)
    assert _ids(run("search_transaction", merchant="TIENDA DON JOSE", approx_date="2026-05-20", window_days=10)) \
        == [3, 1]                                        # 3 has no merchant: kept on date alone
    assert 1 not in _ids(run("search_transaction", merchant="Farmacia", approx_date="2026-05-30", window_days=0))


def test_ac_11_amounts_round_trip_exactly_in_the_original_currency_without_score(gold_dir):
    run = Run(gold_dir)
    [usd] = run("search_transaction", amount=1234.567, approx_date="2026-05-20", window_days=0).candidates
    [ars] = run("search_transaction", S_CARLA, amount=35000, approx_date="2026-05-30", window_days=0).candidates
    assert (usd.amount, usd.currency, usd.amount_usd, usd.merchant) == (1234.567, "USD", 1234.567, None)
    assert (ars.amount, ars.currency, ars.amount_usd) == (35000.0, "ARS", 100.0)   # null amount_usd: 350 ARS/USD
    assert "fraud_score" not in usd.model_dump() and usd.synthetic is False


def test_ac_11_profile_gives_the_first_name_and_masked_confirmed_channels_only(gold_dir):
    links = {ANA: [SimpleNamespace(channel="telegram", address="987654821", confirmed=True),
                   SimpleNamespace(channel="email", address="ana.perez@example.com", confirmed=True),
                   SimpleNamespace(channel="email", address="other@example.com", confirmed=False)]}
    run = Run(gold_dir, channels=lambda customer: links.get(customer, []))
    ana = run("get_customer_profile")
    assert ana == tools.GetCustomerProfileOut(first_name="Ana", language="es", country="MX", display_currency="MXN",
                                              channels=[{"channel": "telegram", "masked_address": "···4821"},
                                                        {"channel": "email", "masked_address": "a···@example.com"}])
    dump = ana.model_dump_json()
    assert not any(pii in dump for pii in ("Pérez", "DOC-SECRET", "ana.perez", "+5255", "Calle", "other@"))
    assert run("get_customer_profile", S_BRUNO).display_currency == "USD"          # the session preference wins
    assert run("get_customer_profile", S_CARLA).model_dump(include={"country", "display_currency", "channels"}) \
        == {"country": "AR", "display_currency": "ARS", "channels": []}


def test_ac_11_the_loader_reads_named_gold_columns_only_and_never_gold_eval(gold_dir):
    loaded = Gold(gold_dir / "gold")                     # gold_eval's file is unreadable: it was never opened
    columns = {table: [r[0] for r in loaded._rows(f"DESCRIBE {table}", [])] for table in ("card", "customer")}
    assert "is_fraud" not in columns["card"] and "fraud_score" in columns["card"]
    assert columns["customer"] == ["customer_id", "first_name", "country"]
    with pytest.raises(ValueError, match="gold_eval"):
        Gold(gold_dir / "gold_eval")


def test_ac_20_convert_amount_answers_null_without_a_verified_labeled_rate(gold_dir):
    assert Run(gold_dir)("convert_amount", amount=69.44, currency="USD").converted is None   # never amount_gate's 18.0
    seen = []

    def fx(amount, source, target):
        seen.append((amount, source, target))
        return {"amount": "1249.92", "rate": "18.0000", "rate_source": "Banxico FIX [external]", "as_of": "2026-05-29"}
    out = Run(gold_dir, convert=fx)("convert_amount", amount=69.44, currency="USD")
    assert out.converted == tools.ConvertedAmount(amount="1249.92", currency="MXN", rate="18.0000",
                                                  rate_source="Banxico FIX [external]", as_of="2026-05-29")
    assert seen == [(69.44, "USD", "MXN")]               # to_currency None: the display currency
    unlabeled = Run(gold_dir, convert=lambda *a: {**fx(*a), "rate_source": " "})
    assert unlabeled("convert_amount", amount=1, currency="USD", to_currency="COP").converted is None
    other = Run(gold_dir, convert=lambda *a: {**fx(*a), "currency": "MXN"})      # asked COP, got MXN: not relabeled
    assert other("convert_amount", amount=1, currency="USD", to_currency="COP").converted is None
    assert other("convert_amount", amount=1, currency="USD", to_currency="MXN").converted.currency == "MXN"


def test_ac_08_a_live_session_search_is_unavailable_until_the_live_clock_lands(gold_dir):
    assert Run(gold_dir)("search_transaction", S_LIVE, amount=69.44).code == "UNAVAILABLE"
