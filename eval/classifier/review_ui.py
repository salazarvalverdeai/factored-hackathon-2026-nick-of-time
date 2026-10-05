"""A page to review a classifier draft on screen instead of in a spreadsheet (spec 09 T5, ADR 0025).

    PYTHONPATH=packages python -m eval.classifier.review_ui --split test     # draft/review_test.html

It reads `draft/review_<split>.csv` (made by `review.py export`) and writes ONE self-contained HTML file with the rows
inside: open it in a browser, no server, no network, no model. The page decides nothing: every row starts without a
decision, the reviewer sets `keep`, `fix` or `drop` by hand, and "Download CSV" writes the same columns `review.py
promote` reads (empty `fixed_*` cell = keep the draft value, `null` = clear it). Work is kept in the browser's local
storage and can be reloaded from a downloaded CSV, so a review can stop and resume. The page never writes the repo.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from eval.classifier.review import CSV_FIELDS, FIXED, INTENTS, INJECTION, ROOT, SPLITS, ReviewError, _paths

TEMPLATE = Path(__file__).with_name("review_ui.html")


def build(root: Path = ROOT, split: str = "test") -> Path:
    """Write draft/review_<split>.html from draft/review_<split>.csv and return its path."""
    draft = _paths(root)[1]
    source = draft / f"review_{split}.csv"
    if not source.exists():
        raise ReviewError(f"no {source}; run `python -m eval.classifier.review export --split {split}` first")
    with source.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    data = {"split": split, "fields": CSV_FIELDS, "fixed": list(FIXED), "intents": [*INTENTS, INJECTION], "rows": rows}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")       # safe inside <script>
    out = draft / f"review_{split}.html"
    out.write_text(TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", blob), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=SPLITS, default="test")
    args = parser.parse_args(argv)
    try:
        print(build(ROOT, args.split))
    except ReviewError as error:
        print(f"error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
