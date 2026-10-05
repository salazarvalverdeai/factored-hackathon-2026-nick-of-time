"""Spec 17 task FEAT (D-015): search for transaction-time fraud signal beyond §4.2, on train + validation only.

Every candidate uses fields known at transaction time and only strictly earlier rows: DuckDB RANGE frames over the
timestamp in microseconds end 1 µs before the row, so a same-timestamp or later row is never history (AC-02). History
is every status (D-009); candidates are emitted for Approved/Pending rows only. Labels come only through
`fraud_split.read_labels` for train and validation (AC-05, ADR 0022); no test-window transaction is read. Output is
aggregates only, outside the repo:
    python -m scripts.ml.fraud_signal_search --gold $GOLD --eval $GOLD_EVAL [--out DIR]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

from scripts.ml import fraud_screen as sc
from scripts.ml import fraud_split as fs

H, D = 3_600_000_000, 86_400_000_000  # one hour and one day in microseconds
SMOOTH = 100.0  # pseudo-count of the train-only category rates [assumption]
N_BOOT, N_PERM, SEED = 2000, 500, 17
LATE_TRAIN = "2025-09-01"  # late-train replication check: past the cold start of §4.2 (2025-06 to 2025-08)
REFERENCE = "reference (not a candidate)"
MIN_DEV = 0.02  # materiality [assumption]: a rare flag no fraud carries has AUC 0.4999 with a zero-width CI


def _w(agg: str, part: str, span: int | None = None) -> str:
    """`agg` over the strictly earlier rows of the partition (within `span` µs when given)."""
    lo = "UNBOUNDED" if span is None else str(span)
    return f"{agg} OVER (PARTITION BY {part} ORDER BY us RANGE BETWEEN {lo} PRECEDING AND 1 PRECEDING)"


def _km(a1: str, o1: str, a2: str, o2: str) -> str:
    return (f"12742 * asin(sqrt(pow(sin(radians({a2} - {a1}) / 2), 2) + cos(radians({a1})) * cos(radians({a2})) "
            f"* pow(sin(radians({o2} - {o1}) / 2), 2)))")


_LOC = "max(CASE WHEN lat IS NOT NULL AND lon IS NOT NULL THEN {'us': us, 'lat': lat, 'lon': lon} END)"
WINDOWS = {  # stage 1; e = customer, else product (as in fraud_features)
    "w_n": _w("count(*)", "e"), "w_n30": _w("count(*)", "e", 30 * D),
    "w_card_1h": _w("count(*)", "product_id", H), "w_card_24h": _w("count(*)", "product_id", D),
    "w_card_7d": _w("count(*)", "product_id", 7 * D), "w_card_last": _w("max(us)", "product_id"),
    "w_decl_24h": _w("sum((st = 'Declined')::INT)", "e", D), "w_decl_7d": _w("sum((st = 'Declined')::INT)", "e", 7 * D),
    "w_n_tc": _w("count(*)", "e, tc"), "w_n_city": _w("count(*)", "e, city"), "w_n_ch": _w("count(*)", "e, channel"),
    "w_n_mcat": _w("count(*)", "e, mcat"), "w_last_m": _w("max(us)", "e, mname"),
    "w_loc": _w(_LOC, "e"), "w_hlat": _w("avg(CASE WHEN lon IS NOT NULL THEN lat END)", "e"),
    "w_hlon": _w("avg(CASE WHEN lat IS NOT NULL THEN lon END)", "e"),
    "w_mean": _w("avg(amt)", "e"), "w_std": _w("stddev_samp(amt)", "e"), "w_max": _w("max(amt)", "e"),
    "w_sin": _w("avg(sin(2 * pi() * hr / 24))", "e"), "w_cos": _w("avg(cos(2 * pi() * hr / 24))", "e"),
    "w_same_h": _w("count(*)", "e, hr"), "w_same_dow": _w("count(*)", "e, dow"),
    "w_m_1h": _w("count(*)", "mname", H), "w_city_1h": _w("count(*)", "city", H),
}
_KM_PREV = _km("struct_extract(w_loc, 'lat')", "struct_extract(w_loc, 'lon')", "lat", "lon")
_MEAN_H = "((degrees(atan2(w_sin, w_cos)) / 15 + 24) % 24)"
CANDIDATES = {  # stage 2: name -> (family, expression over base + WINDOWS columns)
    "cust_n_30d": ("velocity (customer)", "w_n30"),
    "card_n_1h": ("velocity (card)", "w_card_1h"), "card_n_24h": ("velocity (card)", "w_card_24h"),
    "card_n_7d": ("velocity (card)", "w_card_7d"),
    "card_secs_since_prev": ("velocity (card)", "(us - w_card_last) / 1e6"),
    "card_first_use": ("velocity (card)", "(w_card_last IS NULL)::INT"),
    "declines_24h": ("declines before", "coalesce(w_decl_24h, 0)"),  # an empty frame sums to NULL
    "declines_7d": ("declines before", "coalesce(w_decl_7d, 0)"),
    "first_country": ("novelty", "(w_n_tc = 0)::INT"),
    "first_city": ("novelty", "CASE WHEN city IS NOT NULL THEN (w_n_city = 0)::INT END"),
    "first_channel": ("novelty", "(w_n_ch = 0)::INT"),
    "first_merchant_category": ("novelty", "CASE WHEN mcat IS NOT NULL THEN (w_n_mcat = 0)::INT END"),
    "secs_since_merchant": ("novelty", "CASE WHEN mname IS NOT NULL THEN (us - w_last_m) / 1e6 END"),
    "km_prev_located": ("geo", _KM_PREV),
    "speed_kmh": ("geo", f"{_KM_PREV} / greatest((us - struct_extract(w_loc, 'us')) / {H}, 1 / 60)"),
    "km_from_home": ("geo", _km("w_hlat", "w_hlon", "lat", "lon")),
    "amount_z": ("amount vs history", "(amt - w_mean) / nullif(w_std, 0)"),
    "amount_over_max": ("amount vs history", "amt / nullif(w_max, 0)"),
    "hour_dev": ("time habit", f"CASE WHEN w_n > 0 THEN least(abs(hr - {_MEAN_H}), 24 - abs(hr - {_MEAN_H})) END"),
    "same_hour_share": ("time habit", "w_same_h / nullif(w_n, 0)"),
    "same_weekday_share": ("time habit", "w_same_dow / nullif(w_n, 0)"),
    "product_age_days": ("product / customer", "date_diff('day', product_opening_date, td::DATE)"),
    "customer_tenure_days": ("product / customer", "date_diff('day', registration_date::DATE, td::DATE)"),
    "customer_age_years": ("product / customer", "date_sub('year', date_of_birth, td::DATE)"),  # complete years
    "merchant_n_1h": ("merchant / city load", "CASE WHEN mname IS NOT NULL THEN w_m_1h END"),
    "city_n_1h": ("merchant / city load", "CASE WHEN city IS NOT NULL THEN w_city_1h END"),
}
RATES = {"merchant_name_rate": ["mname"], "city_rate": ["city"], "branch_rate": ["branch_id"],
         "merchant_category_x_country_rate": ["mcat", "tc"]}  # train-only smoothed fraud rate per level
COMPLAINTS = "complaints_90d"  # created in the 90 days before and in an earlier daily file (process_date < tx date)


def build_candidates(con, cutoff: str = fs.WINDOWS[fs.VALIDATION][1]) -> pl.DataFrame:
    """One row per Approved/Pending transaction before `cutoff`: id, CANDIDATES, complaints, rate keys, bank score.

    Needs views `transactions_enriched`, `customers` and `complaints` on `con`; never reads labels."""
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _base AS SELECT t.transaction_id, epoch_us(t.transaction_date) AS us,
      t.transaction_date AS td, coalesce(t.customer_id, t.product_id) AS e, t.product_id, t.customer_id,
      coalesce(t.amount_usd, CASE WHEN t.currency = 'USD' THEN t.amount END) AS amt, t.channel,
      t.merchant_name AS mname, t.merchant_category AS mcat, t.transaction_country AS tc, t.transaction_city AS city,
      t.branch_id, t.latitude AS lat, t.longitude AS lon, t.transaction_status AS st, t.response_code AS rc,
      t.fraud_score, t.product_opening_date, hour(t.transaction_date) AS hr, isodow(t.transaction_date) AS dow,
      c.registration_date, c.date_of_birth
      FROM transactions_enriched t LEFT JOIN customers c ON c.customer_id = t.customer_id
      WHERE t.transaction_date < TIMESTAMP '{cutoff}'""")
    stage1 = ", ".join(f"{v} AS {k}" for k, v in WINDOWS.items())
    stage2 = ", ".join(f"{v} AS {k}" for k, (_, v) in CANDIDATES.items())
    return con.execute(f"""WITH s1 AS (SELECT *, {stage1} FROM _base),
      s2 AS (SELECT transaction_id, customer_id, td, mname, city, branch_id, mcat, tc, fraud_score, {stage2}
             FROM s1 WHERE st IN ('Approved', 'Pending')),
      cmp AS (SELECT s2.transaction_id, count(*) AS n FROM s2 JOIN complaints c ON c.customer_id = s2.customer_id
              AND c.creation_date < s2.td AND c.creation_date >= s2.td - INTERVAL 90 DAY
              AND c.process_date < s2.td::DATE GROUP BY 1)
      SELECT s2.* EXCLUDE (customer_id), coalesce(cmp.n, 0) AS {COMPLAINTS}
      FROM s2 LEFT JOIN cmp USING (transaction_id)""").pl()


def auc_ci(y: np.ndarray, x: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float, float]:
    """ROC-AUC (ties count 1/2, null as the lowest value) and a stratified bootstrap 95% CI. Frauds and legitimate rows
    are resampled separately, as multinomial counts over the bins that the fraud values cut the sorted legitimate
    values into, which is exact and cheap at 225k rows."""
    x = np.where(np.isnan(x), -np.inf, x)
    pos, neg = x[y == 1], np.sort(x[y == 0])
    m, n = len(pos), len(neg)
    u, pc = np.unique(pos, return_counts=True)
    k = len(u)
    edges = np.empty(2 * k + 2, dtype=np.int64)
    edges[0], edges[-1] = 0, n
    edges[1:-1:2], edges[2:-1:2] = np.searchsorted(neg, u, "left"), np.searchsorted(neg, u, "right")
    counts = np.diff(edges)  # bins: below u0, equal u0, between u0 and u1, equal u1, ..., above u(k-1)

    def auc(pos_counts, bins):
        return (pos_counts * (np.cumsum(bins, axis=-1)[..., 0::2][..., :k] + 0.5 * bins[..., 1::2])).sum(-1) / (m * n)

    rng = np.random.default_rng(seed)
    boot = auc(rng.multinomial(m, pc / m, size=n_boot), rng.multinomial(n, counts / n, size=n_boot))
    return float(auc(pc, counts)), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def is_signal(va: tuple, tr: tuple) -> bool:
    """Both 95% CIs exclude 0.5 on the same side and the validation AUC is at least MIN_DEV from 0.5 [assumption]."""
    (ava, lva, hva), (_, ltr, htr) = va, tr
    return bool(abs(ava - 0.5) >= MIN_DEV and ((lva > 0.5 and ltr > 0.5) or (hva < 0.5 and htr < 0.5)))


def train_rates(key_tr: list, y_tr: np.ndarray, key_va: list, folds: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Smoothed fraud rate per level from train labels only: validation gets the train map, train gets out-of-fold."""
    prior = float(y_tr.mean())

    def fit(keys, y):
        g = pl.DataFrame({"k": keys, "y": y}).group_by("k").agg(pl.col("y").sum().alias("s"), pl.len().alias("n"))
        return dict(zip(g["k"].to_list(), ((g["s"] + SMOOTH * prior) / (g["n"] + SMOOTH)).to_list()))

    def apply(mp, keys):
        return np.array([mp.get(v, prior) for v in keys], dtype=float)

    fold, ktr = np.random.default_rng(SEED).integers(0, folds, len(key_tr)), np.array(key_tr, object)
    out = np.empty(len(key_tr))
    for i in range(folds):
        out[fold == i] = apply(fit(ktr[fold != i].tolist(), y_tr[fold != i]), ktr[fold == i].tolist())
    return out, apply(fit(key_tr, y_tr), key_va)


def search(df: pl.DataFrame) -> dict:
    """Single-candidate AUC with CI on train, late train (from LATE_TRAIN, past the cold start) and validation;
    `is_signal` per candidate; and the 95th percentile of the largest |AUC - 0.5| over every candidate (not the
    reference) under permuted validation labels, a family-wise yardstick."""
    df = df.sort("transaction_id")  # the out-of-fold folds and the permutations depend on row order
    tr, va = df.filter(pl.col("split_window") == fs.TRAIN), df.filter(pl.col("split_window") == fs.VALIDATION)
    ytr, yva = tr["is_fraud"].cast(pl.Int8).to_numpy(), va["is_fraud"].cast(pl.Int8).to_numpy()
    late = (tr["td"] >= datetime.fromisoformat(LATE_TRAIN)).to_numpy()
    num = lambda d, c: d[c].cast(pl.Float64).fill_nan(None).to_numpy().astype(float)  # noqa: E731
    pairs = [(f, c, num(tr, c), num(va, c)) for c, (f, _) in CANDIDATES.items()]
    pairs.append(("complaints before", COMPLAINTS, num(tr, COMPLAINTS), num(va, COMPLAINTS)))
    for name, cols in RATES.items():
        key = pl.concat_str([pl.col(c).cast(pl.Utf8).fill_null("<null>") for c in cols], separator="|")
        pairs.append(("category rate (train only)", name, *train_rates(tr.select(key).to_series().to_list(), ytr,
                                                                      va.select(key).to_series().to_list())))
    pairs.append((REFERENCE, "bank_fraud_score", num(tr, sc.BANK), num(va, sc.BANK)))
    rows = []
    for fam, name, xtr, xva in pairs:
        a_tr, a_late, a_va = auc_ci(ytr, xtr), auc_ci(ytr[late], xtr[late]), auc_ci(yva, xva)
        rows.append({"family": fam, "candidate": name, "coverage_validation": float(np.mean(~np.isnan(xva))),
                     "auc_train": a_tr[0], "ci_train": list(a_tr[1:]), "auc_train_late": a_late[0],
                     "ci_train_late": list(a_late[1:]), "auc_validation": a_va[0], "ci_validation": list(a_va[1:]),
                     "signal": is_signal(a_va, a_tr)})
    ranks = np.vstack([pl.Series(np.where(np.isnan(x), -np.inf, x)).rank("average").to_numpy()
                       for fam, _, _, x in pairs if fam != REFERENCE])
    m, n, rng = int(yva.sum()), len(yva) - int(yva.sum()), np.random.default_rng(SEED)
    perm = [np.abs((ranks[:, rng.choice(len(yva), m, replace=False)].sum(1) - m * (m + 1) / 2) / (m * n) - 0.5).max()
            for _ in range(N_PERM)]
    return {"n": {fs.TRAIN: tr.height, fs.VALIDATION: va.height, "train_late": int(late.sum())},
            "n_fraud": {fs.TRAIN: int(ytr.sum()), fs.VALIDATION: int(yva.sum()), "train_late": int(ytr[late].sum())},
            "familywise_max_abs_dev_95": float(np.percentile(perm, 95)), "n_candidates": int(len(ranks)), "rows": rows}


def load(gold: str | Path, labels_path: str | Path) -> tuple[pl.DataFrame, str]:
    con = fs.connect(gold)
    for t in ("customers", "complaints"):
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{Path(gold) / (t + '.parquet')}')")
    split = fs.build_split(con)
    labels = fs.read_labels(labels_path, split, {fs.TRAIN, fs.VALIDATION})
    df = build_candidates(con).join(labels.select("transaction_id", "split_window", "is_fraud"), on="transaction_id")
    if not set(df["split_window"].unique()) <= fs.LABEL_WINDOWS:
        raise fs.LabelAccessError("a test-window row reached the signal search")
    return df, fs.split_hash(split)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--out", default=None, help="directory outside the repo (or $FRAUD_SCREEN_OUT)")
    a = ap.parse_args()
    out = sc.out_dir(a.out)
    df, h = load(a.gold, Path(a.eval) / "transaction_labels.parquet")
    rec = {"split_hash": h, "label_windows": sorted(fs.LABEL_WINDOWS), **search(df)}
    (out / "fraud_signal_search.json").write_text(json.dumps(rec, indent=2, allow_nan=False))
    for r in rec["rows"]:
        print(f"{r['family']:28s} {r['candidate']:34s} cov={r['coverage_validation']:.2f} "
              f"train={r['auc_train']:.3f} [{r['ci_train'][0]:.3f}, {r['ci_train'][1]:.3f}] "
              f"late={r['auc_train_late']:.3f} [{r['ci_train_late'][0]:.3f}, {r['ci_train_late'][1]:.3f}] "
              f"val={r['auc_validation']:.3f} [{r['ci_validation'][0]:.3f}, {r['ci_validation'][1]:.3f}]"
              f"{'  SIGNAL' if r['signal'] else ''}")
    print(f"family-wise 95% max |AUC-0.5| over {rec['n_candidates']} candidates under permuted validation labels: "
          f"{rec['familywise_max_abs_dev_95']:.3f}")


if __name__ == "__main__":
    main()
