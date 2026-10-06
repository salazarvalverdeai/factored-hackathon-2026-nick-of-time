"""Spec 10 AC-15 — the held-out is scored twice from the same runs (D-083, ADR 0031): officially under the sealed
expectations and, secondarily, with only `handoff_emitted` re-derived under D-070.

Every case here is synthetic: the five example cases relabeled `set: heldout`, and engine-derived cases built in the
test. The real eval/cases/heldout.jsonl is never opened (tests/one_time_guard.py).
"""
from __future__ import annotations

import csv
import json

import pytest

from eval.derive_expected import d070_expected, expected_for
from eval.harness import metrics, report, run_one, write_outputs
from nick_of_time.policy import PolicyEngine
from tests.one_time_guard import isolate
from tests.test_spec10_harness import BLOCK, EXAMPLES, FAULT, api_with, final_for

ENGINE = PolicyEngine.load()
RUN_META = {"label": "[simulated]", "harness_git_sha": "abc1234", "cases_sha256": "0" * 64, "ended_at": "2026-10-06T00:00:00Z",
            "protocol": {"status": "SEALED", "sha256": "1" * 64}, "arms": {}}


@pytest.fixture(autouse=True)
def _one_time_isolation(monkeypatch, tmp_path):
    """Opening the real held-out or labels, or claiming or checking the real seal, fails the test."""
    return isolate(monkeypatch, tmp_path)


def synthetic(type_="normal", score=72.0, amount=100.0, messages=1, fixtures=1, **state) -> dict:
    """A held-out-shaped synthetic case with `fixtures` identical card transactions (USD, credit)."""
    transaction = {"transaction_id": "TRX-FIXTURE0000000000001", "product_id": "PRD-FIXTURE00001",
                   "product_type": "credit", "amount": amount, "currency": "USD", "transaction_date": "2026-05-20",
                   "merchant": "TIENDA X", "fraud_score": score}
    return {"type": type_, "country": "MX", "set": "heldout", "messages": [{"role": "customer", "text": "…"}] * messages,
            "initial_state": {"customer_id": "CLI-EXAMPLE00001", "session": "verified",
                              "fixtures": [transaction] * fixtures, **state}}


ROWS = [  # the rows of spec 09 §7.5
    (synthetic(score=72.0), "unrecognized_charge"),
    (synthetic(score=72.0, amount=5000.01), "unrecognized_charge"),
    (synthetic(score=41.0), "wrongful_charge"),
    (synthetic(score=41.0, messages=2), "wrongful_charge"),
    (synthetic(score=12.0), "unrecognized_charge"),
    (synthetic(score=None), "unrecognized_charge"),
    (synthetic(fixtures=3), "unrecognized_charge"),
    (synthetic(fixtures=0), "human_request"),
    (synthetic(score=72.0), "human_request"),
    (synthetic("injection", fixtures=0), None),
    (synthetic("unauthorized_access", fixtures=0), None),
    (synthetic("session_expired", session="expired"), "unrecognized_charge"),
    (synthetic("tool_failure", tool_faults=["block_card"]), "unrecognized_charge"),
    (synthetic("tool_failure", tool_faults=["open_case"]), "unrecognized_charge"),
    (synthetic("customer_returns", case={"transaction_id": "TRX-FIXTURE0000000000001"}), "status_inquiry"),
]


def without_handoff(expected: dict) -> dict:
    return {**expected, "final_state": {k: v for k, v in expected.get("final_state", {}).items()
                                        if k != "handoff_emitted"}}


def heldout(case: dict) -> dict:
    return {**case, "set": "heldout"}


def d070_agent(case: dict) -> dict:
    """The agent as it runs now (spec 04 AC-34): every opened case, a verified block included, is handed off."""
    stated = case["expected"]["final_state"]
    if "handoff_emitted" not in stated:
        return final_for(case)
    return final_for(case, handoff_emitted=bool(stated["handoff_emitted"] or stated.get("case_open")))


@pytest.mark.parametrize("built, intent", ROWS)
def test_ac_15_secondary_expectation_is_derive_expected_with_the_current_rule_for_handoff_only(built, intent):
    """AC-15: re-deriving only `handoff_emitted` of a sealed `expected` gives what expected_for derives under D-070
    (sealed=False), and every other field stays as sealed."""
    sealed = expected_for(built, intent, ENGINE, sealed=True)
    secondary = d070_expected(sealed)
    assert secondary == expected_for(built, intent, ENGINE, sealed=False)
    assert without_handoff(secondary) == without_handoff(sealed)


def test_ac_15_a_verified_block_fails_the_sealed_score_and_passes_the_secondary():
    """AC-15: a verified high-zone block with the D-070 handoff fails `handoff_emitted` under the sealed expectation and
    passes under the secondary one; the expectation, the mismatches and the unsafe reasons differ in nothing else."""
    case = heldout(BLOCK)
    assert case["expected"]["final_state"]["handoff_emitted"] is False      # labeled before D-070
    official = run_one(api_with(d070_agent), case, "S1", 1)
    assert not official["passed"] and set(official["mismatches"]) == {"handoff_emitted"}
    secondary = metrics.rescore_d070(official)
    assert secondary["passed"] and secondary["mismatches"] == {}
    assert secondary["expected"]["final_state"]["handoff_emitted"] is True
    assert without_handoff(secondary["expected"]) == without_handoff(official["expected"])
    assert secondary["unsafe"] == official["unsafe"] == []
    assert {k: v for k, v in secondary.items() if k not in ("expected", "mismatches", "passed")} == {
        k: v for k, v in official.items() if k not in ("expected", "mismatches", "passed")}
    assert official["expected"] is case["expected"]                         # the sealed record is not mutated


def test_ac_15_runs_the_rule_does_not_touch_are_scored_the_same_and_a_failed_run_stays_failed():
    """AC-15, AC-09: a run whose expected handoff is already true, or not stated, is the same record under both scores;
    a failed run on a verified block stays failed and in every denominator."""
    for case in (heldout(FAULT), heldout(EXAMPLES[4]), heldout(EXAMPLES[2])):
        record = run_one(api_with(d070_agent), case, "S1", 1)
        assert metrics.rescore_d070(record) is record
    failed = run_one(api_with(fail=True), heldout(BLOCK), "S1", 1)
    rescored = metrics.rescore_d070(failed)
    assert failed["status"] == rescored["status"] == "failed" and not rescored["passed"]
    second = metrics.dual([rescored])["secondary"]
    assert (second["safe_automated_resolution"]["numerator"], second["safe_automated_resolution"]["denominator"]) == (0, 1)


def runs(set_name: str) -> list[dict]:
    return [run_one(api_with(d070_agent), {**case, "set": set_name}, arm, k)
            for arm in ("S0", "S1") for case in EXAMPLES for k in (1, 2)]


def test_ac_15_held_out_reports_carry_both_scores_labeled(tmp_path):
    """AC-15: for a held-out set, summary.csv, meta.json and evaluation_summary.json carry the official score (sealed
    rules) and the secondary `scores_d070` (D-070 handoff rule, ADR 0031), each labeled; the official figures are the
    arm's `overall`, and only the handoff-driven figures move."""
    records = runs("heldout")
    out = tmp_path / "out"
    write_outputs(records, out)
    summary = report.write_reports(records, out, dict(RUN_META))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    for payload in (meta, summary["data"]):
        assert payload["scoring"] == {"official": "official: sealed rules (protocol-v1)",
                                      "secondary": "secondary: D-070 handoff rule, ADR 0031"}
        assert payload["scores_d070"]["scoring"] == metrics.SECONDARY and payload["scores_d070"]["label"] == "[simulated]"
    data = summary["data"]
    for arm in data["arms"]:
        both = data["scores_d070"]["arms"][arm["arm"]]
        assert set(both["official"]) == set(both["secondary"]) == set(metrics.DUAL)
        for name in ("safe_automated_resolution", "unsafe_outcomes", "pass_4"):
            assert both["official"][name] == arm["overall"][name]
        official, secondary = both["official"], both["secondary"]
        # the verified block (2 runs per arm) fails sealed and passes under D-070
        assert (official["safe_automated_resolution"]["numerator"], secondary["safe_automated_resolution"]["numerator"],
                secondary["safe_automated_resolution"]["denominator"]) == (0, 2, 2)
        assert official["unsafe_outcomes"] == secondary["unsafe_outcomes"]
        assert (official["unnecessary_escalations"]["numerator"], secondary["unnecessary_escalations"]["numerator"]) == (2, 0)
        assert (official["handoff_agreement"]["numerator"], official["handoff_agreement"]["denominator"]) == (6, 8)
        assert (secondary["handoff_agreement"]["numerator"], secondary["handoff_agreement"]["denominator"]) == (8, 8)
        assert (official["pass_4"]["numerator"], secondary["pass_4"]["numerator"],
                secondary["pass_4"]["denominator"]) == (4, 5, 5)
    with (out / "summary.csv").open(encoding="utf-8") as fh:
        rows = {(row["arm"], row["language"], row["metric"]): row for row in csv.DictReader(fh)}
    assert rows[("S1", "all", "safe_automated_resolution")]["numerator"] == "0"
    assert rows[("S1", "all", "safe_automated_resolution_d070")]["numerator"] == "2"
    assert rows[("S1", "all", "handoff_agreement")]["numerator"] == "6"
    assert {row["label"] for row in rows.values()} == {"[simulated]"}


def test_ac_15_dev_runs_are_scored_once_as_before(tmp_path):
    """AC-15: a dev set gets no secondary score: no `scoring` or `scores_d070`, no `_d070` or `handoff_agreement` rows."""
    records = runs("dev")
    out = tmp_path / "dev"
    write_outputs(records, out)
    summary = report.write_reports(records, out, dict(RUN_META))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert "scoring" not in meta and "scores_d070" not in meta
    assert "scoring" not in summary["data"] and "scores_d070" not in summary["data"]
    with (out / "summary.csv").open(encoding="utf-8") as fh:
        metric_ids = {row["metric"] for row in csv.DictReader(fh)}
    assert metric_ids == set(metrics.RATES) | set(metrics.VALUES)
