"""Spec 12 Q1 — specs 11, 15 and 17 fix the `data` shape of the three /evaluation result files.

Supporting evidence for spec 12 AC-01 (whose own evidence is [U]): the shapes the page is built on are well formed.

The JSON examples in "7.1 Web export shape" must parse, describe `data` only (the envelope of spec 01 §6.2 is added by
the exporter) and carry the protocol status/hash that AC-04 and AC-05 need. No result file may exist yet: eval/PROTOCOL.md
treats them as results (spec 12 §7.1, "No placeholder result files").
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHAPES = {
    "specs/11-intent-classifier.md": "classifier.json",
    "specs/15-model-benchmark.md": "benchmark.json",
    "specs/17-fraud-model.md": "fraud_benchmark.json",
}
ENVELOPE = {"generated_at", "git_sha", "source"}


def _example(spec: str) -> dict:
    text = (ROOT / spec).read_text(encoding="utf-8")
    section = text.split("### 7.1 Web export shape", 1)[1]
    block = re.search(r"```json\n(.*?)\n```", section, re.S)
    assert block, f"{spec}: no JSON example in 7.1"
    return json.loads(block.group(1))


@pytest.mark.parametrize("spec", SHAPES)
def test_ac_01_example_is_valid_data_with_protocol_guard(spec):
    """AC-01: the example parses, is the `data` object (no envelope keys) and has the protocol status and hash."""
    data = _example(spec)
    assert isinstance(data, dict) and not ENVELOPE & set(data)
    assert {"status", "sha256"} <= set(data["protocol"])
    assert data["protocol"]["status"] in {"SEALED", "UNSEALED"}
    assert data["label"] in {"[simulated]", "[data]"}


def test_ac_01_spec_12_points_to_the_three_subsections():
    text = (ROOT / "specs/12-insight-pages.md").read_text(encoding="utf-8")
    for n in (11, 15, 17):
        assert f"spec {n} §7.1" in text


def test_ac_01_no_result_file_exists_while_the_protocol_is_unsealed():
    """Spec 12 §7.1: a placeholder result would block sealing the protocol (fixtures under __fixtures__ are allowed).

    Applies only while eval/PROTOCOL.md reads `Status: UNSEALED`; after M02 the real files may be committed.
    """
    status = re.search(r"^- Status: (\w+)$", (ROOT / "eval/PROTOCOL.md").read_text(encoding="utf-8"), re.M).group(1)
    if status != "UNSEALED":
        pytest.skip("protocol sealed: real result files are allowed")
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split("\n")
    found = [f for f in out if Path(f).name in SHAPES.values() and "__fixtures__" not in f]
    assert found == []
