"""CLI of the ops job (spec 14). See data/ops/__init__.py.

    PYTHONPATH=packages python -m data.ops run --source sample [--gold PATH] [--web PATH] [--mode replay|live]
    PYTHONPATH=packages python -m data.ops replay [--gold PATH] [--web PATH] [--limit N]     # §11, `make ops-replay`

`--gold` defaults to $GOLD_PATH, then data/gold. With `--source sample` the export goes to data/ops/ops_kpis.json
unless `--web` names another path: a seeded store must never pass for operation on the public page.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from data.ops.run import OPS_DIR, ROOT, run

WEB = ROOT / "apps" / "web" / "public" / "data" / "ops_kpis.json"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m data.ops")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="snapshot → bronze → silver → gold → manifest → ops_kpis.json")
    p_run.add_argument("--source", choices=["sample", "postgres"], default="sample")
    p_run.add_argument("--gold", type=Path, default=Path(os.environ.get("GOLD_PATH") or ROOT / "data" / "gold"))
    p_run.add_argument("--web", type=Path, default=OPS_DIR / "ops_kpis.json")
    p_run.add_argument("--mode", choices=["replay", "live"], default="replay")
    p_rep = sub.add_parser("replay", help="the W3 complaints through S0 → the job → ops_kpis.json with the series")
    p_rep.add_argument("--gold", type=Path, default=Path(os.environ.get("GOLD_PATH") or ROOT / "data" / "gold"))
    p_rep.add_argument("--web", type=Path, default=WEB)
    p_rep.add_argument("--limit", type=int, default=None, help="first N complaints only (a quick check)")
    args = parser.parse_args()
    if args.cmd == "replay":
        return replay(args)
    if args.source == "postgres":
        raise SystemExit("spec 14 T5: the Postgres snapshot is not built yet; use --source sample")
    from data.ops import bronze, sample
    from nick_of_time.store.memory import MemoryStore
    store = sample.seed(MemoryStore(), sample.gold_transactions(args.gold))
    manifest = run(bronze.from_memory(store), gold_path=args.gold, web=args.web, mode=args.mode)
    print(json.dumps({k: manifest[k] for k in ("version", "changed_tables", "checks")}, indent=1))


def replay(args: argparse.Namespace) -> None:
    """Spec 14 §11: the as-is query, the replay into an in-memory store, the job; reports run time and rows."""
    import time

    from data.ops import bronze, series
    from data.ops import replay as rp
    start = time.perf_counter()
    asis = series.asis(args.gold)
    asis.write_csv(series.ASIS_SQL.with_suffix(".csv"))
    store, contacts = rp.run(args.gold, limit=args.limit)
    simulated = time.perf_counter() - start
    manifest = run(bronze.from_memory(store), gold_path=args.gold, web=args.web, contacts=contacts, asis=asis)
    print(json.dumps({"contacts": contacts.height, "outcomes": dict(contacts["outcome"].value_counts().iter_rows()),
                      "rows": {t: m["rows"] for t, m in manifest["tables"].items()},
                      "source_rows": {t: s["rows"] for t, s in manifest["source"]["tables"].items()},
                      "seconds": {"replay": round(simulated, 1), "total": round(time.perf_counter() - start, 1)},
                      "web": str(args.web)}, indent=1))


if __name__ == "__main__":
    main()
