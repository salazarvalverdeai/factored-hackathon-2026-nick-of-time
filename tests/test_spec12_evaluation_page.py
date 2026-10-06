"""Spec 12 T3 — /evaluation: the [T] criteria are proven by node tests; this file keeps the CI coverage check honest.

The display logic is tested offline by `npm test` in apps/web (lib/evaluation.test.ts). These tests fail if those tests
lose their citations or if the code paths they cover disappear.
"""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "apps/web"
TEST_TS = (WEB / "lib/evaluation.test.ts").read_text(encoding="utf-8")
LIB_TS = (WEB / "lib/evaluation.ts").read_text(encoding="utf-8")
RESULTS_TSX = (WEB / "app/evaluation/results.tsx").read_text(encoding="utf-8")


def _titles_citing(ac: str) -> list[str]:
    return re.findall(rf'^test\("spec 12 {ac}:[^"]+"', TEST_TS, re.M)


def test_ac_04_pending_state_has_a_node_test_and_a_code_path():
    """AC-04: a missing result file gives "results pending" with what is missing; the node tests cite it."""
    assert len(_titles_citing("AC-04")) >= 2
    assert "results pending" in LIB_TS and "export function pending(" in LIB_TS
    assert "pending(" in RESULTS_TSX or "pending(" in (WEB / "app/evaluation/page.tsx").read_text(encoding="utf-8")


def test_ac_05_development_notice_has_node_tests_including_a_missing_protocol():
    """AC-05: the notice shows unless the run is the sealed held-out; a missing protocol counts as unsealed."""
    titles = _titles_citing("AC-05")
    assert len(titles) >= 2 and any("without a protocol" in t for t in titles)
    assert "protocol?.status" in LIB_TS and "development-notice" in RESULTS_TSX


def test_ac_06_rates_show_numerator_denominator_and_interval():
    """AC-06 ([U] for the page, [T] for the helper): rates go through rateParts, which carries n, N and the interval."""
    assert _titles_citing("AC-06")
    for part in ("numerator", "denominator", "ci_low", "ci_high"):
        assert part in LIB_TS
    assert "rateParts" in RESULTS_TSX or "rateText" in RESULTS_TSX
    assert "<table" in RESULTS_TSX or "<Table" in RESULTS_TSX


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def test_ac_10_as_is_panel_has_node_tests_and_a_code_path():
    """AC-10: the as-is vs with Nick of Time panel exists, is pending without a sealed run, and lib/panel.test.ts cites it."""
    panel_tests = _read("lib/panel.test.ts")
    assert len(re.findall(r'^test\("spec 12 AC-10:', panel_tests, re.M)) >= 3
    assert "panelState" in _read("lib/panel.ts") and "as-is-panel" in _read("app/evaluation/panel.tsx")
    assert "results pending" in _read("app/evaluation/panel.tsx")
    assert "AsIsPanel" in _read("app/evaluation/page.tsx")


def test_ac_11_explanations_detail_links_and_limitations_exist():
    """AC-11: node tests cite it; Explain, Limitations and the Detail links are in the code and the specs they point to exist."""
    assert len(_titles_citing("AC-11")) >= 3
    explain = _read("app/evaluation/explain.tsx")
    assert "export function Explain" in explain and "export function Limitations" in explain and "Detail" in explain
    page = _read("app/evaluation/page.tsx")
    assert "<Limitations" in page and "limitations(" in page and 'href="/agent"' in page
    sections = _read("app/evaluation/sections.tsx")
    assert all(f'detail="{key}"' in sections for key in ("benchmark", "classifier", "fraud"))
    assert 'detail="harness"' in RESULTS_TSX
    for path in ("specs/10-eval-harness.md", "specs/11-intent-classifier.md", "specs/15-model-benchmark.md", "specs/17-fraud-model.md", "eval/PROTOCOL.md"):
        assert f'"{path}"' in LIB_TS and (WEB.parents[1] / path).exists(), path
    assert "EVALUATION_DATA_DIR" in _read("README.md")
