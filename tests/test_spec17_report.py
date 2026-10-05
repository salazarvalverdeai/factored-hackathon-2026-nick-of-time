"""Spec 17 T4 (17c): the report, the exporter and the test-window guards (AC-04, AC-05); spec 10 T7: held-out run once
(AC-07). Offline, synthetic."""
import json

import numpy as np
import polars as pl
import pytest
from sklearn.metrics import average_precision_score

from eval.harness import report as harness_report
from eval.harness.__main__ import main as harness_main
from eval.harness.client import HarnessError
from scripts.ml import fraud_report as fr
from scripts.ml import fraud_screen as sc
from scripts.ml import fraud_split as fs
from tests.test_spec10_report import EXAMPLE_FILE, SEALED
from tests.test_spec17_screen import prepared

SEAL = {"status": "UNSEALED", "sha256": None}


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
    df = df.with_columns(pl.col("product_type"))                     # synthetic: "Tarjeta Débito" rows are the card subset
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
        for sub in arm["subsets"].values():
            assert set(sub) >= {"pr_auc", "pr_auc_ci", "brier", "recall_at_bank_precision", "recall_no_score_at_1pct",
                                "by_score_band", "by_country", "by_segment"}
            assert [b["band"] for b in sub["by_score_band"]] == list(fr.BANDS)
            assert set(sub["recall_at_bank_precision"]["0.80"]) == {"value", "numerator", "denominator", "ci_low", "ci_high"}
    assert out["data"]["windows"]["test"]["frauds"] is None            # the test labels were not read
    assert (tmp_path / "res/fraud_benchmark.csv").read_text().startswith("arm,subset,pr_auc")


def test_ac_04_test_window_is_refused_while_unsealed_and_reads_no_label(tmp_path, monkeypatch, capsys):
    with pytest.raises(fs.LabelAccessError):
        fs.read_test_labels("x.parquet", pl.DataFrame({"transaction_id": [], "split_window": []}), sealed=False)
    monkeypatch.setattr(fs, "read_test_labels", lambda *a, **k: pytest.fail("test labels read while UNSEALED"))
    monkeypatch.setattr(fr, "load_window", lambda *a, **k: pytest.fail("data opened while UNSEALED"))
    monkeypatch.setattr(fr, "REPO", tmp_path)
    code = fr.main(["--gold", "g", "--eval", "e", "--models", "m", "--window", "test"])
    assert code == 2 and "not SEALED" in capsys.readouterr().err and not list(tmp_path.rglob("fraud_benchmark.*"))


def test_ac_04_sealed_test_window_is_scored_once(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fr, "load_window", lambda *a, **k: (_ for _ in ()).throw(KeyError("reached the data")))
    monkeypatch.setattr("eval.harness.report.protocol_seal", lambda *a: {"status": "SEALED", "sha256": "a" * 64})
    monkeypatch.setattr("eval.harness.report.require_protocol_tag", lambda *a: None)
    (tmp_path / "fraud_benchmark.json").write_text("{}")
    assert fr.main(["--gold", "g", "--eval", "e", "--models", "m", "--window", "test", "--out", str(tmp_path)]) == 2
    assert "already scored" in capsys.readouterr().err
    (tmp_path / "fraud_benchmark.json").unlink()
    with pytest.raises(KeyError, match="reached the data"):             # sealed and unscored: it goes on to the data
        fr.main(["--gold", "g", "--eval", "e", "--models", "m", "--window", "test", "--out", str(tmp_path)])


def test_ac_07_heldout_runs_once_and_writes_no_marker_while_unsealed(tmp_path, monkeypatch):
    """Spec 10 AC-07 / T7: UNSEALED leaves no marker; a sealed run claims the marker and a second run is refused."""
    marker = tmp_path / "results/HELDOUT_RUN.json"
    monkeypatch.setattr(harness_report, "HELDOUT_RUN", marker)
    monkeypatch.setattr(harness_report.claim_heldout_run, "__defaults__", (marker,))
    protocol = tmp_path / "PROTOCOL.md"
    protocol.write_text(SEALED.format(status="UNSEALED", sha="pending"), encoding="utf-8")
    monkeypatch.setattr(harness_report.check_heldout, "__defaults__", (protocol, tmp_path / "heldout.sha256"))
    assert harness_main(["run", "--set", "heldout", "--arms", "S0,S1,S2", "--cases", str(EXAMPLE_FILE)]) == 2
    assert not marker.exists()
    harness_report.claim_heldout_run(["S0"], EXAMPLE_FILE)
    assert json.loads(marker.read_text())["arms"] == ["S0"]
    with pytest.raises(HarnessError, match="runs once"):
        harness_report.claim_heldout_run(["S0"], EXAMPLE_FILE)


def test_ac_04_sealed_string_without_the_protocol_tag_is_refused(tmp_path, monkeypatch, capsys):
    """The seal is the lead's tag on the sealing commit, not the word SEALED in the file (T7 and 17c)."""
    monkeypatch.setattr("eval.harness.report.protocol_seal", lambda *a: {"status": "SEALED", "sha256": "a" * 64})
    monkeypatch.setattr(harness_report.require_protocol_tag, "__defaults__", ("no-such-tag",))
    monkeypatch.setattr(fr, "load_window", lambda *a, **k: pytest.fail("data opened without the tag"))
    assert fr.main(["--gold", "g", "--eval", "e", "--models", "m", "--window", "test", "--out", str(tmp_path)]) == 2
    assert "no-such-tag is missing" in capsys.readouterr().err
    with pytest.raises(HarnessError, match="no-such-tag is missing"):
        harness_report.require_protocol_tag("no-such-tag")
