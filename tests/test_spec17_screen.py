"""Spec 17 T3 (17b): the sklearn screen, calibration, cost harness, label guard (AC-03, AC-05). Offline, synthetic."""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import joblib
import numpy as np
import polars as pl
import pytest
from sklearn.dummy import DummyClassifier

from scripts.ml import fraud_features as ff
from scripts.ml import fraud_screen as sc
from scripts.ml import fraud_split as fs

GOLD = os.environ.get("GOLD_PATH")
GOLD_EVAL = Path(os.environ.get("GOLD_EVAL_PATH", Path(__file__).resolve().parents[1] / "data" / "gold_eval"))


def synthetic(n=600, seed=1):
    """Transactions across train, validation and test months; frauds are large foreign night purchases."""
    rng = np.random.default_rng(seed)
    start = datetime(2025, 6, 1)
    rows, fraud = [], {}
    for i in range(n):
        when = start + timedelta(days=int(i * 330 / n), hours=int(rng.integers(0, 24)), minutes=i % 60)
        bad = rng.random() < 0.08
        amt = float(rng.uniform(800, 3000) if bad else rng.uniform(5, 200))
        tid = f"T{i:04d}"
        fraud[tid] = bool(bad)
        rows.append(dict(
            transaction_id=tid, transaction_date=when, customer_id=f"C{i % 25}", product_id=f"P{i % 25}", amount=amt,
            amount_usd=amt, currency="USD", channel="POS" if i % 2 else "Online", transaction_type="Purchase",
            transaction_category=None, merchant_name=f"M{i % 9}", merchant_category="Retail",
            transaction_country="Peru" if bad else "Argentina", latitude=-34.6, longitude=-58.4,
            product_type="Tarjeta Débito" if i % 3 else "Cuenta", customer_country="Argentina" if i % 4 else "Mexico",
            customer_segment="Plus", fraud_score=float(rng.uniform(40, 90)) if bad and i % 3 else None,
            transaction_status="Approved"))
    tx = pl.DataFrame(rows, infer_schema_length=None)
    con = duckdb.connect()
    con.register("transactions_enriched", tx.to_arrow())
    return tx, fs.build_split(con), fraud


def prepared(tmp_path, monkeypatch=None):
    tx, split, fraud = synthetic()
    lab_path = tmp_path / "labels.parquet"
    pl.DataFrame({"transaction_id": list(fraud), "is_fraud": list(fraud.values())}).write_parquet(lab_path)
    labels = fs.read_labels(lab_path, split, fs.LABEL_WINDOWS)
    tx = tx.filter(pl.col("transaction_date") < datetime(2026, 4, 1))
    return sc.assemble(tx, split, labels), fs.split_hash(split), split, lab_path




def test_ac_03_every_arm_trains_scores_and_is_calibrated_on_validation(tmp_path):
    df, h, _, _ = prepared(tmp_path)
    rec = sc.run_screen(df, h, tmp_path / "out")
    names = {r["arm"] for r in rec["results"]}
    assert names == {"s_bank", "iforest", "logreg", "sgd", "gnb", "tree", "rf", "extra_trees", "hgb", "mlp", "stacked"}
    n_val = df.filter(pl.col("split_window") == fs.VALIDATION).height
    for r in rec["results"]:
        assert r["n"] == n_val  # a shuffled or misjoined label vector would fail the positive control below
        if r["arm"] in ("logreg", "sgd", "tree", "rf", "extra_trees", "hgb", "mlp", "stacked"):
            assert r["pr_auc"] >= 0.8, r["arm"]  # positive control: synthetic frauds are large foreign purchases
        assert 0 <= r["pr_auc"] <= 1 + 1e-9 and 0 <= r["brier_calibration_window"] <= 1 and set(r["by_month"]) == {"2026-02", "2026-03"}
        assert r["split_hash"] == h


def test_ac_03_calibrator_uses_only_validation_scores(tmp_path, monkeypatch):
    df, h, _, _ = prepared(tmp_path)
    seen = []
    real = sc.fit_calibrator
    monkeypatch.setattr(sc, "fit_calibrator", lambda arm, s, y: (seen.append(len(s)), real(arm, s, y))[1])
    sc.run_screen(df, h, tmp_path / "out", arms={"logreg": sc.make_arms()["logreg"]})
    n_val = df.filter(pl.col("split_window") == fs.VALIDATION).height
    assert seen and set(seen) == {n_val}


def test_ac_03_downsampling_is_train_only_and_keeps_all_frauds():
    y = np.array([0] * 5000 + [1] * 10)
    idx = sc.downsample(y)
    assert y[idx].sum() == 10 and len(idx) == 10 + sc.LEGIT_PER_FRAUD * 10


def test_ac_03_harness_records_time_size_p95_hash_and_stamps_models(tmp_path):
    df, h, _, _ = prepared(tmp_path)
    out = tmp_path / "out"
    rec = sc.run_screen(df, h, out, arms={"tree": sc.make_arms()["tree"]})
    r = next(x for x in rec["results"] if x["arm"] == "tree")
    assert r["train_seconds"] > 0 and r["p95_ms"] > 0 and r["model_bytes"] > 0 and r["throughput_tps"] > 0
    f = out / "models" / "fraud-screen-tree.joblib"
    assert r["model_sha256"] == sc.sha256_file(f)
    assert joblib.load(f)["meta"]["split_hash"] == h
    strict = json.loads((out / "fraud_screen_validation.json").read_text(),
                        parse_constant=lambda c: pytest.fail(f"{c} is not JSON"))  # NaN/Infinity rejected, as in JS
    assert strict["split_hash"] == h
    bank = next(x for x in strict["results"] if x["arm"] == "s_bank")
    assert bank["recall_budget_1pct_no_bank_score"] is None  # all ties: undefined, written as null
    slices = [v for x in strict["results"] for k in ("by_country", "by_segment") for v in x[k].values()]
    assert slices and all(v["n_fraud"] > 0 and 0 <= v["recall_budget_1pct"] <= 1 for v in slices)


def test_ac_03_cold_start_history_length_feature():
    assert "n_prev" in ff.FEATURES
    t0 = datetime(2025, 9, 1)
    rows = [dict(transaction_id=f"x{i}", transaction_date=t0 + timedelta(days=i), customer_id="C", product_id="P",
                 amount=1.0, amount_usd=1.0, currency="USD", channel="POS", transaction_type="Purchase",
                 transaction_category=None, merchant_name="M", merchant_category="R", transaction_country="A",
                 latitude=None, longitude=None, product_type="Cuenta", customer_country="A",
                 transaction_status="Approved") for i in range(3)]
    assert ff.build_features(pl.DataFrame(rows, infer_schema_length=None))["n_prev"].to_list() == [0, 1, 2]


def test_ac_05_screen_never_sees_test_rows_or_labels(tmp_path, monkeypatch):
    tx, split, fraud = synthetic()
    lab = tmp_path / "labels.parquet"
    pl.DataFrame({"transaction_id": list(fraud), "is_fraud": list(fraud.values())}).write_parquet(lab)
    asked = []
    real = fs.read_labels
    monkeypatch.setattr(fs, "read_labels", lambda p, s, w: (asked.append(set(w)), real(p, s, w))[1])
    gold = tmp_path / "gold"
    gold.mkdir()
    tx.write_parquet(gold / "transactions_enriched.parquet")
    df, h = sc.load_data(gold, lab)
    assert asked == [{fs.TRAIN, fs.VALIDATION}]
    assert set(df["split_window"].unique()) == {fs.TRAIN, fs.VALIDATION}
    test_ids = set(split.filter(pl.col("split_window") == fs.TEST)["transaction_id"])
    assert not test_ids & set(df["transaction_id"])
    with pytest.raises(fs.LabelAccessError):
        fs.read_labels(lab, split, {fs.TEST})


def test_ac_05_assemble_refuses_test_window_rows():
    tx, split, fraud = synthetic()  # labels for every window, bypassing read_labels: assemble is the second guard
    labels = pl.DataFrame({"transaction_id": list(fraud), "is_fraud": list(fraud.values())})
    with pytest.raises(fs.LabelAccessError):
        sc.assemble(tx, split, labels)


def test_ac_05_no_screen_code_reads_labels_except_through_the_guard():
    src = Path(sc.__file__).read_text()
    assert "transaction_labels" not in src.replace("transaction_labels.parquet", "")  # only the file name in main()
    for banned in ("read_parquet", "scan_parquet", ".parquet'", "is_fraud FROM", "read_table", "pyarrow"):
        assert banned not in src, banned
    assert not re.search(r"FROM\s+['\"]?\{", src)  # f-string FROM '{path}'
    assert "fs.read_labels(" in src


def test_ac_05_outputs_stay_outside_the_repo(tmp_path, monkeypatch):
    assert sc.out_dir(str(tmp_path / "o")).exists()
    with pytest.raises(ValueError):
        sc.out_dir(str(sc.REPO / "eval" / "results"))
    df, h, _, _ = prepared(tmp_path)
    refused = sc.REPO / "eval" / "results" / "spec17-refused"
    with pytest.raises(ValueError):
        sc.run_screen(df, h, refused, arms={"gnb": sc.make_arms()["gnb"]})
    assert not refused.exists()
    written = []  # every path run_screen writes: the model files and the JSON record
    real_dump, real_write = sc.joblib.dump, Path.write_text
    monkeypatch.setattr(sc.joblib, "dump", lambda obj, p: (written.append(Path(p)), real_dump(obj, p))[1])
    monkeypatch.setattr(Path, "write_text", lambda p, *a, **k: (written.append(p), real_write(p, *a, **k))[1])
    sc.run_screen(df, h, tmp_path / "out", arms={"gnb": sc.make_arms()["gnb"]})
    assert len(written) == 3  # gnb, stacked, JSON
    assert all(sc.REPO not in p.resolve().parents for p in written)


@pytest.mark.skipif(not GOLD or not GOLD_EVAL.exists(), reason="opt-in: set GOLD_PATH (real gold run)")
def test_ac_03_real_gold_run_opt_in(tmp_path):
    df, h = sc.load_data(GOLD, GOLD_EVAL / "transaction_labels.parquet")
    rec = sc.run_screen(df, h, sc.out_dir(str(tmp_path / "real")))
    assert rec["split_hash"] == h


def test_ac_03_downsampling_runs_on_the_train_window_only(tmp_path, monkeypatch):
    df, h, _, _ = prepared(tmp_path)
    seen = []
    real = sc.downsample
    monkeypatch.setattr(sc, "downsample", lambda y, *a: (seen.append(len(y)), real(y, *a))[1])
    sc.run_screen(df, h, tmp_path / "out", arms={"logreg": sc.make_arms()["logreg"]})
    assert seen and set(seen) == {df.filter(pl.col("split_window") == fs.TRAIN).height}


def test_ac_03_saved_model_carries_encoder_and_reproduces_scores(tmp_path, monkeypatch):
    df, h, _, _ = prepared(tmp_path)
    out = tmp_path / "out"
    scored = {}  # the validation scores each arm produced during the screen
    real = sc.fit_calibrator
    monkeypatch.setattr(sc, "fit_calibrator", lambda arm, s, y: (scored.__setitem__(arm, s.copy()), real(arm, s, y))[1])
    sc.run_screen(df, h, out, arms={"tree": sc.make_arms()["tree"]})
    va = df.filter(pl.col("split_window") == fs.VALIDATION)
    for arm, features in (("tree", ff.FEATURES), ("stacked", ff.FEATURES + [sc.BANK])):
        saved = joblib.load(out / "models" / f"fraud-screen-{arm}.joblib")
        meta = saved["meta"]
        assert meta["features"] == features and meta["bank_fill"] == -1.0 and meta["categorical_codes"]
        X, _ = sc.encode(va, meta["categorical_codes"], meta["features"])  # the file alone, no code-side lists
        np.testing.assert_array_equal(sc.raw_score(arm, saved["model"], X), scored[arm])
    assert meta["stacked_on"] == "tree" and meta["bank_column"]["null_fill"] == -1.0  # raw 0-100 score, not /100


def test_ac_03_machine_record_and_stacked_fallback(tmp_path):
    df, h, _, _ = prepared(tmp_path)
    dummy = lambda: DummyClassifier(strategy="prior")  # noqa: E731 — base-rate PR-AUC, below 2x the base rate
    rec = sc.run_screen(df, h, tmp_path / "out", arms={"logreg": dummy, "hgb": dummy})
    assert {"platform", "cpu_count", "ram_bytes", "python", "scikit_learn"} <= set(rec["machine"])
    assert next(r for r in rec["results"] if r["arm"] == "stacked")["stacked_on"] == "hgb"  # max() alone picks logreg
    rec = sc.run_screen(df, h, tmp_path / "out", arms={"tree": sc.make_arms()["tree"], "hgb": dummy})
    assert next(r for r in rec["results"] if r["arm"] == "stacked")["stacked_on"] == "tree"  # clears 2x: kept
