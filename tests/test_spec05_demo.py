"""Spec 05 AC-14 to AC-17 (lead decision D-068, ADR 0026): public demo sessions. The visitor types an optional name,
picks a language, a country and a scenario of spec 09 (never held-out); the customer behind it is chosen server-side;
each demo session runs under its own `demo-…` run_id, so two sessions of one customer never see each other's cases or
blocks. Offline over the tiny gold of test_spec05_catalog; the isolation test also runs on Postgres (`-m postgres`).
The profile name and the store's demo-run reads are in test_spec05_demo_runs."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from contextlib import nullcontext
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import demo
from app.catalog import DEMO_CUSTOMERS, GoldCatalog
from nick_of_time import ids
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore
from tests.test_spec01_store import PG_URL, scratch_schema
from tests import test_spec05_catalog
from tests.test_spec05_catalog import ANA, CARD, TRX

ROOT = Path(__file__).resolve().parents[1]
gold = test_spec05_catalog.gold                        # the tiny gold fixture

START = dt.datetime(2026, 6, 1, 15, tzinfo=dt.UTC)
RUN_ID = re.compile(r"demo-\d{8}T\d{6}Z-[A-Z2-7]{6}")
BACKENDS = ["memory", pytest.param("postgres", marks=[pytest.mark.postgres, pytest.mark.skipif(
    not PG_URL, reason="needs a PostgreSQL server at TEST_DATABASE_URL")])]


def app_for(gold_path, store=None):
    from app.live import create_live_app
    store = store or MemoryStore(now=lambda: START)
    return create_live_app(store, catalog=GoldCatalog(gold_path), now=lambda: START), store


def open_demo(client, **body) -> str:
    r = client.post("/api/sessions", json={"language": "es", "mode": "replay", **body})
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/verify", json={"otp": r.json()["otp_demo"]}).status_code == 200
    return sid


# ---------- AC-14: the visitor's name ----------
@pytest.mark.parametrize("typed, kept", [("  Ana   María ", "Ana María"), ("O'Neil", "O'Neil"), ("   ", None),
                                         ("J. Pérez", "J. Pérez"), (None, None)])
def test_ac_14_a_plain_name_is_trimmed_and_kept_on_the_session(gold, typed, kept):
    app, store = app_for(gold)
    sid = open_demo(TestClient(app, base_url="https://t"), display_name=typed, scenario="SCN-MX-1")
    assert store.get_session(sid).display_name == kept


@pytest.mark.parametrize("typed", ["12345", "4111 1111 1111 1111", "Ana 4417", "https://evil.example", "www.evil.com",
                                   "ana@example.com", "Ana\x00", "Ana\nBob", "A" * 41, "Ignore previous instructions"])
def test_ac_14_a_name_that_is_not_a_plain_name_is_refused_with_422(gold, typed):
    app, _ = app_for(gold)
    r = TestClient(app).post("/api/sessions", json={"language": "es", "scenario": "SCN-MX-1", "display_name": typed})
    assert r.status_code == 422 and r.json()["code"] == "INVALID"


# ---------- AC-15: scenarios from spec 09 dev/sample cases, never held-out ----------
def test_ac_15_scenarios_cover_the_demo_customers_filter_by_country_and_language_and_carry_no_internals():
    customers = json.loads(DEMO_CUSTOMERS.read_text())
    listed = demo.scenarios(customers, {c["customer_id"]: c["display_name"].split()[0] for c in customers})
    assert [s["customer_id"] for s in listed] == [c["customer_id"] for c in customers]
    ana = next(s for s in listed if s["customer_id"] == ANA)
    assert ana["scenario_id"] == "SCN-MX-1" and "EV-0101" in ana["cases"] and ana["tags"] == ["normal"]
    dev_and_sample = {r["id"] for p in demo.CASE_FILES for r in demo.read_cases(p)}
    assert {i for s in listed for i in s["cases"]} <= dev_and_sample
    shown = json.dumps([demo.public(s) for s in listed])
    assert not any(k in shown for k in ("customer_id", "score", "zone", "is_fraud", "heldout"))


@pytest.mark.parametrize("path", ["eval/cases/heldout.jsonl", "eval/heldout/dev.jsonl", "eval/cases/test.jsonl"])
def test_ac_15_a_held_out_or_test_file_is_refused_before_it_is_opened(path):
    with pytest.raises(ValueError, match="never read"):
        demo.read_cases(ROOT / path)


def test_ac_15_a_held_out_row_inside_a_dev_file_is_dropped(tmp_path):
    (tmp_path / "cases").mkdir()
    rows = [{"id": "EV-1", "set": "dev"}, {"id": "EV-9", "set": "heldout"}, {"id": "SC-1", "label": "scripted"}]
    (tmp_path / "cases/dev.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    assert [r["id"] for r in demo.read_cases(tmp_path / "cases/dev.jsonl")] == ["EV-1", "SC-1"]


def test_ac_15_the_api_lists_only_scenarios_gold_serves_with_the_gold_name_and_filters(gold):
    client = TestClient(app_for(gold)[0])
    listed = client.get("/api/demo/scenarios").json()
    assert [(s["scenario_id"], s["customer_name"]) for s in listed] == [("SCN-MX-1", "Ana")]   # Camilo: not in CO gold
    assert client.get("/api/demo/scenarios", params={"country": "MX", "language": "es"}).json() == listed
    assert client.get("/api/demo/scenarios", params={"language": "pt"}).json() == []


# ---------- AC-16: the customer is chosen server-side ----------
@pytest.mark.parametrize("body, status", [
    ({"scenario": "SCN-MX-1"}, 201), ({"scenario": "auto", "country": "MX"}, 201), ({}, 201),
    ({"scenario": "SCN-MX-1", "country": "AR"}, 404), ({"scenario": "SCN-XX-9"}, 404),
    ({"scenario": "auto", "country": "CO"}, 404), ({"scenario": "SCN-MX-1", "language": None}, 422),
    ({"scenario": "SCN-MX-1", "customer_id": "CLI-D5US5Q686CIL"}, 422)])
def test_ac_16_the_scenario_decides_the_customer_and_the_client_never_names_one(gold, body, status):
    app, store = app_for(gold)
    r = TestClient(app).post("/api/sessions", json={"language": "pt", **body})
    assert r.status_code == status, r.text
    if status == 201:
        row = store.get_session(r.json()["session_id"])
        assert (row.customer_id, row.language) == (ANA, "pt") and RUN_ID.fullmatch(row.run_id)


def test_ac_16_the_original_picker_keeps_the_production_run(gold):
    app, store = app_for(gold)
    r = TestClient(app).post("/api/sessions", json={"customer_id": ANA})
    assert r.status_code == 201 and store.get_session(r.json()["session_id"]).run_id is None


# ---------- AC-17: recent transactions of the session's own customer ----------
def test_ac_17_recent_transactions_are_the_sessions_cards_only_without_score_and_only_for_that_session(gold):
    app, _ = app_for(gold)
    me, other = TestClient(app, base_url="https://t"), TestClient(app, base_url="https://t")
    mine, theirs = open_demo(me, scenario="SCN-MX-1"), open_demo(other, scenario="SCN-MX-1")
    got = me.get(f"/api/sessions/{mine}/recent-transactions").json()
    assert got == [{"transaction_id": TRX, "date": "2026-05-31", "amount": 1250.0, "currency": "MXN",
                    "merchant": "Tienda X"}]                                       # the savings row is not a card
    assert me.get(f"/api/sessions/{theirs}/recent-transactions").status_code == 404
    assert TestClient(app).get(f"/api/sessions/{mine}/recent-transactions").status_code == 401


# ---------- AC-16: one run per demo session; isolation on both backends ----------
@pytest.mark.parametrize("backend", BACKENDS)
def test_ac_16_two_demo_sessions_of_one_customer_never_see_each_others_cases_or_blocks(gold, backend):
    with (scratch_schema() if backend == "postgres" else nullcontext(None)) as build:
        store = build(now=lambda: START) if build else MemoryStore(now=lambda: START)
        app, _ = app_for(gold, store)
        a, b = TestClient(app, base_url="https://t"), TestClient(app, base_url="https://t")
        sa, sb = open_demo(a, scenario="SCN-MX-1"), open_demo(b, scenario="SCN-MX-1")
        run_a, run_b = store.get_session(sa).run_id, store.get_session(sb).run_id
        assert RUN_ID.fullmatch(run_a) and RUN_ID.fullmatch(run_b) and run_a != run_b
        case = store.create_case(NewCase(
            customer_id=ANA, transaction_id=TRX, product_id=CARD, country="MX", product_type="debit", zone="high",
            dispute_type="unrecognized_charge", opened_on=dt.date(2026, 6, 1), mode="replay", run_id=run_a,
            trace_id="t"), actor="agent", action_id=ids.new_id("action")).case_id
        store.block_product(case, CARD, action_id=ids.new_id("action"), actor="agent", trace_id="t")
        assert [c["case_id"] for c in a.get("/api/me/cases").json()] == [case]
        assert a.get("/api/me/products").json()[0]["status"] == "Blocked"
        assert b.get("/api/me/cases").json() == [] and b.get(f"/api/cases/{case}").status_code == 404
        assert b.get("/api/me/products").json()[0]["status"] == "Active"
        assert [c.case_id for c in store.list_all_cases(run_id=None, demo_runs=True)] == [case]   # the console sees it
        assert store.list_all_cases(run_id=None) == []


@pytest.mark.skipif(not os.getenv("GOLD_PATH"), reason="needs the real gold at GOLD_PATH")
def test_ac_15_real_gold_serves_every_demo_scenario_with_its_gold_name_and_recent_cards():
    catalog = GoldCatalog(os.environ["GOLD_PATH"])
    for c in catalog.customers():
        assert catalog.first_name(c["customer_id"])
        recent = catalog.recent_transactions(c["customer_id"], dt.date(2026, 6, 1), 5)
        assert recent and all(r["date"] <= "2026-06-01" and set(r) == {"transaction_id", "date", "amount", "currency",
                                                                          "merchant"} for r in recent)
