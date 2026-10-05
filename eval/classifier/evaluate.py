"""Score the classifier arms, choose τ on validation and export the report (spec 11 T3, T4, T6; AC-02, AC-03, AC-07).

    PYTHONPATH=packages python -m eval.classifier.evaluate --split validation --arms B0,B1   # make classifier
    PYTHONPATH=packages python -m eval.classifier.evaluate --split test --arms B0,B1         # make classifier-test

`validation` is a development run: written only to eval/.runs/classifier/ (git-ignored) and labeled "development run
on validation", never to a path of the protocol's results. `test` is refused unless eval/PROTOCOL.md is SEALED, tagged
protocol-v1 in HEAD's history, and the promoted split files hash to the sealed manifest; it then writes models/intent-b1-v1.joblib, eval/results/classifier.csv
and apps/web/public/data/classifier.json (§7.1), once. B1 is fit on train, calibrated on validation, and τ is the lowest
B1 threshold with precision ≥ 0.95 on validation (AC-07); every arm is reported at that τ [assumption]. Dates resolve
against DEMO_TODAY (replay, ADR 0020).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np

from eval.classifier.review import INTENTS, LANGS, manifest_sha256
from eval.harness.metrics import percentile, wilson
from eval.harness.report import git_sha, now
from nick_of_time import llm
from nick_of_time.config import DEMO_TODAY
from nick_of_time.nlu import injection_flagged, load_nlu
from nick_of_time.nlu.learned import DISPUTES, B1NLU, train_b1
from nick_of_time.nlu.rules import VERSION as B0_VERSION

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.fromisoformat(DEMO_TODAY)
TARGET_PRECISION, ORDER = 0.95, ("B0", "B1", "B3", "B2")
FLOOR_F1, FLOOR_RECALL, P95_MS, USD_PER_1000 = 0.90, 0.95, 1500, 1.0      # eval/PROTOCOL.md §1.3-1.4 [assumption]
DEV_LABEL = "development run on validation: not a test result, never used for selection (eval/PROTOCOL.md §1.1)"
RULE_REVIEW = "test split without independent human review"               # ADR 0025 amendment (rules-v1)
SEAL_TAG = "protocol-v1"                                                  # eval/PROTOCOL.md "Seal": tag of the sealing commit


class EvalError(RuntimeError):
    """The run is refused (unsealed protocol, missing or changed split files, budget)."""


def seal(root: Path = ROOT) -> dict:
    text = (root / "eval" / "PROTOCOL.md").read_text(encoding="utf-8")
    block = re.search(r"^<!-- SEAL:BEGIN -->$(.*?)^<!-- SEAL:END -->$", text, re.M | re.S)
    fields = dict(re.findall(r"^- ([^:\n]+): (.+)$", block.group(1) if block else "", re.M))
    hexed = {k: (v.strip() if re.fullmatch(r"[0-9a-f]{64}", v.strip()) else None) for k, v in fields.items()}
    return {"status": fields.get("Status", "UNSEALED").strip(), "sha256": hexed.get("Protocol sha256"),
            "split_manifest_sha256": hexed.get("Classifier split manifest sha256")}


def protocol_tagged(root: Path = ROOT) -> bool:
    """The seal tag exists, its commit is in HEAD's history and eval/PROTOCOL.md is unchanged since it."""
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    tagged = git("show", f"refs/tags/{SEAL_TAG}:eval/PROTOCOL.md")
    return (tagged.returncode == 0 and git("merge-base", "--is-ancestor", f"refs/tags/{SEAL_TAG}", "HEAD").returncode == 0
            and tagged.stdout == (root / "eval" / "PROTOCOL.md").read_bytes())


def load_splits(split: str, root: Path = ROOT) -> tuple[dict[str, list[dict]], str]:
    """train, validation and the scored split. Test: only the promoted, sealed files. Validation dev runs fall back to
    the human-reviewed drafts while the files are not promoted (review.py applies the decisions; test is never read)."""
    d = root / "eval" / "classifier"
    if split == "test":
        if seal(root)["status"] != "SEALED":
            raise EvalError("refused: eval/PROTOCOL.md is UNSEALED; the test split is scored once, after the seal (M02)")
        if not protocol_tagged(root):
            raise EvalError(f"refused: no {SEAL_TAG} tag in HEAD's history with this eval/PROTOCOL.md (M02 tags it)")
        blobs = {f"eval/classifier/{s}.jsonl": (d / f"{s}.jsonl").read_bytes() for s in ("train", "validation", "test")
                 if (d / f"{s}.jsonl").exists()}
        if len(blobs) != 3 or manifest_sha256(blobs) != seal(root)["split_manifest_sha256"]:
            raise EvalError("refused: the promoted split files are missing or differ from the sealed manifest")
    names = ("train", "validation") + (("test",) if split == "test" else ())
    if all((d / f"{s}.jsonl").exists() for s in names):
        rows = {s: [json.loads(x) for x in (d / f"{s}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
                for s in names}
        return rows, "promoted split files"
    from eval.classifier.review import _reviewed
    return {s: _reviewed(root, s) for s in names}, "human-reviewed drafts (split files not promoted yet)"


def run_arm(nlu, rows: list[dict]) -> list[dict]:
    """One reading per row; a provider error or no valid tool input is `intent=None` (wrong, D-022)."""
    out = []
    for r in rows:
        t0 = time.perf_counter()
        try:
            res = nlu.parse(r["text"], today=TODAY)
            p = {"intent": res.intent, "confidence": res.confidence, "dispute": res.dispute_detected,
                 "slots": res.slots.model_dump()}
        except llm.LLMError:
            p = {"intent": None, "confidence": 0.0, "dispute": False, "slots": {}}
        last = getattr(nlu, "last", None)
        p["ms"] = (time.perf_counter() - t0) * 1000
        p["cost"] = (last.cost_usd or 0.0) if last is not None else 0.0
        out.append(p)
    return out


def rate(num: int, den: int) -> dict:
    lo, hi = wilson(num, den)
    r4 = (lambda x: None if x is None else round(x, 4))
    return {"value": r4(num / den) if den else None, "numerator": num, "denominator": den, "ci_low": r4(lo),
            "ci_high": r4(hi)}


def f1_scores(gold: list[str], pred: list) -> tuple[dict, float]:
    per = {}
    for c in INTENTS:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp, fn = sum(g != c and p == c for g, p in zip(gold, pred)), sum(g == c and p != c for g, p in zip(gold, pred))
        per[c] = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0
    return per, sum(per.values()) / len(per)


def bootstrap_ci(gold: list[str], pred: list, n: int = 2000, seed: int = 11) -> list:
    rng, idx = np.random.default_rng(seed), np.arange(len(gold))
    vals = [f1_scores([gold[i] for i in s], [pred[i] for i in s])[1] for s in rng.choice(idx, (n, len(idx)))]
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def ece(conf: list[float], correct: list[bool], bins: int = 10) -> float:
    total = 0.0
    for b in range(bins):
        cell = [i for i, c in enumerate(conf) if b / bins < c <= (b + 1) / bins or (b == 0 and c == 0)]
        if cell:
            total += len(cell) * abs(np.mean([correct[i] for i in cell]) - np.mean([conf[i] for i in cell]))
    return round(total / len(conf), 4) if conf else None


def slot_ok(gold: dict, pred: dict) -> bool:
    """All four slots right [assumption]: amount numerically, merchant ignoring case and spaces, the rest exactly."""
    def amount(x):
        try:
            return Decimal(x) if x else None
        except InvalidOperation:
            return x
    norm = (lambda m: " ".join(m.casefold().split()) if m else None)
    return (amount(gold.get("amount")) == amount(pred.get("amount")) and gold.get("currency") == pred.get("currency")
            and gold.get("date") == pred.get("date") and norm(gold.get("merchant")) == norm(pred.get("merchant")))


def choose_tau(conf: list[float], correct: list[bool]) -> float | None:
    """AC-07: the lowest threshold whose accepted messages keep precision ≥ 0.95; None when no threshold does."""
    for t in sorted(set(round(c, 4) for c in conf)):
        ok = [k for c, k in zip(conf, correct) if c >= t]
        if ok and sum(ok) / len(ok) >= TARGET_PRECISION:
            return t
    return None


def by_language(rows: list[dict], preds: list[dict], tau: float | None) -> dict:
    out = {}
    for lang in LANGS:
        ix = [i for i, r in enumerate(rows) if r["language"] == lang]
        gold, pred = [rows[i]["intent"] for i in ix], [preds[i]["intent"] for i in ix]
        per, macro = f1_scores(gold, pred)
        disp = [i for i in ix if rows[i]["intent"] in DISPUTES]
        flag = [i for i in ix if rows[i]["intent"] in DISPUTES or rows[i].get("also_dispute")]
        human = [i for i in ix if rows[i]["intent"] == "human_request"]
        acc = [i for i in ix if tau is not None and preds[i]["confidence"] >= tau]
        out[lang] = {
            "macro_f1": round(macro, 4), "macro_f1_ci": bootstrap_ci(gold, pred),
            "per_class_f1": {c: round(v, 4) for c, v in per.items()},
            "dispute_recall": rate(sum(preds[i]["intent"] in DISPUTES for i in disp), len(disp)),
            "dispute_detected_recall": rate(sum(preds[i]["dispute"] for i in flag), len(flag)),
            "human_request_recall": rate(sum(preds[i]["intent"] == "human_request" for i in human), len(human)),
            "slot_accuracy": rate(sum(slot_ok(rows[i]["slots"], preds[i]["slots"]) for i in disp), len(disp)),
            "ece": ece([preds[i]["confidence"] for i in ix], [g == p for g, p in zip(gold, pred)]),
            "coverage_at_tau": rate(len(acc), len(ix)),
            "precision_at_tau": rate(sum(rows[i]["intent"] == preds[i]["intent"] for i in acc), len(acc))}
    return out


def family(model_id: str | None) -> str | None:
    """Vendor of a Bedrock model id, region prefix dropped: us.anthropic.claude-... -> anthropic."""
    parts = (model_id or "").split(".")
    return parts[1] if parts[0] in ("us", "eu", "apac", "global") and len(parts) > 1 else parts[0] or None


def score_arm(arm: str, nlu, rows: list[dict], preds: list[dict], tau: float | None) -> dict:
    ms, n = [p["ms"] for p in preds], len(preds)
    langs = by_language(rows, preds, tau)
    floors = all(langs[g]["macro_f1"] >= FLOOR_F1 and (langs[g][k]["value"] or 0) >= FLOOR_RECALL
                 for g in LANGS for k in ("dispute_recall", "human_request_recall"))
    floors = floors and all((langs[g]["precision_at_tau"]["value"] or 0) >= TARGET_PRECISION for g in LANGS)
    authors = {family(r.get("author")) for r in rows}
    return {"arm": arm, "version": getattr(nlu, "version", B0_VERSION),
            "p50_ms": round(percentile(ms, 0.5), 2), "p95_ms": round(percentile(ms, 0.95), 2),
            "cost_per_1000_usd": round(sum(p["cost"] for p in preds) / n * 1000, 4), "meets_floors": floors,
            "mcnemar_p_vs_best": None,
            "human_request_answered_out_of_scope": sum(r["intent"] == "human_request" and p["intent"] == "out_of_scope"
                                                       for r, p in zip(rows, preds)),
            "missing_tool_calls": sum(p["intent"] is None for p in preds),
            "same_family_as_generator": hasattr(nlu, "client") and family(nlu.version) in authors,   # LLM arms only
            "by_language": langs}


def mcnemar(a: list[bool], b: list[bool]) -> float:
    """Exact two-sided McNemar on the discordant pairs (Dietterich 1998)."""
    x, y = sum(i and not j for i, j in zip(a, b)), sum(j and not i for i, j in zip(a, b))
    n = x + y
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(x, y) + 1)) / 2 ** n)


def choose(arms: list[dict], correct: dict[str, list[bool]]) -> str | None:
    """Spec 11 §4.1 rules 1-4: floors, p95 and cost; simplest arm not significantly worse than the best; B0 stays when
    no learned arm beats it with significance. The best arm is the most accurate eligible one [assumption]."""
    eligible = [a["arm"] for a in arms if a["meets_floors"] and a["p95_ms"] <= P95_MS
                and a["cost_per_1000_usd"] <= USD_PER_1000]
    best = max(eligible or list(correct), key=lambda a: sum(correct[a]))
    for a in arms:
        a["mcnemar_p_vs_best"] = round(mcnemar(correct[a["arm"]], correct[best]), 4)
    if "B0" in correct and not any(sum(correct[a]) > sum(correct["B0"]) and mcnemar(correct[a], correct["B0"]) < 0.05
                                   for a in eligible if a != "B0"):
        return "B0"
    keep = [a for a in eligible if mcnemar(correct[a], correct[best]) >= 0.05 or a == best]
    return min(keep, key=ORDER.index) if keep else None


def evaluate(split: str, arms: list[str], root: Path = ROOT) -> Path:
    data, source = load_splits(split, root)
    intent_rows = {s: [r for r in v if r.get("label") != "injection" and r.get("intent")] for s, v in data.items()}
    train, val, scored = intent_rows["train"], intent_rows["validation"], intent_rows[split]
    b1 = B1NLU(train_b1([r["text"] for r in train], [r["intent"] for r in train],
                        [r["text"] for r in val], [r["intent"] for r in val]))
    val_preds = run_arm(b1, val)
    tau = choose_tau([p["confidence"] for p in val_preds], [r["intent"] == p["intent"] for r, p in zip(val, val_preds)])
    nlus = {"B0": load_nlu("B0"), "B1": b1}
    out_dir = (root / "apps/web/public/data") if split == "test" else root / "eval/.runs/classifier" / now().replace(":", "")
    model_dir = (root / "models") if split == "test" else out_dir
    model_dir.mkdir(parents=True, exist_ok=True)
    b1.save(model_dir / "intent-b1-v1.joblib")                 # frozen before the scored split is read (§0 rule 1)
    preds = {a: (val_preds if a == "B1" and split == "validation" else run_arm(nlus[a], scored)) for a in arms}
    report = [score_arm(a, nlus[a], scored, preds[a], tau) for a in arms]
    correct = {a: [r["intent"] == p["intent"] for r, p in zip(scored, preds[a])] for a in arms}
    chosen = choose(report, correct)
    inj = [injection_flagged(r["text"]) for r in data[split] if r.get("label") == "injection"]
    legit = [injection_flagged(r["text"]) for r in scored]
    s = seal(root)
    payload = {"label": "[simulated]", "protocol": s, "run": "test" if split == "test" else DEV_LABEL,
               "split_source": source, f"{split}_split": {"sentences": {g: sum(r["language"] == g for r in scored)
                                                                       for g in LANGS}, "injection_rows": len(inj)},
               "tau": tau, "chosen_arm": chosen, "arms": report,
               "injection": [{"arm": "rules", "recall": rate(sum(inj), len(inj)),
                              "false_positive_rate": rate(sum(legit), len(legit))}]}
    if split == "test" and any(r.get("reviewer") == "rules-v1" for r in data["test"]):
        payload["review_note"] = RULE_REVIEW
    doc = {"generated_at": now(), "git_sha": git_sha(), "data": payload,
           "source": f"eval/classifier/evaluate.py [simulated], {split} split ({source})"}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "classifier.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if split == "test":
        write_csv(root / "eval/results/classifier.csv", report)
    return out_dir / "classifier.json"


def write_csv(path: Path, report: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["label", "arm", "language", "metric", "value"])
        for a in report:
            for lang, m in a["by_language"].items():
                for k, v in m.items():
                    v = v["value"] if isinstance(v, dict) and "value" in v else v   # a rate keeps its value
                    w.writerow(["[simulated]", a["arm"], lang, k, json.dumps(v) if isinstance(v, (dict, list)) else v])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--split", choices=("validation", "test"), default="validation")
    ap.add_argument("--arms", default="B0,B1")
    args = ap.parse_args(argv)
    try:
        path = evaluate(args.split, [a.strip() for a in args.arms.split(",")])
    except EvalError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
