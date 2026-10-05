"""Spec 10 T3, T4, T5 — run metadata, the web summary, the held-out guard and the blocks-against-label report."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import duckdb
import pytest

from eval.harness import Api, HarnessError, labels, metrics, report, run_set, write_outputs
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


def test_ac_11_run_writes_the_web_summary_in_the_contract_shape(tmp_path, monkeypatch):
    """AC-11: when a run set ends, evaluation_summary.json has the envelope of spec 01 and the data of §7.2."""
    monkeypatch.setattr(labels, "LABELS", tmp_path / "no-labels.parquet")    # as in CI, even where labels are pulled
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
    assert set(arm) == {"arm", "run_meta", "overall", "cells", "latency_ms", "cost_usd", "blocks_vs_label",
                        "second_turn_recovery"}
    assert arm["second_turn_recovery"] is None and data["variant_cases"] == 0     # AC-13: no recovery variant here
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


def sealed_heldout(tmp_path: Path, monkeypatch, status: str = "SEALED") -> Path:
    """A held-out file of the five examples, hashed, with a protocol in `status`; the guard's paths point at it."""
    cases, protocol, hash_file = tmp_path / "heldout.jsonl", tmp_path / "PROTOCOL.md", tmp_path / "heldout.sha256"
    cases.write_text("".join(json.dumps({**case, "set": "heldout"}, ensure_ascii=False) + "\n" for case in EXAMPLES),
                     encoding="utf-8", newline="\n")
    protocol.write_text(SEALED.format(status=status, sha="a" * 64), encoding="utf-8")
    hash_file.write_text(report.sha256_of(cases) + "\n", encoding="ascii")
    for name, path in (("PROTOCOL", protocol), ("HELDOUT_HASH", hash_file), ("HELDOUT_CASES", cases)):
        monkeypatch.setattr(report, name, path)
    return cases


def test_ac_07_run_set_itself_refuses_heldout_cases_before_the_seal(tmp_path, monkeypatch):
    """AC-07 (FR-06): spec 15 calls run_set directly, so the guard runs there too and seeds nothing when refused."""
    seen: list = []
    heldout = [{**case, "set": "heldout"} for case in EXAMPLES]
    with pytest.raises(HarnessError, match="UNSEALED, not SEALED|differ from the sealed file"):   # repo protocol
        run_set(heldout, ["S1"], runs=1, api=api_with(seen=seen))
    sealed_heldout(tmp_path, monkeypatch, status="UNSEALED")
    with pytest.raises(HarnessError, match="UNSEALED, not SEALED"):
        run_set(heldout[:1], ["S1"], runs=1, api=api_with(seen=seen))
    assert not seen
    assert len(run_set(EXAMPLES, ["S1"], runs=1, api=api_with())) == 5       # dev cases need no seal


def test_ac_07_run_set_runs_only_the_sealed_heldout_as_sealed(tmp_path, monkeypatch):
    """AC-07: once sealed, held-out cases run only when the file matches its hash and each case matches the file."""
    cases = sealed_heldout(tmp_path, monkeypatch)
    heldout = [json.loads(line) for line in cases.read_text(encoding="utf-8").splitlines()]
    assert all(r["status"] == "ok" for r in run_set(heldout, ["S1"], runs=1, api=api_with()))
    edited = [{**heldout[0], "messages": [{"text": "otro texto"}]}, *heldout[1:]]
    seen: list = []
    with pytest.raises(HarnessError, match="differ from the sealed file: EV-0001"):
        run_set(edited, ["S1"], runs=1, api=api_with(seen=seen))
    cases.write_text(cases.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(HarnessError, match="differs from eval/heldout.sha256"):
        run_set(heldout, ["S1"], runs=1, api=api_with(seen=seen))
    cases.unlink()
    with pytest.raises(HarnessError, match="case file .* is missing"):
        run_set(heldout, ["S1"], runs=1, api=api_with(seen=seen))
    assert not seen


def test_ac_07_a_missing_case_file_stops_the_command_with_an_error(tmp_path, capsys):
    """AC-07: a missing --cases file is a HarnessError (exit 2), not a traceback."""
    code = main(["run", "--set", "dev", "--arms", "S1", "--cases", str(tmp_path / "nope.jsonl"), "--out",
                 str(tmp_path / "run")], api=api_with())
    assert code == 2 and "the case file" in capsys.readouterr().err and not (tmp_path / "run").exists()


def test_ac_11_a_finished_run_folder_is_never_overwritten(tmp_path, capsys):
    """AC-11 (§7.1): a second run into a folder that holds a run stops before calling the system."""
    out = run_command(tmp_path)
    before = (out / "runs.jsonl").read_text(encoding="utf-8")
    seen: list = []
    code = main(["run", "--set", "dev", "--arms", "S1", "--runs", "1", "--cases", str(EXAMPLE_FILE), "--out", str(out)],
                api=api_with(seen=seen))
    assert code == 2 and not seen and "already holds a run" in capsys.readouterr().err
    assert (out / "runs.jsonl").read_text(encoding="utf-8") == before


def test_ac_05_run_meta_flags_drift_between_runs_of_one_arm(capsys):
    """AC-05: if the system under test changes during a run set, meta.json says which fields changed."""
    later = {**RUN_META, "git_sha": "def5678", "prompt_hash": "sha256:beef"}
    runs = [record(BLOCK, 1, run_meta=RUN_META), record(BLOCK, 2, run_meta=later), record(AMBIGUOUS, 1, run_meta=later)]
    meta = report.meta(runs, EXAMPLE_FILE, report.now())
    assert meta["arms"]["S1"] == {**RUN_META, "drift": {"git_sha": ["abc1234", "def5678"],
                                                         "prompt_hash": ["sha256:feed", "sha256:beef"]}}
    steady = report.meta([record(BLOCK, 1, run_meta=RUN_META), record(BLOCK, 2, run_meta=RUN_META)], EXAMPLE_FILE,
                         report.now())
    assert steady["arms"]["S1"] == RUN_META


def test_ac_02_summary_rows_carry_the_label_the_set_and_pass_k(tmp_path, capsys):
    """AC-02 (§5 Honesty): every summary.csv row says [simulated] and its set; the headline names pass^k for --runs."""
    out = run_command(tmp_path)
    with (out / "summary.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows and {(row["label"], row["set"]) for row in rows} == {("[simulated]", "dev")}
    printed = capsys.readouterr().out
    assert "pass^2 5/5" in printed and "pass_4" not in printed and metrics.runs_per_case(
        [record(BLOCK, k) for k in (1, 2, 3)]) == 3


def test_ac_12_run_set_closes_the_client_it_opens(monkeypatch):
    """AC-12: with `api_url`, run_set opens its own client and closes it when the set ends."""
    opened: list[Api] = []

    def at(base_url: str) -> Api:
        api = api_with()
        opened.append(api)
        return api

    monkeypatch.setattr(Api, "at", staticmethod(at))
    run_set(EXAMPLES[:1], ["S1"], runs=1, api_url="http://eval.test")
    assert len(opened) == 1 and opened[0].http.is_closed
    given = api_with()
    run_set(EXAMPLES[:1], ["S1"], runs=1, api=given)
    assert not given.http.is_closed                                      # a client the caller gave stays open


def test_ac_01_make_eval_runs_the_dev_set_on_s0_and_s1():
    """AC-01 (T6, §6): `make eval` runs the dev set on S0 and S1 against the local api; never the held-out."""
    import shutil
    import subprocess
    if not shutil.which("make"):
        pytest.skip("make is not installed")
    dry = subprocess.run(["make", "-n", "eval"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert "-m eval.harness run --set dev --arms S0,S1 --runs 4 --api http://localhost:8000" in dry
    assert "heldout" not in dry and "--cases" not in dry
    other = subprocess.run(["make", "-n", "eval", "EVAL_CASES=eval/examples.jsonl", "EVAL_RUNS=2"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout
    assert "--runs 2" in other and "--cases eval/examples.jsonl" in other
