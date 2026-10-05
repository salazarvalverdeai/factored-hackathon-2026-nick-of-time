"""Spec 09 AC-04 (T5): the on-screen review page is a view of the review CSV; it makes no decision."""
import csv
import json
import re
import shutil
from pathlib import Path

import pytest

from eval.classifier import review, review_ui

DRAFT = Path(review.ROOT) / "eval/classifier/draft"


@pytest.fixture
def root(tmp_path):
    draft = tmp_path / "eval/classifier/draft"
    draft.mkdir(parents=True)
    shutil.copy(DRAFT / "test.jsonl", draft / "test.jsonl")
    review.export(tmp_path, "test")
    return tmp_path


def test_ac_04_the_page_embeds_every_row_with_no_decision_and_no_network(root):
    out = review_ui.build(root, "test")
    html = out.read_text(encoding="utf-8")
    data = json.loads(re.search(r"const DATA = (\{.*\});\n", html).group(1))
    rows = list(csv.DictReader((root / "eval/classifier/draft/review_test.csv").open(encoding="utf-8")))
    assert [r["id"] for r in data["rows"]] == [r["id"] for r in rows] and len(rows) == 264
    assert all(r["decision"] == "" and r["reviewer"] == "" for r in data["rows"])      # nothing is pre-decided
    assert data["fields"] == review.CSV_FIELDS                                          # the columns promote reads
    assert not re.search(r"https?://|fetch\(|XMLHttpRequest", html)                     # self-contained, offline
    assert html.count("</script>") == 1                                                 # the data cannot close the tag


def test_ac_04_the_page_needs_the_exported_csv_first(tmp_path):
    with pytest.raises(review.ReviewError):
        review_ui.build(tmp_path, "test")
