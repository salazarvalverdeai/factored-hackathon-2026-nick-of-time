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
NO_SLOTS = ("jev",)               # Jev answers one typed choice, the intent only (b1.jev_items): slot accuracy is n/a
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
    bootstrap CI, slot accuracy over the gold slots that are set [assumption] (an empty rate, shown n/a, for an arm
    that returns no slots), latency and cost per 1,000 messages. A sentence whose call failed (`error`, spec 15 §4.1)
    is wrong and counted in `errors`, not again in `missing_tool_calls`."""
    items, rng = row["items"], random.Random(SEED)
    by = {lang: [i for i in items if i["language"] == lang] for lang in LANGS}
    slots = [] if row.get("arm") in NO_SLOTS else [
        _same(f, g, (i["pred_slots"] or {}).get(f)) for i in items for f, g in i["gold_slots"].items() if g is not None]
    lat = [i["latency_ms"] for i in items if i["latency_ms"] is not None]
    return {"accuracy": rate(sum(i["pred"] == i["gold"] for i in items), len(items)),
            "macro_f1": {lang: _r(macro_f1(v)) for lang, v in by.items()},
            "macro_f1_ci": {lang: bootstrap_ci(v, rng) for lang, v in by.items()},
            "dispute_recall": recall(items, DISPUTES), "human_request_recall": recall(items, {"human_request"}),
            "recall_by_language": {lang: {"dispute": recall(v, DISPUTES)["value"],
                                          "human_request": recall(v, {"human_request"})["value"]} for lang, v in by.items()},
            "slot_accuracy": rate(sum(slots), len(slots)),
            "missing_tool_calls": sum(not i["tool_call"] and not i.get("error") for i in items),
            "errors": sum(bool(i.get("error")) for i in items),
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


# [assumption] How this code reads PROTOCOL §2.3 where it is silent (lead decision D-077 pending; recommended
# reading). Flip SELECTION_READING if the lead picks the other one; every output names the reading it used.
#  - rule 2, "the best arm": "among_passing" takes the best among the arms that pass rule 1 (spec 11 §4, "among the
#    rest"); "all_measured" takes the best of every measured arm, even one that fails a hard limit.
#  - every arm fails rule 1, or none that meets the bar passes the production gate: §2.3 does not say; B0 rules stays
#    (the no-LLM option, PROTOCOL §0.3) and the output says so.
#  - no arm measured at all: no arm is chosen ("none") and the command refuses, instead of naming B0 unmeasured.
#  - rule 5 is coded as written: B0 stays when NO LLM arm beats it with significance (not only the chosen arm).
SELECTION_READING = "among_passing"
READINGS = {
    "among_passing": "the best arm of rule 2 is chosen among the arms that pass rule 1 (spec 11 §4, among the rest)",
    "all_measured": "the best arm of rule 2 is the best of every measured arm, including arms that fail rule 1"}
ASSUMPTION = "[assumption] D-077 pending"


def select(rows: list[dict], production: dict[str, bool], reading: str | None = None) -> dict:
    """PROTOCOL §2.3 for `understand`: (1) hard limits, (2) not significantly worse than the best (McNemar p >= 0.05),
    (3) cheapest (tie: lower p95), (4) production gate, (5) if no LLM arm beats B0 with significance, B0 stays.
    Fills `hard_limits_failed`, `meets_bar`, `pareto` and `mcnemar_p_vs_best` on each measured row and returns the
    model map entry with `chosen_by` and the `reading` of SELECTION_READING it used. [assumption] "best" = the highest
    intent accuracy, the quantity McNemar compares; the readings where §2.3 is silent are those of SELECTION_READING."""
    reading = reading or SELECTION_READING
    if reading not in READINGS:
        raise ValueError(f"unknown selection reading {reading!r}; known: {sorted(READINGS)}")
    base = {"reading": reading, "reading_label": f"{ASSUMPTION}: {READINGS[reading]}"}
    ok = [r for r in rows if r["status"] == "ok" and r["items"]]
    if not ok:
        return {**base, "best_measured": None, "bar_reference": None, "cheapest_meeting_bar": None, "chosen": "none",
                "chosen_by": "refused: no arm was measured, so no arm is chosen", "refused": True,
                "notes": ["no arm was measured: the command refuses to name a model map"]}
    correct = {r["arm"]: [i["pred"] == i["gold"] for i in r["items"]] for r in ok}
    acc = {r["arm"]: r["metrics"]["accuracy"]["value"] for r in ok}
    cost = {r["arm"]: r["metrics"]["cost_per_1000_usd"] for r in ok}

    def top(cands: list[dict]) -> str | None:
        return max(cands, key=lambda r: (acc[r["arm"]], -cost[r["arm"]]))["arm"] if cands else None

    for r in ok:
        r["hard_limits_failed"] = hard_limit_failures(r["metrics"])
    passing = [r for r in ok if not r["hard_limits_failed"]]
    best = top(ok)
    reference = top(passing) if reading == "among_passing" else best
    for r in ok:
        r["mcnemar_p_vs_best"] = _r(mcnemar(correct[reference or best], correct[r["arm"]]))
        r["meets_bar"] = (not r["hard_limits_failed"] and reference is not None
                          and (r["arm"] == reference or r["mcnemar_p_vs_best"] >= ALPHA))
        r["pareto"] = not any(cost[o["arm"]] <= cost[r["arm"]] and acc[o["arm"]] >= acc[r["arm"]]
                              and (cost[o["arm"]], acc[o["arm"]]) != (cost[r["arm"]], acc[r["arm"]]) for o in ok)
    bar = sorted((r for r in ok if r["meets_bar"]), key=lambda r: (cost[r["arm"]], r["metrics"]["p95_ms"] or 0))
    gated = [r["arm"] for r in bar if r["arm"] in NO_LLM or production.get(r["arm"])]
    notes = [f"{r['arm']} meets the bar but fails the production gate" for r in bar if r["arm"] not in gated]
    chosen, chosen_by = (gated[0], "rules 1-4") if gated else (None, None)
    llm_beats = [a for a in correct if a not in NO_LLM and "b0_rules" in correct and acc[a] > acc["b0_rules"]
                 and mcnemar(correct["b0_rules"], correct[a]) < ALPHA]
    if "b0_rules" in correct and chosen not in NO_LLM and not llm_beats:
        chosen, chosen_by = "b0_rules", "rule 5: no LLM arm beats B0 with significance, B0 stays"
    elif chosen is None:
        why = "every measured arm fails rule 1 (hard limits)" if not passing else \
            "no arm meets the bar and passes the production gate"
        chosen, chosen_by = "b0_rules", f"{ASSUMPTION}: fallback not in PROTOCOL §2.3 ({why}): the no-LLM option B0 stays"
        if "b0_rules" not in correct:
            notes.append("B0 rules was not measured in this run; it stays as the no-LLM default")
    notes.append(f"chosen by {chosen_by}")
    return {**base, "best_measured": best, "bar_reference": reference,
            "cheapest_meeting_bar": bar[0]["arm"] if bar else None, "chosen": chosen, "chosen_by": chosen_by,
            "refused": False, "notes": notes}


def selection_md(model_map: dict) -> str:
    """The model map and the selection reading as Markdown, for bench_b1.md (AC-07)."""
    lines = ["## Model map (`understand`, PROTOCOL §2.3)", "",
             f"- Best measured: `{model_map.get('best_measured')}`",
             f"- Best arm for the bar (rule 2): `{model_map.get('bar_reference')}`",
             f"- Cheapest that meets the bar: `{model_map.get('cheapest_meeting_bar')}`",
             f"- Chosen: `{model_map.get('chosen')}` ({model_map.get('chosen_by')})",
             f"- Reading: {model_map.get('reading_label')}"]
    lines += [f"- Note: {n}" for n in model_map.get("notes", [])]
    return "\n".join(lines) + "\n"


def _na(value) -> str:
    return "n/a" if value is None else str(value)


def _errors(row: dict, m: dict) -> str:
    """Failed sentences of the arm, with their error classes (b1 `errors`) when known."""
    by_class = row.get("errors") or {}
    return f"{m.get('errors', 0)}" + (f" ({', '.join(f'{k} {v}' for k, v in sorted(by_class.items()))})"
                                      if by_class else "")


def table(rows: list[dict]) -> str:
    """AC-03 as Markdown: one line per arm, unavailable arms with their reason."""
    head = ("| Arm | Status | Accuracy [95% CI] | Macro-F1 es / pt | Dispute recall | Person recall | Slot acc. | "
            "No tool call | Errors | p50 / p95 ms | USD per 1k | Bar | Pareto |\n|" + "---|" * 13)
    lines = [head]
    for r in sorted(rows, key=lambda r: -r["metrics"]["accuracy"]["value"] if r.get("metrics") else 1):
        m = r.get("metrics")
        if not m:
            lines.append(f"| {r['arm']} | {r['status']}: {(r.get('reason') or '')[:80]} |" + " |" * 11)
            continue
        a, f = m["accuracy"], m["macro_f1"]
        lines.append(f"| {r['arm']} | ok | {a['value']} [{a['ci_low']}, {a['ci_high']}] | {f['es']} / {f['pt']} | "
                     f"{m['dispute_recall']['value']} | {m['human_request_recall']['value']} | "
                     f"{_na(m['slot_accuracy']['value'])} | {m['missing_tool_calls']} | {_errors(r, m)} | "
                     f"{m['p50_ms']} / {m['p95_ms']} | "
                     f"{m['cost_per_1000_usd']} | {'yes' if r.get('meets_bar') else 'no'} | "
                     f"{'yes' if r.get('pareto') else 'no'} |")
    return "\n".join(lines) + "\n"
