"""Human review of the classifier drafts and promotion to the split files (spec 09 §7.6, AC-04, AC-10; ADR 0025).

    PYTHONPATH=packages python -m eval.classifier.review export --split train    # draft/review_train.csv
    PYTHONPATH=packages python -m eval.classifier.review promote --dry-run       # validate the three reviewed CSVs
    PYTHONPATH=packages python -m eval.classifier.review promote                 # write eval/classifier/*.jsonl

Review (ADR 0025): every draft line gets a `decision` — `keep`, `fix` (with the `fixed_*` cells to change) or `drop` —
and the `reviewer`'s GitHub handle. Train and validation are reviewed by the lead; test by someone who is not the
classifier's developer (in practice @gianzk). `checks` lists the deterministic hints (planned slot missing, card type
added, language drift, and from `generate --recheck`: same_as_seed, duplicate:<first id>, near_duplicate:<id>:<jaccard>,
language_leak, too_short, injection_without_marker, cross_split_duplicate:<split>/<id>); no model produces them, so they
do not bias a test review (ADR 0025). A hint is not a decision: the reviewer still reads every line and decides.

`fixed_*` cells: empty keeps the draft value, `null` clears it. `fixed_intent` takes one of the five intents or
`injection`; `fixed_also_dispute` takes `true` or `false`; `fixed_amount` is a decimal ("1250.50"), `fixed_currency`
an ISO code, `fixed_date` YYYY-MM-DD resolved against DEMO_TODAY.

Promotion needs the three reviewed CSVs, refuses any row without a decision or reviewer, a test split reviewed by the
classifier developer, a sealed protocol, and a set outside spec 11 AC-06 (shares within 3 points of 60/15/25, at least
100 test sentences per language and 20 per intent per language, injection rows excluded, D-022). Kept rows get
`review_status: kept`, fixed rows `fixed` with the replaced draft values in `original`; dropped rows are not written.
It prints the manifest sha256 of `eval/PROTOCOL.md` Seal (b); it never writes it into the protocol (that is M02).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPLITS = ("train", "validation", "test")
SHARES = {"train": 0.60, "validation": 0.15, "test": 0.25}
SHARE_TOLERANCE = 0.03                      # D-017e, eval/PROTOCOL.md §1.1
MIN_TEST_PER_LANGUAGE = 100                 # spec 11 AC-06
MIN_TEST_PER_INTENT_LANGUAGE = 20           # spec 11 AC-06
LANGS = ("es", "pt")
INTENTS = ("unrecognized_charge", "wrongful_charge", "status_inquiry", "human_request", "out_of_scope")
INJECTION = "injection"
# ADR 0025: the test split is not reviewed by the classifier's developer. GitHub handles, without "@".
CLASSIFIER_DEVELOPERS = ("salazarvalverdeai",)
DECISIONS = ("keep", "fix", "drop")
# ADR 0025 amendment (lead, 2026-10-05): when no independent person can review the test split before the seal, it may
# be decided by these fixed rules, signed RULE_REVIEWER, only with `promote --allow-rule-review`. The classifier
# developer may still never review test. Results on such a split are labeled "without independent human review".
RULE_REVIEWER = "rules-v1"
RULE_DROP = ("duplicate", "same_as_seed", "near_duplicate", "language_leak", "injection_without_marker")
RULE_SLOT_MISSING = {"amount_missing": "fixed_amount", "currency_missing": "fixed_currency", "date_missing": "fixed_date",
                     "merchant_missing": "fixed_merchant", "card_missing": "fixed_card"}
SLOT_FIELDS = ("amount", "currency", "date", "merchant")
FIXED = ("fixed_text", "fixed_intent", "fixed_also_dispute", "fixed_amount", "fixed_currency", "fixed_date",
         "fixed_merchant", "fixed_card")
CSV_FIELDS = ["id", "seed_id", "source", "language", "intent", "label", "also_dispute", *SLOT_FIELDS, "card", "text",
              "checks", "decision", *FIXED, "reviewer", "note"]
DECIMAL = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")          # nick_of_time.contracts.DECIMAL


class ReviewError(ValueError):
    """The review cannot be promoted as it is."""


def _paths(root: Path) -> tuple[Path, Path]:
    return root / "eval" / "classifier", root / "eval" / "classifier" / "draft"


def _drafts(root: Path, split: str) -> list[dict]:
    path = _paths(root)[1] / f"{split}.jsonl"
    if not path.exists():
        raise ReviewError(f"no draft file {path}")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _cell(value) -> str:
    return "" if value is None else ("true" if value is True else "false" if value is False else str(value))


def export(root: Path = ROOT, split: str = "train", force: bool = False) -> Path:
    """Write draft/review_<split>.csv with one row per draft line; refuses to overwrite review work."""
    out = _paths(root)[1] / f"review_{split}.csv"
    if out.exists() and not force:
        raise ReviewError(f"{out} exists; it may hold review work (use --force to overwrite)")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in _drafts(root, split):
            w.writerow({"id": r["id"], "seed_id": _cell(r["seed_id"]), "source": r["source"], "language": r["language"],
                        "intent": _cell(r["intent"]), "label": _cell(r.get("label")),
                        "also_dispute": _cell(r["also_dispute"]), **{k: _cell(r["slots"][k]) for k in SLOT_FIELDS},
                        "card": _cell(r["card"]), "text": r["text"], "checks": ";".join(r["checks"])})
    return out


def _fold(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").casefold()) if unicodedata.category(c) != "Mn")


def rule_decision(draft: dict) -> dict:
    """RULE_REVIEWER decision: drop copies, language leaks and unmarked injections; null a planned slot the text does not
    carry; take the card type the text names; keep the rest. Deterministic, no model."""
    hints = {h.split(":")[0] for h in draft.get("checks", [])}
    if hints & set(RULE_DROP):
        return {"decision": "drop"}
    text, digits = _fold(draft["text"]), re.sub(r"\D", "", draft["text"])
    slots, fixed = draft["slots"], {}
    for hint, col in RULE_SLOT_MISSING.items():
        if hint in hints:
            fixed[col] = "null"
    amount = (slots.get("amount") or "").split(".")[0]
    if amount and re.sub(r"\D", "", amount) not in digits:
        fixed["fixed_amount"], fixed["fixed_currency"] = "null", "null"
    if slots.get("merchant") and _fold(slots["merchant"]).split()[0] not in text:
        fixed["fixed_merchant"] = "null"
    named = "credit" if "credito" in text else ("debit" if "debito" in text else None)
    if draft.get("card") and named != draft["card"]:
        fixed["fixed_card"] = named or "null"
    elif not draft.get("card") and named:
        fixed["fixed_card"] = named
    if "dispute_missing" in hints:
        fixed["fixed_also_dispute"] = "false"
    return {"decision": "fix", **fixed} if fixed else {"decision": "keep"}


def auto_review(root: Path = ROOT, split: str = "test", force: bool = False) -> Path:
    """Fill draft/review_<split>.csv with RULE_REVIEWER decisions (ADR 0025 fallback, test only)."""
    out = export(root, split, force)
    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    by_id = {d["id"]: d for d in _drafts(root, split)}
    for r in rows:
        r.update(rule_decision(by_id[r["id"]]), reviewer=RULE_REVIEWER, note="rules-v1: no independent human review")
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return out


def _handle(name: str) -> str:
    return name.strip().lstrip("@").lower()


def _slot_value(field: str, raw: str, row_id: str):
    if raw == "null":
        return None
    ok = {"amount": DECIMAL.fullmatch(raw), "currency": re.fullmatch(r"[A-Z]{3}", raw),
          "date": re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw), "merchant": raw.strip()}[field]
    if field == "date" and ok:
        date.fromisoformat(raw)
    if not ok:
        raise ReviewError(f"{row_id}: fixed_{field} {raw!r} is not valid")
    return raw.strip()


def apply_review(draft: dict, rev: dict, split: str, allow_rule_review: bool = False) -> dict | None:
    """The promoted row for one reviewed draft line, or None when it is dropped."""
    rid = draft["id"]
    decision = (rev.get("decision") or "").strip().lower()
    if decision not in DECISIONS:
        raise ReviewError(f"{split} {rid}: decision must be one of {DECISIONS}, got {decision!r}")
    reviewer = (rev.get("reviewer") or "").strip()
    if not reviewer:
        raise ReviewError(f"{split} {rid}: no reviewer")
    if split == "test" and _handle(reviewer) in CLASSIFIER_DEVELOPERS:
        raise ReviewError(f"test {rid}: reviewed by {reviewer}, the classifier developer (ADR 0025)")
    if _handle(reviewer) == RULE_REVIEWER and not (split == "test" and allow_rule_review):
        raise ReviewError(f"{split} {rid}: {RULE_REVIEWER} decides test only, with promote --allow-rule-review")
    if decision == "drop":
        return None
    row = {k: v for k, v in draft.items() if k != "checks"}
    row["slots"] = dict(draft["slots"])
    original: dict = {}
    changes = {k: (rev.get(k) or "").strip() for k in FIXED}
    if decision == "fix" and not any(changes.values()):
        raise ReviewError(f"{split} {rid}: decision fix but no fixed_* cell")
    if decision == "keep" and any(changes.values()):
        raise ReviewError(f"{split} {rid}: decision keep but a fixed_* cell is filled (use fix)")
    if changes["fixed_text"]:
        original["text"], row["text"] = draft["text"], changes["fixed_text"]
    if changes["fixed_intent"]:
        new = changes["fixed_intent"]
        if new not in (*INTENTS, INJECTION):
            raise ReviewError(f"{split} {rid}: fixed_intent {new!r} is not an intent or {INJECTION!r}")
        original["intent"], original["label"] = draft["intent"], draft.get("label")
        row.pop("label", None)
        row["intent"] = None if new == INJECTION else new
        if new == INJECTION:
            row = {**{k: row[k] for k in ("id", "text", "language", "intent")}, "label": INJECTION,
                   **{k: v for k, v in row.items() if k not in ("id", "text", "language", "intent")}}
    if changes["fixed_also_dispute"]:
        if changes["fixed_also_dispute"] not in ("true", "false"):
            raise ReviewError(f"{split} {rid}: fixed_also_dispute must be true or false")
        original["also_dispute"], row["also_dispute"] = draft["also_dispute"], changes["fixed_also_dispute"] == "true"
    slot_changes = {f: changes[f"fixed_{f}"] for f in SLOT_FIELDS if changes[f"fixed_{f}"]}
    if slot_changes:
        original["slots"] = dict(draft["slots"])
        for f, raw in slot_changes.items():
            row["slots"][f] = _slot_value(f, raw, f"{split} {rid}")
    if changes["fixed_card"]:
        original["card"], row["card"] = draft["card"], None if changes["fixed_card"] == "null" else changes["fixed_card"]
    if row.get("label") == INJECTION and row["intent"] is not None:
        raise ReviewError(f"{split} {rid}: an injection row has no intent")
    row["review_status"] = "fixed" if original else "kept"
    row["reviewer"] = reviewer
    if original:
        row["original"] = original
    return row


def _reviewed(root: Path, split: str, allow_rule_review: bool = False) -> list[dict]:
    path = _paths(root)[1] / f"review_{split}.csv"
    if not path.exists():
        raise ReviewError(f"no reviewed file {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    drafts = _drafts(root, split)
    by_id = {r["id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise ReviewError(f"{split}: duplicate ids in {path.name}")
    missing = [d["id"] for d in drafts if d["id"] not in by_id]
    unknown = sorted(set(by_id) - {d["id"] for d in drafts})
    if missing or unknown:
        raise ReviewError(f"{split}: {len(missing)} draft rows missing from {path.name} {missing[:3]}, "
                          f"{len(unknown)} unknown ids {unknown[:3]}")
    return [r for d in drafts if (r := apply_review(d, by_id[d["id"]], split, allow_rule_review)) is not None]


def validate(rows: dict[str, list[dict]]) -> dict:
    """Spec 11 AC-06 on the promoted rows; the same rules as tests/test_spec11_protocol.py. Returns the counts."""
    authors = {s: {r["author"] for r in v} for s, v in rows.items()}
    for a, b in combinations(SPLITS, 2):
        if authors[a] & authors[b]:
            raise ReviewError(f"author in both {a} and {b}: {sorted(authors[a] & authors[b])}")
    total = sum(len(v) for v in rows.values())
    if not total:
        raise ReviewError("no row left")
    shares = {s: len(rows[s]) / total for s in SPLITS}
    for s, share in SHARES.items():
        if abs(shares[s] - share) > SHARE_TOLERANCE:
            raise ReviewError(f"share of {s} is {shares[s]:.3f}, outside {share} ± {SHARE_TOLERANCE}")
    test = [r for r in rows["test"] if r.get("label") != INJECTION]
    per_cell = {f"{lang}/{i}": sum(r["language"] == lang and r["intent"] == i for r in test)
                for lang in LANGS for i in INTENTS}
    for lang in LANGS:
        n = sum(r["language"] == lang for r in test)
        if n < MIN_TEST_PER_LANGUAGE:
            raise ReviewError(f"test has {n} {lang} sentences, fewer than {MIN_TEST_PER_LANGUAGE} per language")
    low = {c: n for c, n in per_cell.items() if n < MIN_TEST_PER_INTENT_LANGUAGE}
    if low:
        raise ReviewError(f"test below {MIN_TEST_PER_INTENT_LANGUAGE} per intent per language: {low}")
    if not any(r.get("label") == INJECTION for r in rows["test"]):
        raise ReviewError("no injection row in the test split")
    return {"rows": {s: len(v) for s, v in rows.items()}, "shares": {s: round(x, 4) for s, x in shares.items()},
            "test_per_language_intent": per_cell,
            "injection": {s: sum(r.get("label") == INJECTION for r in v) for s, v in rows.items()}}


def manifest_sha256(blobs: dict[str, bytes]) -> str:
    """Seal (b) of eval/PROTOCOL.md: sha256 of '<sha256>  <path>' lines in C-locale path order."""
    lines = "".join(f"{hashlib.sha256(b).hexdigest()}  {p}\n" for p, b in sorted(blobs.items(), key=lambda x: x[0].encode()))
    return hashlib.sha256(lines.encode()).hexdigest()


def _sealed(root: Path) -> bool:
    protocol = root / "eval" / "PROTOCOL.md"
    if not protocol.exists():
        return False
    block = re.search(r"^<!-- SEAL:BEGIN -->$(.*?)^<!-- SEAL:END -->$", protocol.read_text(encoding="utf-8"), re.M | re.S)
    return bool(block and re.search(r"^- Status: SEALED\s*$", block.group(1), re.M))


def promote(root: Path = ROOT, dry_run: bool = False, force: bool = False, allow_rule_review: bool = False) -> dict:
    """Validate the three reviewed CSVs and write eval/classifier/{train,validation,test}.jsonl (all or nothing)."""
    if _sealed(root):
        raise ReviewError("eval/PROTOCOL.md is sealed: the split files are frozen (ADR 0021); a new set needs a new seal")
    out_dir = _paths(root)[0]
    existing = sorted(out_dir.glob("*.jsonl"))
    if existing and not force and not dry_run:
        raise ReviewError(f"split files already exist ({', '.join(p.name for p in existing)}); use --force")
    rows = {s: _reviewed(root, s, allow_rule_review) for s in SPLITS}
    counts = validate(rows)
    blobs = {f"eval/classifier/{s}.jsonl": "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[s]).encode()
             for s in SPLITS}
    if not dry_run:
        for rel, data in blobs.items():
            (root / rel).write_bytes(data)
    return {**counts, "manifest_sha256": manifest_sha256(blobs), "files": sorted(blobs), "written": not dry_run,
            "status": {s: {k: sum(r["review_status"] == k for r in v) for k in ("kept", "fixed")}
                       for s, v in rows.items()},
            "test_review": ("rules-v1: no independent human review (ADR 0025 amendment)"
                            if any(r["reviewer"] == RULE_REVIEWER for r in rows["test"]) else "human")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="write draft/review_<split>.csv")
    ex.add_argument("--split", choices=SPLITS, action="append")
    ex.add_argument("--force", action="store_true")
    pr = sub.add_parser("promote", help="validate the reviewed CSVs and write the split files")
    pr.add_argument("--dry-run", action="store_true")
    pr.add_argument("--force", action="store_true")
    pr.add_argument("--allow-rule-review", action="store_true", help="accept a test split decided by rules-v1 (ADR 0025)")
    ar = sub.add_parser("auto-review", help="decide the test split by the fixed rules (ADR 0025 fallback)")
    ar.add_argument("--split", choices=("test",), default="test")
    ar.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "export":
            for split in args.split or SPLITS:
                print(export(ROOT, split, args.force).relative_to(ROOT))
            return 0
        if args.cmd == "auto-review":
            print(auto_review(ROOT, args.split, args.force).relative_to(ROOT))
            return 0
        result = promote(ROOT, args.dry_run, args.force, args.allow_rule_review)
    except ReviewError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in result.items() if k != "manifest_sha256"}, indent=2))
    print(f"classifier split manifest sha256 (eval/PROTOCOL.md Seal b, recorded at M02): {result['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
