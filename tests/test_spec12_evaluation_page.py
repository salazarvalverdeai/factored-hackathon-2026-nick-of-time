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
