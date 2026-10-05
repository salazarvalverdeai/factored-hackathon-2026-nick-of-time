"""Spec 12 T2 — the pitch numbers `/analytics` shows are the ones in queries/pitch/*.csv, nothing typed by hand."""
from __future__ import annotations

import json
import re
from pathlib import Path

from queries.pitch import export_web

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = json.loads((ROOT / "apps/web/public/data/pitch_numbers.json").read_text(encoding="utf-8"))


def test_ac_08_committed_pitch_numbers_equal_the_rebuild_from_the_csvs():
    """AC-08: rebuilding the pitch data from queries/pitch/*.csv gives the `data` of the committed JSON."""
    rebuilt = json.loads(json.dumps(export_web.build(), ensure_ascii=False))   # same types as a JSON reader sees
    assert rebuilt == COMMITTED["data"], "run `python queries/pitch/export_web.py` and commit the result"


def test_ac_08_committed_file_has_the_insight_envelope_and_its_label():
    """AC-08: the file is `{generated_at, git_sha, source, data}` (spec 01 §6.2) and its source carries [data]."""
    assert list(COMMITTED) == ["generated_at", "git_sha", "source", "data"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", COMMITTED["generated_at"])
    assert re.fullmatch(r"[0-9a-f]{7,40}", COMMITTED["git_sha"])
    assert "[data]" in COMMITTED["source"] and "queries/pitch" in COMMITTED["source"]


def test_ac_08_the_export_reads_only_the_versioned_csvs():
    """AC-08: the export has no dataset access: it opens only the pNN_*.csv files next to it."""
    source = (ROOT / "queries/pitch/export_web.py").read_text(encoding="utf-8")
    assert "read_parquet" not in source and "duckdb" not in source and "gold" not in source
    named = set(re.findall(r"p\d{2}_\w+\.csv", source))
    assert named and all((ROOT / "queries/pitch" / name).exists() for name in named)
