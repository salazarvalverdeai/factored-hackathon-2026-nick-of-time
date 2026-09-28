"""CLI del pipeline. Ver data/pipeline/__init__.py."""
from __future__ import annotations

import argparse

from data.pipeline.config import DATA_DIR, TABLES, Layout, setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m data.pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="bronze → silver → gold → checks")
    p_run.add_argument("--source", choices=["s3", "local"], default="s3",
                       help="s3: lista y sincroniza el bucket con las credenciales de .env; local: espejo data/")
    p_run.add_argument("--tables", nargs="*", default=list(TABLES), choices=list(TABLES))
    sub.add_parser("fixture", help="fixture late_arrival: delivery_1 y luego delivery_2 en data/_fixture_run/")
    sub.add_parser("report", help="genera data/quality_report.md desde los resultados")
    args = parser.parse_args()
    setup_logging()

    if args.cmd == "run":
        from data.pipeline.run import run
        run(args.source, Layout(DATA_DIR), tuple(t for t in TABLES if t in args.tables))
    elif args.cmd == "fixture":
        from data.pipeline.run import run_fixture
        run_fixture()
    elif args.cmd == "report":
        from data.pipeline.report import write_report
        write_report()


if __name__ == "__main__":
    main()
