"""Spec 17 T4 (17c): score the frozen arms on a window, report AC-04 and export fraud_benchmark.json (spec 17 §7.1).

    PYTHONPATH=packages python -m scripts.ml.fraud_report --gold G --eval data/gold_eval --models SCREEN_OUT --window validation
    PYTHONPATH=packages python -m scripts.ml.fraud_report --gold G --eval data/gold_eval --models SCREEN_OUT --window test
    PYTHONPATH=packages python -m scripts.ml.fraud_report --models SCREEN_OUT --freeze     # writes FROZEN, to commit

`validation` is a development run (written to eval/.runs/, git-ignored). `test` runs once (ADR 0022 rule 2,
eval/PROTOCOL.md §3.1): it computes the split hash (no label), calls `seal_guard.check_seal` with it, checks that every
pre-registered arm (§3.4) has a model file whose sha256 equals the hash COMMITTED in FROZEN, then `seal_guard.claim_run`;
only then does it read the test labels, once, and it stops unless the test window holds the pre-registered 211 frauds
(75 on cards). It writes eval/results/fraud-test/ and apps/web/public/data/fraud_benchmark.json; `--out` is refused.
`--eval` must be under data/gold_eval (constitution rule 7). Everything is [data] (gold v1); the thresholds of §4.4
are [assumption]."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
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

REPO = sc.REPO                                       # where the outputs and the committed manifest live
CODE = Path(__file__).resolve().parents[2]           # where scripts.ml is importable (the peak-memory subprocess)
FROZEN = "eval/results/fraud_models_frozen.json"     # committed hashes of the frozen model files (ADR 0022 rule 2)
RUN_NAME = "fraud-test"                              # seal_guard run name; out folder eval/results/fraud-test/
GOLD_EVAL = "data/gold_eval"                         # the only home of is_fraud (constitution rule 7)
TEST_FRAUDS = {"all": 211, "card": 75}               # PROTOCOL §3.1, pre-registered test-window counts [data]
CLASS = {"iforest": "IsolationForest", "logreg": "LogisticRegression", "sgd": "SGDClassifier", "gnb": "GaussianNB",
         "tree": "DecisionTreeClassifier", "rf": "RandomForestClassifier", "extra_trees": "ExtraTreesClassifier",
         "hgb": "HistGradientBoostingClassifier", "mlp": "MLPClassifier", "stacked": "stacked"}
# Rule 4 tie-break by family: linear < tree < ensemble < neural < stacked (PROTOCOL §3.3). The protocol does not rank
# `no-labels` (IsolationForest) or `probabilistic` (GaussianNB); ranking them with linear is [assumption].
SIMPLE = {"no-labels": 0, "linear": 0, "probabilistic": 0, "tree": 1, "ensemble": 2, "neural": 3, "stacked": 4}
CARD = ("Tarjeta Débito", "Tarjeta Crédito")
BANDS = {"none": np.isnan, "<30": lambda b: b < 30, "30-49": lambda b: (b >= 30) & (b < 50), ">=50": lambda b: b >= 50}
MIN_SLICE, FLOOR, P95_MS, MAX_MB, NO_SCORE_MIN = 20, 0.8, 50.0, 200.0, 0.30   # §4.4, all [assumption]
COST = ("train_seconds", "score_p95_ms", "throughput_per_s", "model_mb", "peak_memory_mb")


class Refused(RuntimeError):
    """The report stops: a check of the frozen models, the arm list, the counts or the paths failed."""


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
    """§4.4 on the `all` subset (PROTOCOL §3.3, D-022: the card subset is reported and does not gate): sets
    `passes_rule` (rules 1-3) on each arm; returns the rule-4 choice or S-bank (rule 5)."""
    bm = arms[0]["subsets"]["all"]
    for a in arms[1:]:
        m, diff = a["subsets"]["all"], a["_diff"]["all"]
        recall = {k: m["recall_at_bank_precision"][k]["value"] or 0 for k in ("0.80", "0.95")}
        floor = FLOOR * (m["recall_at_1pct"]["value"] or 0)
        rule1 = (all(recall[k] >= (bm["recall_at_bank_precision"][k]["value"] or 0) for k in recall)
                 and all((x["recall"]["value"] or 0) >= floor for key in ("by_country", "by_segment")
                         for x in m[key] if x["n_fraud"] >= MIN_SLICE)
                 and a["cost"]["score_p95_ms"] <= P95_MS and a["cost"]["model_mb"] <= MAX_MB)
        rule2 = diff["bank_low"] > 0 or (m["recall_no_score_at_1pct"]["value"] or 0) >= NO_SCORE_MIN
        a["passes_rule"] = bool(rule1 and rule2 and diff["best_high"] >= 0)   # rule 3: not significantly worse
    ok = [a for a in arms[1:] if a["passes_rule"]]
    cost = lambda a: (a["cost"]["score_p95_ms"], a["cost"]["model_mb"], a["cost"]["train_seconds"], SIMPLE[a["family"]])  # noqa: E731
    return min(ok, key=cost)["arm"] if ok else "S-bank"


def peak_mb(path: Path, arm: str, X: np.ndarray) -> float:
    """Peak RSS of a fresh process that loads the model and scores 1,000 rows (libraries included). The sample goes to
    a temporary folder, never next to the frozen model files, and is removed even on a crash."""
    code = ("import joblib,numpy as np,resource,sys;from scripts.ml.fraud_screen import raw_score;"
            "m=joblib.load(sys.argv[1]);raw_score(sys.argv[2],m['model'],np.load(sys.argv[3]));"
            "print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)")
    with tempfile.TemporaryDirectory(prefix="fraud-peak-") as tmp:
        npy = Path(tmp) / "sample.npy"
        np.save(npy, X[:1000])
        out = subprocess.run([sys.executable, "-c", code, str(path), arm, str(npy)], cwd=CODE, capture_output=True,
                             text=True, check=True).stdout
    return round(float(out) / (2**20 if sys.platform == "darwin" else 1024), 1)    # bytes on macOS, KB on Linux


def load_split(gold):
    """The time split and its hash; no label is read (the guard needs the hash before any label)."""
    con = fs.connect(gold)
    split = fs.build_split(con)
    return con, split, fs.split_hash(split)


def load_window(con, split: pl.DataFrame, labels_path, window: str, sealed: bool) -> pl.DataFrame:
    """Features of every row up to the end of `window`; labels of train/validation, plus the test window when sealed."""
    labels, allowed = fs.read_labels(labels_path, split, fs.LABEL_WINDOWS), fs.LABEL_WINDOWS
    if window == fs.TEST:
        labels = pl.concat([labels, fs.read_test_labels(labels_path, split, sealed=sealed)])
        allowed = allowed | {fs.TEST}
    cols = ", ".join([*ff.INPUT_COLUMNS, ff.STATUS_COL, sc.BANK, "customer_segment"])
    tx = con.execute(f"SELECT {cols} FROM transactions_enriched "
                     f"WHERE transaction_date < TIMESTAMP '{fs.WINDOWS[window][1]}'").pl()
    return sc.assemble(tx, split, labels, allowed)


def _committed(root: Path, rel: str) -> bytes:
    """The bytes of `rel` at HEAD, refused when it is not committed or the working tree differs."""
    shown = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=root, capture_output=True)
    if shown.returncode != 0:
        raise Refused(f"{rel} is not committed: the frozen model hashes must be in the repo before the test window")
    if not (root / rel).is_file() or (root / rel).read_bytes() != shown.stdout:
        raise Refused(f"{rel} in the working tree differs from HEAD")
    return shown.stdout


def freeze_manifest(models: Path) -> dict:
    """FROZEN from the existing screen record (no re-fit): each arm's model sha256 as the screen recorded it, checked
    against the file, and the sha256 of the record itself."""
    record_path = models / "fraud_screen_validation.json"
    screen = json.loads(record_path.read_text())
    rec = {r["arm"]: r for r in screen["results"]}
    arms = {}
    for key in CLASS:
        path = models / "models" / f"fraud-screen-{key}.joblib"
        if key not in rec or not path.is_file():
            raise Refused(f"the screen in {models} has no model for the pre-registered arm {key}")
        if sc.sha256_file(path) != rec[key]["model_sha256"]:
            raise Refused(f"{path.name} differs from the screen record")
        arms[key] = {"arm": CLASS[key], "family": rec[key]["family"], "model_sha256": rec[key]["model_sha256"],
                     "model_bytes": rec[key]["model_bytes"],
                     **({"stacked_on": rec[key]["stacked_on"]} if key == "stacked" else {})}
    return {"label": "[data]", "source": "scripts/ml/fraud_screen.py on gold v1, train window, calibrated on validation "
                                         "(spec 17 T3); hashes copied from fraud_screen_validation.json, no re-fit",
            "split_hash": screen["split_hash"], "screen_record_sha256": sc.sha256_file(record_path), "arms": arms}


def check_frozen(models: Path, split_hash: str, root: Path = REPO) -> dict:
    """Before the test window: every pre-registered arm (PROTOCOL §3.4) has a model file whose sha256 equals the hash
    committed in FROZEN and the screen record, and the record and the split are the frozen ones."""
    frozen = json.loads(_committed(root, FROZEN))
    record_path = models / "fraud_screen_validation.json"
    if not record_path.is_file():
        raise Refused(f"{record_path} is missing")
    if sc.sha256_file(record_path) != frozen["screen_record_sha256"]:
        raise Refused("the screen record differs from the frozen one (its sha256 is not the committed one)")
    screen = json.loads(record_path.read_text())
    if not split_hash == frozen["split_hash"] == screen["split_hash"]:
        raise Refused("the split hash differs from the one the frozen models were trained on")
    rec = {r["arm"]: r for r in screen["results"]}
    missing = [k for k in CLASS if k not in frozen["arms"] or k not in rec
               or not (models / "models" / f"fraud-screen-{k}.joblib").is_file()]
    if missing:
        raise Refused(f"pre-registered arm(s) without a frozen model: {missing}")
    for key in CLASS:
        digest = sc.sha256_file(models / "models" / f"fraud-screen-{key}.joblib")
        if not digest == frozen["arms"][key]["model_sha256"] == rec[key]["model_sha256"]:
            raise Refused(f"fraud-screen-{key}.joblib is not the frozen model (sha256 differs from {FROZEN})")
    return frozen


def check_test_counts(win: pl.DataFrame) -> dict:
    """The test window must hold the pre-registered fraud counts (PROTOCOL §3.1), else the data is not the sealed one."""
    seen = {"all": int(win["is_fraud"].sum()),
            "card": int(win.filter(pl.col("product_type").is_in(list(CARD)))["is_fraud"].sum())}
    if seen != TEST_FRAUDS:
        raise Refused(f"the test window holds {seen} frauds, not the pre-registered {TEST_FRAUDS}")
    return seen


def score_arms(win: pl.DataFrame, val: pl.DataFrame, screen: dict, models: Path, window: str = fs.VALIDATION,
               frozen: dict | None = None):
    """Scores and calibrated probabilities per arm on `win`, plus the arm records with their cost figures. On the test
    window every pre-registered arm (PROTOCOL §3.4) must be there and match the committed hashes of `frozen`."""
    rec = {r["arm"]: r for r in screen["results"]}
    present = [k for k in CLASS if (models / "models" / f"fraud-screen-{k}.joblib").exists() and k in rec]
    if window == fs.TEST:
        if missing := [k for k in CLASS if k not in present]:
            raise Refused(f"pre-registered arm(s) without a model file: {missing}; the test window is not scored")
        if frozen is None:
            raise Refused(f"the test window needs the committed frozen hashes ({FROZEN})")
    scores = {"S-bank": win[sc.BANK].fill_null(sc.BANK_FILL).to_numpy() / 100}
    sv = val[sc.BANK].fill_null(sc.BANK_FILL).to_numpy() / 100
    yv = val["is_fraud"].to_numpy().astype(int)
    cals = {"S-bank": sc.fit_calibrator("bank", sv, yv).predict_proba(sc._logit(scores["S-bank"], "bank"))[:, 1]}
    arms = [{"arm": "S-bank", "key": "S-bank", "family": "baseline", "version": "fraud_score", "cost": dict.fromkeys(COST, 0.0)}]
    for key in present:
        path = models / "models" / f"fraud-screen-{key}.joblib"
        digest = sc.sha256_file(path)
        if digest != rec[key]["model_sha256"] or (frozen and digest != frozen["arms"][key]["model_sha256"]):
            raise Refused(f"{path.name} is not the frozen model (sha256 differs from the screen record or {FROZEN})")
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


def run_report(df: pl.DataFrame, split_hash: str, models: Path, window: str, reps: int, seal: dict,
               frozen: dict | None = None) -> dict:
    """`seal` is what the result embeds as `protocol`: the dict of seal_guard.check_seal on the test window."""
    screen = json.loads((models / "fraud_screen_validation.json").read_text())
    if screen["split_hash"] != split_hash:
        raise Refused("the split hash differs from the one the models were trained on")
    win = df.filter(pl.col("split_window") == window)
    scores, cals, arms = score_arms(win, df.filter(pl.col("split_window") == fs.VALIDATION), screen, models, window,
                                    frozen)
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
            a.setdefault("_diff", {})[name] = {"bank_low": float(np.percentile(d - boot["S-bank"][1], 2.5)),
                                               "best_high": float(np.percentile(d - boot[best][1], 97.5))}
    chosen = judge(arms)                                    # on `all` only (PROTOCOL §3.3, D-022)
    arms[0]["passes_rule"] = None
    for a in arms:
        for k in ("_diff", "key"):
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


def _under(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def main(argv=None) -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--gold"), cli.add_argument("--eval", help=f"the folder of transaction_labels.parquet, under {GOLD_EVAL}")
    cli.add_argument("--models", required=True, help="the --out of fraud_screen (outside the repo)")
    cli.add_argument("--window", choices=(fs.VALIDATION, fs.TEST), default=fs.VALIDATION)
    cli.add_argument("--out", type=Path, help="output folder of a validation run (default eval/.runs/fraud-dev-<time>)")
    cli.add_argument("--boot", type=int, help="bootstrap replicates (default 500 dev, 2000 test)")
    cli.add_argument("--freeze", action="store_true", help=f"write {FROZEN} from the screen record in --models and stop")
    a = cli.parse_args(argv)
    models = Path(a.models)
    try:
        if a.freeze:
            path = REPO / FROZEN
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(freeze_manifest(models), indent=2) + "\n", encoding="utf-8", newline="\n")
            print(f"wrote {FROZEN}; commit it before the test window")
            return 0
        if not (a.gold and a.eval):
            raise Refused("--gold and --eval are required")
        labels_path = Path(a.eval) / "transaction_labels.parquet"
        if not _under(labels_path, REPO / GOLD_EVAL):        # constitution rule 7, ADR 0022
            raise Refused(f"--eval must be under {GOLD_EVAL}/, the only home of the labels")
    except Refused as error:
        print(f"stop: {error}", file=sys.stderr)
        return 2
    if a.window == fs.VALIDATION:
        from eval.harness.report import protocol_seal
        out = a.out or REPO / "eval/.runs" / f"fraud-dev-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        try:
            con, split, h = load_split(a.gold)
            df = load_window(con, split, labels_path, fs.VALIDATION, sealed=False)
            data = run_report(df, h, models, fs.VALIDATION, a.boot or 500, protocol_seal())
        except Refused as error:
            print(f"stop: {error}", file=sys.stderr)
            return 2
        write(data, out, out)
        print(f"{data['run_kind']}: chosen arm {data['chosen_arm']}; wrote fraud_benchmark.csv and .json in {out}")
        return 0
    return score_test_window(a.gold, labels_path, models, a.boot or 2000, a.out, root=REPO)


def score_test_window(gold, labels_path: Path, models: Path, reps: int, out_arg=None, root: Path = REPO) -> int:
    """The one scoring of the test window. Before the claim: the split hash (no label), the seal with that hash, the
    output folders and the frozen models. After the claim: the labels, once; a stop leaves aborted.json next to the
    marker, so the one look is never silent."""
    from eval.harness import seal_guard
    out = root / seal_guard.RESULTS_DIR / RUN_NAME
    web = root / "apps/web/public/data/fraud_benchmark.json"
    try:
        if out_arg:
            raise Refused("the test window takes no --out: it writes eval/results/fraud-test/ and the web export")
        con, split, h = load_split(gold)
        guard = seal_guard.check_seal(inputs={"fraud_split": h}, root=root)
        if web.exists() or (out.exists() and any(out.iterdir())):
            raise Refused(f"the test window was already scored or started ({web.name} or {out} exists); it is scored once")
        frozen = check_frozen(models, h, root)
        seal_guard.claim_run(RUN_NAME, out, guard, root=root)
    except (Refused, seal_guard.SealError) as error:
        print(f"stop: {error}", file=sys.stderr)
        return 2
    try:
        df = load_window(con, split, labels_path, fs.TEST, sealed=True)     # the one read of the test labels
        check_test_counts(df.filter(pl.col("split_window") == fs.TEST))
        data = run_report(df, h, models, fs.TEST, reps, guard, frozen)
        write(data, out, web.parent)
    except BaseException as error:                        # a crash after the claim is recorded, never silent
        (out / "aborted.json").write_text(json.dumps({"run_status": "aborted", "error": f"{type(error).__name__}: {error}",
                                                      "protocol": guard}, indent=2) + "\n", encoding="utf-8")
        print(f"stop after the claim: {type(error).__name__}: {error}; recorded in {out / 'aborted.json'}",
              file=sys.stderr)
        return 3
    print(f"{data['run_kind']}: chosen arm {data['chosen_arm']}; wrote {out} and {web}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
