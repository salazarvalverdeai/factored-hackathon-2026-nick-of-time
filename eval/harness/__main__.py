"""Command line of the harness (spec 10 §6). From the repo root, with PYTHONPATH=packages:

    python -m eval.harness run --set dev --arms S0,S1 [--runs 4] [--api URL] [--out DIR] [--cases FILE] [--web FILE]
    python -m eval.harness report DIR [--web FILE]      # recompute the summary from runs.jsonl, no system call

The held-out runs only after eval/PROTOCOL.md is SEALED (AC-07); its summary is also written for the web page.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval.harness import Api, HarnessError, metrics, report, run_set, write_outputs

ROOT = Path(__file__).resolve().parents[2]


def _headline(records: list[dict], n_cases: int, run_meta: dict) -> None:
    """One line per arm. The metric id stays `pass_4` (spec 10 §7.2); its label says how many runs a case had."""
    labels = {"pass_4": f"pass^{metrics.runs_per_case(records)}"}
    for arm in dict.fromkeys(record["arm"] for record in records):
        mine = [record for record in records if record["arm"] == arm]
        stats = metrics.group(mine)
        print(f"[simulated] {arm}: {len(mine)} runs of {n_cases} cases, "
              f"{sum(record['status'] == 'failed' for record in mine)} failed · "
              + " · ".join(f"{labels.get(name, name)} {stats[name]['numerator']}/{stats[name]['denominator']}"
                           for name in ("pass_4", "safe_automated_resolution", "unsafe_outcomes")))
        if "second_turn_recovery" in stats:             # AC-13 (D-071): the recovery variants, apart
            print(f"[simulated] {arm}: second_turn_recovery "
                  + " · ".join(f"{name.removeprefix('second_turn_')} {stats[name]['numerator']}/"
                               f"{stats[name]['denominator']}" for name in metrics.RECOVERY))
        if drift := run_meta["arms"].get(arm, {}).get("drift"):
            print(f"warning: {arm} changed between runs ({', '.join(drift)}); see meta.json", file=sys.stderr)


def _read_cases(path: Path) -> list[dict]:
    if not path.is_file():
        raise HarnessError(f"the case file {path} is missing")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None, api: Api | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.harness")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a case set on some arms")
    run.add_argument("--set", dest="set_name", choices=("dev", "heldout"), required=True)
    run.add_argument("--arms", required=True, help="comma-separated arms, e.g. S0,S1")
    run.add_argument("--runs", type=int, default=4)
    run.add_argument("--api", default="http://localhost:8000", help="base URL of an api with EVAL_MODE=true")
    run.add_argument("--out", type=Path, help="output folder; default eval/.runs/<utc time>-dev or "
                                              "eval/results/<date>-heldout")
    run.add_argument("--cases", type=Path, help="case file; default eval/cases/<set>.jsonl")
    run.add_argument("--web", type=Path, help="also write the web summary here; default for the held-out: "
                                              "apps/web/public/data/evaluation_summary.json")
    run.add_argument("--workers", type=int, default=4)
    again = commands.add_parser("report", help="recompute the summary of a finished run")
    again.add_argument("out", type=Path)
    again.add_argument("--web", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "report":
            lines = (args.out / "runs.jsonl").read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines if line.strip()]
            write_outputs(records, args.out)
            run_meta = json.loads((args.out / "meta.json").read_text(encoding="utf-8"))
            report.write_reports(records, args.out, run_meta, args.web)
            _headline(records, len({record["case_id"] for record in records}), run_meta)
            return 0
        heldout = args.set_name == "heldout"
        path = args.cases or ROOT / "eval/cases" / f"{args.set_name}.jsonl"
        if heldout:
            report.check_heldout(path)
        cases = [case for case in _read_cases(path) if case["set"] == args.set_name]
        started, today = report.now(), datetime.now(timezone.utc)
        out = args.out or (ROOT / "eval/results" / f"{today:%Y-%m-%d}-heldout" if heldout
                           else ROOT / "eval/.runs" / f"{today:%Y%m%dT%H%M%SZ}-dev")
        if (out / "runs.jsonl").exists():                    # a committed held-out result is never replaced silently
            raise HarnessError(f"{out} already holds a run; pass another --out or move it first")
        records = run_set(cases, [arm for arm in args.arms.split(",") if arm], args.runs, api=api,
                          api_url=args.api, workers=args.workers)
    except HarnessError as error:
        print(f"harness stopped: {error}", file=sys.stderr)
        return 2
    write_outputs(records, out)
    run_meta = report.meta(records, path, started)
    report.write_reports(records, out, run_meta, args.web or (report.WEB_SUMMARY if heldout else None))
    _headline(records, len(cases), run_meta)
    print(f"wrote runs.jsonl, summary.csv, meta.json and evaluation_summary.json in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
