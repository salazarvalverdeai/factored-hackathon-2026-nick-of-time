"""Spec 09 AC-02 — every demo customer meets its scenario's rule on gold, so replay mode always reaches a case.

Rules (scripts/demo_customers.py): "one card" = exactly one card charge of the stated product in the search window of
`search_transaction` (30 days before DEMO_TODAY, Approved or Pending); "several" = charges of at least 2 cards there."""
from __future__ import annotations

import json

import polars as pl
import pytest

from scripts import demo_customers as dc

CUSTOMERS = json.loads(dc.CUSTOMERS.read_text(encoding="utf-8"))
GOLD = dc.gold_dir()


def window(rows: list[tuple[str, str, str]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=["customer_id", "product_id", "product"], orient="row")


def test_ac_02_rules_on_synthetic_windows():
    """AC-02: the one-card rule wants one charge on the stated product; the several rule wants 2 different cards."""
    assert dc.holds(dc.ONE_CARD, "credit", window([("C", "P1", "credit")]))
    assert not dc.holds(dc.ONE_CARD, "credit", window([]))                       # a customer with no recent charge
    assert not dc.holds(dc.ONE_CARD, "credit", window([("C", "P1", "credit"), ("C", "P1", "credit")]))
    assert not dc.holds(dc.ONE_CARD, "debit", window([("C", "P1", "credit")]))
    assert dc.holds(dc.SEVERAL, None, window([("C", "P1", "credit"), ("C", "P2", "debit")]))
    assert not dc.holds(dc.SEVERAL, None, window([("C", "P1", "credit"), ("C", "P1", "credit")]))


def test_ac_02_rule_follows_the_scenario_text():
    """AC-02: one rule per scenario, the product from display_name."""
    assert {c["scenario"].split(" · ")[0] for c in CUSTOMERS} == {
        "Unrecognized charge on one card", "Unrecognized charge among several recent ones"}
    rules = [dc.rule_of(c)[0] for c in CUSTOMERS]
    assert rules.count(dc.ONE_CARD) == 4 and rules.count(dc.SEVERAL) == 2


@pytest.mark.skipif(GOLD is None, reason="data/gold has no parquet in this checkout")
def test_ac_02_every_demo_customer_meets_its_rule_on_gold():
    """AC-02: the six demo customers have recent charges in the replay search window."""
    results = dc.check(GOLD, CUSTOMERS)
    assert results == {c["customer_id"]: True for c in CUSTOMERS}, results
