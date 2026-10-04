"""Spec 17 T1/T2: time split + hash (AC-01), no-leakage features (AC-02), label windows (AC-05). Offline, synthetic."""
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl
import pytest

from scripts.ml import fraud_features as ff
from scripts.ml import fraud_split as fs

T0 = datetime(2025, 9, 1, 12, 0, 0)
GOLD = Path(__file__).resolve().parents[1] / "data" / "gold"
GOLD_EVAL = Path(__file__).resolve().parents[1] / "data" / "gold_eval"


def row(tid, when, cust="C1", amount=100.0, merchant="M1", lat=-34.6, lon=-58.4, **kw):
    base = dict(transaction_id=tid, transaction_date=when, customer_id=cust, product_id="P-" + cust, amount=amount,
                amount_usd=amount, currency="USD", channel="POS", transaction_type="Purchase",
                transaction_category=None, merchant_name=merchant, merchant_category="Retail",
                transaction_country="Argentina", latitude=lat, longitude=lon, product_type="Tarjeta Débito",
                customer_country="Argentina", customer_segment="Plus",
                # fields that must never matter:
                product_status="Active", process_date=when.date(), qc_late_arrival=False, fraud_score=10.0,
                transaction_status="Approved")
    base.update(kw)
    return base


def frame(rows):
    return pl.DataFrame(rows, infer_schema_length=None)


def feats(rows):
    return ff.build_features(frame(rows)).to_dicts()


# ---------- AC-01: split ----------
def split_fixture():
    d = [("a", datetime(2025, 5, 31, 23, 59, 59)), ("b", datetime(2025, 6, 1)), ("c", datetime(2026, 1, 31, 23, 0)),
         ("d", datetime(2026, 2, 1)), ("e", datetime(2026, 3, 31, 23, 0)), ("f", datetime(2026, 4, 1)),
         ("g", datetime(2026, 5, 15)), ("h", datetime(2026, 6, 1))]
    rows = [{"transaction_id": i, "transaction_date": t, "transaction_status": "Approved"} for i, t in d]
    rows.append({"transaction_id": "x", "transaction_date": datetime(2025, 8, 1), "transaction_status": "Declined"})
    return pl.DataFrame(rows)


def con_with(tx):
    con = duckdb.connect()
    con.register("transactions_enriched", tx.to_arrow())
    return con


def test_ac_01_windows_by_time_and_agent_cases_not_in_train():
    s = dict(fs.build_split(con_with(split_fixture())).iter_rows())
    assert s == {"b": "train", "c": "train", "d": "validation", "e": "validation", "f": "test", "g": "test"}
    assert fs.WINDOWS[fs.TRAIN][1] <= "2026-05-01"  # agent cases (specs 09, 10) are from May 2026


def test_ac_01_split_hash_is_deterministic_and_detects_changes():
    s = fs.build_split(con_with(split_fixture()))
    assert fs.split_hash(s) == fs.split_hash(s.reverse())
    moved = s.with_columns(pl.when(pl.col("transaction_id") == "c").then(pl.lit("test"))
                           .otherwise(pl.col("split_window")).alias("split_window"))
    assert fs.split_hash(moved) != fs.split_hash(s)
    assert len(fs.split_hash(s)) == 64


# ---------- AC-05: labels only for train/validation ----------
def label_fixture(tmp_path):
    s = fs.build_split(con_with(split_fixture()))
    p = tmp_path / "transaction_labels.parquet"
    pl.DataFrame({"transaction_id": s["transaction_id"], "is_fraud": [True] * s.height}).write_parquet(p)
    return s, p


def test_ac_05_label_reader_never_returns_or_accepts_test_window(tmp_path):
    s, p = label_fixture(tmp_path)
    out = fs.read_labels(p, s, fs.LABEL_WINDOWS)
    assert set(out["split_window"]) == {"train", "validation"} and out.height == 4
    for bad in ({"test"}, {"train", "test"}, set(), {"other"}):
        with pytest.raises(fs.LabelAccessError):
            fs.read_labels(p, s, bad)


def test_ac_05_monthly_counts_do_not_read_test_labels(tmp_path):
    s, p = label_fixture(tmp_path)
    con = con_with(split_fixture().with_columns(pl.lit("Tarjeta Débito").alias("product_type")))
    con.execute(f"CREATE VIEW transaction_labels AS SELECT * FROM read_parquet('{p}')")
    m = {r["month"].isoformat()[:7]: r for r in fs.monthly_counts(con).to_dicts()}
    assert m["2026-04"]["n_transactions"] == 1 and m["2026-04"]["n_fraud"] is None
    assert m["2026-05"]["n_fraud"] is None and m["2026-01"]["n_fraud"] == 1


# ---------- AC-02: features ----------
def test_ac_02_feature_names_exclude_forbidden_fields():
    assert not [c for c in ff.FEATURES if ff.is_forbidden(c)]
    for c in ("product_status", "process_date", "is_fraud", "qc_future_date"):
        assert ff.is_forbidden(c)
    out = ff.build_features(frame([row("t1", T0)]))
    assert out.columns == ["transaction_id", *ff.FEATURES]


def test_ac_02_history_uses_only_strictly_earlier_transactions():
    rows = [row("t1", T0, amount=10), row("t2", T0 + timedelta(minutes=30), amount=20),
            row("t3", T0 + timedelta(hours=2), amount=40), row("t4", T0 + timedelta(hours=2), amount=999),  # same time
            row("o1", T0 + timedelta(minutes=45), cust="C2", amount=5000)]  # other customer
    f = {r["transaction_id"]: r for r in feats(rows)}
    assert (f["t1"]["n_1h"], f["t1"]["n_7d"], f["t1"]["first_at_merchant"]) == (0, 0, True)
    assert f["t1"]["amount_vs_median"] is None and f["t1"]["secs_since_prev"] is None
    assert (f["t2"]["n_1h"], f["t2"]["amt_1h"], f["t2"]["first_at_merchant"]) == (1, 10, False)
    assert f["t2"]["secs_since_prev"] == 1800 and f["t2"]["km_from_prev"] == 0
    # t3 and t4 share a timestamp: neither sees the other; each sees t1 and t2 in 24h, only t2 in 1h? (90 min > 1 h)
    for t in ("t3", "t4"):
        assert (f[t]["n_1h"], f[t]["n_24h"], f[t]["amt_24h"]) == (0, 2, 30)
        assert f[t]["secs_since_prev"] == 5400
    assert f["t3"]["amount_vs_median"] == pytest.approx(40 / 15) and f["t4"]["amount_vs_median"] == pytest.approx(999 / 15)
    assert f["o1"]["n_24h"] == 0 and f["o1"]["first_at_merchant"] is True


def test_ac_02_changing_same_time_or_later_transactions_does_not_change_a_feature():
    base = [row("t1", T0, amount=10), row("t2", T0 + timedelta(hours=1), amount=20),
            row("t3", T0 + timedelta(hours=1), amount=30, merchant="M2", lat=-33.0),
            row("t4", T0 + timedelta(hours=5), amount=50)]
    ref = {r["transaction_id"]: r for r in feats(base)}["t2"]
    changed = [dict(r) for r in base]
    changed[2].update(amount=1e6, amount_usd=1e6, merchant_name="M1", latitude=10.0)  # same-time neighbour
    changed[3].update(amount=1e6, amount_usd=1e6, latitude=10.0)  # later
    changed.append(row("t5", T0 + timedelta(days=30), amount=1e6))
    assert {r["transaction_id"]: r for r in feats(changed)}["t2"] == ref


def test_ac_02_forbidden_fields_and_labels_do_not_change_features():
    base = [row("t1", T0), row("t2", T0 + timedelta(hours=1))]
    ref = feats(base)
    noisy = [dict(r, product_status="Closed", process_date=datetime(2030, 1, 1).date(), qc_late_arrival=True,
                  fraud_score=99.0, transaction_status="Reversed", is_fraud=True, qc_x=1) for r in base]
    assert feats(noisy) == ref


def test_ac_02_static_features():
    f = feats([row("t1", datetime(2025, 9, 6, 23, 0), amount=99.0, transaction_country="Chile")])[0]
    assert f["abroad"] is True and f["hour"] == 23 and f["weekday"] == 6  # Saturday (ISO 6)
    assert f["log_amount_usd"] == pytest.approx(4.60517, abs=1e-4)


@pytest.mark.skipif(not (GOLD / "transactions_enriched.parquet").exists(), reason="opt-in: real gold absent")
def test_ac_01_real_gold_split_sums_to_approved_pending():
    con = fs.connect(GOLD)
    s = fs.build_split(con)
    n = con.execute("select count(*) from transactions_enriched where transaction_status in ('Approved','Pending')").fetchone()[0]
    assert s.height <= n and set(s["split_window"]) == {"train", "validation", "test"}
