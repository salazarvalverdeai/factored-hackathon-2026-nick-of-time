"""Spec 15 T5/T6: B1 metrics, the lean rule, the Pareto chart and the development command (AC-03, AC-04, AC-07).
Fake provider only, no network (CLAUDE.md). The one-time test-split command is covered in test_spec15_guard.py on a
throwaway repository: no test here reaches the real seal guard or the real test split."""
from __future__ import annotations

import json
import re

import pytest

from eval.bench import __main__ as cli
from eval.bench import b1, chart, core, gate, report


@pytest.fixture(autouse=True)
def never_the_real_test_split(monkeypatch, tmp_path):
    """Safety net: the command never sees the real repository (so the real seal guard can never pass and claim the
    one-time run) and the real test split is never read."""
    monkeypatch.setattr(cli, "ROOT", tmp_path / "not-a-repo")
    real = b1.load_split

    def load(split, *a, **k):
        if split == "test":
            pytest.fail("the real test split must never be read by a test")
        return real(split, *a, **k)
    monkeypatch.setattr(b1, "load_split", load)


ROWS = [{"id": f"V{i}", "language": lang, "intent": intent, "text": text, "slots": {"amount": "45", "date": None}}
        for i, (lang, intent, text) in enumerate([
            ("es", "unrecognized_charge", "No reconozco un cargo de 45 dólares en mi tarjeta."),
            ("es", "human_request", "Quiero hablar con una persona."),
            ("pt", "unrecognized_charge", "Não reconheço uma cobrança de 45 reais no meu cartão."),
            ("pt", "status_inquiry", "Como está o meu caso?")])]


def test_ac_03_metrics_are_rate_objects_with_wilson_ci_latency_and_cost():
    items = [{"id": str(i), "language": "es", "gold": g, "pred": p, "gold_slots": {"amount": "10"},
              "pred_slots": {"amount": "10.00"}, "tool_call": True, "latency_ms": ms, "tokens_in": 0,
              "tokens_out": 0, "cost_usd": 0.001}
             for i, (g, p, ms) in enumerate([("human_request", "human_request", 100), ("out_of_scope", "out_of_scope", 200),
                                             ("human_request", "out_of_scope", 300), ("wrongful_charge", "wrongful_charge", 400)])]
    m = report.arm_metrics({"items": items})
    assert m["accuracy"] == report.rate(3, 4) and m["accuracy"]["ci_low"] < 0.75 < m["accuracy"]["ci_high"]
    assert m["macro_f1"]["es"] == pytest.approx(round((2 / 3 + 2 / 3 + 1) / 3, 4))
    assert m["human_request_recall"]["value"] == 0.5 and m["slot_accuracy"]["value"] == 1.0
    assert (m["p50_ms"], m["p95_ms"], m["cost_per_1000_usd"]) == (200, 400, 1.0)


def measured(arm, correct, cost, p95=100):
    other = {"unrecognized_charge": "human_request", "human_request": "unrecognized_charge"}
    items = [{"id": str(i), "language": lang, "gold": intent, "pred": intent if ok else other[intent],
              "gold_slots": {}, "pred_slots": {}, "tool_call": True, "latency_ms": p95, "tokens_in": 0, "tokens_out": 0,
              "cost_usd": cost / 1000}
             for i, (ok, lang, intent) in enumerate(zip(correct, ["es", "es", "pt", "pt"] * 100,
                                                         ["unrecognized_charge", "human_request"] * 200))]
    row = {"arm": arm, "status": "ok", "items": items}
    return {**row, "metrics": report.arm_metrics(row)}


def test_ac_07_mcnemar_is_exact_and_paired():
    assert report.mcnemar([True] * 10, [True] * 10) == 1.0
    assert report.mcnemar([True] * 6, [False] * 6) == pytest.approx(2 / 64)


def test_ac_07_lean_rule_picks_the_cheapest_arm_not_significantly_worse_that_passes_the_gate():
    """AC-07, PROTOCOL §2.3: hard limits, McNemar bar against the best, cheapest, then the production gate."""
    best = measured("sonnet-4-6", [True] * 100, 1.5)
    close = measured("nova-lite", [True] * 99 + [False], 0.03)
    cheap = measured("nova-micro", [True] * 98 + [False] * 2, 0.01)
    weak = measured("b0_rules", [True] * 60 + [False] * 40, 0.0)
    rows = [best, close, cheap, weak]
    mm = report.select(rows, {"sonnet-4-6": True, "nova-lite": True, "nova-micro": False})
    assert mm["best_measured"] == "sonnet-4-6" and mm["cheapest_meeting_bar"] == "nova-micro"
    assert mm["chosen"] == "nova-lite" and any("nova-micro" in n for n in mm["notes"])
    assert weak["meets_bar"] is False and weak["hard_limits_failed"] and weak["pareto"] is True
    assert best["pareto"] and close["pareto"] and cheap["pareto"]


def test_ac_07_rule_5_b0_stays_when_no_llm_arm_beats_it():
    rows = [measured("b0_rules", [True] * 50 + [False] * 50, 0.0), measured("haiku-4-5", [True] * 52 + [False] * 48, 0.5)]
    assert report.select(rows, {"haiku-4-5": True})["chosen"] == "b0_rules"


def test_ac_04_chart_has_one_point_per_measured_arm_and_labels_the_frontier():
    rows = [measured("b0_rules", [True] * 60 + [False] * 40, 0.0), measured("haiku-4-5", [True] * 100, 0.5),
            measured("nova-pro", [True] * 90 + [False] * 10, 0.9), {"arm": "jev", "status": "unavailable"}]
    report.select(rows, {})
    out = chart.svg(rows, "[simulated] test")
    assert out.count("<circle") == 3 + 2 and "haiku-4-5 · p95" in out and "nova-pro · p95" not in out
    assert "[simulated]" in out and "<title>nova-pro: accuracy 0.9" in out


def test_ac_01_test_split_refuses_limits_arms_and_the_fake_provider(monkeypatch, capsys):
    """AC-01: the test split runs once, whole, on Bedrock; a partial or fake run is refused before the guard."""
    monkeypatch.setattr(cli, "check_test_seal", lambda: pytest.fail("refused before the guard"))
    for extra in (["--limit", "2"], ["--arms", "b0_rules"], ["--provider", "fake"]):
        assert cli.main(["--split", "test", *extra]) == 2 and "refused" in capsys.readouterr().err


def test_dev_run_writes_only_git_ignored_files_labeled_as_development(monkeypatch, tmp_path):
    """A validation run never writes a result path of the seal guard; its export carries the §7.1 keys."""
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "generator", lambda split: "google.gemma-3-27b-it")
    monkeypatch.setattr(b1, "load_split", lambda split: ROWS)
    arms = [a for a in core.load_arms() if a["id"] in ("b0_rules", "nova-micro", "gemma-3-12b")]
    monkeypatch.setattr(core, "load_arms", lambda: arms)
    assert cli.main(["--split", "validation", "--provider", "fake"]) == 0
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files and all(p.relative_to(tmp_path).parts[:3] == ("eval", ".runs", "bench") for p in files)
    data = json.loads(next(p for p in files if p.name == "benchmark.json").read_text())["data"]
    assert data["run_kind"] == cli.DEV_LABEL and data["mode"] == "replay" and data["label"] == "[simulated]"
    arm = next(a for a in data["b1"]["arms"] if a["arm"] == "gemma-3-12b")
    assert arm["same_family_as_generator"] is True and arm["gate"]["criteria"]
    assert {"macro_f1", "macro_f1_ci", "dispute_recall", "missing_tool_calls", "p95_ms", "cost_per_1000_usd",
            "meets_bar", "pareto", "tool_choice_mode", "temperature", "price"} <= set(arm)
    assert set(data["model_map"]["understand"]) >= {"best_measured", "cheapest_meeting_bar", "chosen"}
    assert "test_review" not in data and data["protocol"] == cli.protocol_seal()      # dev runs: no guard, no claim
    items = next(p for p in files if p.name == "bench_b1_items.jsonl").read_text().splitlines()
    assert len(items) == len(ROWS) * len(arms)                                         # streamed once, not rewritten
    table = next(p for p in files if p.name == "bench_b1.md").read_text()
    assert "## Model map" in table and "[assumption] D-077 pending" in table and "| Errors |" in table
    assert cli.main(["--split", "validation", "--provider", "fake"]) == 0              # a dev rerun starts fresh
    assert len(next(p for p in files if p.name == "bench_b1_items.jsonl").read_text().splitlines()) == len(items)


def test_ac_10_es_pt_quality_is_written_by_the_run():
    """AC-10, D-012: `es_pt_quality` passes only for an arm the run measured above the macro-F1 floor in both
    languages; an arm it could not measure stays "not documented"."""
    arms = [a for a in core.load_arms() if a["id"] in ("haiku-4-5", "nova-pro", "jev")]
    rows = [measured("haiku-4-5", [True] * 100, 0.5), measured("nova-pro", [True] * 60 + [False] * 40, 0.9)]
    gate_rows = gate.gate_rows(arms, gate.load_evidence(), "2026-10-05")
    report.measured_quality(gate_rows, rows, "development run")
    verdicts = {g["arm"]: g["verdict"] for g in gate_rows if g["criterion"] == "es_pt_quality"}
    assert verdicts == {"haiku-4-5": "pass", "nova-pro": "fail", "jev": "not documented"}


def cells(n: int, wrong: set[int]) -> list[bool]:
    return [i not in wrong for i in range(n)]


def correct_of(row: dict) -> list[bool]:
    return [i["pred"] == i["gold"] for i in row["items"]]


def test_ac_07_rule_2_best_arm_is_taken_among_arms_that_pass_rule_1_by_default():
    """AC-07, [assumption] D-077 pending: under the recommended reading the bar of rule 2 is set by the best arm that
    passes rule 1 (spec 11 §4, "among the rest"); flipping SELECTION_READING compares with the best of every arm."""
    def rows():
        return [measured("sonnet-4-6", [True] * 400, 5.0, p95=2000),           # most accurate, fails the p95 limit
                measured("nova-lite", cells(400, set(range(8))), 0.06),          # passes rule 1, 8 errors
                measured("b0_rules", [True] * 240 + [False] * 160, 0.0)]
    production = {"sonnet-4-6": True, "nova-lite": True}
    mm = report.select(rows(), production)
    assert report.SELECTION_READING == "among_passing" and mm["reading"] == "among_passing"
    assert (mm["best_measured"], mm["bar_reference"], mm["chosen"], mm["chosen_by"]) == (
        "sonnet-4-6", "nova-lite", "nova-lite", "rules 1-4")
    assert mm["reading_label"].startswith("[assumption] D-077 pending")
    other = report.select(rows(), production, reading="all_measured")
    assert other["bar_reference"] == "sonnet-4-6" and other["cheapest_meeting_bar"] is None
    assert other["chosen"] == "b0_rules" and other["chosen_by"].startswith("[assumption]")
    with pytest.raises(ValueError):
        report.select(rows(), production, reading="nope")


def test_ac_07_every_arm_failing_rule_1_falls_back_to_b0_and_says_so():
    """AC-07: §2.3 is silent when every arm fails the hard limits; B0 stays, labeled [assumption] in chosen_by."""
    rows = [measured("sonnet-4-6", [True] * 400, 5.0, p95=2000), measured("b0_rules", [True] * 240 + [False] * 160, 0.0)]
    mm = report.select(rows, {"sonnet-4-6": True})
    assert mm["chosen"] == "b0_rules" and mm["refused"] is False
    assert mm["chosen_by"].startswith("[assumption]") and "every measured arm fails rule 1" in mm["chosen_by"]


def test_ac_07_no_measured_arm_refuses_instead_of_naming_b0():
    """AC-07: with no arm measured the rule names no arm (chosen "none", refused) rather than an unmeasured B0."""
    mm = report.select([{"arm": "jev", "status": "unavailable", "items": []},
                        {"arm": "b0_rules", "status": "unavailable", "items": []}], {})
    assert mm["chosen"] == "none" and mm["refused"] is True and mm["chosen_by"].startswith("refused")


def test_ac_07_rule_5_reads_no_llm_arm_beats_b0_as_written():
    """AC-07, PROTOCOL §2.3 rule 5: B0 stays only when NO LLM arm beats it; a cheap arm that meets the bar is kept
    when another LLM arm beats B0, even if the cheap arm alone does not."""
    sonnet = measured("sonnet-4-6", [True] * 400, 5.0)
    nova = measured("nova-lite", cells(400, {0, 29, 2, 3}), 0.06)              # one error per cell: passes rule 1
    b0 = measured("b0_rules", cells(400, {1, 5, 9, 13, 17, 21, 25}), 0.0)      # es human_request recall 0.93: fails
    assert report.mcnemar(correct_of(b0), correct_of(nova)) >= report.ALPHA      # nova-lite alone does not beat B0
    assert report.mcnemar(correct_of(b0), correct_of(sonnet)) < report.ALPHA     # sonnet-4-6 does
    mm = report.select([sonnet, nova, b0], {"sonnet-4-6": True, "nova-lite": True})
    assert (mm["chosen"], mm["chosen_by"]) == ("nova-lite", "rules 1-4")


def test_ac_03_failed_sentences_are_errors_not_missing_tool_calls():
    """AC-03, AC-06: a sentence whose call failed is wrong and counted in `errors` (with its class in the table),
    and not counted again in `missing_tool_calls`."""
    base = {"language": "es", "gold": "human_request", "gold_slots": {}, "latency_ms": 10, "tokens_in": 0,
            "tokens_out": 0, "cost_usd": 0.0}
    items = [{**base, "id": "1", "pred": None, "pred_slots": {}, "tool_call": False, "latency_ms": None,
              "error": "ThrottlingException: slow down"},
             {**base, "id": "2", "pred": None, "pred_slots": {}, "tool_call": False, "error": None},
             {**base, "id": "3", "pred": "human_request", "pred_slots": {}, "tool_call": True, "error": None}]
    row = {"arm": "haiku-4-5", "status": "ok", "items": items, "errors": {"ThrottlingException": 1}}
    row["metrics"] = m = report.arm_metrics(row)
    assert (m["errors"], m["missing_tool_calls"], m["accuracy"]["numerator"]) == (1, 1, 1)
    line = next(x for x in report.table([row]).splitlines() if x.startswith("| haiku-4-5"))
    assert "| 1 | 1 (ThrottlingException 1) |" in line


def test_ac_03_jev_slot_accuracy_is_not_applicable():
    """AC-03: Jev answers the intent only, so its slot accuracy is an empty rate (n/a), not 0."""
    items = [{"id": "1", "language": "pt", "gold": "unrecognized_charge", "pred": "unrecognized_charge",
              "gold_slots": {"amount": "45"}, "pred_slots": {}, "tool_call": True, "latency_ms": 5, "tokens_in": 1,
              "tokens_out": 0, "cost_usd": 0.0, "error": None}]
    jev = {"arm": "jev", "status": "ok", "items": items}
    jev["metrics"] = report.arm_metrics(jev)
    assert jev["metrics"]["slot_accuracy"] == report.rate(0, 0) and jev["metrics"]["slot_accuracy"]["value"] is None
    assert "| n/a |" in report.table([jev])
    assert report.arm_metrics({"arm": "haiku-4-5", "items": items})["slot_accuracy"]["value"] == 0.0


def test_ac_04_chart_uses_only_brand_tokens():
    """AC-04: the SVG uses the BRAND.md §6 colors only (Surface, Slate, Violet, White)."""
    rows = [measured("b0_rules", [True] * 60 + [False] * 40, 0.0), measured("haiku-4-5", [True] * 100, 0.5)]
    report.select(rows, {})
    colors = set(re.findall(r"#[0-9A-Fa-f]{6}", chart.svg(rows, "[simulated] x")))
    assert colors <= {"#111827", "#94A3B8", "#7C3AED", "#FFFFFF"}


def test_ac_04_chart_and_table_re_render_from_items_without_any_model_call(monkeypatch, tmp_path):
    """AC-04: `--from-items` rebuilds the table and the chart from a scored-items JSONL; no model is called."""
    monkeypatch.setattr(cli, "generator", lambda split: "google.gemma-3-27b-it")
    monkeypatch.setattr(b1, "run", lambda *a, **k: pytest.fail("no model may run"))
    lines = [{"arm": r["arm"], **i} for r in (measured("b0_rules", [True] * 60 + [False] * 40, 0.0),
                                              measured("haiku-4-5", [True] * 100, 0.5)) for i in r["items"]]
    lines[0]["error"] = "ThrottlingException: x"
    src = tmp_path / "bench_b1_items.jsonl"
    src.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    out = tmp_path / "out"
    assert cli.main(["--split", "validation", "--from-items", str(src), "--out", str(out)]) == 0
    table = (out / "bench_b1.md").read_text(encoding="utf-8")
    assert "re-rendered from bench_b1_items.jsonl" in table and "Chosen: `" in table
    assert "ThrottlingException 1" in table and "D-077" in table
    assert "haiku-4-5 · p95" in (out / "benchmark_cost_quality.svg").read_text(encoding="utf-8")


def test_ac_05_run_date_comes_from_the_replay_clock(monkeypatch):
    """AC-05, AC-09, ADR 0020: B1 runs in replay, so its run date is DEMO_TODAY, never the system date."""
    monkeypatch.setenv("DEMO_TODAY", "2026-05-15")
    assert cli.run_date() == "2026-05-15"
    monkeypatch.delenv("DEMO_TODAY")
    assert cli.run_date() == "2026-06-01"


def test_ac_07_dev_run_with_no_measured_arm_refuses_to_choose(monkeypatch, tmp_path, capsys):
    """AC-07: when no arm was measured the command writes its record and exits non-zero, naming no model map."""
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "generator", lambda split: None)
    monkeypatch.setattr(b1, "load_split", lambda split: ROWS)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    jev = [a for a in core.load_arms() if a["id"] == "jev"]
    monkeypatch.setattr(core, "load_arms", lambda: jev)
    assert cli.main(["--split", "validation", "--provider", "fake"]) == 3
    assert "refused to choose" in capsys.readouterr().err
