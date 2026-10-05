"""B1 benchmark command (spec 15: AC-01, AC-03, AC-04, AC-07). From the repo root, with PYTHONPATH=.:packages:

    python -m eval.bench --split test                       # make bench: the pre-registered run, once, after the seal
    python -m eval.bench --split validation [--limit N]     # make bench-dev: development run, git-ignored output
    ... [--provider bedrock|fake] [--arms a,b] [--dry-run]  # --dry-run prints the [projected] spend and stops
    python -m eval.bench --split S --from-items FILE        # re-render table and chart from scored items, no model call

Only the test split writes the result files of spec 15 §4.5 (eval/results/, benchmark.json, the SVG). Before the first
model call it runs the shared seal guard (eval/harness/seal_guard.py): `check_seal` (tag protocol-v1 on the sealing
commit, the protocol and the classifier split manifest as sealed, no uncommitted sealed input), then
`claim_run("bench")`, which writes eval/results/bench/bench.start.json and refuses a second run; it also refuses while
any official output already exists. Test results carry `test_review: rules-v1` and the PROTOCOL §1.1 label (ADR 0028).
Every other run goes to eval/.runs/bench/<DEMO_TODAY>-<split>-<provider>/ (git-ignored), labeled a development run.

B1 TF-IDF + LR (spec 11): a development run trains it as `make classifier` does (fit on train, calibrated on
validation) into its folder. The test run never fits it: it loads the file the classifier-test run recorded in
classifier.json `b1_model`, refused before the claim when that record, the file or its sha256 is missing or differs,
so `make classifier-test` runs before `make bench`. benchmark.json records the B1 file as `b1_model`.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

from eval.bench import b1, chart, core, gate, report
from eval.harness import seal_guard
from eval.harness.report import git_sha, now, protocol_seal
from eval.harness.seal_guard import SealError

ROOT = b1.ROOT
SEAL_COMMIT = seal_guard.SEAL_COMMIT    # the sealing commit that tag protocol-v1 must resolve to
SEAL_INPUTS = {"classifier_splits": None}         # the guard hashes eval/classifier/*.jsonl itself (seal field (b))
RUN_NAME, CLAIM_DIR = "bench", "eval/results/bench"   # claim marker: eval/results/bench/bench.start.json
TEST_REVIEW = seal_guard.TEST_REVIEW                  # "rules-v1" (ADR 0028)
TEST_REVIEW_LABEL = "test split decided by fixed rules, without independent human review"    # PROTOCOL §1.1
DEV_LABEL = "development run on validation — not the pre-registered test result"
RERENDER_DIR = "eval/.runs/bench/rerender"
OFFICIAL = {"csv": "eval/results/bench_b1.csv", "items": "eval/results/bench_b1_items.jsonl",
            "gate": "eval/results/bench_gate.csv", "table": "eval/results/bench_b1.md",
            "json": "apps/web/public/data/benchmark.json", "svg": "docs/assets/benchmark_cost_quality.svg"}
CSV_FIELDS = ["arm", "status", "reason", "model_id", "version", "prompt_hash", "tool_choice_mode", "temperature",
              "price_input_per_1m", "price_output_per_1m", "price_status", "price_source_url", "price_checked_on",
              "run_date", "accuracy", "accuracy_ci_low", "accuracy_ci_high", "macro_f1_es", "macro_f1_pt",
              "dispute_recall", "human_request_recall", "slot_accuracy", "missing_tool_calls", "errors",
              "errors_by_class", "p50_ms", "p95_ms", "cost_per_1000_usd", "meets_bar", "pareto", "mcnemar_p_vs_best",
              "same_family_as_generator", "test_review", "test_review_label"]


def check_test_seal() -> dict:
    """The shared guard for the one-time test run: raises SealError unless the seal holds; returns the dict that
    benchmark.json embeds as `protocol` (status, sha256, tag, commit, head, test_review, inputs)."""
    return seal_guard.check_seal(inputs=dict(SEAL_INPUTS), root=ROOT, commit=SEAL_COMMIT)


def existing_outputs(root: Path | None = None) -> list[str]:
    """Official outputs that already exist in the working tree, on HEAD or on origin/main: the test run never
    overwrites them (spec 15 §4.5, PROTOCOL §0.2)."""
    root = root or ROOT
    found = [rel for rel in OFFICIAL.values() if (root / rel).exists()]
    for ref in ("HEAD", "refs/remotes/origin/main"):
        for rel in OFFICIAL.values():
            probe = subprocess.run(["git", "cat-file", "-e", f"{ref}:{rel}"], cwd=root, capture_output=True)
            if probe.returncode == 0:
                found.append(f"{ref}:{rel}")
    return found


def run_date() -> str:
    """The run date (AC-05, AC-09, ADR 0020): B1 runs only in replay, against the fixed DEMO_TODAY every arm reads
    (`b1.TODAY`), never the system date nor a DEMO_TODAY set in the environment, so the run date, `demo_today` and
    the development folder name all say the same day."""
    return b1.TODAY


def has_b1(arms: list[dict]) -> bool:
    return any(a["provider"] == "classifier" for a in arms)


def dev_b1_model(out_dir: Path) -> b1.B1Model:
    """Development runs train B1 as `make classifier` does (train only, calibrated on validation, fixed seed) into the
    run folder; a failure makes only the B1 arm unavailable, with its reason (AC-06)."""
    try:
        return b1.train_b1_model(ROOT, out_dir)
    except Exception as exc:              # no splits, no scikit-learn, a class missing: the other arms still run
        return b1.B1Model(reason=f"B1 could not be trained: {type(exc).__name__}: {exc}"[:300])


def vendor(model_id: str | None) -> str | None:
    return model_id.removeprefix("us.").split(".")[0] if model_id else None


def generator(split: str) -> str | None:
    meta = json.loads((ROOT / "eval/classifier/draft/generation.json").read_text(encoding="utf-8"))
    return meta["generators"].get(split, {}).get("model_id")


def review_fields(split: str) -> dict:
    """PROTOCOL §1.1, ADR 0028: every test result says how the test split was decided."""
    return {"test_review": TEST_REVIEW, "test_review_label": TEST_REVIEW_LABEL} if split == "test" else {}


def export(rows, gate_rows, model_map, prices, split, seal, run_date, provider, b1_model=None) -> dict:
    """`{generated_at, git_sha, source, data}` with `data` in the shape of spec 15 §7.1. On the test split `seal` is
    the dict of the seal guard, embedded whole as `protocol`. `b1_model` records the B1 file scored (path, sha256,
    scikit-learn version, source) or why the arm could not run; None when the run had no B1 arm."""
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
                                     "slot_accuracy", "missing_tool_calls", "errors", "p50_ms", "p95_ms",
                                     "cost_per_1000_usd")},
            "errors_by_class": r.get("errors") or {},
            "meets_bar": r.get("meets_bar"), "pareto": r.get("pareto"), "mcnemar_p_vs_best": r.get("mcnemar_p_vs_best"),
            "same_family_as_generator": r.get("same_family_as_generator"),
            "gate": {"benchmark_pass": v.get("benchmark"), "production_pass": v.get("production"),
                     "criteria": [{k: g[k] for k in ("criterion", "needed_benchmark", "needed_production", "verdict",
                                                     "evidence_url", "checked_on")} for g in by_arm.get(r["arm"], [])]}})
    kind = "pre-registered test run" if split == "test" else DEV_LABEL
    data = {"label": "[simulated]", "protocol": seal, "mode": "replay", "demo_today": b1.TODAY, "run_date": run_date,
            "split": split, "run_kind": kind, **review_fields(split), "provider": provider,
            "b1_model": None if b1_model is None else (b1_model.record or {"path": None, "sha256": None,
                                                                          "reason": b1_model.reason}),
            "b1": {"arms": arms},
            "word": {"arms": []}, "judge": {"arms": []}, "b2": {"set": "dev", "cases": 20, "runs_per_case": 4, "arms": []},
            "model_map": {"understand": model_map, "word": {"chosen": "templates"},
                          "judge": {"chosen": "haiku-4-5"}}}            # word: AC-12 pending; judge: spec 15 Q4
    return {"generated_at": now(), "git_sha": git_sha(), "source": f"eval/bench B1 [simulated], {kind}", "data": data}


def csv_row(r: dict, split: str = "validation") -> dict:
    m = r.get("metrics") or {}
    acc = m.get("accuracy") or {}
    flat = {"accuracy": acc.get("value"), "accuracy_ci_low": acc.get("ci_low"), "accuracy_ci_high": acc.get("ci_high"),
            "macro_f1_es": (m.get("macro_f1") or {}).get("es"), "macro_f1_pt": (m.get("macro_f1") or {}).get("pt"),
            **{k: (m.get(k) or {}).get("value") for k in ("dispute_recall", "human_request_recall", "slot_accuracy")}}
    return {**r, **{k: m.get(k) for k in ("missing_tool_calls", "errors", "p50_ms", "p95_ms", "cost_per_1000_usd")},
            **flat, "errors_by_class": json.dumps(r.get("errors") or {}, sort_keys=True), **review_fields(split)}


def score(results: list[dict], arms: list[dict], split: str, date: str, official: bool) -> tuple[list[dict], dict]:
    """Metrics per measured arm, the gate rows with `es_pt_quality` from this run, and the lean-rule model map."""
    gen = vendor(generator(split))
    for r in results:
        r.setdefault("items", [])
        r["same_family_as_generator"] = vendor(r["model_id"]) == gen if r["model_id"] else False
        if r["status"] == "ok" and r["items"]:
            r["metrics"] = report.arm_metrics(r)
    gate_rows = gate.gate_rows(arms, gate.load_evidence(), date)
    report.measured_quality(gate_rows, results, f"{OFFICIAL['csv'] if official else 'development run'}, macro-F1 "
                            f"per language >= {report.MACRO_F1_FLOOR}")
    model_map = report.select(results, {a: v["production"] for a, v in gate.summary(gate_rows).items()})
    return gate_rows, model_map


def label_of(split: str, provider: str) -> str:
    if split == "test":
        return f"[simulated] pre-registered test run; {TEST_REVIEW_LABEL} (test_review: {TEST_REVIEW}, ADR 0028)"
    return f"[simulated] {DEV_LABEL} ({provider})"


def table_md(results: list[dict], model_map: dict, label: str) -> str:
    return f"{label}\n\n" + report.table(results) + "\n" + report.selection_md(model_map)


def results_from_items(path: Path, arms: list[dict], prices: dict, date: str) -> list[dict]:
    """Rows of `b1.run` rebuilt from a scored-items JSONL (one line per sentence with its arm), so the table and the
    chart can be re-rendered without calling any model. Only arms with items appear."""
    by_arm: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            it = json.loads(line)
            by_arm.setdefault(it.pop("arm"), []).append(it)
    meta = {a["id"]: a for a in arms}
    rows = []
    for arm_id, items in by_arm.items():
        row = core.make_row(meta.get(arm_id, {"id": arm_id}), prices, b1.PROMPT, date)
        errors: dict[str, int] = {}
        for it in items:
            if it.get("error"):
                name = it["error"].split(":", 1)[0]
                errors[name] = errors.get(name, 0) + 1
        rows.append({**row, "items": items, "errors": errors})
    return rows


def rerender(args, arms: list[dict], prices: dict) -> int:
    """`--from-items`: the table and the SVG again from scored items; writes only to a git-ignored folder."""
    date = run_date()
    results = results_from_items(args.from_items, arms, prices, date)
    _, model_map = score(results, arms, args.split, date, official=False)
    out = Path(args.out) if args.out else ROOT / RERENDER_DIR
    out.mkdir(parents=True, exist_ok=True)
    label = f"{label_of(args.split, args.provider)}; re-rendered from {args.from_items.name}"
    (out / Path(OFFICIAL["table"]).name).write_text(table_md(results, model_map, label), encoding="utf-8")
    n = max((len(r["items"]) for r in results), default=0)
    (out / Path(OFFICIAL["svg"]).name).write_text(chart.svg(results, f"{label}, {n} sentences, run {date}"),
                                                  encoding="utf-8")
    print(f"re-rendered {len(results)} arms from {args.from_items} into {out} (no model was called)")
    return 0


def refuse(message: str) -> int:
    print(f"refused: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="spec 15 B1 benchmark")
    ap.add_argument("--split", choices=("test", "validation", "train"), required=True)
    ap.add_argument("--provider", choices=("bedrock", "fake"), default="bedrock")
    ap.add_argument("--arms", help="comma-separated arm ids (default: every arm of arms.yaml)")
    ap.add_argument("--limit", type=int, help="development runs only: first N sentences per language and intent")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-items", type=Path, help="re-render the table and the chart from a scored-items JSONL")
    ap.add_argument("--out", help=f"--from-items only: output folder (default {RERENDER_DIR})")
    args = ap.parse_args(argv)
    arms, prices = core.load_arms(), core.load_prices()
    if args.from_items:
        return rerender(args, arms, prices)
    official = args.split == "test"
    b1_model = None
    if official and (args.limit or args.arms or args.provider != "bedrock"):
        return refuse("the test split runs once, whole, on Bedrock (no --limit, --arms or fake provider)")
    if official:
        try:
            seal = check_test_seal()
        except SealError as exc:
            return refuse(f"the seal does not hold: {exc}")
        present = existing_outputs()
        if present:
            return refuse(f"official B1 outputs already exist and are never overwritten: {present[:5]}")
        if has_b1(arms):
            try:                                      # before the claim: a missing B1 file never burns the one run
                b1_model = b1.official_b1_model(ROOT, seal)
            except b1.BenchError as exc:
                return refuse(str(exc))
        if not args.dry_run:
            try:
                seal_guard.claim_run(RUN_NAME, ROOT / CLAIM_DIR, seal, root=ROOT)
            except SealError as exc:
                return refuse(str(exc))
    else:
        seal = protocol_seal()
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
    date = run_date()
    paths = ({k: ROOT / v for k, v in OFFICIAL.items()} if official else
             {k: ROOT / "eval/.runs/bench" / f"{date}-{args.split}-{args.provider}" / Path(v).name
              for k, v in OFFICIAL.items()})
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)
    if not official:
        paths["items"].unlink(missing_ok=True)       # a development rerun starts a fresh stream; the test run never
        if has_b1(arms):
            b1_model = dev_b1_model(paths["json"].parent)
    provider = b1.smoke.bedrock_provider() if args.provider == "bedrock" else b1.fake_provider
    results = b1.run(arms, rows, provider, prices, date, items_path=paths["items"],    # items streamed as scored
                     b1_model=b1_model)
    gate_rows, model_map = score(results, arms, args.split, date, official)
    payload = export(results, gate_rows, model_map, prices, args.split, seal, date, args.provider, b1_model)
    paths["json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with paths["csv"].open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_row(r, args.split) for r in results)
    gate.write_csv(gate_rows, paths["gate"])
    label = label_of(args.split, args.provider)
    paths["table"].write_text(table_md(results, model_map, label), encoding="utf-8")
    paths["svg"].write_text(chart.svg(results, f"{label}, {len(rows)} sentences, run {date}"), encoding="utf-8")
    spent = sum(i["cost_usd"] for r in results for i in r["items"]) + sum(r.get("smoke_cost_usd", 0) for r in results)
    print(report.table(results))
    tag = "USD [data]" if args.provider == "bedrock" else "USD [simulated] (fake provider: no model was called)"
    print(f"model map (understand): {json.dumps(model_map)}\nspent {spent:.4f} {tag} · outputs in "
          f"{paths['json'].parent if not official else 'eval/results, apps/web/public/data, docs/assets'}")
    if model_map.get("refused"):
        print(f"refused to choose: {model_map['chosen_by']}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
