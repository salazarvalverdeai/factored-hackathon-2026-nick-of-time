"""Spec 14 §11 (lead, 2026-10-05): Bank today and the replay of the W3 complaints through S0, on a tiny gold fixture.
Offline: no network, no LLM, no real gold; `is_fraud` is planted and gold_eval is unreadable, so a read would fail."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import polars as pl
import pytest

from data.ops import bronze, replay, series
from data.ops.run import run
from nick_of_time import ids
from nick_of_time.store import NewCase

NOW = dt.datetime(2026, 10, 5, 12, tzinfo=dt.UTC)
C = {"MX1": ("CLI-MX0000000001", "México"), "CO": ("CLI-CO0000000001", "Colombia"),
     "AR": ("CLI-AR0000000001", "Argentina"), "MX2": ("CLI-MX0000000002", "México")}


def _trx(n: int, who: str, day: dt.date, amount: float, currency: str, score: float) -> dict:
    return {"transaction_id": f"TRX-{n:020d}", "product_id": f"PRD-{n:012d}", "customer_id": C[who][0],
            "transaction_date": dt.datetime.combine(day, dt.time(10)), "amount": amount, "currency": currency,
            "amount_usd": None, "merchant_name": None, "transaction_status": "Approved", "fraud_score": score,
            "product_type": "Tarjeta Débito", "transaction_country": C[who][1], "is_fraud": True}   # planted


def _complaint(n: int, who: str, day: dt.date, category: str = "Transactions", sub: str | None = "Cargo no reconocido",
               amount: float | None = None, currency: str | None = None, case_type: str = "Claim") -> dict:
    created = dt.datetime.combine(day, dt.time(9))
    return {"complaint_id": f"CMP-{n:04d}", "creation_date": created, "customer_id": C[who][0], "category": category,
            "case_type": case_type, "subcategory": sub, "claimed_amount": amount, "currency": currency,
            "first_response_date": created + dt.timedelta(days=n % 3), "status": "Escalated" if n == 2 else "Open",
            "sla_breached": n == 3, "resolution_days": None}


@pytest.fixture
def gold(tmp_path: Path):
    root = tmp_path / "gold"
    root.mkdir()
    pl.DataFrame([_trx(1, "MX1", dt.date(2026, 3, 8), 120.0, "USD", 80.0),           # one named charge, zone high
                  _trx(2, "CO", dt.date(2026, 4, 1), 50000.0, "COP", 60.0),          # two charges: the engine asks
                  _trx(3, "CO", dt.date(2026, 4, 3), 60000.0, "COP", 60.0),
                  _trx(4, "MX2", dt.date(2026, 2, 10), 15.5, "USD", 10.0)],          # one unnamed charge, zone human
                 schema_overrides={"amount_usd": pl.Float64}).write_parquet(root / "transactions_enriched.parquet")
    pl.DataFrame({"customer_id": [c for c, _ in C.values()], "country": [k for _, k in C.values()],
                  "segment": ["Basic"] * 4, "first_name": ["Ana", "Bruno", "Carla", "Dora"]}).write_parquet(
        root / "customers.parquet")
    pl.DataFrame([_complaint(1, "MX1", dt.date(2026, 3, 10), amount=120.0, currency="USD"),
                  _complaint(2, "CO", dt.date(2026, 4, 5), "Fees", "Cobro indebido", case_type="Complaint"),
                  _complaint(3, "AR", dt.date(2026, 5, 2), amount=999.0, currency="ARS"),
                  _complaint(4, "MX2", dt.date(2026, 2, 12), sub=None, case_type="Request"),
                  _complaint(5, "MX1", dt.date(2026, 3, 11), "Account"),                  # not W3
                  _complaint(6, "MX1", dt.date(2025, 5, 20))]).write_parquet(root / "complaints.parquet")  # before
    labels = tmp_path / "gold_eval" / "transaction_labels.parquet"
    labels.parent.mkdir()
    pl.DataFrame({"transaction_id": ["TRX-00000000000000000001"], "is_fraud": [True]}).write_parquet(labels)
    os.chmod(labels, 0)                                  # opening it would fail the run
    yield root
    os.chmod(labels, 0o600)


def job(gold: Path, out: Path, store=None, contacts=None) -> dict:
    if store is None:
        store, contacts = replay.run(gold)
    run(bronze.from_memory(store), gold_path=gold, out=out, web=out / "ops_kpis.json", now=NOW, contacts=contacts,
        asis=series.asis(gold))
    return json.loads((out / "ops_kpis.json").read_text())["data"]


def test_ac_12_the_replay_is_deterministic(gold, tmp_path):
    """AC-12: the same gold gives the same outcomes, the same gold tables and the same series."""
    first, second = job(gold, tmp_path / "a"), job(gold, tmp_path / "b")
    assert first == second
    for name in ("ops_kpis", "replay_contacts"):
        assert pl.read_parquet(tmp_path / "a/gold" / f"{name}.parquet").equals(
            pl.read_parquet(tmp_path / "b/gold" / f"{name}.parquet"))
    total = first["series"]["replay"]["total"]
    assert (total["contacts"], total["cases_opened"], total["first_contact_resolution"]["numerator"],
            total["escalated"]["numerator"]) == (4, 2, 1, 1)


def test_ac_13_no_fraud_label_and_no_gold_eval(gold, tmp_path):
    """AC-13: the run succeeds with gold_eval unreadable and is_fraud planted; gold_eval is refused by name; no
    output carries the label."""
    data = job(gold, tmp_path)
    for refused in (replay.complaints, series.asis):
        with pytest.raises(ValueError, match="gold_eval"):
            refused(tmp_path / "gold_eval")
    assert "is_fraud" not in json.dumps(data)
    for name in ("ops_kpis", "replay_contacts"):
        assert "is_fraud" not in pl.read_parquet(tmp_path / "gold" / f"{name}.parquet").columns


def test_ac_14_several_candidates_ask_and_open_nothing(gold):
    """AC-14: two candidate charges → the engine asks, as in production; no case is opened for that customer. No
    candidate asks too; one unnamed charge is confirmed [assumption] and opens a case."""
    store, contacts = replay.run(gold)
    assert contacts["outcome"].to_list() == ["automated", "asked_several", "asked_none", "handoff"]
    assert store.list_cases(C["CO"][0], run_id=None) == [] and store.list_cases(C["AR"][0], run_id=None) == []
    assert contacts["confirmed"].to_list() == [False, False, False, True]
    blocked = store.list_cases(C["MX1"][0], run_id=None)[0]
    assert blocked.zone == "high" and blocked.credit_deadline == dt.date(2026, 3, 12)    # MX, 2 business days


def test_ac_15_each_series_carries_label_source_window_and_notes(gold, tmp_path):
    """AC-15: Bank today [data], With Nick of Time [simulated], Live pending; each with its source, window and
    notes; the final resolution time exists for the bank only."""
    data = job(gold, tmp_path)["series"]
    bank, sim, live = data["bank_today"], data["replay"], data["live"]
    assert (bank["label"], sim["label"]) == ("[data]", "[simulated]") and data["window"] == ["2025-06", "2026-05"]
    for s in (bank, sim):
        assert s["source"] and s["window"] == data["window"] and set(s["notes"]) >= {
            "days_to_receipt", "first_contact_resolution", "escalated", "outside_sla_at_intake"}
    assert (live["status"], live["message"]) == ("pending", "Pending: no live traffic yet")
    assert bank["total"]["contacts"] == 4 and bank["total"]["escalated"]["numerator"] == 1
    assert bank["total"]["first_contact_resolution"] == {"value": pytest.approx(0.436, abs=1e-3), "numerator": 51021,
                                                         "denominator": 117021, "constant": True}
    assert "resolution_days" in bank["total"] and "resolution_days" not in sim["total"]
    assert [m["month"] for m in bank["months"]] == ["2026-02", "2026-03", "2026-04", "2026-05"]


def test_ac_16_an_eval_row_never_counts(gold, tmp_path):
    """AC-16: a case written by an evaluation run (run_id set) in the same store never reaches the replay series."""
    store, contacts = replay.run(gold)
    store.create_case(NewCase(customer_id=C["MX2"][0], transaction_id="TRX-00000000000000000004",
                              product_id="PRD-000000000004", country="MX", product_type="debit", zone="human",
                              dispute_type="unrecognized_charge", opened_on=dt.date(2026, 2, 12), mode="replay",
                              run_id="eval-dev:S0:1", trace_id="T-eval"), actor="agent", action_id=ids.new_id("action"))
    total = job(gold, tmp_path, store, contacts)["series"]["replay"]["total"]
    assert total["cases_opened"] == 2 and total["contacts"] == 4
