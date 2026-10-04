"""Spec 17 T1/T2: time split + hash (AC-01), no-leakage features (AC-02), label windows (AC-05). Offline, synthetic."""
import os
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl
import pytest

from scripts.ml import fraud_features as ff
from scripts.ml import fraud_split as fs

REAL_SPLIT_HASH = "877a3a2386375dd35fe535e29f1f04d2326fa79bcc5c65349b151cda445df15a"  # gold v1, spec 17 §4.1
T0 = datetime(2025, 9, 1, 12, 0, 0)
GOLD = Path(os.environ.get("GOLD_PATH", Path(__file__).resolve().parents[1] / "data" / "gold"))
GOLD_EVAL = Path(__file__).resolve().parents[1] / "data" / "gold_eval"


def row(tid, when, cust="C1", amount=100.0, merchant="M1", lat=-34.6, lon=-58.4, **kw):
    base = dict(transaction_id=tid, transaction_date=when, customer_id=cust, product_id="P-" + cust, amount=amount,
                amount_usd=amount, currency="USD", channel="POS", transaction_type="Purchase",
                transaction_category=None, merchant_name=merchant, merchant_category="Retail",
                transaction_country="Argentina", latitude=lat, longitude=lon, product_type="Tarjeta Débito",
                customer_country="Argentina", customer_segment="Plus",  # segment: snapshot, not a feature
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
                  fraud_score=99.0, transaction_status="Pending", is_fraud=True, qc_x=1) for r in base]
    assert feats(noisy) == ref


def test_ac_02_static_features():
    f = feats([row("t1", datetime(2025, 9, 6, 23, 0), amount=99.0, transaction_country="Chile")])[0]
    assert f["abroad"] is True and f["hour"] == 23 and f["weekday"] == 6  # Saturday (ISO 6)
    assert f["log_amount_usd"] == pytest.approx(4.60517, abs=1e-4)


def test_ac_02_segment_and_input_columns_are_not_leaky():
    # snapshot at the cut (contracts/gold_contract.md, docs/eda/data_quality.md §A1) [D-010]
    assert "customer_segment" not in ff.FEATURES
    assert not [c for c in ff.INPUT_COLUMNS if ff.is_forbidden(c)]
    f1 = feats([row("t1", T0, customer_segment="Plus")])
    assert f1 == feats([row("t1", T0, customer_segment="Premium")])


def test_ac_02_history_is_all_statuses_and_emits_only_approved_pending():
    base = [row("d1", T0, amount=10, transaction_status="Declined"),
            row("t2", T0 + timedelta(minutes=10), amount=20, transaction_status="Approved"),
            row("t3", T0 + timedelta(minutes=20), amount=30, transaction_status="Reversed")]
    f = {r["transaction_id"]: r for r in feats(base)}
    assert set(f) == {"t2"} and (f["t2"]["n_1h"], f["t2"]["amt_1h"]) == (1, 10)  # Declined is history, not emitted
    later = base + [row("t4", T0 + timedelta(hours=1), amount=5)]
    flipped = [dict(r, transaction_status="Reversed") if r["transaction_id"] == "t2" else r for r in later]
    a = {r["transaction_id"]: r for r in feats(later)}["t4"]
    b = {r["transaction_id"]: r for r in feats(flipped)}["t4"]
    assert a == b  # a status change on an earlier row does not change which rows are history


def test_ac_02_usd_fallback_entity_fallback_and_window_boundaries():
    f = feats([row("u1", T0, amount=50.0, amount_usd=None, currency="USD"),
               row("u2", T0, amount=50.0, amount_usd=None, currency="ARS")])
    assert f[0]["amount_usd_f"] == 50.0 and f[1]["amount_usd_f"] is None
    # no customer_id: the product is the entity (P-X shared by two rows), another product is separate
    f = {r["transaction_id"]: r for r in feats([
        row("e1", T0, cust="X", customer_id=None, product_id="P-X"),
        row("e2", T0 + timedelta(minutes=5), cust="X", customer_id=None, product_id="P-X"),
        row("e3", T0 + timedelta(minutes=6), cust="Y", customer_id=None, product_id="P-Y")])}
    assert f["e2"]["n_1h"] == 1 and f["e3"]["n_1h"] == 0
    # lower bounds are inclusive: an earlier row exactly 1 h / 24 h / 7 d back counts, one second more does not
    for w, name in ((3600, "1h"), (86400, "24h"), (7 * 86400, "7d")):
        t = T0 + timedelta(days=30)
        f = {r["transaction_id"]: r for r in feats([
            row("in", t - timedelta(seconds=w)), row("out", t - timedelta(seconds=w + 1), amount=1), row("now", t)])}
        assert f["now"][f"n_{name}"] == 1 and f["now"][f"amt_{name}"] == 100.0


def test_ac_02_distance_uses_previous_transaction_with_a_known_location():
    f = {r["transaction_id"]: r for r in feats([
        row("a", T0, lat=-34.6, lon=-58.4), row("b", T0 + timedelta(hours=1), lat=None, lon=None),
        row("c0", T0 + timedelta(hours=2), lat=10.0, lon=10.0),  # located, same time as c, earlier in input
        row("c", T0 + timedelta(hours=2), lat=-34.6, lon=-58.4)])}
    # km from a, time from b: a same-timestamp row (c0) is never history, even when located and listed first
    assert f["c"]["km_from_prev"] == 0 and f["c"]["secs_since_prev"] == 3600
    assert f["b"]["km_from_prev"] is None


# ---------- AC-01: boundaries are not duplicated by accident ----------
def test_ac_01_sql_boundaries_equal_windows_and_windows_change_the_hash(monkeypatch):
    import re
    f02 = (fs.QUERIES / "f02_time_split.sql").read_text()
    dates = re.findall(r"transaction_date (>=|<) TIMESTAMP '(\d{4}-\d{2}-\d{2})'", f02)
    expected = [(op, d) for a, b in fs.WINDOWS.values() for op, d in ((">=", a), ("<", b))]
    assert dates[:6] == expected  # the CASE branches, in window order
    f01 = (fs.QUERIES / "f01_monthly_counts.sql").read_text()
    assert set(re.findall(r"DATE '(\d{4}-\d{2}-\d{2})'", f01)) == {fs.WINDOWS[fs.TEST][0]}
    s = fs.build_split(con_with(split_fixture()))
    h = fs.split_hash(s)
    monkeypatch.setitem(fs.WINDOWS, fs.TEST, ("2026-04-02", "2026-06-01"))
    assert fs.split_hash(s) != h


def test_ac_05_labels_view_cannot_see_test_window_labels(tmp_path):
    s, p = label_fixture(tmp_path)
    con = con_with(split_fixture())
    fs.register_labels(con, fs.read_labels(p, s, fs.LABEL_WINDOWS))
    seen = {r[0] for r in con.execute("select transaction_id from transaction_labels").fetchall()}
    test_ids = set(s.filter(pl.col("split_window") == "test")["transaction_id"])
    assert seen and not seen & test_ids


@pytest.mark.skipif(not (GOLD / "transactions_enriched.parquet").exists(), reason="opt-in: real gold absent (GOLD_PATH)")
def test_ac_01_real_gold_split_hash_and_counts():
    con = fs.connect(GOLD)
    s = fs.build_split(con)
    n = con.execute("select count(*) from transactions_enriched where transaction_status in ('Approved','Pending')").fetchone()[0]
    assert s.height == n  # every gold transaction is inside the three windows
    assert dict(s.group_by("split_window").len().iter_rows()) == {"train": 925246, "validation": 224784, "test": 238990}
    assert fs.split_hash(s) == REAL_SPLIT_HASH


def test_ac_05_main_reads_only_train_validation_labels_and_f01_filters_them(tmp_path, monkeypatch):
    import re
    import sys
    s, _ = label_fixture(tmp_path)  # the label file also holds labels for the test-window ids
    gold = tmp_path / "gold"
    gold.mkdir()
    split_fixture().with_columns(pl.lit("Tarjeta Débito").alias("product_type")).write_parquet(
        gold / "transactions_enriched.parquet")
    seen: list[set] = []
    real = fs.monthly_counts

    def spy(con):
        seen.append({r[0] for r in con.execute("select transaction_id from transaction_labels").fetchall()})
        return real(con)

    monkeypatch.setattr(fs, "monthly_counts", spy)
    monkeypatch.setattr(sys, "argv", ["fraud_split", "--gold", str(gold), "--eval", str(tmp_path),
                                      "--out", str(tmp_path / "out")])
    fs.main()
    assert seen == [set(s.filter(pl.col("split_window").is_in(["train", "validation"]))["transaction_id"])]
    # second guard: f01 joins labels only for months before the test window
    f01 = (fs.QUERIES / "f01_monthly_counts.sql").read_text()
    lab = re.search(r"lab AS \((.*?)\)\nSELECT", f01, re.S).group(1)
    assert re.search(rf"WHERE t\.month < DATE '{fs.WINDOWS[fs.TEST][0]}'", lab)
