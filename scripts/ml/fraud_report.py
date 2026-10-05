"""Spec 17 T4 (17c): score the frozen arms on a window, report AC-04 and export fraud_benchmark.json (spec 17 §7.1).

    PYTHONPATH=packages python -m scripts.ml.fraud_report --gold G --eval E --models SCREEN_OUT --window validation
    PYTHONPATH=packages python -m scripts.ml.fraud_report --gold G --eval E --models SCREEN_OUT --window test

`validation` is a development run (written to eval/.runs/, git-ignored). `test` refuses to start while eval/PROTOCOL.md
is not SEALED, refuses model files that differ from the screen's recorded hashes (frozen) and refuses a second run; it
reads the test labels once (ADR 0022) and writes eval/results/fraud_benchmark.csv and
apps/web/public/data/fraud_benchmark.json. Everything is [data] (gold v1); the thresholds of §4.4 are [assumption]."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from sklearn.metrics import brier_score_loss, precision_recall_curve

from scripts.ml import fraud_features as ff
from scripts.ml import fraud_screen as sc
from scripts.ml import fraud_split as fs

REPO = sc.REPO
CLASS = {"iforest": "IsolationForest", "logreg": "LogisticRegression", "sgd": "SGDClassifier", "gnb": "GaussianNB",
         "tree": "DecisionTreeClassifier", "rf": "RandomForestClassifier", "extra_trees": "ExtraTreesClassifier",
         "hgb": "HistGradientBoostingClassifier", "mlp": "MLPClassifier", "stacked": "stacked"}
SIMPLE = {"no-labels": 0, "linear": 0, "probabilistic": 0, "tree": 1, "ensemble": 2, "neural": 3, "stacked": 4}
CARD = ("Tarjeta Débito", "Tarjeta Crédito")
BANDS = {"none": np.isnan, "<30": lambda b: b < 30, "30-49": lambda b: (b >= 30) & (b < 50), ">=50": lambda b: b >= 50}
MIN_SLICE, FLOOR, P95_MS, MAX_MB, NO_SCORE_MIN = 20, 0.8, 50.0, 200.0, 0.30   # §4.4, all [assumption]
COST = ("train_seconds", "score_p95_ms", "throughput_per_s", "model_mb", "peak_memory_mb")


def rate(k, n) -> dict:
    """Rate object of spec 10 §7.2 with the 95% Wilson interval; value null when undefined."""
    from eval.harness.metrics import wilson
    if k is None or not n:
        return {"value": None, "numerator": None, "denominator": int(n or 0), "ci_low": None, "ci_high": None}
    lo, hi = wilson(int(k), int(n))
    return {"value": round(k / n, 4), "numerator": int(k), "denominator": int(n), "ci_low": round(lo, 4),
            "ci_high": round(hi, 4)}


def top_flags(s, budget=0.01) -> np.ndarray:
    flags = np.zeros(len(s), bool)
    flags[np.argsort(-s, kind="stable")[:max(1, int(round(budget * len(s))))]] = True
    return flags


def recall_at_precision(y, s, p) -> dict:
    prec, rec, _ = precision_recall_curve(y, s)
    ok = prec[:-1] >= p
    return rate(int(round(rec[:-1][ok].max() * y.sum())) if ok.any() else 0, y.sum())


def prep(y, s):
    order = np.argsort(-s, kind="stable")
    ss = s[order]
    return order, y[order].astype(float), np.r_[0, np.flatnonzero(ss[1:] != ss[:-1]) + 1]


def boot_ap(prepped, w) -> float:
    """Average precision with row weights `w` (bootstrap counts); w = 1 equals sklearn's average_precision_score."""
    order, ys, starts = prepped
    ws = w[order]
    tp, n = np.add.reduceat(ws * ys, starts), np.add.reduceat(ws, starts)
    cn, ctp = np.cumsum(n), np.cumsum(tp)
    prec = np.divide(ctp, cn, out=np.zeros_like(ctp), where=cn > 0)
    return float((tp / tp.sum() * prec).sum()) if tp.sum() else float("nan")


def bootstrap(y, scores: dict, reps: int, seed=sc.SEED) -> dict:
    """{arm: (PR-AUC, bootstrap draws)}; every arm sees the same resamples, so differences are paired."""
    rng, n = np.random.default_rng(seed), len(y)
    prepped = {a: prep(y, s) for a, s in scores.items()}
    draws = {a: np.empty(reps) for a in scores}
    for b in range(reps):
        w = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        for a, p in prepped.items():
            draws[a][b] = boot_ap(p, w)
    return {a: (boot_ap(p, np.ones(n)), draws[a]) for a, p in prepped.items()}


def subset_arm(y, s, cal, bank, country, segment, ap, ci) -> dict:
    """AC-04 metrics of one arm on one subset. Recall by slice is at the 1% window budget (D-017b)."""
    flag, noscore, fraud = top_flags(s), np.isnan(bank), y == 1
    ns = fraud & noscore
    out = {"pr_auc": round(ap, 4), "pr_auc_ci": [round(float(v), 4) for v in ci],
           "brier": round(float(brier_score_loss(y, cal)), 6),
           "recall_at_bank_precision": {"0.80": recall_at_precision(y, s, 0.80), "0.95": recall_at_precision(y, s, 0.95)},
           "recall_at_1pct": rate(int(flag[fraud].sum()), fraud.sum()),
           "recall_no_score_at_1pct": rate(int(top_flags(s[noscore])[y[noscore] == 1].sum()), ns.sum())
           if noscore.any() and len(set(s[noscore])) > 1 else rate(None, ns.sum())}   # S-bank is constant there: ties

    def by(key, groups, keep_empty=False):
        return [{key: g, "n_fraud": int((m & fraud).sum()), "recall": rate(int(flag[m & fraud].sum()), (m & fraud).sum())}
                for g, m in groups if keep_empty or (m & fraud).any()]
    out["by_score_band"] = by("band", [(b, f(bank)) for b, f in BANDS.items()], True)
    out["by_country"] = by("country", [(g, country == g) for g in sorted(set(country) - {None})])
    out["by_segment"] = by("segment", [(g, segment == g) for g in sorted(set(segment) - {None})])
    return out


def judge(arms: list[dict]) -> str:
    """§4.4 on the `all` subset: sets `passes_rule` (rules 1-3) on each arm; returns the rule-4 choice or S-bank (rule 5)."""
    bm = arms[0]["subsets"]["all"]
    for a in arms[1:]:
        m = a["subsets"]["all"]
        recall = {k: m["recall_at_bank_precision"][k]["value"] or 0 for k in ("0.80", "0.95")}
        floor = FLOOR * (m["recall_at_1pct"]["value"] or 0)
        rule1 = (all(recall[k] >= (bm["recall_at_bank_precision"][k]["value"] or 0) for k in recall)
                 and all((x["recall"]["value"] or 0) >= floor for key in ("by_country", "by_segment")
                         for x in m[key] if x["n_fraud"] >= MIN_SLICE)
                 and a["cost"]["score_p95_ms"] <= P95_MS and a["cost"]["model_mb"] <= MAX_MB)
        rule2 = a["_diff_bank_low"] > 0 or (m["recall_no_score_at_1pct"]["value"] or 0) >= NO_SCORE_MIN
        a["passes_rule"] = bool(rule1 and rule2 and a["_diff_best_high"] >= 0)   # rule 3: not significantly worse
    ok = [a for a in arms[1:] if a["passes_rule"]]
    cost = lambda a: (a["cost"]["score_p95_ms"], a["cost"]["model_mb"], a["cost"]["train_seconds"], SIMPLE[a["family"]])  # noqa: E731
    return min(ok, key=cost)["arm"] if ok else "S-bank"


def peak_mb(path: Path, arm: str, X: np.ndarray) -> float:
    """Peak RSS of a fresh process that loads the model and scores 1,000 rows (libraries included)."""
    npy = path.with_suffix(".sample.npy")
    np.save(npy, X[:1000])
    code = ("import joblib,numpy as np,resource,sys;from scripts.ml.fraud_screen import raw_score;"
            "m=joblib.load(sys.argv[1]);raw_score(sys.argv[2],m['model'],np.load(sys.argv[3]));"
            "print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)")
    out = subprocess.run([sys.executable, "-c", code, str(path), arm, str(npy)], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout
    npy.unlink()
    return round(float(out) / (2**20 if sys.platform == "darwin" else 1024), 1)    # bytes on macOS, KB on Linux


def load_window(gold, labels_path, window: str, sealed: bool) -> tuple[pl.DataFrame, str]:
    """Features of every row up to the end of `window`; labels of train/validation, plus the test window when sealed."""
    con = fs.connect(gold)
    split = fs.build_split(con)
    labels, allowed = fs.read_labels(labels_path, split, fs.LABEL_WINDOWS), fs.LABEL_WINDOWS
    if window == fs.TEST:
        labels = pl.concat([labels, fs.read_test_labels(labels_path, split, sealed=sealed)])
        allowed = allowed | {fs.TEST}
    cols = ", ".join([*ff.INPUT_COLUMNS, ff.STATUS_COL, sc.BANK, "customer_segment"])
    tx = con.execute(f"SELECT {cols} FROM transactions_enriched "
                     f"WHERE transaction_date < TIMESTAMP '{fs.WINDOWS[window][1]}'").pl()
    return sc.assemble(tx, split, labels, allowed), fs.split_hash(split)


def score_arms(win: pl.DataFrame, val: pl.DataFrame, screen: dict, models: Path):
    """Scores and calibrated probabilities per arm on `win`, plus the arm records with their cost figures."""
    rec = {r["arm"]: r for r in screen["results"]}
    scores = {"S-bank": win[sc.BANK].fill_null(sc.BANK_FILL).to_numpy() / 100}
    sv = val[sc.BANK].fill_null(sc.BANK_FILL).to_numpy() / 100
    yv = val["is_fraud"].to_numpy().astype(int)
    cals = {"S-bank": sc.fit_calibrator("bank", sv, yv).predict_proba(sc._logit(scores["S-bank"], "bank"))[:, 1]}
    arms = [{"arm": "S-bank", "key": "S-bank", "family": "baseline", "version": "fraud_score", "cost": dict.fromkeys(COST, 0.0)}]
    for key in [k for k in CLASS if (models / "models" / f"fraud-screen-{k}.joblib").exists()]:
        path = models / "models" / f"fraud-screen-{key}.joblib"
        if sc.sha256_file(path) != rec[key]["model_sha256"]:
            raise SystemExit(f"stop: {path.name} is not the frozen model (sha256 differs from the screen record)")
        art = joblib.load(path)
        X = sc.encode(win, art["meta"]["categorical_codes"], art["meta"]["features"])[0]
        t = time.perf_counter()
        scores[key] = sc.raw_score(key, art["model"], X)
        batch = time.perf_counter() - t
        cals[key] = art["calibrator"].predict_proba(sc._logit(scores[key], key))[:, 1]
        arms.append({"arm": CLASS[key], "key": key, "family": rec[key]["family"], "version": rec[key]["model_sha256"][:12],
                     **({"stacked_on": rec[key]["stacked_on"]} if key == "stacked" else {}),
                     "cost": {"train_seconds": round(rec[key]["train_seconds"], 2),
                              "score_p95_ms": round(sc.p95_ms(key, art["model"], X), 3),
                              "throughput_per_s": round(len(X) / max(batch, 1e-9)),
                              "model_mb": round(rec[key]["model_bytes"] / 2**20, 2), "peak_memory_mb": peak_mb(path, key, X)}})
    return scores, cals, arms


def run_report(df: pl.DataFrame, split_hash: str, models: Path, window: str, reps: int, seal: dict) -> dict:
    screen = json.loads((models / "fraud_screen_validation.json").read_text())
    if screen["split_hash"] != split_hash:
        raise SystemExit("stop: the split hash differs from the one the models were trained on")
    win = df.filter(pl.col("split_window") == window)
    scores, cals, arms = score_arms(win, df.filter(pl.col("split_window") == fs.VALIDATION), screen, models)
    y, bank = win["is_fraud"].to_numpy().astype(int), win[sc.BANK].to_numpy().astype(float)
    country, segment = win["customer_country"].to_numpy(), win["customer_segment"].to_numpy()
    for name, m in (("all", np.ones(len(y), bool)), ("card", win["product_type"].is_in(list(CARD)).to_numpy())):
        boot = bootstrap(y[m], {a["key"]: scores[a["key"]][m] for a in arms}, reps)
        best = max(boot, key=lambda k: boot[k][0])
        for a in arms:
            ap, d = boot[a["key"]]
            ci = np.percentile(d, [2.5, 97.5])
            a.setdefault("subsets", {})[name] = subset_arm(y[m], scores[a["key"]][m], cals[a["key"]][m], bank[m], country[m],
                                                          segment[m], ap, ci)
            a["_diff_bank_low"] = float(np.percentile(d - boot["S-bank"][1], 2.5))
            a["_diff_best_high"] = float(np.percentile(d - boot[best][1], 97.5))
    chosen = judge(arms)
    arms[0]["passes_rule"] = None
    for a in arms:
        for k in ("_diff_bank_low", "_diff_best_high", "key"):
            a.pop(k)
    wins = {w: {"from": b[:7], "to": (datetime.fromisoformat(e) - timedelta(days=1)).strftime("%Y-%m")}
            for w, (b, e) in fs.WINDOWS.items()}
    wins[fs.TEST].update(transactions=len(win) if window == fs.TEST else None, frauds=int(y.sum()) if window == fs.TEST else None)
    mach = screen["machine"]
    return {"label": "[data]", "run_kind": "test window, scored once" if window == fs.TEST else "development run on validation",
            "scored_window": window, "protocol": {**seal, "fraud_split_hash": split_hash}, "windows": wins,
            "machine": {"cpu": f"{mach['platform']}, {mach['cpu_count']} cores", "memory_gb": round(mach["ram_bytes"] / 2**30, 1)},
            "chosen_arm": chosen, "arms": arms}


def write(data: dict, csv_dir: Path, json_dir: Path) -> None:
    """CSV of the headline figures and the spec 01 §6.2 envelope around `data` (spec 17 §7)."""
    from eval.harness.report import git_sha, now
    csv_dir.mkdir(parents=True, exist_ok=True), json_dir.mkdir(parents=True, exist_ok=True)
    with (csv_dir / "fraud_benchmark.csv").open("w", newline="", encoding="utf-8") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(["arm", "subset", "pr_auc", "pr_auc_low", "pr_auc_high", "brier", "recall_p80", "recall_p95",
                      "recall_no_score_1pct", "passes_rule"])
        for a in data["arms"]:
            for name, m in a["subsets"].items():
                r = m["recall_at_bank_precision"]
                out.writerow([a["arm"], name, m["pr_auc"], *m["pr_auc_ci"], m["brier"], r["0.80"]["value"], r["0.95"]["value"],
                              m["recall_no_score_at_1pct"]["value"], a["passes_rule"]])
    env = {"generated_at": now(), "git_sha": git_sha(), "source": f"scripts/ml/fraud_report.py, {data['run_kind']} [data]", "data": data}
    (json_dir / "fraud_benchmark.json").write_text(json.dumps(env, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                                  encoding="utf-8")


def main(argv=None) -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--gold", required=True), cli.add_argument("--eval", required=True)
    cli.add_argument("--models", required=True, help="the --out of fraud_screen (outside the repo)")
    cli.add_argument("--window", choices=(fs.VALIDATION, fs.TEST), default=fs.VALIDATION)
    cli.add_argument("--out", type=Path, help="override the output folder (default: see the module doc)")
    cli.add_argument("--boot", type=int, help="bootstrap replicates (default 500 dev, 2000 test)")
    a = cli.parse_args(argv)
    from eval.harness.report import protocol_seal
    seal, test = protocol_seal(), a.window == fs.TEST
    dev = REPO / "eval/.runs" / f"fraud-dev-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    csv_dir, json_dir = (a.out, a.out) if a.out else ((REPO / "eval/results", REPO / "apps/web/public/data") if test else (dev, dev))
    if test and seal["status"] != "SEALED":                     # before any data or label is opened
        print(f"stop: eval/PROTOCOL.md is {seal['status']}, not SEALED; the test window is not scored", file=sys.stderr)
        return 2
    if test:                                                    # status string alone is not the seal: the tag is
        from eval.harness.client import HarnessError
        try:
            from eval.harness.report import require_protocol_tag
            require_protocol_tag()
        except HarnessError as error:
            print(f"stop: {error}", file=sys.stderr)
            return 2
    if test and ((csv_dir / "fraud_benchmark.csv").exists() or (json_dir / "fraud_benchmark.json").exists()):
        print("stop: the test window was already scored (fraud_benchmark.* exists); it is scored once", file=sys.stderr)
        return 2
    df, h = load_window(a.gold, Path(a.eval) / "transaction_labels.parquet", a.window, test)
    data = run_report(df, h, Path(a.models), a.window, a.boot or (2000 if test else 500), seal)
    write(data, csv_dir, json_dir)
    print(f"{data['run_kind']}: chosen arm {data['chosen_arm']}; wrote fraud_benchmark.csv and .json in {csv_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
