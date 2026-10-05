"""Spec 17 T4 (17c): the report, the exporter and the one-time test-window run (AC-04, AC-05; ADR 0022 rule 2).

Offline and synthetic: the test-window runs happen in a throwaway git repository sealed like the real one (tag
protocol-v1, PROTOCOL with the synthetic split hash, committed frozen model hashes), with synthetic gold, labels and
models in tmp_path. Nothing here reads data/gold_eval or the real fraud labels.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from sklearn.metrics import average_precision_score

from eval.harness import seal_guard
from scripts.ml import fraud_report as fr
from scripts.ml import fraud_screen as sc
from scripts.ml import fraud_split as fs
from tests.test_spec17_screen import prepared, synthetic

SEAL = {"status": "UNSEALED", "sha256": None}
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
       "-c", "tag.gpgsign=false", "-c", "init.defaultBranch=main"]
BODY = "# Evaluation protocol\n\nSynthetic, for the spec 17 tests.\n\n"


def test_ac_04_weighted_average_precision_matches_sklearn_with_ties():
    rng = np.random.default_rng(0)
    y, s = rng.integers(0, 2, 500), rng.integers(0, 20, 500).astype(float)   # many ties, like the bank score
    assert fr.boot_ap(fr.prep(y, s), np.ones(500)) == pytest.approx(average_precision_score(y, s))


def test_ac_04_rates_carry_a_wilson_interval_and_null_when_undefined():
    r = fr.rate(5, 10)
    assert (r["value"], r["numerator"], r["denominator"]) == (0.5, 5, 10) and 0.23 < r["ci_low"] < 0.5 < r["ci_high"] < 0.77
    assert fr.rate(None, 0)["value"] is None


def test_ac_04_report_has_every_metric_on_all_and_card_and_strict_json(tmp_path):
    df, h, _, _ = prepared(tmp_path)
    sc.run_screen(df, h, tmp_path / "screen", arms={k: sc.make_arms()[k] for k in ("logreg", "tree")})
    data = fr.run_report(df, h, tmp_path / "screen", fs.VALIDATION, 20, SEAL)
    fr.write(data, tmp_path / "res", tmp_path / "web")
    out = json.loads((tmp_path / "web/fraud_benchmark.json").read_text(), parse_constant=lambda c: pytest.fail(c))
    assert set(out) == {"generated_at", "git_sha", "source", "data"} and out["data"]["label"] == "[data]"
    assert out["data"]["run_kind"] == "development run on validation" and out["data"]["protocol"]["fraud_split_hash"] == h
    assert [a["arm"] for a in out["data"]["arms"]][:2] == ["S-bank", "LogisticRegression"]
    assert out["data"]["arms"][-1]["arm"] == "stacked" and out["data"]["chosen_arm"]
    for arm in out["data"]["arms"]:
        assert set(arm["cost"]) == set(fr.COST) and set(arm["subsets"]) == {"all", "card"}
        assert not any(k.startswith("_") for k in arm)
        for sub in arm["subsets"].values():
            assert set(sub) >= {"pr_auc", "pr_auc_ci", "brier", "recall_at_bank_precision", "recall_no_score_at_1pct",
                                "recall_at_1pct", "by_score_band", "by_country", "by_segment"}
            assert [b["band"] for b in sub["by_score_band"]] == list(fr.BANDS)
            assert set(sub["recall_at_bank_precision"]["0.80"]) == {"value", "numerator", "denominator", "ci_low", "ci_high"}
    assert out["data"]["windows"]["test"]["frauds"] is None            # the test labels were not read
    assert (tmp_path / "res/fraud_benchmark.csv").read_text().startswith("arm,subset,pr_auc")
    assert not list((tmp_path / "screen/models").glob("*.npy"))         # peak_mb leaves no sample next to the models


def test_ac_04_rules_2_and_3_are_judged_on_all_products_not_on_the_card_subset(tmp_path, monkeypatch):
    """AC-04, PROTOCOL §3.3 and D-022: the paired-bootstrap differences of rules 2 and 3 come from `all`. On the
    synthetic fixture LogisticRegression beats S-bank on all products (lower bound of the difference > 0) but not on
    cards (lower bound <= 0; its no-score recall is 0.25 < 0.30), so it passes only when judged on `all`."""
    df, h, _, _ = prepared(tmp_path)
    sc.run_screen(df, h, tmp_path / "screen", arms={k: sc.make_arms()[k] for k in ("logreg", "tree")})
    seen, real = {}, fr.judge
    monkeypatch.setattr(fr, "judge", lambda arms: (seen.update({a["arm"]: a["_diff"] for a in arms[1:]}), real(arms))[1])
    data = fr.run_report(df, h, tmp_path / "screen", fs.VALIDATION, 20, SEAL)
    diff = seen["LogisticRegression"]
    assert diff["card"]["bank_low"] <= 0 < diff["all"]["bank_low"]
    logreg = next(a for a in data["arms"] if a["arm"] == "LogisticRegression")
    assert logreg["subsets"]["all"]["recall_no_score_at_1pct"]["value"] < fr.NO_SCORE_MIN
    assert logreg["passes_rule"] is True


def _arm(name, all_diff, card_diff, no_score=0.0):
    sub = {"recall_at_bank_precision": {"0.80": {"value": 0.5}, "0.95": {"value": 0.5}},
           "recall_at_1pct": {"value": 0.5}, "recall_no_score_at_1pct": {"value": no_score},
           "by_country": [], "by_segment": []}
    return {"arm": name, "family": "linear", "subsets": {"all": sub, "card": sub},
            "cost": {"score_p95_ms": 1.0, "model_mb": 1.0, "train_seconds": 1.0},
            "_diff": {"all": all_diff, "card": card_diff}}


def test_ac_04_judge_reads_only_the_all_subset():
    """AC-04 (D-022): an arm that passes rules 2 and 3 on all products and fails them on cards passes, and the reverse
    fails; the card subset never gates."""
    bank = {"arm": "S-bank", "subsets": {"all": _arm("x", {}, {})["subsets"]["all"]}}
    good_all = _arm("A", {"bank_low": 0.01, "best_high": 0.0}, {"bank_low": -0.2, "best_high": -0.1})
    good_card = _arm("B", {"bank_low": -0.2, "best_high": -0.1}, {"bank_low": 0.01, "best_high": 0.0})
    assert fr.judge([bank, good_all, good_card]) == "A"
    assert (good_all["passes_rule"], good_card["passes_rule"]) == (True, False)


def test_ac_05_score_arms_refuses_the_test_window_without_every_pre_registered_arm(tmp_path):
    """AC-05, PROTOCOL §3.4: on the test window a missing model file is a refusal, never a silently dropped arm."""
    df, h, _, _ = prepared(tmp_path)
    sc.run_screen(df, h, tmp_path / "screen", arms={k: sc.make_arms()[k] for k in ("logreg", "tree")})
    screen = json.loads((tmp_path / "screen/fraud_screen_validation.json").read_text())
    val = df.filter(pl.col("split_window") == fs.VALIDATION)
    with pytest.raises(fr.Refused, match="without a model file: .*iforest"):
        fr.score_arms(val, val, screen, tmp_path / "screen", fs.TEST, frozen={"arms": {}})
    assert fr.score_arms(val, val, screen, tmp_path / "screen")[2][1]["arm"] == "LogisticRegression"   # dev run


def test_ac_05_labels_outside_gold_eval_are_refused(tmp_path, monkeypatch, capsys):
    """AC-05, constitution rule 7: `--eval` must be under data/gold_eval, on either window; nothing is opened."""
    monkeypatch.setattr(fr, "REPO", tmp_path / "repo")
    monkeypatch.setattr(fr, "load_split", lambda *a, **k: pytest.fail("data opened with labels outside gold_eval"))
    for window in (fs.VALIDATION, fs.TEST):
        code = fr.main(["--gold", "g", "--eval", str(tmp_path / "elsewhere"), "--models", "m", "--window", window])
        assert code == 2 and "must be under data/gold_eval" in capsys.readouterr().err


# ---------- the one-time test-window run, in a throwaway sealed repository ----------

def git(repo: Path, *args: str) -> str:
    return subprocess.run([*GIT, *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def screened(tmp_path_factory):
    """Synthetic gold with a test window, its labels, and a full screen of every pre-registered arm (no test label)."""
    base = tmp_path_factory.mktemp("fraud")
    tx, split, fraud = synthetic()
    gold = base / "gold"
    gold.mkdir()
    tx.write_parquet(gold / "transactions_enriched.parquet")
    labels = pl.DataFrame({"transaction_id": list(fraud), "is_fraud": list(fraud.values())})
    df, h, _, _ = prepared(base)
    sc.run_screen(df, h, base / "screen")
    test_ids = set(split.filter(pl.col("split_window") == fs.TEST)["transaction_id"])
    card = set(tx.filter(pl.col("product_type").is_in(list(fr.CARD)))["transaction_id"])
    counts = {"all": sum(fraud[t] for t in test_ids), "card": sum(fraud[t] for t in test_ids & card)}
    assert counts["all"] > 0 and counts["card"] > 0
    return {"gold": gold, "labels": labels, "screen": base / "screen", "split_hash": h, "counts": counts}


@pytest.fixture
def sealed(tmp_path, screened, monkeypatch):
    """A repository sealed on the synthetic split hash, with the frozen hashes committed and the labels under
    data/gold_eval; fr.REPO points at it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".gitignore").write_text("data/\n")
    block = (f"{seal_guard.BEGIN}\n- Status: SEALED\n- Protocol sha256: {hashlib.sha256(BODY.encode()).hexdigest()}\n"
             f"- Fraud split hash (spec 17 T1): {screened['split_hash']}\n- Sealed on: 2026-10-05\n{seal_guard.END}\n")
    (repo / "eval").mkdir()
    (repo / seal_guard.PROTOCOL_PATH).write_text(BODY + block, encoding="utf-8", newline="\n")
    sha = commit(repo, "seal")
    git(repo, "tag", seal_guard.SEAL_TAG)
    frozen = repo / fr.FROZEN
    frozen.parent.mkdir(parents=True)
    frozen.write_text(json.dumps(fr.freeze_manifest(screened["screen"]), indent=2) + "\n")
    commit(repo, "freeze the fraud models")
    (repo / "data/gold_eval").mkdir(parents=True)
    screened["labels"].write_parquet(repo / "data/gold_eval/transaction_labels.parquet")
    monkeypatch.setattr(fr, "REPO", repo)
    monkeypatch.setattr(seal_guard, "SEAL_COMMIT", sha)
    monkeypatch.setattr(seal_guard.check_seal, "__defaults__", (None, seal_guard.ROOT, seal_guard.SEAL_TAG, sha))
    return repo


def score(screened, repo: Path, *extra: str) -> int:
    return fr.main(["--gold", str(screened["gold"]), "--eval", str(repo / "data/gold_eval"), "--models",
                    str(screened["screen"]), "--window", "test", "--boot", "20", *extra])


def watch_labels(monkeypatch, repo: Path) -> list:
    """Spy on the one reader of the test labels; records whether the run was already claimed when it was called."""
    calls, real = [], fs.read_test_labels

    def spy(*args, **kwargs):
        calls.append((repo / "eval/results/fraud-test/fraud-test.start.json").exists())
        return real(*args, **kwargs)
    monkeypatch.setattr(fs, "read_test_labels", spy)
    return calls


def test_ac_04_test_window_is_scored_once_after_the_seal_and_the_claim(sealed, screened, monkeypatch, capsys):
    """AC-04, AC-05, ADR 0022 rule 2: with the seal holding, the frozen models matching the committed hashes and the
    pre-registered fraud counts, the test window is scored once; the labels are read after the claim; the result
    embeds the guard; a second run is refused before any label read."""
    monkeypatch.setattr(fr, "TEST_FRAUDS", screened["counts"])
    calls = watch_labels(monkeypatch, sealed)
    assert score(screened, sealed) == 0, capsys.readouterr().err
    assert calls == [True]
    out = json.loads((sealed / "apps/web/public/data/fraud_benchmark.json").read_text())["data"]
    assert out["run_kind"] == "test window, scored once" and out["scored_window"] == "test"
    assert out["protocol"]["status"] == "SEALED" and out["protocol"]["tag"] == "protocol-v1"
    assert out["protocol"]["inputs"] == {"fraud_split": screened["split_hash"]}
    assert out["protocol"]["fraud_split_hash"] == screened["split_hash"]
    assert out["windows"]["test"]["frauds"] == screened["counts"]["all"]
    assert [a["arm"] for a in out["arms"]] == ["S-bank", *fr.CLASS.values()]
    assert (sealed / "eval/results/fraud-test/fraud_benchmark.csv").is_file()
    assert not list((screened["screen"] / "models").glob("*.npy"))
    assert score(screened, sealed) == 2 and "scored once" in capsys.readouterr().err
    (sealed / "apps/web/public/data/fraud_benchmark.json").unlink()     # even without the export, the claim refuses
    assert score(screened, sealed) == 2 and "eval/results/fraud-test" in capsys.readouterr().err
    assert calls == [True]


def test_ac_05_test_counts_other_than_the_pre_registered_stop_after_the_claim_and_stay_recorded(sealed, screened,
                                                                                               capsys):
    """AC-05 (PROTOCOL §3.1): 211 and 75 are pre-registered; other data stops the run after the claim, which leaves
    aborted.json, and the window is never scored a second time."""
    assert score(screened, sealed) == 3
    assert "not the pre-registered {'all': 211, 'card': 75}" in capsys.readouterr().err
    aborted = json.loads((sealed / "eval/results/fraud-test/aborted.json").read_text())
    assert aborted["run_status"] == "aborted" and aborted["protocol"]["status"] == "SEALED"
    assert not (sealed / "apps/web/public/data/fraud_benchmark.json").exists()
    assert score(screened, sealed) == 2


@pytest.mark.parametrize("breakage, message", [
    ("model", "not the frozen model"),
    ("missing", "without a frozen model"),
    ("uncommitted", "not committed"),
    ("edited", "working tree differs"),
    ("out", "takes no --out"),
    ("split", "fraud_split differs"),
])
def test_ac_05_test_window_refuses_before_any_label_or_claim(sealed, screened, monkeypatch, capsys, tmp_path,
                                                              breakage, message):
    """AC-05, ADR 0022 rule 2: a model file whose sha256 is not the committed one, a missing pre-registered arm, frozen
    hashes that are not committed or edited, `--out`, or a split hash other than the sealed one stop the run before the
    claim and before any test label is read."""
    calls = watch_labels(monkeypatch, sealed)
    models = screened["screen"] / "models"
    extra = ()
    if breakage in ("model", "missing"):
        copy = tmp_path / "screen"
        subprocess.run(["cp", "-R", str(screened["screen"]), str(copy)], check=True)
        monkeypatch.setitem(screened, "screen", copy)
        models = copy / "models"
        if breakage == "model":
            with (models / "fraud-screen-logreg.joblib").open("ab") as fh:
                fh.write(b"\0")
        else:
            (models / "fraud-screen-mlp.joblib").unlink()
    elif breakage == "uncommitted":
        git(sealed, "rm", "-q", "--cached", fr.FROZEN)
        git(sealed, "commit", "-q", "-m", "unfreeze")                   # the file stays, untracked
    elif breakage == "edited":
        (sealed / fr.FROZEN).write_text("{}\n")
    elif breakage == "out":
        extra = ("--out", str(sealed / "eval/results/elsewhere"))
    elif breakage == "split":
        monkeypatch.setattr(fr, "load_split", lambda gold: (None, None, "f" * 64))
    assert score(screened, sealed, *extra) == 2
    assert message in capsys.readouterr().err
    assert calls == [] and not (sealed / "eval/results/fraud-test").exists()
