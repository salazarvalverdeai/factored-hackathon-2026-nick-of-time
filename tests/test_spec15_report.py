"""Spec 15 T5/T6: B1 metrics, the lean rule, the Pareto chart and the post-seal command (AC-03, AC-04, AC-07).
Fake provider only, no network (CLAUDE.md)."""
from __future__ import annotations

import json

import pytest

from eval.bench import __main__ as cli
from eval.bench import b1, chart, core, gate, report

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


def test_post_seal_command_refuses_the_test_split_while_unsealed(monkeypatch, tmp_path, capsys):
    """The single post-seal command: `--split test` refuses to run while eval/PROTOCOL.md is not SEALED."""
    monkeypatch.setattr(cli, "protocol_seal", lambda: {"status": "UNSEALED", "sha256": None})
    monkeypatch.setattr(b1, "run", lambda *a, **k: pytest.fail("no model may run"))
    assert cli.main(["--split", "test"]) == 2 and "UNSEALED" in capsys.readouterr().err


def test_post_seal_command_refuses_a_sealed_protocol_without_the_lead_tag(monkeypatch, capsys):
    """SEALED is not enough: the lead's `protocol-v1` tag must sit on the merged sealing commit."""
    assert cli.protocol_tagged("no-such-tag-15b") is False
    monkeypatch.setattr(cli, "protocol_seal", lambda: {"status": "SEALED", "sha256": "a" * 64})
    monkeypatch.setattr(cli, "protocol_tagged", lambda: False)
    monkeypatch.setattr(b1, "run", lambda *a, **k: pytest.fail("no model may run"))
    assert cli.main(["--split", "test"]) == 2 and "protocol-v1" in capsys.readouterr().err


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


def test_ac_10_es_pt_quality_is_written_by_the_run():
    """AC-10, D-012: `es_pt_quality` passes only for an arm the run measured above the macro-F1 floor in both
    languages; an arm it could not measure stays "not documented"."""
    arms = [a for a in core.load_arms() if a["id"] in ("haiku-4-5", "nova-pro", "jev")]
    rows = [measured("haiku-4-5", [True] * 100, 0.5), measured("nova-pro", [True] * 60 + [False] * 40, 0.9)]
    gate_rows = gate.gate_rows(arms, gate.load_evidence(), "2026-10-05")
    report.measured_quality(gate_rows, rows, "development run")
    verdicts = {g["arm"]: g["verdict"] for g in gate_rows if g["criterion"] == "es_pt_quality"}
    assert verdicts == {"haiku-4-5": "pass", "nova-pro": "fail", "jev": "not documented"}
