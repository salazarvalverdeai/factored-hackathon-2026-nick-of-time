"""Acceptance-criteria coverage gate (CONTRIBUTING.md section 3).

For each specs/NN-*.md: read its Status and the criteria of section 3 with their evidence tag. Every non-P1 [T]
criterion needs a test in tests/test_specNN_*.py (or a test folder the spec names, e.g. apps/api/tests/) whose
function name contains ac_NN or whose docstring cites AC-NN.

Implemented specs fail on a missing test; Approved / In progress specs only print a warning table; Draft and
Superseded specs are skipped. Usage: python scripts/ci/ac_coverage.py [--specs DIR] [--root DIR]
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

CRITERION = re.compile(r"^\s*-\s+\*\*AC-(\d+)\b")
TAG = re.compile(r"\[([TCUD](?:\s*,\s*[TCUD])*)\]")
P1_RANGE = re.compile(r"AC-(\d+)(?:\s*[–-]\s*(?:AC-)?(\d+))?")
TEST_DIR = re.compile(r"((?:apps|packages|eval|data)/[\w./-]*tests?)/")


def parse_spec(text: str) -> dict:
    """Return status, criteria {n: {"tags": set, "p1": bool}} and the extra test folders the spec names."""
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
            continue
        if not in_section:
            continue
        if m := CRITERION.match(line):
            cur = int(m.group(1))
            buf[cur] = line
        elif cur is not None and line.strip() and not line.lstrip().startswith(("- ", "**")):
            buf[cur] += " " + line.strip()
        else:
            cur = None
    p1_listed: set[int] = set()
    for line in lines:
        if line.lstrip().startswith("|") and re.search(r"\*\*P1\b", line):
            for a, b in P1_RANGE.findall(line):
                p1_listed.update(range(int(a), int(b or a) + 1))
    crit: dict[int, dict] = {}
    for n, body in buf.items():
        head = body.split("—", 1)[0]
        tags = TAG.findall(body.split("·")[-1]) if "·" in body else []
        crit[n] = {
            "tags": {t.strip() for g in tags for t in g.split(",")},
            "p1": bool(re.search(r"\[P1\]|\(P1\)", head)) or n in p1_listed,
        }
    return {"status": status, "criteria": crit, "folders": sorted(set(TEST_DIR.findall(text)))}


def cited_acs(py: Path) -> set[int]:
    """AC numbers evidenced by tests in one file: ac_NN in a test name or AC-NN in its docstring."""
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            found.update(int(n) for n in re.findall(r"ac_(\d+)", node.name.lower()))
            found.update(int(n) for n in re.findall(r"AC-(\d+)", ast.get_docstring(node) or ""))
    return found


def evidence(root: Path, nn: str, folders: list[str]) -> set[int]:
    files = list((root / "tests").glob(f"test_spec{nn}_*.py"))
    for f in folders:
        if (root / f).is_dir():
            files += (root / f).rglob("test_*.py")
    out: set[int] = set()
    for f in files:
        out |= cited_acs(f)
    return out


def check(specs_dir: Path, root: Path) -> tuple[list[str], int]:
    report: list[str] = []
    failures = 0
    for spec in sorted(specs_dir.glob("[0-9][0-9]-*.md")):
        nn = spec.name[:2]
        info = parse_spec(spec.read_text(encoding="utf-8"))
        status = info["status"]
        if status.startswith("implemented"):
            mode = "enforce"
        elif status.startswith(("in progress", "approved")):
            mode = "warn"
        else:
            report.append(f"spec {nn} ({status or 'no status'}): skipped\n")
            continue
        have = evidence(root, nn, info["folders"])
        rows, missing = [], 0
        for n, c in sorted(info["criteria"].items()):
            if "T" not in c["tags"]:
                state = "skip (non-[T])"
            elif c["p1"]:
                state = "skip (P1)"
            elif n in have:
                state = "ok"
            else:
                state, missing = "MISSING", missing + 1
            rows.append(f"  AC-{n:02d}  {state}")
        verdict = "FAIL" if mode == "enforce" and missing else ("warn" if missing else "ok")
        report.append(f"spec {nn} ({status}, {mode}): {missing} missing -> {verdict}\n" + "\n".join(rows) + "\n")
        failures += verdict == "FAIL"
    return report, failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--specs", type=Path)
    args = ap.parse_args(argv)
    report, failures = check(args.specs or args.root / "specs", args.root)
    print("\n".join(report))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
