"""B1 table, lean-rule selection, Pareto chart and web export (spec 15 T5 T6: AC-03, AC-04, AC-07). Computes only from
the per-sentence items of `b1.run`; the lean rule is eval/PROTOCOL.md §2.3 for the `understand` task."""
from __future__ import annotations

import math
import random
from typing import get_args

from eval.harness.metrics import percentile, wilson
from nick_of_time.contracts import Intent

INTENTS, LANGS = get_args(Intent), ("es", "pt")
DISPUTES = {"unrecognized_charge", "wrongful_charge"}
MACRO_F1_FLOOR, RECALL_FLOOR, P95_LIMIT_MS, ALPHA = 0.90, 0.95, 1500, 0.05     # PROTOCOL §1.3 and §2.3 [assumption]
NO_LLM = ("b0_rules", "b1_tfidf_lr")
BOOTSTRAP, SEED = 1000, 15


def _r(x, d=4):
    return None if x is None else round(x, d)


def rate(num: int, den: int) -> dict:
    lo, hi = wilson(num, den)
    return {"value": _r(num / den) if den else None, "numerator": num, "denominator": den, "ci_low": _r(lo),
            "ci_high": _r(hi)}


def macro_f1(items: list[dict]) -> float | None:
    f1 = []
    for c in INTENTS:
        tp = sum(i["gold"] == c and i["pred"] == c for i in items)
        miss = sum((i["gold"] == c) != (i["pred"] == c) for i in items)
        if tp + miss:
            f1.append(2 * tp / (2 * tp + miss))
    return sum(f1) / len(f1) if f1 else None


def bootstrap_ci(items: list[dict], rng: random.Random) -> list:
    if not items:
        return [None, None]
    stats = sorted(macro_f1([rng.choice(items) for _ in items]) or 0.0 for _ in range(BOOTSTRAP))
    return [_r(stats[int(0.025 * BOOTSTRAP)]), _r(stats[int(0.975 * BOOTSTRAP) - 1])]


def _same(field: str, gold, pred) -> bool:
    if pred is None:
        return False
    if field == "amount":
        try:
            return math.isclose(float(gold), float(pred))
        except (TypeError, ValueError):
            return False
    return str(gold).strip().casefold() == str(pred).strip().casefold()


def recall(items: list[dict], wanted: set) -> dict:
    hits = [i["pred"] in wanted for i in items if i["gold"] in wanted]
    return rate(sum(hits), len(hits))


def arm_metrics(row: dict) -> dict:
    """AC-03 for one arm: accuracy and recalls as rate objects (95% Wilson), macro-F1 per language with a 95%
    bootstrap CI, slot accuracy over the gold slots that are set [assumption], latency and cost per 1,000 messages."""
    items, rng = row["items"], random.Random(SEED)
    by = {lang: [i for i in items if i["language"] == lang] for lang in LANGS}
    slots = [_same(f, g, i["pred_slots"].get(f)) for i in items for f, g in i["gold_slots"].items() if g is not None]
    lat = [i["latency_ms"] for i in items if i["latency_ms"] is not None]
    return {"accuracy": rate(sum(i["pred"] == i["gold"] for i in items), len(items)),
            "macro_f1": {lang: _r(macro_f1(v)) for lang, v in by.items()},
            "macro_f1_ci": {lang: bootstrap_ci(v, rng) for lang, v in by.items()},
            "dispute_recall": recall(items, DISPUTES), "human_request_recall": recall(items, {"human_request"}),
            "recall_by_language": {lang: {"dispute": recall(v, DISPUTES)["value"],
                                          "human_request": recall(v, {"human_request"})["value"]} for lang, v in by.items()},
            "slot_accuracy": rate(sum(slots), len(slots)),
            "missing_tool_calls": sum(not i["tool_call"] for i in items),
            "p50_ms": percentile(lat, 0.5), "p95_ms": percentile(lat, 0.95),
            "cost_per_1000_usd": _r(1000 * sum(i["cost_usd"] for i in items) / len(items), 6) if items else None,
            "cost_usd": _r(sum(i["cost_usd"] for i in items), 6)}


def mcnemar(a: list[bool], b: list[bool]) -> float:
    """Exact two-sided McNemar p-value on paired correctness of the same sentences."""
    only_a, only_b = sum(x and not y for x, y in zip(a, b)), sum(y and not x for x, y in zip(a, b))
    n = only_a + only_b
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(only_a, only_b) + 1)) / 2 ** n)


def hard_limit_failures(m: dict) -> list[str]:
    out = [f"macro-F1 {lang} below {MACRO_F1_FLOOR}" for lang in LANGS if (m["macro_f1"][lang] or 0) < MACRO_F1_FLOOR]
    out += [f"{k} recall {lang} below {RECALL_FLOOR}" for lang in LANGS for k, v in m["recall_by_language"][lang].items()
            if (v or 0) < RECALL_FLOOR]
    return out + ([f"p95 above {P95_LIMIT_MS} ms"] if (m["p95_ms"] or 0) > P95_LIMIT_MS else [])


def measured_quality(gate_rows: list[dict], rows: list[dict], evidence: str) -> None:
    """`es_pt_quality` (spec 15 §4.5, D-012) is measured by this run: pass when an arm meets the macro-F1 floor in
    both languages; an arm the run could not measure stays "not documented"."""
    floors = {r["arm"]: all((r["metrics"]["macro_f1"][lang] or 0) >= MACRO_F1_FLOOR for lang in LANGS)
              for r in rows if r.get("metrics")}
    for g in gate_rows:
        if g["criterion"] == "es_pt_quality" and g["arm"] in floors:
            g.update(verdict="pass" if floors[g["arm"]] else "fail", evidence_url=evidence)


def select(rows: list[dict], production: dict[str, bool]) -> dict:
    """PROTOCOL §2.3 for `understand`: hard limits, not significantly worse than the best (McNemar p >= 0.05),
    cheapest (tie: lower p95), production gate, then rule 5 (an LLM arm must beat B0 with significance).
    Fills `meets_bar`, `pareto` and `mcnemar_p_vs_best` on each measured row and returns the model map entry.
    [assumption] "best" = the highest intent accuracy, the quantity McNemar compares."""
    ok = [r for r in rows if r["status"] == "ok" and r["items"]]
    if not ok:
        return {"best_measured": None, "cheapest_meeting_bar": None, "chosen": "b0_rules", "notes": ["no arm measured"]}
    correct = {r["arm"]: [i["pred"] == i["gold"] for i in r["items"]] for r in ok}
    acc = {r["arm"]: r["metrics"]["accuracy"]["value"] for r in ok}
    cost = {r["arm"]: r["metrics"]["cost_per_1000_usd"] for r in ok}
    best = max(ok, key=lambda r: (acc[r["arm"]], -cost[r["arm"]]))["arm"]
    for r in ok:
        r["hard_limits_failed"] = hard_limit_failures(r["metrics"])
        r["mcnemar_p_vs_best"] = _r(mcnemar(correct[best], correct[r["arm"]]))
        r["meets_bar"] = not r["hard_limits_failed"] and (r["arm"] == best or r["mcnemar_p_vs_best"] >= ALPHA)
        r["pareto"] = not any(cost[o["arm"]] <= cost[r["arm"]] and acc[o["arm"]] >= acc[r["arm"]]
                              and (cost[o["arm"]], acc[o["arm"]]) != (cost[r["arm"]], acc[r["arm"]]) for o in ok)
    bar = sorted((r for r in ok if r["meets_bar"]), key=lambda r: (cost[r["arm"]], r["metrics"]["p95_ms"] or 0))
    gated = [r["arm"] for r in bar if r["arm"] in NO_LLM or production.get(r["arm"])]
    notes = [f"{r['arm']} meets the bar but fails the production gate" for r in bar if r["arm"] not in gated]
    chosen = gated[0] if gated else None
    if "b0_rules" in correct and chosen not in NO_LLM:
        beats = [a for a in correct if a not in NO_LLM and acc[a] > acc["b0_rules"]
                 and mcnemar(correct["b0_rules"], correct[a]) < ALPHA]
        if chosen is None:   # [assumption] §2.3 does not say what happens when no arm meets rule 1
            notes.append("no arm meets the hard limits and the bar: the no-LLM option B0 stays")
        elif chosen not in beats:
            notes.append(f"{chosen} does not beat B0 with significance: B0 stays (rule 5)")
        chosen = "b0_rules" if chosen is None or chosen not in beats else chosen
    return {"best_measured": best, "cheapest_meeting_bar": bar[0]["arm"] if bar else None,
            "chosen": chosen or "none", "notes": notes}


def table(rows: list[dict]) -> str:
    """AC-03 as Markdown: one line per arm, unavailable arms with their reason."""
    head = ("| Arm | Status | Accuracy [95% CI] | Macro-F1 es / pt | Dispute recall | Person recall | Slot acc. | "
            "No tool call | p50 / p95 ms | USD per 1k | Bar | Pareto |\n|" + "---|" * 12)
    lines = [head]
    for r in sorted(rows, key=lambda r: -r["metrics"]["accuracy"]["value"] if r.get("metrics") else 1):
        m = r.get("metrics")
        if not m:
            lines.append(f"| {r['arm']} | {r['status']}: {(r.get('reason') or '')[:80]} |" + " |" * 10)
            continue
        a, f = m["accuracy"], m["macro_f1"]
        lines.append(f"| {r['arm']} | ok | {a['value']} [{a['ci_low']}, {a['ci_high']}] | {f['es']} / {f['pt']} | "
                     f"{m['dispute_recall']['value']} | {m['human_request_recall']['value']} | "
                     f"{m['slot_accuracy']['value']} | {m['missing_tool_calls']} | {m['p50_ms']} / {m['p95_ms']} | "
                     f"{m['cost_per_1000_usd']} | {'yes' if r.get('meets_bar') else 'no'} | "
                     f"{'yes' if r.get('pareto') else 'no'} |")
    return "\n".join(lines) + "\n"
