"""Spec 14 §11 (lead, 2026-10-05): Bank today and the replay of real card charges through S0, on a tiny gold fixture.
Offline: no network, no LLM, no real gold; `is_fraud` is planted and gold_eval is unreadable, so a read would fail."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import polars as pl
import pytest

from data.ops import bronze, replay, sample, series
from data.ops.run import run
from nick_of_time import ids
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore

NOW = dt.datetime(2026, 10, 5, 12, tzinfo=dt.UTC)
C = {"MX1": ("CLI-MX0000000001", "México"), "CO": ("CLI-CO0000000001", "Colombia"),
     "AR": ("CLI-AR0000000001", "Argentina"), "MX2": ("CLI-MX0000000002", "México")}


def _trx(n: int, who: str, day: dt.date, amount: float, currency: str, score: float | None, merchant=None,
         status="Approved", ptype="Tarjeta Débito") -> dict:
    return {"transaction_id": f"TRX-{n:020d}", "product_id": f"PRD-{n:012d}", "customer_id": C[who][0],
            "transaction_date": dt.datetime.combine(day, dt.time(10)), "amount": amount, "currency": currency,
            "amount_usd": None, "merchant_name": merchant, "transaction_status": status, "fraud_score": score,
            "product_type": ptype, "transaction_country": C[who][1], "is_fraud": True}            # planted


def _complaint(n: int, day: dt.date, category: str = "Transactions", case_type: str = "Claim") -> dict:
    created = dt.datetime.combine(day, dt.time(9))
    return {"complaint_id": f"CMP-{n:04d}", "creation_date": created, "customer_id": C["MX1"][0],
            "category": category, "case_type": case_type, "first_response_date": created + dt.timedelta(days=n % 3),
            "status": "Escalated" if n == 2 else "Open", "sla_breached": n == 3, "resolution_days": None}


@pytest.fixture
def gold(tmp_path: Path):
    root = tmp_path / "gold"
    root.mkdir()
    pl.DataFrame([_trx(1, "MX1", dt.date(2026, 3, 8), 120.0, "USD", 80.0, "Uber"),     # zone high: block
                  _trx(2, "CO", dt.date(2026, 4, 1), 50000.0, "COP", 10.0, "Exito"),   # twins: the engine asks
                  _trx(3, "CO", dt.date(2026, 4, 1), 50000.0, "COP", 10.0, "Exito"),
                  _trx(4, "MX2", dt.date(2026, 2, 10), 15.5, "USD", None),              # no score: zone human
                  _trx(5, "AR", dt.date(2026, 5, 4), 999.0, "ARS", 20.0, "Coto"),
                  _trx(6, "AR", dt.date(2026, 5, 6), 30.0, "ARS", 20.0, status="Declined"),   # never sampled
                  _trx(7, "AR", dt.date(2025, 12, 1), 30.0, "ARS", 20.0),                # before the window
                  _trx(8, "AR", dt.date(2026, 5, 7), 30.0, "ARS", 20.0, ptype="Cuenta Ahorro")],
                 schema_overrides={"amount_usd": pl.Float64}).write_parquet(root / "transactions_enriched.parquet")
    pl.DataFrame({"customer_id": [c for c, _ in C.values()], "country": [k for _, k in C.values()],
                  "segment": ["Basic"] * 4, "first_name": ["Ana", "Bruno", "Carla", "Dora"]}).write_parquet(
        root / "customers.parquet")
    days = [dt.date(2026, 2, 11), dt.date(2026, 3, 9), dt.date(2026, 4, 2), dt.date(2026, 4, 4), dt.date(2026, 5, 5)]
    pl.DataFrame([*(_complaint(n, d, "Fees" if n % 2 else "Transactions", "Complaint") for n, d in enumerate(days, 1)),
                  _complaint(9, dt.date(2026, 3, 11), "Account"),                        # not W3
                  _complaint(10, dt.date(2025, 12, 20))]).write_parquet(root / "complaints.parquet")   # before
    labels = tmp_path / "gold_eval" / "transaction_labels.parquet"
    labels.parent.mkdir()
    pl.DataFrame({"transaction_id": ["TRX-00000000000000000001"], "is_fraud": [True]}).write_parquet(labels)
    os.chmod(labels, 0)                                  # opening it would fail the run
    yield root
    os.chmod(labels, 0o600)


def simulate(gold: Path, merchant: bool = True):
    return replay.run(gold, series.quota(series.asis(gold)), merchant=merchant)


def job(gold: Path, out: Path, store=None, contacts=None, web: Path | None = None) -> dict:
    if store is None:
        store, contacts = simulate(gold)
    web = web or out / "ops_kpis.json"
    run(bronze.from_memory(store), gold_path=gold, out=out, web=web, now=NOW, contacts=contacts,
        asis=series.asis(gold), variant=simulate(gold, merchant=False)[1])
    return json.loads(web.read_text())["data"]


def test_ac_12_the_replay_is_deterministic(gold, tmp_path):
    """AC-12: the same gold gives the same sample, outcomes, gold tables and series."""
    first, second = job(gold, tmp_path / "a"), job(gold, tmp_path / "b")
    assert first == second
    for name in ("ops_kpis", "replay_contacts"):
        assert pl.read_parquet(tmp_path / "a/gold" / f"{name}.parquet").equals(
            pl.read_parquet(tmp_path / "b/gold" / f"{name}.parquet"))
    total = first["series"]["replay"]["total"]
    assert (total["contacts"], total["cases_opened"], total["handed_to_analyst"]["numerator"]) == (5, 3, 2)
    assert total["complete_intake"] == {"value": 0.6, "numerator": 3, "denominator": 5}
    assert total["safe_automated_resolution"] == {"value": 1.0, "numerator": 1, "denominator": 1}


def test_ac_13_no_fraud_label_and_no_gold_eval(gold, tmp_path):
    """AC-13: the run succeeds with gold_eval unreadable and is_fraud planted; gold_eval is refused by name; no
    output carries the label."""
    data = job(gold, tmp_path)
    with pytest.raises(ValueError, match="gold_eval"):
        replay.sample(tmp_path / "gold_eval", {"2026-03": 1})
    with pytest.raises(ValueError, match="gold_eval"):
        series.asis(tmp_path / "gold_eval")
    assert "is_fraud" not in json.dumps(data) and "is_fraud" not in replay.SAMPLE_SQL.read_text()
    for name in ("ops_kpis", "replay_contacts"):
        assert "is_fraud" not in pl.read_parquet(tmp_path / "gold" / f"{name}.parquet").columns


def test_ac_14_several_candidates_ask_and_open_nothing(gold):
    """AC-14: a sample sized to the bank's W3 complaints per month, of approved card charges in the window; two
    candidate charges → the engine asks, as in production, and nothing opens; a named charge opens its own case."""
    store, contacts = simulate(gold)
    assert contacts["month"].to_list() == ["2026-02", "2026-03", "2026-04", "2026-04", "2026-05"]
    assert contacts["outcome"].to_list() == ["handoff", "automated", "asked_several", "asked_several", "handoff"]
    assert contacts["complete_intake"].to_list() == [True, True, False, False, True]
    assert store.list_cases(C["CO"][0], run_id=None) == []
    blocked = store.list_cases(C["MX1"][0], run_id=None)[0]
    assert (blocked.transaction_id, blocked.zone) == ("TRX-00000000000000000001", "high")
    assert blocked.credit_deadline == dt.date(2026, 3, 11)                            # MX: 2 business days


def test_ac_15_each_series_carries_label_source_window_and_notes(gold, tmp_path):
    """AC-15: Bank today [data], With Nick of Time [simulated], Live pending; each with its source, window and
    notes; the bank's FCR against complete intake; the final resolution time for the bank only."""
    data = job(gold, tmp_path)["series"]
    bank, sim, live = data["bank_today"], data["replay"], data["live"]
    assert (bank["label"], sim["label"]) == ("[data]", "[simulated]") and data["window"] == ["2026-01", "2026-05"]
    assert data["compare"] == [{"bank_today": "first_contact_resolution", "replay": "complete_intake"},
                               {"bank_today": "days_to_receipt", "replay": "days_to_receipt"}]
    for s, context in ((bank, {"escalated", "outside_sla_at_intake", "resolution_days"}),
                       (sim, {"handed_to_analyst", "opened_without_deadline", "safe_automated_resolution"})):
        assert s["source"] and s["window"] == data["window"]
        assert set(s["notes"]) >= {*(pair[s["key"]] for pair in data["compare"]), *context}
        assert context <= set(s["total"]), "context figures carry their own definition and are never paired"
    assert not {"escalated", "outside_sla_at_intake"} & set(sim["total"])
    assert (live["status"], live["message"]) == ("pending", "Pending: no live traffic yet")
    assert bank["total"]["contacts"] == sim["total"]["contacts"] == 5 and bank["total"]["escalated"]["numerator"] == 1
    assert bank["total"]["first_contact_resolution"] == {"value": pytest.approx(0.436, abs=1e-3), "numerator": 51021,
                                                         "denominator": 117021, "constant": True}
    assert "resolution_days" in bank["total"] and "resolution_days" not in sim["total"]
    assert "not the bank's resolved-at-first-contact" in sim["notes"]["complete_intake"]
    assert "upper bound" in sim["notes"]["complete_intake"]
    sens = sim["sensitivity"]
    assert sens["named"]["complete_intake"]["numerator"] == 3 and sens["amount_and_date"]["asked"]["denominator"] == 5
    assert [m["month"] for m in bank["months"]] == ["2026-02", "2026-03", "2026-04", "2026-05"]


def test_ac_16_an_eval_row_never_counts(gold, tmp_path):
    """AC-16: a case written by an evaluation run (run_id set) in the same store never reaches the replay series."""
    store, contacts = simulate(gold)
    store.create_case(NewCase(customer_id=C["MX2"][0], transaction_id="TRX-00000000000000000004",
                              product_id="PRD-000000000004", country="MX", product_type="debit", zone="human",
                              dispute_type="unrecognized_charge", opened_on=dt.date(2026, 2, 12), mode="replay",
                              run_id="eval-dev:S0:1", trace_id="T-eval"), actor="agent", action_id=ids.new_id("action"))
    total = job(gold, tmp_path, store, contacts)["series"]["replay"]["total"]
    assert total["cases_opened"] == 3 and total["contacts"] == 5


def test_ac_17_the_export_does_not_depend_on_local_state(gold, tmp_path):
    """AC-17: two runs write byte-identical files, also when one output folder holds an earlier run (which moves its
    manifest version); the export names no manifest version."""
    store, contacts = simulate(gold)
    stale = tmp_path / "stale"
    run(bronze.from_memory(sample.seed(MemoryStore(), sample.gold_transactions(gold))), gold_path=gold, out=stale,
        now=NOW)
    job(gold, stale, store, contacts, web=tmp_path / "a.json")
    job(gold, tmp_path / "clean", store, contacts, web=tmp_path / "b.json")
    assert json.loads((stale / "manifest.json").read_text())["version"] == 2
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    assert "manifest v" not in json.loads((tmp_path / "a.json").read_text())["source"]
