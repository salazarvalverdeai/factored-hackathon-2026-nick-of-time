"""Spec 09 T6 (AC-06): second labeling of the 20 dev agent cases.

    python -m eval.second_label export [--force]   # writes eval/labeling/dev_second_label.csv (blank labels)
    python -m eval.second_label agreement          # compares the filled sheet with the first labels

The sample is the whole dev set and never the held-out: the second labeler develops the agent and the classifier, so
they must not read the held-out cases before the seal. This module never opens ``cases/heldout.jsonl``, gold or
``data/gold_eval/``. The exported sheet is blind: it carries no ``expected`` and no first-labeler intent.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parent
DEV = EVAL / "cases" / "dev.jsonl"
PLAN = EVAL / "cases" / "plan" / "dev.jsonl"
LABELING = EVAL / "labeling"
SHEET = LABELING / "dev_second_label.csv"
REPORT = LABELING / "agreement.json"

INTENTS = ("unrecognized_charge", "wrongful_charge", "status_inquiry", "human_request", "out_of_scope")
NO_INTENT = "none"        # the case is refused before any intent matters (the first labels leave the intent absent)
DECISIONS = ("block_and_open_case", "confirm", "ask", "answer_status", "connect_person", "handoff", "deny",
             "reauthenticate", "escalate_unconfirmed_action")
YES_NO = ("yes", "no")
FIELDS = ("intent", "decision", "handoff", "case_open")
ALLOWED = {"intent": INTENTS + (NO_INTENT,), "decision": DECISIONS, "handoff": YES_NO, "case_open": YES_NO}
COLUMNS = ["id", "language", "type", "messages", "state", "intent", "decision", "handoff", "case_open", "labeler", "note"]


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _state_summary(case: dict) -> str:
    s = case["initial_state"]
    parts = [f"country {case['country']}", f"segment {case['segment']}", f"session {s['session']}"]
    fixtures = s.get("fixtures", [])
    if not fixtures:
        parts.append("no candidate transactions")
    for i, f in enumerate(fixtures, 1):
        score = "none" if f.get("fraud_score") is None else f["fraud_score"]
        parts.append(f"candidate {i}: {f.get('amount')} {f.get('currency')} on {f.get('transaction_date')}, "
                     f"merchant {f.get('merchant') or 'none'}, product {f.get('product_type')} {f.get('product_id')}, "
                     f"bank fraud_score {score}")
    if s.get("case"):
        c = s["case"]
        parts.append(f"existing case {s.get('case_id')}: {c.get('dispute_type')} on {c.get('transaction_id')}, "
                     f"status {c.get('queue_status')}, opened {c.get('opened_on')}")
    if s.get("tool_faults"):
        parts.append("tool faults: " + ", ".join(s["tool_faults"]))
    return "; ".join(parts)


def _messages(case: dict) -> str:
    return "\n".join(f"[{i}] {m['text']}" for i, m in enumerate(case["messages"], 1))


def export_rows() -> list[dict]:
    rows = []
    for case in _read(DEV):
        rows.append({"id": case["id"], "language": case["language"], "type": case["type"],
                     "messages": _messages(case), "state": _state_summary(case),
                     "intent": "", "decision": "", "handoff": "", "case_open": "", "labeler": "", "note": ""})
    return rows


def export(force: bool = False, path: Path = SHEET) -> Path:
    if path.exists() and not force:
        raise SystemExit(f"{path} exists; use --force to overwrite it (this erases any labels in it)")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(export_rows())
    return path


def first_labels() -> dict[str, dict[str, str]]:
    intents = {p["id"]: p.get("intent") or NO_INTENT for p in _read(PLAN)}
    yn = lambda v: "yes" if v else "no"  # noqa: E731
    labels = {}
    for case in _read(DEV):
        exp = case["expected"]
        labels[case["id"]] = {"intent": intents[case["id"]], "decision": exp["decision"],
                              "handoff": yn(exp["final_state"].get("handoff_emitted", False)),  # absent on status answers: false,
                              "case_open": yn(exp["final_state"]["case_open"])}
    return labels


def cohen_kappa(a: list[str], b: list[str]) -> float:
    """Cohen's kappa for two raters. Degenerate case: when chance agreement is 1 (both raters used one single
    category for every item) the formula is 0/0; it is defined as 1.0, because they agree on every item."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two non-empty lists of the same length")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    if pe == 1:
        return 1.0
    return (po - pe) / (1 - pe)


def read_sheet(path: Path = SHEET) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    expected_ids = [c["id"] for c in _read(DEV)]
    if sorted(r["id"] for r in rows) != sorted(expected_ids):
        raise SystemExit("the sheet must have exactly the 20 dev case ids")
    problems = []
    for r in rows:
        if not (r.get("labeler") or "").strip():
            problems.append(f"{r['id']}: labeler is empty")
        for f in FIELDS:
            v = (r.get(f) or "").strip().lower()
            if not v:
                problems.append(f"{r['id']}: {f} is empty"
                                + (f" (write '{NO_INTENT}' when no intent applies)" if f == "intent" else ""))
            elif v not in ALLOWED[f]:
                problems.append(f"{r['id']}: {f}={v!r} is not one of {', '.join(ALLOWED[f])}")
    if problems:
        raise SystemExit("incomplete or invalid sheet:\n  " + "\n  ".join(problems))
    return {r["id"]: {f: r[f].strip().lower() for f in FIELDS} | {"labeler": r["labeler"].strip()} for r in rows}


def agreement(sheet: Path = SHEET, report: Path | None = REPORT) -> dict:
    second = read_sheet(sheet)
    first = first_labels()
    ids = sorted(first)
    out = {"sample": "dev", "n_cases": len(ids), "labelers": sorted({v["labeler"] for v in second.values()}),
           "fields": {}}
    for f in FIELDS:
        a = [first[i][f] for i in ids]
        b = [second[i][f] for i in ids]
        agree = sum(x == y for x, y in zip(a, b))
        out["fields"][f] = {"n": len(ids), "agreements": agree, "percent_agreement": round(100 * agree / len(ids), 1),
                            "kappa": round(cohen_kappa(a, b), 3),
                            "disagreements": [i for i, x, y in zip(ids, a, b) if x != y]}
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def markdown_table(result: dict) -> str:
    lines = ["| Field | n | Agreements | % agreement | Cohen's kappa | Disagreeing cases |", "|---|---|---|---|---|---|"]
    for f, r in result["fields"].items():
        lines.append(f"| `{f}` | {r['n']} | {r['agreements']} | {r['percent_agreement']} | {r['kappa']} | "
                     f"{', '.join(r['disagreements']) or '-'} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.second_label", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export", help="write the blind sheet with empty labels")
    exp.add_argument("--force", action="store_true", help="overwrite an existing sheet")
    sub.add_parser("agreement", help="compare the filled sheet with the first labels")
    args = parser.parse_args(argv)
    if args.cmd == "export":
        print(f"wrote {export(force=args.force)}")
    else:
        result = agreement()
        print(json.dumps(result, indent=2))
        print(f"\nwrote {REPORT}\n\nPaste into eval/README.md:\n\n{markdown_table(result)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
