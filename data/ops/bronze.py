"""Bronze (spec 14 §7.1, T1): a faithful copy of the eight operational tables, every value as text (as the data
pipeline's bronze), plus `_loaded_at` and `_source`. Columns come from `store/schema.sql`, so a source that drifts
from the schema fails here. "No lost rows" (AC-01): each table's row count and maximum `created_at` read back from
bronze must equal the source's own, taken in the same read; otherwise the run stops.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import polars as pl

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "packages" / "nick_of_time" / "store" / "schema.sql"
TABLES = ("cases", "case_events", "product_overrides", "notifications", "notification_deliveries", "policy_denials",
          "llm_calls", "settings_events")       # not copied: sessions, customer_channels, link_tokens, idempotency,
#                                                 call_requests, demo_transactions (§7.1, ADR 0020 rule 2)


def schema_columns(sql: str | None = None) -> dict[str, list[str]]:
    """The columns of every `create table` in schema.sql, in order (constraint lines skipped)."""
    sql = sql if sql is not None else SCHEMA_SQL.read_text()
    out = {}
    for name, body in re.findall(r"create table if not exists (\w+) \((.*?)\n\);", sql, re.S):
        out[name] = [m.group(1) for line in body.splitlines()
                     if (m := re.match(r"^  (\w+) ", line)) and m.group(1) not in ("check", "unique")]
    return out


COLUMNS = {t: c for t, c in schema_columns().items() if t in TABLES}


@dataclass(frozen=True)
class Snapshot:
    """One consistent read of the source: rows per table and, read in the same transaction, the row count and the
    maximum `created_at` the source itself reports (the high-water mark)."""
    source: str                                          # "memory" or "postgres"
    rows: dict[str, list[dict[str, Any]]]
    counts: dict[str, int]
    high_water: dict[str, Optional[dt.datetime]]

    @classmethod
    def of(cls, source: str, rows: dict[str, list[dict[str, Any]]]) -> Snapshot:
        return cls(source, rows, {t: len(r) for t, r in rows.items()},
                   {t: _max([x.get("created_at") for x in r]) for t, r in rows.items()})


def _max(values: list[Any]) -> Optional[dt.datetime]:
    parsed = [v if isinstance(v, dt.datetime) else dt.datetime.fromisoformat(v) for v in values if v is not None]
    return max(parsed, default=None)


def from_memory(store: Any) -> Snapshot:
    """[assumption] The in-memory store has no bulk read, so this adapter reads its lists under its lock (one read).
    Its delivery rows have no id or time: `delivery_id` is `<notification_id>#<n>` and `created_at` is null."""
    with store._serial:
        dump = lambda m, **kw: m.model_dump(mode="json", **kw)              # noqa: E731
        overrides = list(store._overrides.values())
        deliveries = [{"delivery_id": f"{nid}#{i}", "notification_id": nid, "status": s, "provider_event": e}
                      for nid, rows in store._deliveries.items() for i, (s, e) in enumerate(rows, 1)]
        rows = {
            "cases": [dump(c, exclude={"action_id", "verification_id"}) for c in store._cases.values()],
            "case_events": [dump(e) for events in store._events.values() for e in events],
            "product_overrides": [{**dump(o, exclude={"action_id", "verification_id"}), "override_id": o.action_id,
                                   "row_no": i} for i, o in enumerate(overrides, 1)],
            "notifications": [dump(n, exclude={"delivery_status"}) for n in store._notifications],
            "notification_deliveries": [{**d, "row_no": i} for i, d in enumerate(deliveries, 1)],
            "policy_denials": [dump(d) for d in store._denials],
            "llm_calls": [dump(c) for c in store._llm_calls],
            "settings_events": [{**s, "row_no": i} for i, s in enumerate(store._settings, 1)]}
        sources = {"cases": store._cases.values(), "case_events": [e for v in store._events.values() for e in v],
                   "product_overrides": overrides, "notifications": store._notifications, "notification_deliveries":
                   deliveries, "policy_denials": store._denials, "llm_calls": store._llm_calls,
                   "settings_events": store._settings}
        counts = {t: len(list(v)) for t, v in sources.items()}
        high = {t: _max([getattr(x, "created_at", None) if not isinstance(x, dict) else x.get("created_at")
                         for x in v]) for t, v in sources.items()}
    return Snapshot("memory", rows, counts, high)


ORDER = {"cases": "case_id", "case_events": "case_id, seq", "product_overrides": "row_no",
         "notifications": "notification_id", "notification_deliveries": "row_no", "policy_denials": "denial_id",
         "llm_calls": "call_id", "settings_events": "row_no"}         # a stable order: one snapshot, one bronze


def _plain(value: Any) -> Any:
    """A Postgres value as the in-memory path holds it: a timestamp in UTC (the server's zone never shows)."""
    if isinstance(value, dt.datetime) and value.tzinfo is not None:
        return value.astimezone(dt.UTC)
    return value


def snapshot_of(rows: dict[str, list[dict[str, Any]]],
                stats: dict[str, tuple[int, Optional[dt.datetime]]]) -> Snapshot:
    """T5, pure: the rows read from Postgres (only the schema.sql columns of the eight §7.1 tables) and each table's
    own `count(*)` and `max(created_at)` from the same transaction, as a `Snapshot` the job reads like the memory
    one. A table the read did not return is an error, never an empty table."""
    missing = [t for t in TABLES if t not in rows or t not in stats]
    if missing:
        raise RuntimeError(f"postgres snapshot: tables not read: {missing}")
    return Snapshot("postgres", {t: [{c: _plain(r[c]) for c in COLUMNS[t]} for r in rows[t]] for t in TABLES},
                    {t: int(stats[t][0]) for t in TABLES}, {t: _plain(stats[t][1]) for t in TABLES})


def from_postgres(dsn: str) -> Snapshot:
    """T5: one read-only REPEATABLE READ transaction over the eight §7.1 tables (rows, counts and high-water marks
    all see the same data); it never writes and ends in a rollback. Only the schema.sql columns are selected, so a
    table that lost one fails here. `dsn` comes from `--dsn` or DATABASE_URL, never from the repo."""
    import psycopg
    from psycopg.rows import dict_row

    rows, stats = {}, {}
    with psycopg.connect(dsn, row_factory=dict_row) as conn:          # not autocommit: one transaction
        conn.execute("set transaction isolation level repeatable read, read only")
        if conn.execute("show transaction_read_only").fetchone()["transaction_read_only"] != "on":
            raise RuntimeError("postgres snapshot: the transaction is not read-only")
        conn.execute("set local time zone 'UTC'")
        for table in TABLES:
            cols = ", ".join(COLUMNS[table])
            rows[table] = conn.execute(f"select {cols} from {table} order by {ORDER[table]}").fetchall()
            got = conn.execute(f"select count(*) as n, max(created_at) as high from {table}").fetchone()
            stats[table] = (got["n"], got["high"])
        conn.rollback()
    return snapshot_of(rows, stats)


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value) if isinstance(value, (int, float, Decimal, str)) else json.dumps(value)


def build(snapshot: Snapshot, out: Path, loaded_at: dt.datetime) -> dict[str, dict[str, Any]]:
    """Write bronze/<table>.parquet and check AC-01 per table; returns {table: {rows, high_water}}."""
    out.mkdir(parents=True, exist_ok=True)
    stats = {}
    for table in TABLES:
        cols, rows = COLUMNS[table], snapshot.rows.get(table, [])
        extra = {k for r in rows for k in r} - set(cols)
        if extra:
            raise RuntimeError(f"bronze {table}: columns not in schema.sql: {sorted(extra)}")
        frame = pl.DataFrame({c: [_text(r.get(c)) for r in rows] for c in cols}, schema={c: pl.Utf8 for c in cols})
        frame = frame.with_columns(pl.lit(loaded_at).alias("_loaded_at"), pl.lit(snapshot.source).alias("_source"))
        frame.write_parquet(out / f"{table}.parquet")
        back = pl.read_parquet(out / f"{table}.parquet")
        got = (back.height, _max(back["created_at"].to_list()))
        want = (snapshot.counts.get(table, 0), snapshot.high_water.get(table))
        if got != want:
            raise RuntimeError(f"bronze {table}: lost rows (rows, max created_at) {got} != source {want}")
        stats[table] = {"rows": got[0], "high_water": None if got[1] is None else got[1].isoformat()}
    return stats
