"""Spec 07 AC-07: the demo picker names gold's first name, the one `get_customer_profile` greets with, so the picker,
the web's greeting and the agent's greeting name the same person. Offline, over a tiny gold whose first names differ
from the hand-written labels of `eval/demo/customers.json` (as the real gold does: "Ana" there is "Gerardo Lucas")."""
from __future__ import annotations

import datetime as dt

import polars as pl
import pytest
from fastapi.testclient import TestClient

from app import demo
from app.catalog import GoldCatalog
from nick_of_time.store.memory import MemoryStore

ANA, BRUNO, SOFIA = "CLI-Y0L7FZFOF0AZ", "CLI-YSL35Q5OYTAJ", "CLI-S3L7P0DXIYV7"


@pytest.fixture(scope="module")
def gold(tmp_path_factory):
    root = tmp_path_factory.mktemp("names") / "gold"
    root.mkdir()
    pl.DataFrame([{"customer_id": ANA, "first_name": "Gerardo Lucas", "country": "México"},
                  {"customer_id": BRUNO, "first_name": "Verónica", "country": "Argentina"}]
                 ).write_parquet(root / "customers.parquet")
    return root


@pytest.mark.parametrize("label, first, shown", [
    ("Ana (MX · debit)", "Gerardo Lucas", "Gerardo Lucas (MX · debit)"),
    ("Bruno (AR · debit)", "Verónica", "Verónica (AR · debit)"),
    ("Ana", "Gerardo", "Gerardo"),
    ("Ana (MX · debit)", None, "Ana (MX · debit)")])
def test_ac_07_the_picker_label_carries_the_gold_first_name(label, first, shown):
    assert demo.picker_label(label, first) == shown


def test_ac_07_the_api_lists_the_demo_customers_with_the_gold_name_the_agent_greets_with(gold):
    from app.live import create_live_app
    start = dt.datetime(2026, 6, 1, 15, tzinfo=dt.UTC)
    client = TestClient(create_live_app(MemoryStore(now=lambda: start), catalog=GoldCatalog(gold), now=lambda: start))
    listed = {c["customer_id"]: c["display_name"] for c in client.get("/api/demo/customers").json()}
    assert listed[ANA] == "Gerardo Lucas (MX · debit)"
    assert listed[BRUNO] == "Verónica (AR · debit)"
    assert listed[SOFIA] == "Sofía (MX · several cards)"            # not in this gold: no session opens for it
    assert len(listed) == 6
