"""Spec 11 protocol tests (AC-01, AC-06), also covering the rule text of specs 15 (AC-07) and 17 (AC-06).

Offline: reads only eval/PROTOCOL.md. Once Diego records a sha256 in the seal block, the hash check becomes real
evidence that the file was not edited after sealing.
"""
import hashlib
import re
from pathlib import Path

PROTOCOL = Path(__file__).resolve().parents[1] / "eval" / "PROTOCOL.md"
BEGIN = b"<!-- SEAL:BEGIN -->"
END = b"<!-- SEAL:END -->"


def _bytes() -> bytes:
    return PROTOCOL.read_bytes()


def _split_seal(data: bytes):
    """Return (bytes without the seal block, seal block text). Same as the sed command in the protocol."""
    lines = data.splitlines(keepends=True)
    keep, block, inside = [], [], False
    for line in lines:
        stripped = line.rstrip(b"\r\n")
        if stripped == BEGIN:
            inside = True
        if inside:
            block.append(line)
        else:
            keep.append(line)
        if stripped == END:
            inside = False
    return b"".join(keep), b"".join(block).decode()


def _field(block: str, name: str) -> str:
    m = re.search(rf"^- {re.escape(name)}: (.+)$", block, re.M)
    assert m, f"seal field missing: {name}"
    return m.group(1).strip()


def test_ac_01_protocol_exists_with_one_section_per_spec():
    text = _bytes().decode()
    for heading in (
        "## 1. Intent classifier and injection detector (spec 11)",
        "## 2. Model benchmark (spec 15)",
        "## 3. Fraud model (spec 17)",
        "## Seal",
    ):
        assert heading in text


def test_ac_01_floors_and_decision_rule_of_spec11_present():
    text = _bytes().decode()
    for needle in (
        "macro-F1 >= 0.90 in ES and in PT `[assumption]`",
        "recall >= 0.95 per language",
        "precision >= 0.95 on the messages accepted at τ",
        "paired McNemar",
        "Discard any arm below a floor of §4.1 in either language.",
        "(B0 < B1 < B3 < B2)",
        "p95 <= 1.5 s and <= 1 USD per 1,000 messages",
        "keep B0 and report it",
        "without exceeding 2% false positives",
        "specs/11-intent-classifier.md",
    ):
        assert needle in text, needle


def test_ac_06_split_by_author_60_15_25_and_test_minimums():
    text = _bytes().decode()
    assert "by author" in text
    assert "| Train | 60% |" in text
    assert "| Validation | 15% |" in text
    assert "| Test | 25% |" in text
    assert "At least **100 test sentences per language**" in text
    assert "**20 per intent per language**" in text


def test_ac_06_lean_rule_of_spec15_and_decision_rule_of_spec17_present():
    text = _bytes().decode()
    for needle in (  # spec 15 AC-07 / §4.4
        "grounding pass rate >= 0.95",
        "preferred over the template in >= 60% of",
        "p95 <= 6 s per turn and no unsafe outcome",
        "the **cheapest**",
        "production gate",
        "specs/15-model-benchmark.md",
        "never used to choose",
        # spec 17 AC-06 / §4.4 and ADR 0022
        "no country or segment",
        "80% of the overall recall `[assumption]`",
        "scoring p95 <= 50 ms and model size <= 200 MB",
        "30% of the frauds with no bank score",
        "the bank's score stays alone",
        "specs/17-fraud-model.md",
        "ADR 0022",
        "2026-04 to 2026-05",
    ):
        assert needle in text, needle


def test_ac_01_assumptions_keep_their_label():
    text = _bytes().decode()
    assert text.count("`[assumption]`") >= 8


def test_ac_01_seal_block_exists_and_states_status():
    data = _bytes()
    _, block = _split_seal(data)
    assert block, "seal block missing"
    assert _field(block, "Status") in {"UNSEALED", "SEALED"}


def test_ac_01_seal_matches_hashing_method_or_is_unsealed():
    data = _bytes()
    body, block = _split_seal(data)
    status = _field(block, "Status")
    recorded = _field(block, "Protocol sha256")
    if status == "UNSEALED":
        # Before M02 (Diego's review) nothing may be recorded as a seal.
        assert recorded == "pending"
        assert _field(block, "Held-out sha256") == "pending"
        return
    assert re.fullmatch(r"[0-9a-f]{64}", recorded), "sealed but no sha256 recorded"
    assert re.fullmatch(r"[0-9a-f]{64}", _field(block, "Held-out sha256"))
    assert hashlib.sha256(body).hexdigest() == recorded, "protocol changed after sealing"
