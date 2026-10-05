"""Spec 10 T3, T4, T5 — run metadata, the web summary, the held-out guard and the blocks-against-label report."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from eval.harness import HarnessError, labels, metrics, report, run_set, write_outputs
from eval.harness.__main__ import main
from tests.test_spec10_harness import AMBIGUOUS, BLOCK, EXAMPLES, FAULT, api_with, final_for, record

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_FILE = ROOT / "eval/examples.jsonl"
RUN_META = {"git_sha": "abc1234", "platform_revision": "rev-7", "policies_version": 2, "provider": "fake",
            "model_graph": "claude-haiku-4-5", "model_fast": "claude-haiku-4-5", "prompt_hash": "sha256:feed",
            "classifier_version": "b0-rules"}
SEALED = """# Evaluation protocol
<!-- SEAL:BEGIN -->
- Status: {status}
- Protocol sha256: {sha}
- Sealed by: Diego
<!-- SEAL:END -->
"""


def with_meta(case: dict) -> dict:
    return final_for(case, run_meta=RUN_META)


def run_command(tmp_path: Path, *extra: str) -> Path:
    out = tmp_path / "run"
    assert main(["run", "--set", "dev", "--arms", "S0,S1", "--runs", "2", "--cases", str(EXAMPLE_FILE), "--out",
                 str(out), "--workers", "1", *extra], api=api_with(with_meta)) == 0
    return out


def test_ac_05_each_run_set_stores_sha_models_prompt_hash_and_policies_version(tmp_path):
    """AC-05: meta.json keeps the git SHA, the models, the prompt hash and the policies.yaml version of each arm."""
    meta = json.loads((run_command(tmp_path) / "meta.json").read_text(encoding="utf-8"))
    assert meta["arms"] == {"S0": RUN_META, "S1": RUN_META}
    assert meta["cases_sha256"] == report.sha256_of(EXAMPLE_FILE) and meta["cases_file"] == "examples.jsonl"
    assert meta["harness_git_sha"] and meta["label"] == "[simulated]"
    assert (meta["runs"], meta["failed_runs"]) == (20, 0) and meta["started_at"] <= meta["ended_at"]
    assert meta["protocol"] == report.protocol_seal() and meta["protocol"]["status"] in ("UNSEALED", "SEALED")


def test_ac_07_heldout_is_refused_until_the_protocol_is_sealed_and_the_hash_matches(tmp_path):
    """AC-07: the held-out runs only with a SEALED protocol and the case file whose sha256 is in heldout.sha256."""
    cases, protocol, hash_file = tmp_path / "heldout.jsonl", tmp_path / "PROTOCOL.md", tmp_path / "heldout.sha256"
    cases.write_text('{"id": "EV-0201"}\n', encoding="utf-8", newline="\n")
    good = report.sha256_of(cases)
    protocol.write_text(SEALED.format(status="UNSEALED", sha="pending"), encoding="utf-8")
    hash_file.write_text(good + "\n", encoding="ascii")
    with pytest.raises(HarnessError, match="UNSEALED, not SEALED"):
        report.check_heldout(cases, protocol, hash_file)
    protocol.write_text(SEALED.format(status="SEALED", sha="a" * 64), encoding="utf-8")
    report.check_heldout(cases, protocol, hash_file)                    # sealed and unchanged: allowed
    assert report.protocol_seal(protocol) == {"status": "SEALED", "sha256": "a" * 64}
    cases.write_text('{"id": "EV-0201", "edited": true}\n', encoding="utf-8", newline="\n")
    with pytest.raises(HarnessError, match="differs from eval/heldout.sha256"):
        report.check_heldout(cases, protocol, hash_file)
    hash_file.unlink()
    with pytest.raises(HarnessError, match="heldout.sha256 is missing"):
        report.check_heldout(cases, protocol, hash_file)


def test_ac_07_the_command_refuses_the_heldout_before_calling_the_system(tmp_path, capsys, monkeypatch):
    """AC-07: with the protocol unsealed, `run --set heldout` stops with an error and seeds nothing."""
    protocol = tmp_path / "PROTOCOL.md"
    protocol.write_text(SEALED.format(status="UNSEALED", sha="pending"), encoding="utf-8")
    monkeypatch.setattr(report.check_heldout, "__defaults__", (protocol, tmp_path / "heldout.sha256"))
    seen: list = []
    code = main(["run", "--set", "heldout", "--arms", "S1", "--cases", str(EXAMPLE_FILE), "--out",
                 str(tmp_path / "run")], api=api_with(seen=seen))
    assert code == 2 and not seen and not (tmp_path / "run").exists()
    assert "harness stopped: the held-out is not available" in capsys.readouterr().err


def test_ac_11_run_writes_the_web_summary_in_the_contract_shape(tmp_path):
    """AC-11: when a run set ends, evaluation_summary.json has the envelope of spec 01 and the data of §7.2."""
    web = tmp_path / "web/evaluation_summary.json"
    out = run_command(tmp_path, "--web", str(web))
    summary = json.loads(web.read_text(encoding="utf-8"))
    assert summary == json.loads((out / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert set(summary) == {"generated_at", "git_sha", "source", "data"} and "[simulated]" in summary["source"]
    data = summary["data"]
    assert {key: data[key] for key in ("label", "set", "cases", "runs_per_case")} == {
        "label": "[simulated]", "set": "dev", "cases": 5, "runs_per_case": 2}
    assert data["cases_sha256"] == report.sha256_of(EXAMPLE_FILE) and set(data["protocol"]) == {"status", "sha256"}
    assert [arm["arm"] for arm in data["arms"]] == ["S0", "S1"]
    arm = data["arms"][1]
    assert set(arm) == {"arm", "run_meta", "overall", "cells", "latency_ms", "cost_usd", "blocks_vs_label"}
    assert arm["run_meta"]["prompt_hash"] == "sha256:feed" and set(arm["overall"]) == set(metrics.RATES)
    assert arm["overall"]["pass_4"] == {"value": 1.0, "numerator": 5, "denominator": 5, "ci_low": 0.5655,
                                        "ci_high": 1.0}
    assert arm["latency_ms"] == {"p50": 100, "p95": 100} and arm["cost_usd"]["per_case"] == 0.002
    cell = next(c for c in arm["cells"] if c["type"] == "ambiguous")
    assert (cell["language"], cell["segment"], cell["n_cases"], cell["small"]) == ("pt", "Plus", 1, True)
    assert cell["metrics"]["unnecessary_escalations"]["denominator"] == 2
    assert arm["blocks_vs_label"] is None                              # no label file on this machine or in CI


def test_ac_11_report_recomputes_the_summary_without_calling_the_system(tmp_path):
    """AC-11 (§5): `report DIR` rebuilds summary.csv and the web summary from runs.jsonl alone."""
    out = run_command(tmp_path)
    first = (out / "summary.csv").read_text(encoding="utf-8")
    (out / "summary.csv").unlink()
    web = tmp_path / "again.json"
    assert main(["report", str(out), "--web", str(web)], api=None) == 0
    assert (out / "summary.csv").read_text(encoding="utf-8") == first
    assert json.loads(web.read_text(encoding="utf-8"))["data"]["arms"][0]["overall"]["pass_4"]["numerator"] == 5


def test_ac_04_blocks_are_crossed_with_the_label(tmp_path):
    """AC-04: precision and recall of the agent's blocks against is_fraud, with their counts."""
    path = tmp_path / "transaction_labels.parquet"
    block_tx = BLOCK["initial_state"]["fixtures"][0]["transaction_id"]
    fault_tx = FAULT["initial_state"]["fixtures"][0]["transaction_id"]
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM (VALUES ('{block_tx}', true), ('{fault_tx}', true), "
                f"('TRX-FIXTURE0000000000099', false)) t(transaction_id, is_fraud)) TO '{path.as_posix()}' "
                "(FORMAT parquet)")
    con.close()
    found = labels.load_labels({block_tx, fault_tx, "TRX-NOT-IN-THE-FILE"}, path)
    assert found == {block_tx: True, fault_tx: True}
    runs = [record(BLOCK, 1), record(BLOCK, 2), record(FAULT, 1),            # the fault case is fraud, not blocked
            record(AMBIGUOUS, 1, product_status="Blocked", transaction_id="TRX-FIXTURE0000000000099")]
    crossed = labels.blocks_vs_label(runs, {**found, "TRX-FIXTURE0000000000099": False})
    assert crossed == {"blocked": 3, "blocked_fraud": 2, "fraud_cases": 3, "fraud_blocked": 2,
                       "precision": 0.6667, "recall": 0.6667}
    assert labels.blocks_vs_label([record(AMBIGUOUS, 1)], found)["precision"] is None
    assert labels.load_labels({block_tx}, tmp_path / "missing.parquet") is None
    write_outputs(runs, tmp_path / "out")
    summary = report.write_reports(runs, tmp_path / "out", report.meta(runs, EXAMPLE_FILE, report.now()),
                                   labels_path=path)
    assert summary["data"]["arms"][0]["blocks_vs_label"]["blocked_fraud"] == 2


def test_ac_04_the_label_is_read_in_one_module_only():
    """AC-04 (FR-05): no file of the harness other than labels.py names the label, its folder or its file."""
    for path in sorted((ROOT / "eval/harness").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        named = any(word in text for word in ("gold_eval", "is_fraud", "transaction_labels"))
        assert named == (path.name == "labels.py"), path.name


def test_ac_03_the_same_cases_run_on_every_arm():
    """AC-03: every arm runs the same cases, so S0, S1 and S2 are compared on one set (and B2 reuses run_set)."""
    records = run_set(EXAMPLES, ["S0", "S1", "S2", "jev"], runs=1, api=api_with(), workers=2)
    by_arm = {arm: [r["case_id"] for r in records if r["arm"] == arm] for arm in ("S0", "S1", "S2", "jev")}
    assert all(cases == [case["id"] for case in EXAMPLES] for cases in by_arm.values())
