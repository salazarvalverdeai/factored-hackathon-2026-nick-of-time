"""Command line of the harness (spec 10 §6). From the repo root, with PYTHONPATH=packages:

    python -m eval.harness run --set dev --arms S0,S1 [--runs 4] [--api URL] [--out DIR] [--cases FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval.harness import Api, HarnessError, metrics, run_set, write_outputs

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None, api: Api | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.harness")
    run = parser.add_subparsers(dest="command", required=True).add_parser("run", help="run a case set on some arms")
    run.add_argument("--set", dest="set_name", choices=("dev", "heldout"), required=True)
    run.add_argument("--arms", required=True, help="comma-separated arms, e.g. S0,S1")
    run.add_argument("--runs", type=int, default=4)
    run.add_argument("--api", default="http://localhost:8000", help="base URL of an api with EVAL_MODE=true")
    run.add_argument("--out", type=Path, help="output folder; default eval/.runs/<utc time>-<set>")
    run.add_argument("--cases", type=Path, help="case file; default eval/cases/<set>.jsonl")
    run.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    path = args.cases or ROOT / "eval/cases" / f"{args.set_name}.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = [case for case in cases if case["set"] == args.set_name]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or ROOT / "eval/.runs" / f"{stamp}-{args.set_name}"
    try:
        records = run_set(cases, [arm for arm in args.arms.split(",") if arm], args.runs, api=api,
                          api_url=args.api, workers=args.workers)
    except HarnessError as error:
        print(f"harness stopped: {error}", file=sys.stderr)
        return 2
    write_outputs(records, out)
    for arm in dict.fromkeys(record["arm"] for record in records):
        mine = [record for record in records if record["arm"] == arm]
        stats = metrics.group(mine)
        print(f"[simulated] {arm}: {len(mine)} runs of {len(cases)} cases, "
              f"{sum(record['status'] == 'failed' for record in mine)} failed · "
              + " · ".join(f"{name} {stats[name]['numerator']}/{stats[name]['denominator']}"
                           for name in ("pass_4", "safe_automated_resolution", "unsafe_outcomes")))
    print(f"wrote {out / 'runs.jsonl'} and {out / 'summary.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
