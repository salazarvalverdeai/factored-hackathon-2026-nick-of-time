"""Isolation for the tests of the one-time commands (spec 10 T7 held-out, spec 17 T4 test window; ADR 0007, 0022).

`isolate(monkeypatch, tmp_path)` points every root those commands use at a throwaway folder, and makes any open of the
real held-out case file or of the real label folder, and any claim_run or check_seal on the real repository, fail the
test. With the real seal intact the shared guard passes in any checkout, so without this a test could claim a real
marker or read the real held-out.
"""
from __future__ import annotations

import builtins
import io
import os
from pathlib import Path

import pytest

REAL_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (REAL_ROOT / "eval/cases/heldout.jsonl", REAL_ROOT / "data/gold_eval")


def _forbidden(path) -> bool:
    try:
        resolved = Path(os.fspath(path)).resolve()
    except TypeError:                                      # a file descriptor
        return False
    return any(resolved == p or resolved.is_relative_to(p.resolve()) for p in FORBIDDEN)


def isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    from eval.harness import heldout, labels, report, seal_guard
    from scripts.ml import fraud_report as fr
    from scripts.ml import fraud_split as fs

    root = tmp_path / "isolated-root"
    root.mkdir(exist_ok=True)
    for name, opener in (("builtins", builtins.open), ("io", io.open)):
        def guarded(file, *args, _opener=opener, **kwargs):
            if _forbidden(file):
                pytest.fail(f"a one-time-command test opened the real {file}")
            return _opener(file, *args, **kwargs)
        monkeypatch.setattr(builtins if name == "builtins" else io, "open", guarded)

    def labels_guard(real):
        def reader(labels_path, *args, **kwargs):
            if _forbidden(labels_path):
                pytest.fail(f"a one-time-command test read the real labels {labels_path}")
            return real(labels_path, *args, **kwargs)
        return reader
    monkeypatch.setattr(fs, "read_labels", labels_guard(fs.read_labels))
    monkeypatch.setattr(fs, "read_test_labels", labels_guard(fs.read_test_labels))
    real_load = labels.load_labels

    def load(transaction_ids, path=None):
        path = path or labels.LABELS
        if _forbidden(path):
            pytest.fail(f"a one-time-command test read the real labels {path}")
        return real_load(transaction_ids, path)
    monkeypatch.setattr(labels, "load_labels", load)
    monkeypatch.setattr(labels, "LABELS", root / "no-labels.parquet")

    real_claim, real_check = seal_guard.claim_run, seal_guard.check_seal

    def claim(name, out_dir, guard=None, root=seal_guard.ROOT, *args, **kwargs):
        if Path(root).resolve() == REAL_ROOT or Path(out_dir).resolve().is_relative_to(REAL_ROOT):
            pytest.fail(f"a one-time-command test tried to claim {name!r} in the real repository")
        return real_claim(name, out_dir, guard, root, *args, **kwargs)

    def check(inputs=None, root=seal_guard.ROOT, tag=seal_guard.SEAL_TAG, commit=seal_guard.SEAL_COMMIT):
        if Path(root).resolve() == REAL_ROOT:
            pytest.fail("a one-time-command test ran check_seal on the real repository")
        return real_check(inputs, root, tag, commit)
    monkeypatch.setattr(seal_guard, "claim_run", claim)
    monkeypatch.setattr(seal_guard, "check_seal", check)

    monkeypatch.setattr(heldout, "ROOT", root)
    monkeypatch.setattr(fr, "REPO", root)
    monkeypatch.setattr(report, "WEB_SUMMARY", root / "apps/web/public/data/evaluation_summary.json")
    return root
