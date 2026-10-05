"""Spec 12 T5 — data_quality.json, the file `/data` reads: built by the pipeline report, never by hand."""
from __future__ import annotations

import json
from pathlib import Path

from data.pipeline.report import data_quality
from data.pipeline.run import run_fixture

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = json.loads((ROOT / "apps/web/public/data/data_quality.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((ROOT / "data/gold/manifest.json").read_text(encoding="utf-8"))


def test_ac_03_committed_file_matches_the_gold_manifest():
    """AC-03: the committed file has the insight envelope and its versions, rules and gold rows are the manifest's."""
    assert list(COMMITTED) == ["generated_at", "git_sha", "source", "data"] and "[data]" in COMMITTED["source"]
    data = COMMITTED["data"]
    assert set(data) == {"label", "layers", "gold_rules", "checks", "manifest", "late_arrival"}
    assert (data["manifest"]["gold_version"], data["manifest"]["contract_version"], data["manifest"]["run_at"]) == (
        MANIFEST["version"], MANIFEST["contract"]["version"], MANIFEST["run_at"])
    assert [(r["id"], r["value"], r["ok"]) for r in data["gold_rules"]] == [
        (r["id"], r["value"], r["ok"]) for r in MANIFEST["contract"]["rules"]]
    assert [layer["layer"] for layer in data["layers"]] == ["bronze", "silver", "gold"]
    gold = {t["table"]: (t["rows"], t["bytes"]) for t in data["layers"][2]["tables"]}
    assert gold == {name: (t["rows"], t["bytes"]) for name, t in MANIFEST["tables"].items()}
    assert all(c["rows_affected"] <= c["denominator"] and c["action"] for c in data["checks"])
    assert not any("is_fraud" in json.dumps(layer) for layer in data["layers"])


def test_ac_03_late_arrival_result_is_in_the_committed_file():
    """AC-03: the late-arrival fixture result is shown as a labeled fixture, with what changed between deliveries."""
    late = COMMITTED["data"]["late_arrival"]
    assert "fixture" in late["label"] and [d["name"] for d in late["deliveries"]] == ["delivery_1", "delivery_2"]
    assert late["rows_added"]["transactions"] > 0 and late["columns_added"] and late["late_rows"] > 0
    assert late["expected_counts"]["matched"] == late["expected_counts"]["total"] > 0
    assert {c["id"] for c in late["checks_changed"]} >= {"LATE-01", "SCH-01"}


def test_ac_03_data_quality_is_built_from_a_pipeline_run(tmp_path):
    """AC-03: data_quality() turns the results of a run (here the fixture's) into the shape of spec 12 §7.2."""
    fixture = run_fixture(tmp_path / "_fixture_run")
    run = fixture["runs"][-1]
    data = data_quality(run, fixture)
    assert data["label"] == "[data]" and data["manifest"]["gold_version"] == 2
    assert {t["table"]: t["rows"] for t in data["layers"][0]["tables"]}["transactions"] == run["bronze"]["transactions"]["rows"]
    assert [t["table"] for t in data["layers"][1]["tables"]] == run["tables"]
    assert len(data["checks"]) == len(run["checks"]) and len(data["gold_rules"]) == 5
    assert data["late_arrival"] == COMMITTED["data"]["late_arrival"]       # the fixture is deterministic
    assert data_quality(run, None)["late_arrival"] is None
    json.dumps(data)                                                       # plain JSON, nothing left to serialize
