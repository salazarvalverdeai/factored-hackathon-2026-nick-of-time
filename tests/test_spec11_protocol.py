"""Spec 11 protocol tests (AC-01, AC-06), also covering the rule text of specs 15 (AC-07) and 17 (AC-06).

Offline: reads eval/PROTOCOL.md, specs/11, specs/15 and (when present) eval/classifier. Once Diego fills the seal block, the
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
SPEC15 = ROOT / "specs" / "15-model-benchmark.md"
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

# Spec 15 §4.4 and §4.5 are read from specs/15 (see _spec15_block). The spec 17 copy stays embedded until PR #46 merges.
# TODO(after #46 merges): read specs/17-fraud-model.md §4.4 with _spec15_block-style slicing and drop this copy.
# Spec 17 §4.4 as on branch feat/17-screen (PR #46), 2026-10-04, with the "pending the lead" qualifiers of rules 1 and 2
# replaced by the wording and tags of D-017b/c/d (decided 2026-10-04).
SPEC17_RULE = """
1. **Hard limits:** at the bank's precision levels (0.80 and 0.95), recall is at least the bank's; no country or segment
   has a recall below 80% of the overall recall `[assumption]`; scoring p95 ≤ 50 ms and model size ≤ 200 MB
   `[assumption]`. The overall, per-country and per-segment recall of this floor are measured at the 1% alert budget (the
   top 1% of the window by score) `[assumption]` (D-017b). The floor applies only to country and segment slices with at
   least 20 frauds in the window; smaller slices are reported with their fraud count and not enforced `[assumption]`
   (D-017c).
2. **Value:** the arm beats S-bank — PR-AUC higher with the 95% bootstrap CI of the difference above zero — **or** it
   catches at least 30% of the frauds with no bank score at an alert budget of 1% of those transactions (AC-04)
   `[assumption]` (D-017d).
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


def _spec15_block(start: str, stop: str) -> str:
    spec = SPEC15.read_text()
    i = spec.index(start)
    return spec[i + len(start): spec.index(stop, i)]


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
    test = [r for r in rows["test"] if r.get("label") != "injection"]  # injection rows count only for AC-04 (D-022)
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
    rule15 = _spec15_block("### 4.4 Lean rule", "### 4.5").split("\n", 1)[1]  # drop the heading's tail
    assert _norm(rule15) in protocol, "spec 15 §4.4 lean rule not copied as one block"
    assert _norm(SPEC17_RULE) in protocol
    assert _norm(SPEC15_GATE_RULE) in protocol
    rows = [x for x in _spec15_block("### 4.5", "- **Prices:**").splitlines() if x.startswith("| ")][1:]  # skip the header; the |--- line does not start with "| "
    assert len(rows) == 9, rows
    for criterion in rows:
        assert _norm(criterion) in protocol, criterion
    # D-012: ES/PT quality is a production-only criterion
    assert "| ES/PT quality measured on our data | — (the benchmark measures it) | yes |" in protocol
    assert "ES/PT quality is a production-only criterion (D-012" in protocol
    assert "spec 15 §4.5" in protocol
    assert "never used to choose" in protocol
    assert "best supervised arm + the bank's score" in protocol
    assert "scoring p95 per transaction" in protocol
    # D-011 and D-016
    assert protocol.count("temperature 0") <= 1
    assert "recorded per arm (`tool_choice_mode`) and reused in B1" in protocol
    assert "0 where the model accepts it, otherwise the provider default; the value used is recorded per arm" in protocol
    assert "cost and efficiency on the same machine" in protocol


def test_ac_01_every_assumption_threshold_keeps_its_label():
    protocol = _norm(_text())
    for needle in (
        "p95 ≤ 6 s per turn and no unsafe outcome",  # label comes from the unlabeled-figure note
        "blind comparisons `[assumption]`",
        "recall below 80% of the overall recall `[assumption]`",
        "model size ≤ 200 MB `[assumption]`",
        "exceeds 20 USD `[assumption]`",
        "20 samples `[assumption]`",
        "depth ≤ 6 `[assumption]`",
        # D-017 (spec 17 §4.3-4.4 on PR #46)
        "no supervised arm exceeds twice the validation base rate, the balanced `HistGradientBoostingClassifier`",
        "threshold is a heuristic `[assumption]`",
        "The overall, per-country and per-segment recall of this floor are measured at the 1% alert budget (the top 1% of "
        "the window by score) `[assumption]` (D-017b)",
        "The floor applies only to country and segment slices with at least 20 frauds in the window; smaller slices are "
        "reported with their fraud count and not enforced `[assumption]` (D-017c)",
        "at an alert budget of 1% of those transactions (AC-04) `[assumption]` (D-017d)",
        "within 3 points of 60/15/25 `[assumption]`",
        "`label: injection`",
        "spec 11 does not say",
        "The injection sentences live **inside the split files**",
        "top-level files whose names start with `train`, `validation` and `test`",
        "the best supervised arm by **validation** PR-AUC",
        "`eval/heldout.sha256` holds exactly one sha256 (64 lowercase hex characters); SEALED requires 64-hex values in "
        "both reference fields",
        "Converse tool use with the schema, forced with `toolChoice`. Each LLM arm walks the ladder `tool` → `any` → "
        "`auto` and steps down only when Bedrock rejects the mode; the first accepted mode decides",
        "a reply with no tool call, or whose tool input fails the schema, is scored as a wrong prediction for that "
        "message and stays in the denominator; the count is reported per arm `[assumption]` (D-022)",
        "Rows with `label: injection` follow the author rule, the shares and the manifest hash, and are scored only by "
        "the injection detector (AC-04); the test minimums and the intent metrics count only the other rows "
        "`[assumption]` (D-022)",
        "Rules 1-2 are judged on all products; the card subset is reported with its CI and does not gate "
        "`[assumption]` (D-022); country is `customer_country`",
        "Decided by the lead on 2026-10-04 and not yet in the specs:** the 20-fraud slice floor (D-017c, spec 17) and the "
        "3-point share tolerance (D-017e, spec 11)",
        "(D-017e, decided by the lead on 2026-10-04)",
    ):
        assert needle in protocol, needle
    assert "the same tolerance `tests/test_spec11_protocol.py` checks" in protocol
    assert "the 20-fraud floor for a slice" in protocol
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


def _check_sealed_references(block: str, heldout: Path) -> None:
    """SEALED needs a name and date, 64-hex references, and one valid hash in eval/heldout.sha256 that matches."""
    for name in ("Sealed by", "Sealed on"):
        assert _field(block, name) != "pending", f"sealed but {name} is pending"
    for name in (HELDOUT_FIELD, FRAUD_FIELD):
        assert HEX64.fullmatch(_field(block, name)), f"sealed but {name} is not 64 lowercase hex"
    if heldout.exists():
        tokens = heldout.read_text().split()
        assert len(tokens) == 1 and HEX64.fullmatch(tokens[0]), "eval/heldout.sha256 must hold exactly one sha256"
        assert _field(block, HELDOUT_FIELD) == tokens[0], "held-out hash differs"


H1, H2 = "a" * 64, "b" * 64


def _sealed_block(held=H1, fraud=H2):
    return (f"- {HELDOUT_FIELD}: {held}\n- {FRAUD_FIELD}: {fraud}\n- Sealed by: Diego\n- Sealed on: 2026-10-05\n")


@pytest.mark.parametrize("held,fraud,file_text", [
    ("TBD", H2, None), (H1, "n/a", None), ("A" * 64, H2, None), (H1, "b" * 63, None),
    ("Pending", H2, None), (H1, H2, "abc\n"), (H1, H2, f"{H1}\n{H2}\n"),
])
def test_ac_01_sealed_rejects_bad_reference_states(tmp_path, held, fraud, file_text):
    heldout = tmp_path / "heldout.sha256"
    if file_text is not None:
        heldout.write_text(file_text)
    with pytest.raises(AssertionError):
        _check_sealed_references(_sealed_block(held, fraud), heldout)


def test_ac_01_sealed_accepts_valid_references(tmp_path):
    heldout = tmp_path / "heldout.sha256"
    heldout.write_text(H1 + "\n")
    _check_sealed_references(_sealed_block(), heldout)
    _check_sealed_references(_sealed_block(), tmp_path / "missing.sha256")


def test_ac_01_unsealed_is_illegal_once_a_result_exists():
    _, block = _split_seal(PROTOCOL.read_bytes())
    if _field(block, "Status") == "UNSEALED":
        assert not _results_exist(), "results exist but the protocol is UNSEALED"
    else:
        _check_sealed_references(block, ROOT / "eval" / "heldout.sha256")


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
