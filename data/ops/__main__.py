"""CLI of the ops job (spec 14). See data/ops/__init__.py.

    PYTHONPATH=packages python -m data.ops run --source sample [--gold PATH] [--web PATH] [--mode replay|live]

`--gold` defaults to $GOLD_PATH, then data/gold. With `--source sample` the export goes to data/ops/ops_kpis.json
unless `--web` names another path: a seeded store must never pass for operation on the public page.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from data.ops.run import OPS_DIR, ROOT, run


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m data.ops")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="snapshot → bronze → silver → gold → manifest → ops_kpis.json")
    p_run.add_argument("--source", choices=["sample", "postgres"], default="sample")
    p_run.add_argument("--gold", type=Path, default=Path(os.environ.get("GOLD_PATH") or ROOT / "data" / "gold"))
    p_run.add_argument("--web", type=Path, default=OPS_DIR / "ops_kpis.json")
    p_run.add_argument("--mode", choices=["replay", "live"], default="replay")
    args = parser.parse_args()
    if args.source == "postgres":
        raise SystemExit("spec 14 T5: the Postgres snapshot is not built yet; use --source sample")
    from data.ops import bronze, sample
    from nick_of_time.store.memory import MemoryStore
    store = sample.seed(MemoryStore(), sample.gold_transactions(args.gold))
    manifest = run(bronze.from_memory(store), gold_path=args.gold, web=args.web, mode=args.mode)
    print(json.dumps({k: manifest[k] for k in ("version", "changed_tables", "checks")}, indent=1))


if __name__ == "__main__":
    main()
