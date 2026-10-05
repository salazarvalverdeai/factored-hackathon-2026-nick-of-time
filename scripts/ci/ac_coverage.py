"""Acceptance-criteria coverage gate (CONTRIBUTING.md section 3).

For each specs/NN-*.md: read its Status and the criteria of section 3 with their evidence tag. Every non-P1 [T]
criterion needs a test in tests/test_specNN_*.py (or a test folder the spec names, e.g. apps/api/tests/) whose
function name contains ac_NN or whose docstring cites AC-NN.

Implemented specs fail on a missing test (or on 0 parsed criteria); Draft, Approved and In progress specs only
print a warning table; Superseded specs are skipped. P1/P2 criteria are skipped. Playwright titles in
apps/web/e2e/specNN-*.spec.ts that start with AC-NN count as evidence. Usage: python scripts/ci/ac_coverage.py [--specs DIR] [--root DIR]
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

CRITERION = re.compile(r"^-\s+(?:\*\*)?AC-(\d+)\b")
TAG = re.compile(r"·\s*\[([TCUD](?:\s*,\s*[TCUD])*)\]")
PHASE = re.compile(r"\[P[12]\]|\(P[12]\)")
AC_RANGE = re.compile(r"AC-(\d+)(?:\s*[–-]\s*(?:AC-)?(\d+))?")
CITE = re.compile(r"(?:spec\s*(\d+)\s*)?AC-(\d+)", re.I)
TEST_DIR = re.compile(r"((?:apps|packages|eval|data)/[\w./-]*tests?)/")
E2E_TITLE = re.compile(r"""\b(?:test|it)(?:\.\w+)?\(\s*['"`]((?:AC-\d+[,\s/&]*)+)""")


def parse_spec(text: str) -> dict:
    """Return status, criteria {n: {"tags": set, "later": bool}} and the extra test folders the spec names."""
    status = ""
    if m := re.search(r"\*\*Status:\*\*\s*([A-Za-z ]+)", text):
        status = " ".join(m.group(1).lower().split())
    lines = text.splitlines()
    in_section = False
    cur: int | None = None
    buf: dict[int, str] = {}
    for line in lines:
        if line.startswith("## "):
            in_section = line.startswith("## 3.")
            cur = None
        elif not in_section:
            continue
        elif m := CRITERION.match(line):
            cur = int(m.group(1))
            buf[cur] = line
        elif cur is not None and line[:1] in (" ", "\t") and line.strip():
            buf[cur] += " " + line.strip()  # wrapped text and nested sub-bullets
        else:
            cur = None
    later: set[int] = set()  # criteria of phase P1/P2 listed in a phase table row
    for line in lines:
        if line.lstrip().startswith("|") and re.search(r"\*\*P[12]\b", line):
            for a, b in AC_RANGE.findall(line):
                later.update(range(int(a), int(b or a) + 1))
    crit: dict[int, dict] = {}
    for n, body in buf.items():
        i = body.find("—")
        head = body[: i + 14] if i >= 0 else body[:40]
        tags = {t.strip() for g in TAG.findall(body) for t in g.split(",")}
        crit[n] = {"tags": tags, "later": bool(PHASE.search(head)) or n in later}
    return {"status": status, "criteria": crit, "folders": sorted(set(TEST_DIR.findall(text)))}


def cited_acs(py: Path, nn: str = "") -> set[int]:
    """AC numbers evidenced by tests in one file: ac_NN in a test name or AC-NN in its docstring.

    A citation of another spec ("spec 05 AC-03") is ignored when that spec is not NN.
    """
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            found.update(int(n) for n in re.findall(r"ac_(\d+)", node.name.lower()))
            for other, n in CITE.findall(ast.get_docstring(node) or ""):
                if not other or not nn or int(other) == int(nn):
                    found.add(int(n))
    return found


def e2e_acs(ts: Path) -> set[int]:
    """AC numbers from Playwright test titles that start with AC-NN (docs/testing.md)."""
    text = ts.read_text(encoding="utf-8", errors="ignore")
    return {int(n) for g in E2E_TITLE.findall(text) for n in re.findall(r"AC-(\d+)", g)}


def evidence(root: Path, nn: str, folders: list[str]) -> set[int]:
    files = list((root / "tests").glob(f"test_spec{nn}_*.py"))
    for f in folders:
        if (root / f).is_dir():
            files += (root / f).rglob("test_*.py")
    out: set[int] = set()
    for f in files:
        out |= cited_acs(f, nn)
    for f in (root / "apps" / "web" / "e2e").glob(f"spec{nn}-*.spec.ts"):
        out |= e2e_acs(f)
    return out


def check(specs_dir: Path, root: Path, annotate: bool = False) -> tuple[list[str], int]:
    report: list[str] = []
    failures = 0
    for spec in sorted(specs_dir.glob("[0-9][0-9]-*.md")):
        nn = spec.name[:2]
        info = parse_spec(spec.read_text(encoding="utf-8"))
        status = info["status"]
        if status.startswith("implemented"):
            mode = "enforce"
        elif status.startswith(("draft", "in progress", "approved")):
            mode = "warn"
        else:
            report.append(f"spec {nn} ({status or 'no status'}): skipped\n")
            continue
        have = evidence(root, nn, info["folders"])
        rows, missing = [], []
        for n, c in sorted(info["criteria"].items()):
            if c["later"]:
                state = "skip (P1/P2)"
            elif not c["tags"]:
                state = "MISSING (no evidence tag)"
            elif "T" not in c["tags"]:
                state = "skip (non-[T])"
            elif n in have:
                state = "ok"
            else:
                state = "MISSING"
            if state.startswith("MISSING"):
                missing.append(n)
            rows.append(f"  AC-{n:02d}  {state}")
        empty = not info["criteria"]
        fail = mode == "enforce" and (bool(missing) or empty)
        verdict = "FAIL" if fail else ("warn" if missing or empty else "ok")
        head = f"spec {nn} ({status}, {mode}): {len(missing)} missing -> {verdict}"
        if empty:
            rows.append("  no criteria parsed from section 3")
        report.append(head + "\n" + "\n".join(rows) + "\n")
        failures += fail
        if annotate:
            level = "error" if fail else "warning"
            for n in missing:
                print(f"::{level} file=specs/{spec.name}::AC-{n:02d} has no test citing it")
            if empty:
                print(f"::{level} file=specs/{spec.name}::no acceptance criteria parsed from section 3")
    return report, failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--specs", type=Path)
    args = ap.parse_args(argv)
    report, failures = check(args.specs or args.root / "specs", args.root, annotate=bool(os.environ.get("GITHUB_ACTIONS")))
    text = "\n".join(report)
    print(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## AC coverage\n\n```\n" + text + "\n```\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
