"""B1 benchmark command (spec 15: AC-01, AC-03, AC-04, AC-07). From the repo root, with PYTHONPATH=.:packages:

    python -m eval.bench --split test                       # make bench: the pre-registered run, only when SEALED
    python -m eval.bench --split validation [--limit N]     # make bench-dev: development run, git-ignored output
    ... [--provider bedrock|fake] [--arms a,b] [--dry-run]  # --dry-run prints the [projected] spend and stops

Only the test split writes the result files of spec 15 §4.5 (eval/results/, benchmark.json, the SVG), and it refuses
to run unless eval/PROTOCOL.md is SEALED and tagged `protocol-v1` on the merged sealing commit. Every other run goes to eval/.runs/bench/, labeled a development run, so
no result path of the seal guard exists before the seal.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from eval.bench import b1, chart, core, gate, report
from eval.harness.report import git_sha, now, protocol_seal

ROOT = b1.ROOT
PROTOCOL_TAG = "protocol-v1"            # set by the lead on the merged sealing commit (eval/PROTOCOL.md "Seal")
DEV_LABEL = "development run on validation — not the pre-registered test result"
OFFICIAL = {"csv": "eval/results/bench_b1.csv", "items": "eval/results/bench_b1_items.jsonl",
            "gate": "eval/results/bench_gate.csv", "table": "eval/results/bench_b1.md",
            "json": "apps/web/public/data/benchmark.json", "svg": "docs/assets/benchmark_cost_quality.svg"}
CSV_FIELDS = ["arm", "status", "reason", "model_id", "version", "prompt_hash", "tool_choice_mode", "temperature",
              "price_input_per_1m", "price_output_per_1m", "price_status", "price_source_url", "price_checked_on",
              "run_date", "accuracy", "accuracy_ci_low", "accuracy_ci_high", "macro_f1_es", "macro_f1_pt",
              "dispute_recall", "human_request_recall", "slot_accuracy", "missing_tool_calls", "p50_ms", "p95_ms",
              "cost_per_1000_usd", "meets_bar", "pareto", "mcnemar_p_vs_best", "same_family_as_generator"]


def protocol_tagged(tag: str = PROTOCOL_TAG) -> bool:
    """The seal is final only once the lead tags it: `protocol-v1` must exist, be an ancestor of HEAD (the merged
    sealing commit) and carry the same eval/PROTOCOL.md as HEAD."""
    def ok(*cmd: str) -> bool:
        return subprocess.run(["git", *cmd], cwd=ROOT, capture_output=True).returncode == 0
    return (ok("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}") and ok("merge-base", "--is-ancestor", tag, "HEAD")
            and ok("diff", "--quiet", tag, "HEAD", "--", "eval/PROTOCOL.md"))


def vendor(model_id: str | None) -> str | None:
    return model_id.removeprefix("us.").split(".")[0] if model_id else None


def generator(split: str) -> str | None:
    meta = json.loads((ROOT / "eval/classifier/draft/generation.json").read_text(encoding="utf-8"))
    return meta["generators"].get(split, {}).get("model_id")


def export(rows, gate_rows, model_map, prices, split, seal, run_date, provider) -> dict:
    """`{generated_at, git_sha, source, data}` with `data` in the shape of spec 15 §7.1."""
    by_arm = {}
    for g in gate_rows:
        by_arm.setdefault(g["arm"], []).append(g)
    verdicts, arms = gate.summary(gate_rows), []
    for r in rows:
        m, p, v = r.get("metrics") or {}, prices.get(r["arm"], {}), verdicts.get(r["arm"], {})
        arms.append({
            "arm": r["arm"], "model_id": r["model_id"], "version": r["version"], "prompt_hash": r["prompt_hash"],
            "tool_choice_mode": r.get("tool_choice_mode"), "temperature": r.get("temperature"), "status": r["status"],
            "unavailable_reason": None if r["status"] == "ok" else r["reason"],
            "price": {"label": p.get("label"), "input_per_1m_usd": p.get("input_per_1m"),
                      "output_per_1m_usd": p.get("output_per_1m"), "source": p.get("source_url"),
                      "date": p.get("checked_on")},
            **{k: m.get(k) for k in ("macro_f1", "macro_f1_ci", "accuracy", "dispute_recall", "human_request_recall",
                                     "slot_accuracy", "missing_tool_calls", "p50_ms", "p95_ms", "cost_per_1000_usd")},
            "meets_bar": r.get("meets_bar"), "pareto": r.get("pareto"), "mcnemar_p_vs_best": r.get("mcnemar_p_vs_best"),
            "same_family_as_generator": r.get("same_family_as_generator"),
            "gate": {"benchmark_pass": v.get("benchmark"), "production_pass": v.get("production"),
                     "criteria": [{k: g[k] for k in ("criterion", "needed_benchmark", "needed_production", "verdict",
                                                     "evidence_url", "checked_on")} for g in by_arm.get(r["arm"], [])]}})
    kind = "pre-registered test run" if split == "test" else DEV_LABEL
    data = {"label": "[simulated]", "protocol": seal, "mode": "replay", "demo_today": b1.TODAY, "run_date": run_date,
            "split": split, "run_kind": kind, "provider": provider, "b1": {"arms": arms},
            "word": {"arms": []}, "judge": {"arms": []}, "b2": {"set": "dev", "cases": 20, "runs_per_case": 4, "arms": []},
            "model_map": {"understand": model_map, "word": {"chosen": "templates"},
                          "judge": {"chosen": "haiku-4-5"}}}            # word: AC-12 pending; judge: spec 15 Q4
    return {"generated_at": now(), "git_sha": git_sha(), "source": f"eval/bench B1 [simulated], {kind}", "data": data}


def csv_row(r: dict) -> dict:
    m = r.get("metrics") or {}
    acc = m.get("accuracy") or {}
    flat = {"accuracy": acc.get("value"), "accuracy_ci_low": acc.get("ci_low"), "accuracy_ci_high": acc.get("ci_high"),
            "macro_f1_es": (m.get("macro_f1") or {}).get("es"), "macro_f1_pt": (m.get("macro_f1") or {}).get("pt"),
            **{k: (m.get(k) or {}).get("value") for k in ("dispute_recall", "human_request_recall", "slot_accuracy")}}
    return {**r, **{k: m.get(k) for k in ("missing_tool_calls", "p50_ms", "p95_ms", "cost_per_1000_usd")}, **flat}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="spec 15 B1 benchmark")
    ap.add_argument("--split", choices=("test", "validation", "train"), required=True)
    ap.add_argument("--provider", choices=("bedrock", "fake"), default="bedrock")
    ap.add_argument("--arms", help="comma-separated arm ids (default: every arm of arms.yaml)")
    ap.add_argument("--limit", type=int, help="development runs only: first N sentences per language and intent")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    seal, official = protocol_seal(), args.split == "test"
    if official and (seal["status"] != "SEALED" or args.limit or args.arms or args.provider != "bedrock"
                     or not protocol_tagged()):
        print(f"refused: the test split runs once, whole, on Bedrock, after the seal (eval/PROTOCOL.md is "
              f"{seal['status']}; tag {PROTOCOL_TAG} on the merged sealing commit: "
              f"{'yes' if protocol_tagged() else 'no'})", file=sys.stderr)
        return 2
    arms, prices = core.load_arms(), core.load_prices()
    if args.arms:
        arms = [a for a in arms if a["id"] in args.arms.split(",")]
    rows = b1.load_split(args.split)
    if args.limit:
        seen: dict = {}
        rows = [r for r in rows if seen.setdefault((r["language"], r["intent"]), []).append(r) or
                len(seen[(r["language"], r["intent"])]) <= args.limit]
    n = len(rows) + len(b1.smoke.LADDER) + 1
    projected = core.projected_spend(arms, prices, n, b1.IN_TOKENS, b1.OUT_TOKENS)
    print(f"{len(arms)} arms x {len(rows)} sentences ({args.split}); projected spend {projected:.4f} USD [projected]")
    if args.dry_run:
        return 0
    run_date = date.today().isoformat()
    provider = b1.smoke.bedrock_provider() if args.provider == "bedrock" else b1.fake_provider
    results = b1.run(arms, rows, provider, prices, run_date)
    gen = vendor(generator(args.split))
    for r in results:
        r.setdefault("items", [])
        r["same_family_as_generator"] = vendor(r["model_id"]) == gen if r["model_id"] else False
        if r["status"] == "ok" and r["items"]:
            r["metrics"] = report.arm_metrics(r)
    gate_rows = gate.gate_rows(arms, gate.load_evidence(), run_date)
    report.measured_quality(gate_rows, results, f"{OFFICIAL['csv'] if official else 'development run'}, macro-F1 "
                            f"per language >= {report.MACRO_F1_FLOOR}")
    model_map = report.select(results, {a: v["production"] for a, v in gate.summary(gate_rows).items()})
    paths = ({k: ROOT / v for k, v in OFFICIAL.items()} if official else
             {k: ROOT / "eval/.runs/bench" / f"{run_date}-{args.split}-{args.provider}" / Path(v).name
              for k, v in OFFICIAL.items()})
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)
    payload = export(results, gate_rows, model_map, prices, args.split, seal, run_date, args.provider)
    paths["json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with paths["csv"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_row(r) for r in results)
    gate.write_csv(gate_rows, paths["gate"])
    paths["items"].write_text("".join(json.dumps({"arm": r["arm"], **i}, ensure_ascii=False) + "\n"
                                      for r in results for i in r["items"]), encoding="utf-8")
    label = "[simulated] pre-registered test run" if official else f"[simulated] {DEV_LABEL} ({args.provider})"
    paths["table"].write_text(f"{label}\n\n" + report.table(results), encoding="utf-8")
    paths["svg"].write_text(chart.svg(results, f"{label}, {len(rows)} sentences, run {run_date}"), encoding="utf-8")
    spent = sum(i["cost_usd"] for r in results for i in r["items"]) + sum(r.get("smoke_cost_usd", 0) for r in results)
    print(report.table(results))
    tag = "USD [data]" if args.provider == "bedrock" else "USD [simulated] (fake provider: no model was called)"
    print(f"model map (understand): {json.dumps(model_map)}\nspent {spent:.4f} {tag} · outputs in "
          f"{paths['json'].parent if not official else 'eval/results, apps/web/public/data, docs/assets'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
