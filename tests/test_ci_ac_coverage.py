"""Tests for scripts/ci/ac_coverage.py on small fixture specs and tests (offline, no repo specs)."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "ac_coverage", Path(__file__).resolve().parents[1] / "scripts" / "ci" / "ac_coverage.py"
)
ac = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ac)

SPEC = """# Spec 99 - fixture
- **Status:** {status} (note)

## 3. Acceptance criteria (EARS)
- **AC-01** - The zone shall be high. · [T]
- **AC-02** - Second criterion that
  wraps onto a second line. · [T]
- **AC-03 [P1]** - Later phase. · [T]
- **AC-04** - (P1) Also later. · [T]
- **AC-05** - Shown in a screenshot. · [U]
- **AC-06** - Listed as P1 in the table. · [T]

## 4. Functional requirements
| **P1 - if time allows** | something | AC-06 |
"""

TEST = '''
def test_ac_01_zone():
    pass


def test_other():
    """AC-02: cited in the docstring."""
'''


def _run(tmp_path, status, with_tests=True):
    (tmp_path / "specs").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "specs" / "99-fixture.md").write_text(SPEC.format(status=status))
    if with_tests:
        (tmp_path / "tests" / "test_spec99_x.py").write_text(TEST)
    return ac.check(tmp_path / "specs", tmp_path)


def test_covered_implemented_spec_passes(tmp_path):
    report, failures = _run(tmp_path, "Implemented")
    assert failures == 0
    text = "\n".join(report)
    assert "AC-03  skip (P1)" in text and "AC-04  skip (P1)" in text
    assert "AC-05  skip (non-[T])" in text and "AC-06  skip (P1)" in text


def test_missing_test_fails_implemented(tmp_path):
    report, failures = _run(tmp_path, "Implemented", with_tests=False)
    assert failures == 1
    assert "AC-01  MISSING" in "\n".join(report)


def test_missing_test_only_warns_in_progress(tmp_path):
    report, failures = _run(tmp_path, "In progress", with_tests=False)
    assert failures == 0
    assert "warn" in "\n".join(report)


def test_draft_is_skipped(tmp_path):
    report, failures = _run(tmp_path, "Draft", with_tests=False)
    assert failures == 0 and "skipped" in report[0]


def test_ac_number_is_not_a_prefix_match(tmp_path):
    (tmp_path / "t.py").write_text("def test_ac_010_x():\n    pass\n")
    assert ac.cited_acs(tmp_path / "t.py") == {10}
