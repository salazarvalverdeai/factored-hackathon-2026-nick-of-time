"""Spec 05 Task 7: the gold catalog. With GOLD_PATH the api serves the spec 09 demo customers and reads their cards and
transactions from gold, so a session's customer is one the MCP server finds (AC-01, AC-05); no customer view carries a
score or a zone (AC-09); gold_eval is refused (constitution #7). Offline, over a tiny gold fixture; the last test checks
the real gold only when GOLD_PATH is set."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from app.catalog import DEMO_CUSTOMERS, DEMO_KEYS, FixtureCatalog, GoldCatalog, catalog_from_env
from nick_of_time.store.memory import MemoryStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server.gold import Gold  # noqa: E402

ANA, CAMILO = "CLI-Y0L7FZFOF0AZ", "CLI-CH2VHQO8WJHX"
DEMO_IDS = {ANA, CAMILO, "CLI-S3L7P0DXIYV7", "CLI-YSL35Q5OYTAJ", "CLI-52TJRRO5YA9F", "CLI-J5VPX6OQPPV2"}
CARD, SAVINGS, TRX, LOAN_TRX = "PRD-ANADEBIT0001", "PRD-ANASAVINGS01", "TRX-ANA00000000000000001", "TRX-ANA00000000000000002"


@pytest.fixture(scope="module")
def gold(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("data") / "gold"
    root.mkdir()
    pl.DataFrame([{"customer_id": ANA, "first_name": "Ana", "country": "México", "email": "x@example.com"},
                  {"customer_id": CAMILO, "first_name": "Camilo", "country": "Argentina", "email": "y@example.com"}]
                 ).write_parquet(root / "customers.parquet")
    pl.DataFrame([{"product_id": p, "customer_id": ANA, "product_type": t, "product_number": n, "product_status": "Active"}
                  for p, t, n in ((CARD, "Tarjeta Débito", "4111111111114417"), (SAVINGS, "Cuenta Ahorro", "000123"))]
                 ).write_parquet(root / "products.parquet")
    pl.DataFrame([{"transaction_id": tid, "product_id": p, "customer_id": ANA, "product_type": t,
                   "transaction_date": dt.datetime(2026, 5, 31, 12, 30), "amount": 1250.0, "currency": "MXN",
                   "amount_usd": 70.0, "merchant_name": "Tienda X", "transaction_status": "Approved",
                   "fraud_score": 72.0, "transaction_country": "México", "is_fraud": True}
                  for tid, p, t in ((TRX, CARD, "Tarjeta Débito"), (LOAN_TRX, SAVINGS, "Cuenta Ahorro"))]
                 ).write_parquet(root / "transactions_enriched.parquet")
    return root


def test_task7_gold_catalog_is_selected_with_gold_path_and_fixtures_without(gold, monkeypatch):
    monkeypatch.setenv("GOLD_PATH", str(gold))
    assert isinstance(catalog_from_env(), GoldCatalog)
    monkeypatch.delenv("GOLD_PATH")
    assert isinstance(catalog_from_env(), FixtureCatalog)


def test_ac_09_demo_customers_are_the_six_of_spec_09_without_score_or_zone(gold):
    customers = GoldCatalog(gold).customers()
    assert {c["customer_id"] for c in customers} == DEMO_IDS
    assert all(tuple(c) == DEMO_KEYS for c in customers)
    assert not any(k in json.dumps(customers) for k in ("score", "zone"))


def test_constitution_7_gold_eval_is_refused(tmp_path):
    with pytest.raises(ValueError, match="gold_eval"):
        GoldCatalog(tmp_path / "gold_eval")


def test_task7_reads_cards_and_card_transactions_only_and_fails_closed(gold):
    catalog = GoldCatalog(gold)
    assert catalog.products(ANA) == [{"product_id": CARD, "type": "debit", "last4": "4417", "status": "Active"}]
    assert catalog.transaction(TRX) == {"transaction_id": TRX, "amount": 1250.0, "currency": "MXN",
                                        "date": "2026-05-31", "merchant": "Tienda X", "synthetic": False}
    assert catalog.transaction(LOAN_TRX) is None and catalog.transaction("TRX-NOPE") is None
    assert catalog.customer(ANA)["country"] == "MX"
    assert catalog.customer(CAMILO) is None                   # gold says another country than the demo: fail closed
    assert catalog.customer("CLI-S3L7P0DXIYV7") is None       # a demo customer gold does not hold
    assert catalog.customer("CLI-NOTADEMO0001") is None       # not a demo customer


def test_ac_01_ac_05_a_session_for_ana_names_a_customer_the_mcp_gold_finds(gold):
    from app.main import create_app
    store = MemoryStore()
    client = TestClient(create_app(store=store, catalog=GoldCatalog(gold)), base_url="https://testserver")
    assert {c["customer_id"] for c in client.get("/api/demo/customers").json()} == DEMO_IDS
    r = client.post("/api/sessions", json={"customer_id": ANA, "mode": "replay"})
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/verify", json={"otp": r.json()["otp_demo"]}).status_code == 200
    assert [p["last4"] for p in client.get("/api/me/products").json()] == ["4417"]
    mcp = Gold(gold)                                          # what the MCP server's reads.py looks up
    customer_id = store.get_session(sid).customer_id
    assert mcp.customer(customer_id) is not None and mcp.transaction(customer_id, TRX) is not None
    assert client.post("/api/sessions", json={"customer_id": "CLI-DEMO0001", "mode": "replay"}).status_code == 404


@pytest.mark.skipif(not os.getenv("GOLD_PATH"), reason="checks the real gold only when GOLD_PATH is set")
def test_task7_every_demo_customer_is_in_the_real_gold_with_a_card():
    catalog = GoldCatalog(os.environ["GOLD_PATH"])
    for c in json.loads(DEMO_CUSTOMERS.read_text()):
        assert catalog.customer(c["customer_id"]) is not None, c["customer_id"]
        assert catalog.products(c["customer_id"]), c["customer_id"]
