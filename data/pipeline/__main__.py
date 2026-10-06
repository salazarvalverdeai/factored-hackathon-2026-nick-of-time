"""Pipeline CLI. See data/pipeline/__init__.py."""
from __future__ import annotations

import argparse
from pathlib import Path

from data.pipeline.config import DATA_DIR, TABLES, Layout, setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m data.pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="bronze → silver → gold → checks")
    p_run.add_argument("--source", choices=["s3", "local"], default="s3",
                       help="s3: lists and syncs the dataset bucket (DATASET_AWS_PROFILE, see .env.example); "
                            "local: data/ mirror")
    p_run.add_argument("--tables", nargs="*", default=list(TABLES), choices=list(TABLES))
    sub.add_parser("fixture", help="late_arrival fixture: delivery_1 and then delivery_2 in data/_fixture_run/")
    p_report = sub.add_parser("report", help="generates data/quality_report.md from the results")
    p_report.add_argument("--json", action="store_true",
                          help="write apps/web/public/data/data_quality.json for the /data page instead")
    p_report.add_argument("--data-dir", type=Path, default=DATA_DIR,
                          help="--json only: folder with gold/run_results.json and _fixture_run/ (read only)")
    args = parser.parse_args()
    setup_logging()

    if args.cmd == "run":
        from data.pipeline.run import run
        run(args.source, Layout(DATA_DIR), tuple(t for t in TABLES if t in args.tables))
    elif args.cmd == "fixture":
        from data.pipeline.run import run_fixture
        run_fixture()
    elif args.cmd == "report":
        from data.pipeline.report import write_json, write_report
        write_json(data_dir=args.data_dir) if args.json else write_report()


if __name__ == "__main__":
    main()
