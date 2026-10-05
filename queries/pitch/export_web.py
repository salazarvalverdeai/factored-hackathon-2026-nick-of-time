"""Exports the pitch numbers to the static JSON that `/analytics` reads (spec 01 §6.2, "Insight data for web pages").

    python queries/pitch/export_web.py

Reads only the `pNN_*.csv` files next to this script (no dataset access) and writes
apps/web/public/data/pitch_numbers.json as `{generated_at, git_sha, source, data}`.
"""
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "apps" / "web" / "public" / "data" / "pitch_numbers.json"

# Zone actions follow contracts/policies.yaml (approval.per_action and actions).
ZONES = [
    ("high", "High zone", "score ≥ 50", "Block the card, verify, open the case"),
    ("medium", "Medium zone", "score 30–49", "The customer confirms; an analyst approves the block"),
    ("human", "Human zone", "score < 30", "Open the case and hand off to an analyst"),
    ("human_no_score", "Human zone", "no score", "Open the case and hand off to an analyst"),
]


def rows(name):
    with open(HERE / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(value):
    f = float(value)
    return int(f) if f.is_integer() else f


def groups(name, value_col, extra):
    """Complaint contacts first, whole bank second, as in the CSVs."""
    labels = ("Complaint contacts", "Whole bank")
    return [{"name": label, "value": num(r[value_col]), **{k: num(r[c]) for k, c in extra.items()}}
            for label, r in zip(labels, rows(name), strict=True)]


def build():
    share = {k: num(v) for k, v in rows("p01_w3_share_complaints.csv")[0].items()}
    ratio = {"numerator": None, "denominator": "denominator", "ci_low": "ci95_low", "ci_high": "ci95_high"}
    contacts = [
        {"key": "fcr", "label": "Resolved at first contact (FCR)", "unit": "%", "scale_max": 100, "query": "p02",
         "groups": groups("p02_fcr_complaint_vs_bank.csv", "fcr_pct", {**ratio, "numerator": "n_resolved"})},
        {"key": "follow_up", "label": "Requires follow-up", "unit": "%", "scale_max": 100, "query": "p03",
         "groups": groups("p03_complaint_follow_up.csv", "follow_up_pct", {**ratio, "numerator": "n_follow_up"})},
        {"key": "duration", "label": "Median contact duration", "unit": "min", "scale_max": 10, "query": "p04",
         "groups": groups("p04_complaint_duration_vs_bank.csv", "duration_p50_min", {"denominator": "n_with_duration"})},
    ]
    thr = rows("p08_fraud_score_thresholds.csv")
    thresholds = [{k: num(r[k]) for k in ("threshold", "n_flagged", "n_frauds_flagged", "precision_pct",
                                          "recall_with_score_pct", "recall_all_frauds_pct")} for r in thr]
    total, scored = int(thr[0]["n_frauds_all"]), int(thr[0]["n_frauds_with_score"])
    by_thr = {int(r["threshold"]): int(r["n_frauds_flagged"]) for r in thr}
    no_score = int(rows("p07_fraud_per_month.csv")[0]["n_frauds_without_score"])
    assert scored + no_score == total
    counts = [by_thr[50], by_thr[30] - by_thr[50], scored - by_thr[30], no_score]
    zones = [{"key": key, "zone": zone, "range": rng, "action": action, "n": n, "pct": round(100 * n / total, 1)}
             for (key, zone, rng, action), n in zip(ZONES, counts, strict=True)]
    return {"share": share, "contacts": contacts, "thresholds": thresholds,
            "frauds": {"total": total, "with_score": scored, "without_score": no_score, "zones": zones}}


if __name__ == "__main__":
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": sha,
        "source": "queries/pitch/*.csv [data] — full synthetic dataset, see queries/README.md",
        "data": build(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
