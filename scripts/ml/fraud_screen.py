"""Spec 17 T3 (17b): scikit-learn screen of the arms of §4.3 on train + validation only (AC-03, AC-05; ADR 0022).

Labels come only through `fraud_split.read_labels` with the train/validation windows; no test-window row is built,
scored or labeled here. Models and outputs go OUTSIDE the repo (eval/PROTOCOL.md seal): `--out` or $FRAUD_SCREEN_OUT,
default a temp directory. Usage:
    python -m scripts.ml.fraud_screen --gold $GOLD --eval $GOLD_EVAL [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import tempfile
import time
from pathlib import Path

import joblib
import numpy as np
import polars as pl
import sklearn
from sklearn.ensemble import (ExtraTreesClassifier, HistGradientBoostingClassifier, IsolationForest,
                              RandomForestClassifier)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_curve
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from scripts.ml import fraud_features as ff
from scripts.ml import fraud_split as fs

REPO = Path(__file__).resolve().parents[2]
SEED = 17
LEGIT_PER_FRAUD = 100  # down-sampling of legitimate train rows [assumption]; calibration on validation fixes the prior
CATEGORICAL = ["currency", "channel", "transaction_type", "transaction_category", "merchant_category", "product_type"]
BANK = "fraud_score"
BANK_FILL = -1.0  # a missing bank score is the lowest value (spec 17 §4.3)
BANK_COLUMN = {"source": "transactions_enriched.fraud_score", "scale": "raw 0-100 (S-bank divides by 100)",
               "null_fill": BANK_FILL}
FAMILY = {"iforest": "no-labels", "logreg": "linear", "sgd": "linear", "gnb": "probabilistic", "tree": "tree",
          "rf": "ensemble", "extra_trees": "ensemble", "hgb": "ensemble", "mlp": "neural", "stacked": "stacked"}


def out_dir(arg: str | None = None) -> Path:
    """Output directory, refused when inside the repo (the protocol seal forbids results there)."""
    p = Path(arg or os.environ.get("FRAUD_SCREEN_OUT") or Path(tempfile.gettempdir()) / "nickoftime-fraud-screen")
    p = p.expanduser().resolve()
    if p == REPO or REPO in p.parents:
        raise ValueError(f"output directory {p} is inside the repo; models and results must stay outside")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _scaled(clf):
    return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(), clf)


def _imputed(clf):
    return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), clf)


def make_arms() -> dict:
    return {
        "iforest": lambda: _imputed(IsolationForest(n_estimators=100, random_state=SEED, n_jobs=-1)),
        "logreg": lambda: _scaled(LogisticRegression(max_iter=500, class_weight="balanced")),
        "sgd": lambda: _scaled(SGDClassifier(loss="log_loss", class_weight="balanced", random_state=SEED)),
        "gnb": lambda: _scaled(GaussianNB()),
        "tree": lambda: _imputed(DecisionTreeClassifier(max_depth=6, class_weight="balanced", random_state=SEED)),
        "rf": lambda: _imputed(RandomForestClassifier(n_estimators=100, min_samples_leaf=3, class_weight="balanced",
                                                      random_state=SEED, n_jobs=-1)),
        "extra_trees": lambda: _imputed(ExtraTreesClassifier(n_estimators=100, min_samples_leaf=3,
                                                             class_weight="balanced", random_state=SEED, n_jobs=-1)),
        "hgb": lambda: HistGradientBoostingClassifier(class_weight="balanced", random_state=SEED),
        "mlp": lambda: _scaled(MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=200, random_state=SEED)),
    }


def load_data(gold: str | Path, labels_path: str | Path) -> tuple[pl.DataFrame, str]:
    """Train + validation rows with features, label, window, month, bank score, country, segment, plus the split hash.

    Transactions on or after the test window start are never read; labels come only through `read_labels`."""
    con = fs.connect(gold)
    split = fs.build_split(con)
    labels = fs.read_labels(labels_path, split, {fs.TRAIN, fs.VALIDATION})
    cutoff = fs.WINDOWS[fs.VALIDATION][1]
    cols = ", ".join([*ff.INPUT_COLUMNS, ff.STATUS_COL, BANK, "customer_segment"])
    tx = con.execute(f"SELECT {cols} FROM transactions_enriched WHERE transaction_date < TIMESTAMP '{cutoff}'").pl()
    return assemble(tx, split, labels), fs.split_hash(split)


def assemble(tx: pl.DataFrame, split: pl.DataFrame, labels: pl.DataFrame) -> pl.DataFrame:
    feats = ff.build_features(tx)
    extra = tx.select("transaction_id", BANK, "customer_segment", "customer_country",
                      pl.col("transaction_date").dt.strftime("%Y-%m").alias("month"))
    df = (feats.join(split, on="transaction_id").join(labels.select("transaction_id", "is_fraud"), on="transaction_id")
          .join(extra, on="transaction_id"))
    if not set(df["split_window"].unique()) <= fs.LABEL_WINDOWS:
        raise fs.LabelAccessError("a test-window row reached the screen")
    return df


def encode(df: pl.DataFrame, cats: dict | None = None, features: list[str] | None = None):
    """Matrix of `features` (default ff.FEATURES; pass a model file's meta["features"] to rescore it) with NaN for null
    numerics; categorical codes learned on the first call (train), -1 for unseen AND for null categories; the bank
    column, when listed, is BANK_COLUMN (raw score, nulls as BANK_FILL)."""
    cats = cats or {c: {v: i for i, v in enumerate(sorted(df[c].drop_nulls().unique().to_list()))} for c in CATEGORICAL}
    cols = []
    for c in features or ff.FEATURES:
        s = df[c]
        if c in cats:
            s = s.replace_strict(cats[c], default=-1, return_dtype=pl.Float64)
        elif c == BANK:
            s = s.fill_null(BANK_FILL)
        cols.append(s.cast(pl.Float64).fill_nan(None).to_numpy())
    return np.column_stack(cols), cats


def raw_score(arm: str, model, X: np.ndarray) -> np.ndarray:
    if arm == "iforest":
        return -model.score_samples(X)
    return model.predict_proba(X)[:, 1]


def _logit(s: np.ndarray, arm: str) -> np.ndarray:
    if arm in ("iforest", "bank"):
        return s.reshape(-1, 1)
    s = np.clip(s, 1e-6, 1 - 1e-6)
    return np.log(s / (1 - s)).reshape(-1, 1)


def fit_calibrator(arm: str, s_val: np.ndarray, y_val: np.ndarray) -> LogisticRegression:
    """Platt scaling fitted on the VALIDATION window only (spec 17 §4.3)."""
    return LogisticRegression(C=1e6, max_iter=1000).fit(_logit(s_val, arm), y_val)


def downsample(y: np.ndarray, seed: int = SEED) -> np.ndarray:
    """Indices of all frauds plus LEGIT_PER_FRAUD legitimate rows per fraud, train window only."""
    rng = np.random.default_rng(seed)
    pos, neg = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    keep = rng.choice(neg, size=min(len(neg), LEGIT_PER_FRAUD * max(len(pos), 1)), replace=False)
    return np.sort(np.concatenate([pos, keep]))


def recall_at_precision(y, s, p) -> float:
    prec, rec, _ = precision_recall_curve(y, s)
    ok = prec[:-1] >= p
    return float(rec[:-1][ok].max()) if ok.any() else 0.0


def recall_at_budget(y, s, budget=0.01) -> float | None:
    if y.sum() == 0:
        return None  # undefined, written as JSON null
    k = max(1, int(round(budget * len(s))))
    return float(y[np.argsort(-s, kind="stable")[:k]].sum() / y.sum())


def metrics(val: pl.DataFrame, s: np.ndarray, calibrated: np.ndarray) -> dict:
    y = val["is_fraud"].to_numpy().astype(int)
    k = max(1, int(round(0.01 * len(s))))
    flagged = np.zeros(len(s), bool)
    flagged[np.argsort(-s, kind="stable")[:k]] = True
    noscore = val[BANK].is_null().to_numpy()
    out = {"n": len(y), "n_fraud": int(y.sum()), "pr_auc": float(average_precision_score(y, s)),
           "recall_p80": recall_at_precision(y, s, 0.80), "recall_p95": recall_at_precision(y, s, 0.95),
           "recall_budget_1pct": recall_at_budget(y, s),
           "recall_budget_1pct_no_bank_score": recall_at_budget(y[noscore], s[noscore]),
           "brier_calibration_window": float(brier_score_loss(y, calibrated)), "by_country": {}, "by_segment": {}, "by_month": {}}
    for key, col in (("by_country", "customer_country"), ("by_segment", "customer_segment")):
        for g in val[col].drop_nulls().unique().sort().to_list():
            m = (val[col] == g).to_numpy() & (y == 1)
            if m.sum():  # recall at the 1% window budget and the fraud count behind it (spec 17 §4.4 rule 1)
                out[key][g] = {"n_fraud": int(m.sum()), "recall_budget_1pct": float(flagged[m].sum() / m.sum())}
    for mth in sorted(val["month"].unique().to_list()):
        m = (val["month"] == mth).to_numpy()
        out["by_month"][mth] = {"n_fraud": int(y[m].sum()),
                                "pr_auc": float(average_precision_score(y[m], s[m])) if y[m].sum() else None,
                                "recall_budget_1pct": recall_at_budget(y[m], s[m])}
    return out


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def p95_ms(arm: str, model, X: np.ndarray, n: int = 100) -> float:
    """Scoring p95 per transaction (single-row calls, model only), same machine as training."""
    lat = []
    for i in range(min(n, len(X))):
        t = time.perf_counter()
        raw_score(arm, model, X[i:i + 1])
        lat.append((time.perf_counter() - t) * 1000)
    return float(np.percentile(lat, 95))


def run_arm(arm, factory, Xtr, ytr, Xva, val, yva, out: Path, split_hash: str, cats: dict,
            features: list[str] = ff.FEATURES, extra_meta: dict | None = None) -> dict:
    if arm == "iforest":  # no labels: a random sample of train rows
        idx = np.sort(np.random.default_rng(SEED).choice(len(Xtr), min(len(Xtr), 100_000), replace=False))
    else:
        idx = downsample(ytr)
    t = time.perf_counter()
    model = factory()
    model.fit(Xtr[idx]) if arm == "iforest" else model.fit(Xtr[idx], ytr[idx])
    train_s = time.perf_counter() - t
    t = time.perf_counter()
    s = raw_score(arm, model, Xva)
    batch_s = time.perf_counter() - t
    cal = fit_calibrator(arm, s, yva)
    res = metrics(val, s, cal.predict_proba(_logit(s, arm))[:, 1])
    path = out / "models" / f"fraud-screen-{arm}.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"arm": arm, "split_hash": split_hash, "features": list(features), "seed": SEED, "categorical_codes": cats,
            "bank_fill": BANK_FILL, "train_rows": int(len(idx)), "windows": fs.WINDOWS, **(extra_meta or {})}
    joblib.dump({"model": model, "calibrator": cal, "meta": meta}, path)
    res.update(arm=arm, family=FAMILY[arm], train_seconds=train_s, model_bytes=path.stat().st_size,
               model_sha256=sha256_file(path), p95_ms=p95_ms(arm, model, Xva),
               throughput_tps=len(Xva) / max(batch_s, 1e-9), split_hash=split_hash)
    return res


def bank_arm(val: pl.DataFrame, split_hash: str) -> dict:
    y = val["is_fraud"].to_numpy().astype(int)
    s = val[BANK].fill_null(BANK_FILL).to_numpy() / 100
    cal = fit_calibrator("bank", s, y)
    res = metrics(val, s, cal.predict_proba(_logit(s, "bank"))[:, 1])
    res["recall_budget_1pct_no_bank_score"] = None  # the bank score is constant there: all ties, undefined
    res.update(arm="s_bank", family="baseline", train_seconds=0.0, model_bytes=0, model_sha256=None, p95_ms=0.0,
               throughput_tps=None, split_hash=split_hash)
    return res


def machine_record() -> dict:
    """Where the cost figures were measured (spec 17 §5). iforest, rf and extra_trees (n_jobs=-1) and hgb (OpenMP, so
    also a stacked arm on hgb) use all cores; logreg and mlp use BLAS threads; tree, sgd and gnb run on one core."""
    ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else None
    return {"platform": platform.platform(), "cpu_count": os.cpu_count(), "ram_bytes": ram,
            "python": platform.python_version(), "scikit_learn": sklearn.__version__,
            "threads": "all cores: iforest/rf/extra_trees (n_jobs=-1), hgb and stacked-on-hgb (OpenMP); "
                       "BLAS threads: logreg/mlp; one core: tree/sgd/gnb"}


def run_screen(df: pl.DataFrame, split_hash: str, out: Path, arms: dict | None = None) -> dict:
    out = out_dir(str(out))
    tr, va = df.filter(pl.col("split_window") == fs.TRAIN), df.filter(pl.col("split_window") == fs.VALIDATION)
    Xtr, cats = encode(tr)
    Xva, _ = encode(va, cats)
    ytr, yva = tr["is_fraud"].to_numpy().astype(int), va["is_fraud"].to_numpy().astype(int)
    arms = arms or make_arms()
    results = [bank_arm(va, split_hash)]
    results += [run_arm(a, f, Xtr, ytr, Xva, va, yva, out, split_hash, cats) for a, f in arms.items()]
    supervised = [r for r in results if r["arm"] in arms and r["arm"] != "iforest"]
    top = max(supervised, key=lambda r: r["pr_auc"])
    base_rate = float(yva.mean())
    # stack on the best supervised arm; if none clears twice the base rate, on balanced HGB [assumption, pending lead]
    best = top["arm"] if top["pr_auc"] > 2 * base_rate or "hgb" not in arms else "hgb"
    feats = ff.FEATURES + [BANK]
    stacked = run_arm("stacked", arms[best], encode(tr, cats, feats)[0], ytr, encode(va, cats, feats)[0], va, yva, out,
                      split_hash, cats, feats, {"stacked_on": best, "bank_column": BANK_COLUMN})
    stacked["stacked_on"] = best
    results.append(stacked)
    rec = {"split_hash": split_hash, "label_windows": sorted(fs.LABEL_WINDOWS), "machine": machine_record(),
           "results": results}
    (out / "fraud_screen_validation.json").write_text(json.dumps(rec, indent=2, default=str, allow_nan=False))
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--out", default=None, help="directory outside the repo (or $FRAUD_SCREEN_OUT)")
    a = ap.parse_args()
    out = out_dir(a.out)
    df, h = load_data(a.gold, Path(a.eval) / "transaction_labels.parquet")
    rec = run_screen(df, h, out)
    for r in rec["results"]:
        print(f"{r['arm']:12s} pr_auc={r['pr_auc']:.3f} r@p80={r['recall_p80']:.2f} r@p95={r['recall_p95']:.2f} "
              f"r@1%={r['recall_budget_1pct']:.2f} train={r['train_seconds']:.1f}s p95={r['p95_ms']:.2f}ms "
              f"size={r['model_bytes']}")


if __name__ == "__main__":
    main()
