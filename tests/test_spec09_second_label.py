"""Spec 09 T6 (AC-06) — the second-labeling kit: blind export, Cohen's kappa and the agreement report."""
from __future__ import annotations

import csv
import json

import pytest

from eval import second_label as sl

# the 20 dev cases; the D-071 recovery variants (`variant_of`) came after the second labeling and are not in its sample
DEV_IDS = [case["id"] for case in map(json.loads, sl.DEV.read_text(encoding="utf-8").splitlines())
           if not case.get("variant_of")]


def _export(tmp_path):
    path = tmp_path / "sheet.csv"
    sl.export(path=path)
    return path


def _fill(path, labels, labeler="lead"):
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r.update(labels[r["id"]])
        r["labeler"] = labeler
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=sl.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_ac_06_export_covers_exactly_the_20_dev_ids(tmp_path):
    rows = list(csv.DictReader(_export(tmp_path).open(encoding="utf-8", newline="")))
    assert [r["id"] for r in rows] == DEV_IDS and len(rows) == 20


def test_ac_06_export_is_blind_and_labels_are_empty(tmp_path):
    text = _export(tmp_path).read_text(encoding="utf-8")
    rows = list(csv.DictReader(text.splitlines(keepends=True)))
    assert "expected" not in rows[0]
    for r in rows:
        assert all(r[f] == "" for f in (*sl.FIELDS, "labeler", "note"))
    # no first-labeler value can leak: the plan notes, the first intent and the derived decisions are not in the sheet
    for plan in sl._read(sl.PLAN):
        assert plan["notes"] not in text
    assert set(rows[0]) == set(sl.COLUMNS)


def test_ac_06_sheet_has_no_type_column(tmp_path):
    rows = list(csv.DictReader(_export(tmp_path).open(encoding="utf-8", newline="")))
    assert "type" not in rows[0] and "type" not in sl.COLUMNS


def test_ac_06_export_state_summary_has_what_a_labeler_needs(tmp_path):
    rows = {r["id"]: r for r in csv.DictReader(_export(tmp_path).open(encoding="utf-8", newline=""))}
    assert "fraud_score" in rows["EV-0101"]["state"] and "session verified" in rows["EV-0101"]["state"]
    assert "existing case K-200112" in rows["EV-0112"]["state"]
    assert "session expired" in rows["EV-0117"]["state"]
    assert "tool faults: block_card" in rows["EV-0118"]["state"]


def test_ac_06_export_never_reads_heldout(monkeypatch, tmp_path):
    opened = []
    real = sl.Path.read_text

    def spy(self, *a, **k):
        opened.append(self.name)
        return real(self, *a, **k)

    monkeypatch.setattr(sl.Path, "read_text", spy)
    _export(tmp_path)
    assert "heldout.jsonl" not in opened and "dev.jsonl" in opened
    assert "heldout" not in str(sl.DEV) + str(sl.PLAN)


def test_ac_06_export_refuses_to_overwrite_without_force(tmp_path):
    path = _export(tmp_path)
    path.write_text("filled by hand", encoding="utf-8")
    with pytest.raises(SystemExit):
        sl.export(path=path)
    assert path.read_text(encoding="utf-8") == "filled by hand"
    sl.export(force=True, path=path)
    assert path.read_text(encoding="utf-8").startswith("id,")


def test_ac_06_kappa_perfect_agreement():
    a = ["x", "y", "x", "y"]
    assert sl.cohen_kappa(a, list(a)) == 1.0


def test_ac_06_kappa_hand_computed_example():
    # 10 items: both say yes 4 times, both no 3 times, A yes / B no 2 times, A no / B yes 1 time
    a = ["y"] * 4 + ["n"] * 3 + ["y"] * 2 + ["n"]
    b = ["y"] * 4 + ["n"] * 3 + ["n"] * 2 + ["y"]
    # po = 0.7; pe = 0.6*0.5 + 0.4*0.5 = 0.5; kappa = 0.2 / 0.5 = 0.4
    assert sl.cohen_kappa(a, b) == pytest.approx(0.4)


def test_ac_06_kappa_chance_agreement_is_zero():
    a = ["y", "y", "n", "n"]
    b = ["y", "n", "y", "n"]
    assert sl.cohen_kappa(a, b) == pytest.approx(0.0)


def test_ac_06_kappa_systematic_disagreement_is_negative():
    assert sl.cohen_kappa(["y", "y", "n", "n"], ["n", "n", "y", "y"]) == pytest.approx(-1.0)


def test_ac_06_kappa_degenerate_single_category_is_one():
    assert sl.cohen_kappa(["y"] * 5, ["y"] * 5) == 1.0


def test_ac_06_agreement_refuses_incomplete_sheet(tmp_path):
    path = _export(tmp_path)
    with pytest.raises(SystemExit, match="incomplete"):
        sl.agreement(sheet=path, report=None)
    first = sl.first_labels()
    _fill(path, first)
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows[3]["labeler"] = ""
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=sl.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(SystemExit, match="labeler is empty"):
        sl.agreement(sheet=path, report=None)


def test_ac_06_agreement_refuses_values_outside_the_vocabulary(tmp_path):
    path = _export(tmp_path)
    labels = {k: dict(v) for k, v in sl.first_labels().items()}
    labels[DEV_IDS[0]]["decision"] = "approve"
    _fill(path, labels)
    with pytest.raises(SystemExit, match="not one of"):
        sl.agreement(sheet=path, report=None)


def test_ac_06_sheet_equal_to_first_labels_gives_full_agreement(tmp_path):
    path = _export(tmp_path)
    _fill(path, sl.first_labels())
    report = tmp_path / "agreement.json"
    result = sl.agreement(sheet=path, report=report)
    assert set(result["fields"]) == set(sl.FIELDS)
    for r in result["fields"].values():
        assert r["n"] == 20 and r["agreements"] == 20 and r["percent_agreement"] == 100.0
        assert r["kappa"] == 1.0 and r["disagreements"] == []
    assert json.loads(report.read_text(encoding="utf-8")) == result
    assert sl.markdown_table(result).count("\n") == 1 + len(sl.FIELDS)


def test_ac_06_agreement_lists_disagreeing_cases(tmp_path):
    path = _export(tmp_path)
    labels = {k: dict(v) for k, v in sl.first_labels().items()}
    other = "deny" if labels[DEV_IDS[0]]["decision"] != "deny" else "ask"
    labels[DEV_IDS[0]]["decision"] = other
    _fill(path, labels)
    r = sl.agreement(sheet=path, report=None)["fields"]["decision"]
    assert r["agreements"] == 19 and r["disagreements"] == [DEV_IDS[0]] and r["kappa"] < 1.0


def test_ac_06_committed_sheet_has_the_dev_ids_and_no_expected_column():
    rows = list(csv.DictReader(sl.SHEET.open(encoding="utf-8", newline="")))
    assert [r["id"] for r in rows] == DEV_IDS
    assert set(rows[0]) == set(sl.COLUMNS)
