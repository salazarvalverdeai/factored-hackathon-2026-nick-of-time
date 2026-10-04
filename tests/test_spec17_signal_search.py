"""Spec 17 task FEAT: candidate features from strictly earlier rows (AC-02), labels only through the guard (AC-05)."""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import pytest
from sklearn.metrics import roc_auc_score

from scripts.ml import fraud_features as ff
from scripts.ml import fraud_signal_search as ss
from scripts.ml import fraud_split as fs
from tests.test_spec17_screen import synthetic
from tests.test_spec17_split_features import REAL_SPLIT_HASH, T0, row

GOLD = os.environ.get("GOLD_PATH")
GOLD_EVAL = Path(os.environ.get("GOLD_EVAL_PATH", Path(__file__).resolve().parents[1] / "data" / "gold_eval"))
EXTRA = dict(transaction_city="Buenos Aires", branch_id="B1", response_code="00", product_opening_date=date(2024, 1, 1))
SANTIAGO = dict(transaction_country="Chile", transaction_city="Santiago", lat=-33.45, lon=-70.66)
OUT = ["transaction_id", *ss.CANDIDATES, ss.COMPLAINTS]


def r(tid, when, **kw):
    return row(tid, when, **{**EXTRA, **kw})


def candidates(rows, complaints=()):
    con = duckdb.connect()
    con.register("transactions_enriched", pl.DataFrame(rows, infer_schema_length=None).to_arrow())
    con.register("customers", pl.DataFrame({"customer_id": ["C1"], "registration_date": [datetime(2020, 1, 1)],
                                            "date_of_birth": [date(1990, 6, 1)]}).to_arrow())
    comp = pl.DataFrame(list(complaints) or [{"customer_id": "X", "creation_date": T0, "process_date": T0.date()}])
    con.register("complaints", comp.to_arrow())
    return {d["transaction_id"]: d for d in ss.build_candidates(con).select(OUT).to_dicts()}


BASE = [r("t1", T0, amount=10, transaction_status="Declined", response_code="51"),  # history only, never emitted
        r("t2", T0 + timedelta(minutes=30), amount=20),
        r("t3", T0 + timedelta(hours=2), amount=40, **SANTIAGO),
        r("t4", T0 + timedelta(hours=2), amount=999, merchant="M9", latitude=10.0, longitude=10.0),  # same time as t3
        r("t5", T0 + timedelta(hours=3), amount=5)]
COMPLAINTS = [{"customer_id": "C1", "creation_date": T0 - timedelta(days=2), "process_date": T0.date() - timedelta(1)},
              {"customer_id": "C1", "creation_date": T0 - timedelta(days=1), "process_date": T0.date() + timedelta(5)},
              {"customer_id": "C1", "creation_date": T0 + timedelta(hours=2), "process_date": T0.date() - timedelta(1)}]
# the last one is created at t3's own time; its process date is set early so that only the creation guard excludes it


def test_ac_02_candidates_use_only_strictly_earlier_rows():
    f = candidates(BASE, COMPLAINTS)
    assert set(f) == {"t2", "t3", "t4", "t5"}  # Declined t1 is history, not a row
    assert (f["t2"]["card_n_1h"], f["t2"]["declines_24h"], f["t2"]["decline_codes_7d"]) == (1, 1, 1)
    assert (f["t2"]["first_country"], f["t2"]["card_first_use"], f["t2"]["secs_since_merchant"]) == (0, 0, 1800)
    t3 = f["t3"]  # t4 shares its timestamp: never history, so t3 sees only t1 and t2
    assert (t3["card_n_24h"], t3["first_country"], t3["first_city"], t3["secs_since_merchant"]) == (2, 1, 1, 5400)
    assert t3["amount_over_max"] == pytest.approx(2.0) and t3["km_prev_located"] == pytest.approx(1137, abs=5)
    assert t3["speed_kmh"] == pytest.approx(t3["km_prev_located"] / 1.5)
    assert t3["complaints_90d"] == 1  # created 2 days before and processed: counted; late or same-time ones are not
    assert f["t4"]["card_n_24h"] == 2 and f["t5"]["card_n_24h"] == 4


def test_ac_02_changing_same_time_or_later_rows_or_forbidden_fields_does_not_change_a_candidate():
    ref = candidates(BASE, COMPLAINTS)["t3"]
    changed = [dict(x) for x in BASE]
    changed[3].update(amount=1e6, amount_usd=1e6, transaction_country="Chile", merchant_name="M1",
                      transaction_status="Declined", latitude=-33.0, longitude=-70.0)  # same-time neighbour
    changed[4].update(amount=1e6, amount_usd=1e6, transaction_country="Peru", transaction_status="Declined")  # later
    changed[2].update(product_status="Closed", qc_late_arrival=True, process_date=date(2030, 1, 1), fraud_score=99.0,
                      response_code="05", transaction_status="Pending", customer_segment="Premium", is_fraud=True)
    changed.append(r("t6", T0 + timedelta(days=3), amount=1e6))
    late = COMPLAINTS + [{"customer_id": "C1", "creation_date": T0 + timedelta(hours=3), "process_date": T0.date()}]
    assert candidates(changed, late)["t3"] == ref
    assert not [c for c in [*ss.CANDIDATES, *ss.RATES, ss.COMPLAINTS] if ff.is_forbidden(c)]


def test_ac_02_bootstrap_auc_matches_sklearn_and_flags_only_material_replicated_signal():
    rng = np.random.default_rng(0)
    y = (rng.random(20_000) < 0.01).astype(int)
    x = np.round(rng.normal(size=y.size) + 1.5 * y, 1)  # ties, planted signal
    x[::7] = np.nan  # null as the lowest value
    auc, lo, hi = ss.auc_ci(y, x)
    assert auc == pytest.approx(roc_auc_score(y, np.nan_to_num(x, nan=-1e9))) and lo < auc < hi and lo > 0.5
    noise = ss.auc_ci(y, rng.normal(size=y.size))
    assert noise[1] < 0.5 < noise[2]
    rare = np.zeros(y.size)
    rare[np.flatnonzero(y == 0)[:30]] = 1  # a flag no fraud carries: CI of zero width just below 0.5, not material
    assert ss.auc_ci(y, rare)[2] < 0.5 and not ss.is_signal(ss.auc_ci(y, rare), ss.auc_ci(y, rare))
    assert ss.is_signal((auc, lo, hi), (auc, lo, hi)) and not ss.is_signal((auc, lo, hi), noise)  # must replicate
    oof, _ = ss.train_rates([str(i) for i in range(y.size)], y, ["0"])  # one level per row: in-sample would leak y
    assert roc_auc_score(y, oof) == 0.5  # out-of-fold, so every train row gets the prior


def synthetic_gold(tmp_path):
    tx, split, fraud = synthetic()
    gold = tmp_path / "gold"
    gold.mkdir()
    tx.with_columns(**{k: pl.lit(v) for k, v in EXTRA.items()}).write_parquet(gold / "transactions_enriched.parquet")
    pl.DataFrame({"customer_id": [f"C{i}" for i in range(25)], "registration_date": [datetime(2020, 1, 1)] * 25,
                  "date_of_birth": [date(1990, 1, 1)] * 25}).write_parquet(gold / "customers.parquet")
    pl.DataFrame({"customer_id": ["C1"], "creation_date": [datetime(2025, 7, 1)], "process_date": [date(2025, 7, 2)]}
                 ).write_parquet(gold / "complaints.parquet")
    lab = tmp_path / "labels.parquet"
    pl.DataFrame({"transaction_id": list(fraud), "is_fraud": list(fraud.values())}).write_parquet(lab)
    return gold, lab, split


def test_ac_05_search_reads_labels_only_through_the_guard_and_writes_outside_the_repo(tmp_path, monkeypatch):
    gold, lab, split = synthetic_gold(tmp_path)
    asked, real = [], fs.read_labels
    monkeypatch.setattr(fs, "read_labels", lambda p, s, w: (asked.append(set(w)), real(p, s, w))[1])
    df, h = ss.load(gold, lab)
    assert asked == [{fs.TRAIN, fs.VALIDATION}] and set(df["split_window"]) == {fs.TRAIN, fs.VALIDATION}
    assert not set(split.filter(pl.col("split_window") == fs.TEST)["transaction_id"]) & set(df["transaction_id"])
    rows = {x["candidate"]: x for x in ss.search(df)["rows"]}
    assert rows["amount_over_max"]["signal"]  # positive control: synthetic frauds are large foreign purchases
    src = Path(ss.__file__).read_text()
    assert src.count("read_parquet") == 1 and "gold_eval" not in src  # one reader, for the gold views
    assert src.replace("transaction_labels.parquet", "").count("transaction_labels") == 0 and "fs.read_labels(" in src
    with pytest.raises(ValueError):  # the protocol seal: no results inside the repo
        monkeypatch.setattr(sys, "argv", ["x", "--gold", str(gold), "--eval", str(tmp_path), "--out",
                                          str(ss.sc.REPO / "eval" / "results" / "spec17-search")])
        ss.main()
    (tmp_path / "transaction_labels.parquet").write_bytes(lab.read_bytes())
    monkeypatch.setattr(sys, "argv", ["x", "--gold", str(gold), "--eval", str(tmp_path), "--out", str(tmp_path / "o")])
    ss.main()
    rec = json.loads((tmp_path / "o" / "fraud_signal_search.json").read_text(), parse_constant=pytest.fail)
    assert rec["split_hash"] == h and rec["label_windows"] == ["train", "validation"]


@pytest.mark.skipif(not GOLD or not GOLD_EVAL.exists(), reason="opt-in: set GOLD_PATH and GOLD_EVAL_PATH")
def test_ac_02_real_gold_no_candidate_beyond_the_bank_score_opt_in():
    df, h = ss.load(GOLD, GOLD_EVAL / "transaction_labels.parquet")
    rec = ss.search(df)
    assert h == REAL_SPLIT_HASH and rec["n_fraud"] == {"train": 896, "validation": 182}
    rows = {x["candidate"]: x for x in rec["rows"]}
    assert rows.pop("bank_fraud_score")["signal"]  # positive control on real data
    assert not [k for k, v in rows.items() if v["signal"]]  # spec 17 §4.2: no transaction-time signal on gold v1
