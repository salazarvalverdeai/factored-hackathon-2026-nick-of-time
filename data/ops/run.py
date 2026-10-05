"""The ops job (spec 14 T1–T4): snapshot → bronze → silver → gold → manifest → ops_kpis.json.

Idempotent (AC-05): gold tables are hashed by content (their rows as CSV, sorted by key), so a writer's metadata never
changes a hash, and the manifest version goes up only when a table's hash changes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Optional

import polars as pl

from data.ops import bronze, gold, series, silver

ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = ROOT / "data" / "ops"
JOB_VERSION = "0.2.0"                   # 0.2.0: automated_rate, replay_contacts and the series (§11)


def sha256(frame: pl.DataFrame) -> str:
    return hashlib.sha256(frame.write_csv().encode()).hexdigest()


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run(snapshot: bronze.Snapshot, *, gold_path: Path, out: Path = OPS_DIR, web: Optional[Path] = None,
        mode: str = "replay", now: Optional[dt.datetime] = None, contacts: Optional[pl.DataFrame] = None,
        asis: Optional[pl.DataFrame] = None) -> dict[str, Any]:
    """Run the job on one snapshot; returns the manifest. `web` is where ops_kpis.json goes (AC-09). `contacts` (one
    outcome row per replayed complaint) becomes gold `replay_contacts`; with `asis` the export carries the series."""
    now = now or dt.datetime.now(dt.UTC)
    stamp = now.isoformat(timespec="seconds")
    sources = bronze.build(snapshot, out / "bronze", now)
    built = silver.build(out / "bronze", out / "silver", gold_path, now)
    tables = gold.build(built["tables"])
    if contacts is not None:
        tables["replay_contacts"] = (contacts.group_by(contacts.columns).len("contacts")
                                     .sort(contacts.columns, nulls_last=True))
    (out / "gold").mkdir(parents=True, exist_ok=True)
    meta = {}
    for name, frame in tables.items():
        frame.write_parquet(out / "gold" / f"{name}.parquet")
        meta[name] = {"path": f"gold/{name}.parquet", "rows": frame.height, "sha256": sha256(frame),
                      "columns": {c: str(t) for c, t in frame.schema.items()}}
    path = out / "manifest.json"
    previous = json.loads(path.read_text()) if path.exists() else None
    changed = [t for t in meta if (previous or {}).get("tables", {}).get(t, {}).get("sha256") != meta[t]["sha256"]]
    if previous is None or changed:
        version, created = (previous or {"version": 0})["version"] + 1, stamp
    else:
        version, created = previous["version"], previous["version_created_at"]
    stats = built["stats"]
    checks = [{"id": f"{check}", "table": t, "n": n} for t, s in stats.items()
              for check, n in s["contract_failures"].items()]
    checks += [{"id": key, "table": t, "n": s[key]} for t, s in stats.items()
               for key in ("quarantined", "qc_gold_missing", "synthetic", "without_case") if key in s]
    excluded = {t: int(f["run_id"].is_not_null().sum()) for t, f in built["tables"].items() if "run_id" in f.columns}
    manifest = {"dataset": "nick_of_time_ops", "label": "[simulated]", "version": version, "version_created_at": created,
                "run_at": stamp, "job_version": JOB_VERSION,
                "source": {"kind": snapshot.source, "tables": sources, "eval_rows_excluded": excluded},
                "silver": {t: {k: v for k, v in s.items() if k != "contract_failures"} for t, s in stats.items()},
                "tables": meta, "checks": checks, "changed_tables": changed,
                "previous": None if previous is None else {"version": previous["version"], "run_at": previous["run_at"]}}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    if web is not None:
        export(tables, web, mode=mode, source=snapshot.source, version=version, now=now,
               series=series.build(tables, contacts, asis) if asis is not None or contacts is not None else None)
    return manifest


def export(tables: dict[str, pl.DataFrame], path: Path, *, mode: str, source: str, version: int,
           now: dt.datetime, series: Optional[dict[str, Any]] = None) -> None:
    """ops_kpis.json with the spec 01 §6.2 envelope (AC-09): `days` and `feedback` are `[simulated]`; `series` (§11)
    carries each series' own label, source, window and notes."""
    payload = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "git_sha": git_sha(),
               "source": (f"make ops-replay — Bank today [data] and the W3 replay [simulated], {source} store, ops "
                          f"manifest v{version}" if series else
                          f"data/ops job [simulated] — {source} store, ops manifest v{version}"),
               "data": {**gold.summary(tables, mode), **({"series": series} if series else {})}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
