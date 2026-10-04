"""Spec 11 protocol tests (AC-01, AC-06), also covering the rule text of specs 15 (AC-07) and 17 (AC-06).

Offline: reads eval/PROTOCOL.md, specs/11 and (when present) eval/classifier. Once Diego fills the seal block, the
hash checks become real evidence that the protocol and the split files were not edited afterwards.
"""
import hashlib
import json
import re
import subprocess
from itertools import combinations
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "eval" / "PROTOCOL.md"
SPEC11 = ROOT / "specs" / "11-intent-classifier.md"
BEGIN = b"<!-- SEAL:BEGIN -->"
END = b"<!-- SEAL:END -->"
HEX64 = re.compile(r"[0-9a-f]{64}")
SPLIT_FIELD = "Classifier split manifest sha256"
HELDOUT_FIELD = "Agent held-out sha256 (eval/heldout.sha256, ADR 0007)"
FRAUD_FIELD = "Fraud split hash (spec 17 T1)"
SPLITS = {"train": 0.60, "validation": 0.15, "test": 0.25}
SHARE_TOLERANCE = 0.03  # a by-author split cannot hit the shares exactly
LANGS = ("es", "pt")
INTENTS = ("unrecognized_charge", "wrongful_charge", "status_inquiry", "human_request", "out_of_scope")
RESULT_GLOBS = (
    "eval/results/*", "models/intent-*", "models/injection-*", "models/fraud-*",
    "apps/web/public/data/classifier.json", "apps/web/public/data/benchmark.json",
    "apps/web/public/data/fraud_benchmark.json",
)

# TODO(after merge): once specs/15-model-benchmark.md and specs/17-fraud-model.md are on this branch, read §4.4 from
# them as _spec11_block does for spec 11, and drop these two copies.
# Verbatim from specs/15-model-benchmark.md §4.4 and specs/17-fraud-model.md §4.4 (2026-10-04).
SPEC15_RULE = """
1. **Hard limits** — `understand`: the floors of spec 11 §4.1 (macro-F1 per language, dispute and `human_request`
   recall) and p95 ≤ 1.5 s per message; `word`: grounding pass rate ≥ 0.95 and preferred over the template in ≥ 60% of
   blind comparisons `[assumption]`; B2: p95 ≤ 6 s per turn and no unsafe outcome.
2. **Quality bar** — keep the arms that are not significantly worse than the best arm on the same items (paired
   McNemar, p ≥ 0.05; in B2, overlapping 95% CIs). A fixed "within 2 points" cannot be measured at this test size
   (spec 11 §4.1).
3. **Lean choice** — among those, the **cheapest** (B1: cost per 1,000 messages; B2: cost per case); a tie goes to the
   lower p95.
4. **Eligibility** — the chosen arm must pass the production gate of §4.5 on the run date; if it does not, the next
   cheapest arm that meets the bar and passes the gate is chosen, and the ADR says why.
5. If no LLM arm beats B0 with significance (McNemar, p < 0.05), B0 stays and that is reported (spec 11 §4).
"""
SPEC17_RULE = """
1. **Hard limits:** at the bank's precision levels (0.80 and 0.95), recall is at least the bank's; no country or segment
   has a recall below 80% of the overall recall `[assumption]`; scoring p95 ≤ 50 ms and model size ≤ 200 MB
   `[assumption]`.
2. **Value:** the arm beats S-bank — PR-AUC higher with the 95% bootstrap CI of the difference above zero — **or** it
   catches at least 30% of the frauds with no bank score at the 1% alert budget `[assumption]`.
3. **Quality bar:** keep the arms whose PR-AUC is not significantly worse than the best arm (paired bootstrap on the
   same test transactions).
4. **Lean choice:** among those, the cheapest to run — lowest scoring p95, then smallest model, then shortest training;
   a tie goes to the simpler family (linear < tree < ensemble < neural < stacked).
5. If no arm passes, the bank's score stays alone and the benchmark is reported as is.
"""
SPEC15_GATE_RULE = '"Not documented" fails a production criterion.'


def _norm(text: str) -> str:
    """Collapse whitespace and ASCII comparison signs to the spec's symbols."""
    text = text.replace(">=", "≥").replace("<=", "≤")
    return re.sub(r"\s+", " ", text).strip()


def _text() -> str:
    return PROTOCOL.read_bytes().decode()


def _split_seal(data: bytes):
    """Return (bytes without the seal block, seal block text); the same lines the sed command removes."""
    keep, block, inside = [], [], False
    for line in data.splitlines(keepends=True):
        stripped = line.rstrip(b"\n")
        if stripped == BEGIN:
            inside = True
        (block if inside else keep).append(line)
        if stripped == END:
            inside = False
    return b"".join(keep), b"".join(block).decode()


def _field(block: str, name: str) -> str:
    m = re.search(rf"^- {re.escape(name)}: (.+)$", block, re.M)
    assert m, f"seal field missing: {name}"
    return m.group(1).strip()


def _spec11_block(start: str, stop: str) -> str:
    spec = SPEC11.read_text()
    return spec[spec.index(start): spec.index(stop, spec.index(start))]


def _split_files(root=ROOT):
    d = root / "eval" / "classifier"
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.relative_to(root).as_posix().encode()) if d.exists() else []
    return files


def _manifest_hash(files, root=ROOT) -> str:
    """Same as the documented command: sha256 of 'file-sha256  path' lines in C-locale path order."""
    lines = "".join(
        f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(root).as_posix()}\n" for f in files
    )
    return hashlib.sha256(lines.encode()).hexdigest()


def test_ac_01_protocol_has_one_section_per_spec_and_a_seal():
    text = _text()
    for heading in (
        "## 1. Intent classifier and injection detector (spec 11)",
        "## 2. Model benchmark (spec 15)",
        "## 3. Fraud model (spec 17)",
        "## Seal",
    ):
        assert heading in text


def test_ac_01_floors_and_decision_rule_match_spec11_verbatim():
    protocol = _norm(_text())
    floors = _spec11_block("**Floors (decided by the lead", "**Decision rule")
    floors = floors.split("\n", 1)[1]  # drop the heading line
    rule = _spec11_block("**Decision rule (copied into `eval/PROTOCOL.md`):**", "## 5.").split("\n", 1)[1]
    for line in floors.strip().splitlines() + rule.strip().splitlines():
        if line.strip():
            assert _norm(line) in protocol, line
    assert _norm(floors) in protocol, "spec 11 floors not copied as one block"
    assert _norm(rule) in protocol, "spec 11 decision rule not copied as one block"
    # thresholds travel with their labels
    for needle in (
        "macro-F1 ≥ 0.90 in ES and in PT `[assumption]`",
        "`human_request` `[assumption]`",
        "test split ≥ 100 sentences per language (AC-06)",
        "classifier accepts `[assumption]`",
    ):
        assert needle in protocol, needle


def test_ac_06_split_by_author_60_15_25_and_test_minimums():
    text = _text()
    assert "**by author**" in text
    for row in ("| Train | 60% |", "| Validation | 15% |", "| Test | 25% |"):
        assert row in text
    assert "**100 test sentences per language** and **20 per intent per language** `[assumption]`" in text
    for intent in INTENTS:
        assert f"`{intent}`" in text, intent


def test_ac_06_split_files_by_author_when_spec09_delivers():
    files = _split_files()
    if not files:
        pytest.skip("eval/classifier not delivered yet (spec 09); layout is an [assumption]")
    rows = {s: [] for s in SPLITS}
    for f in files:
        split = next((s for s in SPLITS if f.stem.startswith(s)), None)
        assert split, f"not a train/validation/test file: {f.name}"
        rows[split] += [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    test = rows["test"]
    assert test, "empty test split"
    authors = {s: {r["author"] for r in v} for s, v in rows.items()}
    for a, b in combinations(SPLITS, 2):
        assert not authors[a] & authors[b], f"author in both {a} and {b}"
    total = sum(len(v) for v in rows.values())
    for split, share in SPLITS.items():
        assert abs(len(rows[split]) / total - share) <= SHARE_TOLERANCE, (split, len(rows[split]) / total)
    for lang in LANGS:
        sub = [r for r in test if r["language"] == lang]
        assert len(sub) >= 100, lang
        for intent in INTENTS:
            assert sum(r["intent"] == intent for r in sub) >= 20, (lang, intent)


def test_spec15_ac_07_and_spec17_ac_06_rules_present():
    protocol = _norm(_text())
    assert _norm(SPEC15_RULE) in protocol
    assert _norm(SPEC17_RULE) in protocol
    assert _norm(SPEC15_GATE_RULE) in protocol
    for criterion in (
        "| Data sent is synthetic only (ADR 0009) | yes | — |",
        "| Provider does not train on our requests | yes | yes |",
        "| Retention documented; zero retention available | — | yes |",
        "| Processing region documented | — | yes |",
        "| Public security certification (SOC 2 / ISO 27001) | — | yes |",
        "| Credentials outside the repo, least privilege | yes | yes |",
        "| Version pinning | yes | yes |",
        "| Availability: GA, SLA or status page | — | yes |",
        "| ES/PT quality measured on our data | yes | yes |",
    ):
        assert criterion in protocol, criterion
    assert "spec 15 §4.5" in protocol
    assert "never used to choose" in protocol
    assert "best supervised arm + the bank's score" in protocol
    assert "scoring p95 per transaction" in protocol
    assert "cost and efficiency on the same machine" in protocol


def test_ac_01_every_assumption_threshold_keeps_its_label():
    protocol = _norm(_text())
    for needle in (
        "p95 ≤ 6 s per turn and no unsafe outcome",  # label comes from the unlabeled-figure note
        "blind comparisons `[assumption]`",
        "recall below 80% of the overall recall `[assumption]`",
        "model size ≤ 200 MB `[assumption]`",
        "1% alert budget `[assumption]`",
        "exceeds 20 USD `[assumption]`",
        "20 samples `[assumption]`",
        "depth ≤ 6 `[assumption]`",
    ):
        assert needle in protocol, needle
    assert "label missing in the spec; to be added to specs 11, 15 and 17 by the lead" in protocol
    assert "aggregate counts computed by the lead on 2026-10-04" in protocol


def test_ac_01_seal_block_has_all_fields_and_status():
    _, block = _split_seal(PROTOCOL.read_bytes())
    for name in (
        "Protocol sha256",
        SPLIT_FIELD,
        HELDOUT_FIELD,
        FRAUD_FIELD,
        "Sealed by",
        "Sealed on",
    ):
        _field(block, name)
    assert _field(block, "Status") in {"UNSEALED", "SEALED"}


def _results_exist(root=ROOT) -> list:
    return [p for g in RESULT_GLOBS for p in root.glob(g) if p.name != ".gitkeep"]


@pytest.mark.parametrize("pattern", RESULT_GLOBS)
def test_ac_01_every_result_path_of_the_seal_procedure_blocks_unsealed(tmp_path, pattern):
    assert f"`{pattern}`" in _text(), pattern
    assert not _results_exist(tmp_path)
    path = tmp_path / pattern.replace("*", "x")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    assert _results_exist(tmp_path) == [path]


def test_ac_01_unsealed_is_illegal_once_a_result_exists():
    _, block = _split_seal(PROTOCOL.read_bytes())
    if _field(block, "Status") == "UNSEALED":
        assert not _results_exist(), "results exist but the protocol is UNSEALED"
    else:
        for name in ("Sealed by", "Sealed on", HELDOUT_FIELD, FRAUD_FIELD):
            assert _field(block, name) != "pending", f"sealed but {name} is pending"
        heldout = ROOT / "eval" / "heldout.sha256"
        if heldout.exists():
            assert _field(block, HELDOUT_FIELD) == (heldout.read_text().split() or [""])[0], "held-out hash differs"


def test_ac_01_seal_matches_hashing_method_or_is_unsealed():
    body, block = _split_seal(PROTOCOL.read_bytes())
    if _field(block, "Status") == "UNSEALED":
        for name in ("Protocol sha256", SPLIT_FIELD):
            assert _field(block, name) == "pending"
        return
    protocol_hash = _field(block, "Protocol sha256")
    assert HEX64.fullmatch(protocol_hash), "sealed but no protocol sha256"
    assert hashlib.sha256(body).hexdigest() == protocol_hash, "protocol changed after sealing"
    files = _split_files()
    assert files, "sealed but no eval/classifier/*.jsonl file matches"
    recorded = _field(block, SPLIT_FIELD)
    assert HEX64.fullmatch(recorded)
    assert _manifest_hash(files) == recorded, "classifier split files changed after sealing"


def test_ac_01_documented_sed_command_agrees_with_python_split():
    body, _ = _split_seal(PROTOCOL.read_bytes())
    out = subprocess.run(
        ["sed", "/^<!-- SEAL:BEGIN -->$/,/^<!-- SEAL:END -->$/d", str(PROTOCOL)],
        capture_output=True, check=True,
    ).stdout
    assert out == body


def test_ac_01_documented_manifest_command_agrees_with_python(tmp_path):
    command = re.search(r"^files=\$\(find eval/classifier .*$", _text(), re.M).group(0)
    d = tmp_path / "eval" / "classifier"
    (d / "injection").mkdir(parents=True)
    (d / "train.jsonl").write_text('{"text": "a"}\n')
    (d / "test.jsonl").write_text('{"text": "b"}\n')
    (d / "injection" / "attacks.jsonl").write_text('{"text": "c"}\n')  # nested: not a split file
    out = subprocess.run(["sh", "-c", command], cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    assert out.split()[0] == _manifest_hash(_split_files(tmp_path), tmp_path)
    for f in d.glob("*.jsonl"):
        f.unlink()
    empty = subprocess.run(["sh", "-c", command], cwd=tmp_path, capture_output=True, text=True)
    assert empty.returncode != 0 and not empty.stdout, "the command must fail when no split file matches"
