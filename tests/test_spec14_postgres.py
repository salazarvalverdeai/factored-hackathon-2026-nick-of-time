"""Spec 14 T5: the Postgres source of the ops job and the Live series of ops_kpis.json.

The snapshot mapping, the Live series and `update_live` run offline on the in-memory store and the tiny gold fixture of
tests/test_spec14_bronze_silver.py. The Postgres tests (`-m postgres`) seed a fresh schema of TEST_DATABASE_URL (the
PostgresStore suite's DSN; never DATABASE_URL, which may be a real database) and drop it afterwards; offline they
skip. No real LLM, no real gold, no network beyond the test database.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import os
import re
import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

import tests.test_spec14_bronze_silver as base
from data.ops import bronze, run as job, sample, series
from nick_of_time import ids
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore

gold = base.gold                                                       # the shared gold fixture
PG_URL = os.environ.get("TEST_DATABASE_URL")
SCHEMA_SQL = bronze.SCHEMA_SQL.read_text()
EXPORT = Path(__file__).resolve().parents[1] / "apps/web/public/data/ops_kpis.json"
DEMO_A, DEMO_B, DEMO_C = ("demo-20261005T120000Z-AAAAAA", "demo-20261005T130000Z-BBBBBB",
                          "demo-20261005T140000Z-CCCCCC")
EVAL = "eval-pg:S0:9"
# personal data seeded into the source that must never reach silver, gold or the export (AC-08)
NAME, OTP, ADDRESS, TEXT, REASON = ("Valentina Prueba", "otp-hash-not-a-secret", "valentina@example.com",
                                    "Hola Valentina, tu caso", "no reconozco esta compra de mi tia")


def add_live_traffic(store: Any, txns: list[dict[str, Any]]) -> None:
    """Two live-mode demo sessions and one replay-mode demo session on the same charge (high zone, verified block,
    dated receipt; the replay one opened on the demo date), one live evaluation case and the personal data a demo
    session leaves: a typed name, an OTP hash, an address, a notification text and a customer's free-text reason."""
    t = txns[1]
    plan = ((DEMO_A, "live"), (DEMO_B, "live"), (EVAL, "live"), (DEMO_C, "replay"))
    for n, (run_id, mode) in enumerate(plan):
        trace = f"T-live-{n}"
        opened = dt.date(2026, 10, 6) if mode == "live" else sample.REPLAY_DAY
        case = store.create_case(NewCase(
            customer_id=t["customer_id"], transaction_id=t["transaction_id"], product_id=t["product_id"],
            country=t["country"], product_type=t["product_type"], zone="high", dispute_type="wrongful_charge",
            opened_on=opened, mode=mode, run_id=run_id, trace_id=trace),
            actor="agent", action_id=ids.new_id("action"))
        store.add_llm_call(trace_id=trace, provider="fake", model="fake-graph", tokens_in=800, tokens_out=90,
                           latency_ms=1000 + 100 * n, cost_usd="0.0030", run_id=run_id)
        block = ids.new_id("action")
        store.block_product(case.case_id, case.product_id, action_id=block, actor="agent", trace_id=trace)
        store.record_verification(case.case_id, block, read="get_product_status", run_id=run_id,
                                  customer_id=case.customer_id, actor="agent", trace_id=trace)
        store.change_status(case.case_id, "verification", on=opened, actor="agent", trace_id=trace)
        store.append_event(case.case_id, "receipt_issued", actor="agent", trace_id=trace,
                           payload={"receipt": {"receipt_id": ids.new_id("receipt"), "deadline": sample.DEADLINE}})
        if run_id == DEMO_A:
            store.append_event(case.case_id, "reevaluation_requested", actor="customer", trace_id=trace,
                               payload={"action_id": ids.new_id("action"), "reason": REASON, "origin": "customer"})
            store.add_notification(case.case_id, event="case_opened", channel="log", masked_address=ADDRESS,
                                   text=TEXT, trigger="auto", actor="agent", trace_id=trace)
    store.create_session(customer_id=t["customer_id"], otp_hash=OTP, expires_at=dt.datetime(2026, 10, 7, tzinfo=dt.UTC),
                         language="es", mode="live", run_id=DEMO_A, display_name=NAME)


@pytest.fixture
def memory(gold: Path) -> MemoryStore:
    """The sample store written the day before T0 (2026-10-04), then the demo traffic on T0's day (2026-10-05)."""
    ticks, shift = itertools.count(), [dt.timedelta(days=-1)]
    store = MemoryStore(now=lambda: base.T0 + shift[0] + dt.timedelta(milliseconds=next(ticks)))
    txns = sample.gold_transactions(gold)
    sample.seed(store, txns)
    shift[0] = dt.timedelta(0)
    add_live_traffic(store, txns)
    return store


def export_copy(tmp_path: Path) -> Path:
    path = tmp_path / "web" / "ops_kpis.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EXPORT, path)
    return path


def live_of(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))["data"]["series"]["live"]


def assert_live_counts_demo_traffic_only(live: dict[str, Any]) -> None:
    """Live ("Public demo traffic") counts, in both modes, the run-null cases of the sample (three replay, one live)
    and the three demo sessions (two live, one replay), never an evaluation case."""
    assert (live["key"], live["name"], live["status"], live["label"]) == (
        "live", "Public demo traffic", "ready", "[simulated]")
    assert live["message"].startswith("Public demo traffic on the deployed app since ")
    assert "historical gold state with the fixed demo date 2026-06-01" in live["reason"]
    assert "live-mode charges are synthetic (ADR 0020)" in live["reason"]
    total = live["total"]
    assert (total["cases"], total["demo_sessions"], total["cases_without_demo_session"]) == (7, 3, 4)
    assert total["synthetic_charges"] == 1 and total["unsafe_outcomes"] == 0      # two sessions are not a duplicate
    assert total["receipt_rate"] == {"value": 5 / 7, "numerator": 5, "denominator": 7}
    assert total["escalation_rate"]["numerator"] == 2 and total["automated_rate"]["numerator"] == 5
    live_mode, replay_mode = total["by_mode"]["live"], total["by_mode"]["replay"]
    assert (live_mode["cases"], live_mode["demo_sessions"], live_mode["synthetic_charges"]) == (3, 2, 1)
    assert (replay_mode["cases"], replay_mode["demo_sessions"], replay_mode["synthetic_charges"]) == (4, 1, 0)
    assert live_mode["receipt_rate"]["numerator"] + replay_mode["receipt_rate"]["numerator"] == 5
    assert sum(d["cases"] for d in live["days"]) == 7
    assert [sum(d["cases_by_mode"].values()) for d in live["days"]] == [d["cases"] for d in live["days"]]
    assert total["latency_p95_ms"] == 2500 and total["cost_usd"] == pytest.approx(4 * 0.0042 + 3 * 0.0030)


# ---------- offline: the mapping, the Live series and update_live ----------

def test_ac_01_postgres_rows_map_to_the_snapshot_without_a_database():
    """AC-01: `snapshot_of` keeps only the schema.sql columns, turns Postgres values into the memory path's (UTC
    timestamps), takes counts and high-water marks from the source's own read, and refuses a table not read."""
    lima = dt.timezone(dt.timedelta(hours=-5))
    at = dt.datetime(2026, 10, 5, 7, 0, tzinfo=lima)
    call = {"call_id": "LC-000000000001", "trace_id": "T-1", "provider": "fake", "model": "m", "tokens_in": 1,
            "tokens_out": 2, "latency_ms": 3, "cost_usd": Decimal("0.0042"), "run_id": None, "created_at": at,
            "display_name": NAME}                                      # a column the job never selects
    rows = {t: [] for t in bronze.TABLES} | {"llm_calls": [call]}
    stats = {t: (0, None) for t in bronze.TABLES} | {"llm_calls": (1, at)}
    snap = bronze.snapshot_of(rows, stats)
    assert snap.source == "postgres" and snap.counts["llm_calls"] == 1 and snap.counts["cases"] == 0
    (row,) = snap.rows["llm_calls"]
    assert list(row) == bronze.COLUMNS["llm_calls"] and "display_name" not in row
    assert row["created_at"] == at and row["created_at"].tzinfo == dt.UTC and row["created_at"].hour == 12
    assert snap.high_water["llm_calls"].tzinfo == dt.UTC
    assert bronze._text(row["cost_usd"]) == "0.0042" and bronze._text(row["created_at"]) == "2026-10-05T12:00:00+00:00"
    with pytest.raises(RuntimeError, match="tables not read"):
        bronze.snapshot_of({k: v for k, v in rows.items() if k != "cases"}, stats)


def test_ac_07_live_series_counts_public_demo_traffic_in_both_modes_and_never_an_eval_run(memory, gold, tmp_path):
    """AC-07: Live, "Public demo traffic" (the lead's reading of 2026-10-06), is built from the rows of operation and
    of the demo sessions (`demo-` runs) in both modes, with a live/replay breakdown, labeled [simulated]; an
    evaluation run never counts, and the gold tables stay operation only. A case's day is the UTC date it was written,
    so the replay-mode demo case counts on 2026-10-05, not on its demo date 2026-06-01."""
    web = export_copy(tmp_path)
    job.run(bronze.from_memory(memory), gold_path=gold, out=tmp_path / "ops", now=base.NOW, live_web=web)
    live = live_of(web)
    assert_live_counts_demo_traffic_only(live)
    assert live["message"] == "Public demo traffic on the deployed app since 2026-10-04"
    assert live["window"] == ["2026-10-04", "2026-10-05"]
    assert [(d["day"], d["cases"], d["cases_by_mode"]) for d in live["days"]] == [
        ("2026-10-04", 4, {"live": 1, "replay": 3}), ("2026-10-05", 3, {"live": 2, "replay": 1})]
    kpis = pl.read_parquet(tmp_path / "ops" / "gold" / "ops_kpis.parquet")
    assert kpis.filter(pl.col("mode") == "live")["cases"].to_list() == [1]           # operation: run_id null only
    assert kpis.filter(pl.col("mode") == "replay")["cases"].to_list() == [3]


def test_ac_09_no_live_rows_keep_the_series_pending(gold, tmp_path):
    """AC-09: with no row of operation or a demo session in either mode, Live stays the pending series and nothing
    else of the committed export changes."""
    store = MemoryStore()
    txns = sample.gold_transactions(gold)
    store.create_case(NewCase(**{k: txns[0][k] for k in ("customer_id", "transaction_id", "product_id", "country",
                                                           "product_type")}, zone="high",
                              dispute_type="unrecognized_charge", opened_on=dt.date(2026, 10, 6), mode="live",
                              run_id=EVAL, trace_id="T-eval"), actor="agent", action_id=ids.new_id("action"))
    web = export_copy(tmp_path)
    job.run(bronze.from_memory(store), gold_path=gold, out=tmp_path / "ops", now=base.NOW, live_web=web)
    assert live_of(web) == series.LIVE
    assert (series.LIVE["name"], series.LIVE["message"]) == ("Public demo traffic", "Pending: no public demo traffic yet")
    before, after = json.loads(EXPORT.read_text(encoding="utf-8")), json.loads(web.read_text(encoding="utf-8"))
    after["data"]["series"]["live"] = before["data"]["series"]["live"]
    assert after == before


def test_ac_09_only_the_live_series_changes_and_a_rerun_is_byte_identical(memory, gold, tmp_path):
    """AC-09, AC-05: `update_live` keeps the envelope, Bank today, the replay, `days` and `feedback` of the committed
    export and replaces only `data.series.live`; two runs on the same snapshot write the same bytes."""
    snap, outputs = bronze.from_memory(memory), []
    for n in (1, 2):
        web = export_copy(tmp_path / str(n))
        job.run(snap, gold_path=gold, out=tmp_path / f"ops{n}", now=base.NOW + dt.timedelta(minutes=n), live_web=web)
        outputs.append(web.read_bytes())
    assert outputs[0] == outputs[1]
    before, after = json.loads(EXPORT.read_text(encoding="utf-8")), json.loads(outputs[0])
    after["data"]["series"]["live"] = before["data"]["series"]["live"]
    assert after == before
    with pytest.raises(SystemExit, match="make ops-replay"):
        job.update_live(tmp_path / "missing.json", series.LIVE)


def test_ac_08_customer_text_never_reaches_silver_gold_or_the_live_series(memory, gold, tmp_path):
    """AC-08: a customer's reevaluation reason stays in bronze; silver, gold and the Live series hold no personal
    column or value."""
    web = export_copy(tmp_path)
    job.run(bronze.from_memory(memory), gold_path=gold, out=tmp_path / "ops", now=base.NOW, live_web=web)
    assert_no_personal_data(tmp_path / "ops", web)


def test_ac_08_ac_09_the_committed_live_series_holds_counts_and_rates_only():
    """AC-08, AC-09: the committed Live series (the run on a restored production backup, spec 14 §11.5) has the §7.4
    shape, adds up across days and modes, and holds no id, run, address or free text: counts and rates only."""
    live = json.loads(EXPORT.read_text(encoding="utf-8"))["data"]["series"]["live"]
    text = json.dumps(live, ensure_ascii=False)
    assert not re.search(r"CLI-|TRX-|PRD-|\bK-|demo-20|eval-|@|\bT-[0-9a-f]{4}", text)
    if live["status"] == "pending":
        assert live == series.LIVE
        return
    assert set(live) == {"key", "name", "status", "label", "message", "reason", "source", "window", "as_of", "days",
                         "total", "feedback", "notes"}
    assert (live["name"], live["label"]) == ("Public demo traffic", "[simulated]")
    assert live["message"] == f"Public demo traffic on the deployed app since {live['window'][0]}"
    total, by_mode = live["total"], live["total"]["by_mode"]
    assert set(by_mode) == set(series.MODES) and sum(m["cases"] for m in by_mode.values()) == total["cases"]
    assert sum(d["cases"] for d in live["days"]) == total["cases"]
    for d in live["days"]:
        assert sum(d["cases_by_mode"].values()) == d["cases"]
    assert by_mode["live"]["synthetic_charges"] == total["synthetic_charges"]   # a synthetic charge is live mode only


FORBIDDEN_COLUMNS = {"otp_hash", "display_name", "address", "masked_address", "text", "payload", "detail",
                     "provider_event", "value", "is_fraud", "fraud_score", "first_name", "email", "phone"}


def assert_no_personal_data(out: Path, web: Path) -> None:
    for layer in ("silver", "gold"):
        for path in sorted((out / layer).glob("*.parquet")):
            frame = pl.read_parquet(path)
            assert not FORBIDDEN_COLUMNS & set(frame.columns), path
            dump = frame.write_csv()
            assert not [v for v in (NAME, OTP, ADDRESS, TEXT, REASON) if v in dump], path
    for path in (out / "gold").glob("*.parquet"):
        assert "customer_id" not in pl.read_parquet(path).columns
    live = json.dumps(live_of(web), ensure_ascii=False)
    assert not [v for v in (NAME, OTP, ADDRESS, TEXT, REASON, "CLI-", "TRX-", "K-", DEMO_A, DEMO_C) if v in live]


# ---------- Postgres: the real source (`-m postgres`) ----------

@contextmanager
def seeded_postgres(gold: Path) -> Iterator[str]:
    """A fresh schema with schema.sql, seeded through PostgresStore like the memory store; yields its DSN."""
    import psycopg
    from psycopg.conninfo import make_conninfo

    from nick_of_time.store.postgres import PostgresStore
    schema = "t14_" + secrets.token_hex(4)
    dsn = make_conninfo(PG_URL, options=f"-c search_path={schema}")
    with psycopg.connect(PG_URL, autocommit=True) as admin:
        admin.execute(f"create schema {schema}")
        try:
            admin.execute(f"set search_path to {schema}")
            admin.execute(SCHEMA_SQL)
            store = PostgresStore(dsn)
            try:
                txns = sample.gold_transactions(gold)
                sample.seed(store, txns)
                add_live_traffic(store, txns)
                store.add_channel_event(store.list_all_cases(run_id=None)[0].case_id, "email", ADDRESS, "linked",
                                        actor="customer", trace_id="T-channel")
            finally:
                store.close()
            yield dsn
        finally:
            admin.execute(f"drop schema {schema} cascade")


def counts(dsn: str) -> dict[str, int]:
    import psycopg
    tables = list(bronze.schema_columns())
    with psycopg.connect(dsn) as conn:
        return {t: conn.execute(f"select count(*) from {t}").fetchone()[0] for t in tables}


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason="needs a PostgreSQL server at TEST_DATABASE_URL")
def test_ac_01_postgres_snapshot_lands_in_bronze_and_never_modifies_the_source(gold, tmp_path):
    """AC-01: one read-only snapshot lands every row of the eight tables in bronze with the source's counts; the
    source's row counts (all schema.sql tables) are the same before and after, and the read transaction refuses a
    write."""
    import psycopg

    with seeded_postgres(gold) as dsn:
        before = counts(dsn)
        snap = bronze.from_postgres(dsn)
        manifest = job.run(snap, gold_path=gold, out=tmp_path / "ops", now=dt.datetime.now(dt.UTC),
                           live_web=export_copy(tmp_path))
        assert counts(dsn) == before
        assert snap.source == "postgres"
        assert {t: snap.counts[t] for t in bronze.TABLES} == {t: before[t] for t in bronze.TABLES}
        assert {t: s["rows"] for t, s in manifest["source"]["tables"].items()} == snap.counts
        assert snap.counts["notifications"] == 1 and snap.counts["product_overrides"] == 7
        with psycopg.connect(dsn) as conn:
            conn.execute("set transaction isolation level repeatable read, read only")
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                conn.execute("insert into settings_events (event_id, key, value, actor) values ('x', 'k', '1', 'agent')")


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason="needs a PostgreSQL server at TEST_DATABASE_URL")
def test_ac_07_postgres_eval_rows_never_count(gold, tmp_path):
    """AC-07: from Postgres, the eval cases (`run_id` not null, not a demo run) never count in Live or in gold; the
    demo sessions count in Live only."""
    with seeded_postgres(gold) as dsn:
        web = export_copy(tmp_path)
        manifest = job.run(bronze.from_postgres(dsn), gold_path=gold, out=tmp_path / "ops",
                           now=dt.datetime.now(dt.UTC), live_web=web)
    assert_live_counts_demo_traffic_only(live_of(web))
    kpis = pl.read_parquet(tmp_path / "ops" / "gold" / "ops_kpis.parquet")
    assert kpis.filter(pl.col("mode") == "live")["cases"].to_list() == [1]
    assert manifest["source"]["eval_rows_excluded"]["cases"] == 5         # gold: sample eval, three demo, live eval
    assert set(pl.read_parquet(tmp_path / "ops" / "bronze" / "cases.parquet")["_source"]) == {"postgres"}
    feedback = pl.read_parquet(tmp_path / "ops" / "gold" / "feedback_cases.parquet")
    assert feedback["mode"].to_list() == ["replay"] * feedback.height


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason="needs a PostgreSQL server at TEST_DATABASE_URL")
def test_ac_08_postgres_personal_columns_never_reach_silver_or_gold(gold, tmp_path):
    """AC-08: with the Postgres column names, the demo display name, the OTP hash, the address, the notification
    text and the customer's reason stay out of silver, gold and the export (sessions and channels are not read)."""
    with seeded_postgres(gold) as dsn:
        web = export_copy(tmp_path)
        job.run(bronze.from_postgres(dsn), gold_path=gold, out=tmp_path / "ops", now=dt.datetime.now(dt.UTC),
                live_web=web)
    assert_no_personal_data(tmp_path / "ops", web)
    assert not {"sessions", "customer_channels"} & {p.stem for p in (tmp_path / "ops" / "bronze").glob("*.parquet")}


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason="needs a PostgreSQL server at TEST_DATABASE_URL")
def test_ac_09_postgres_rerun_writes_a_byte_identical_export(gold, tmp_path):
    """AC-09, AC-05: two runs on the same Postgres rows write the same ops_kpis.json bytes; only Live changed."""
    outputs = []
    with seeded_postgres(gold) as dsn:
        for n in (1, 2):
            web = export_copy(tmp_path / str(n))
            job.run(bronze.from_postgres(dsn), gold_path=gold, out=tmp_path / f"ops{n}", now=dt.datetime.now(dt.UTC),
                    live_web=web)
            outputs.append(web.read_bytes())
    assert outputs[0] == outputs[1]
    before, after = json.loads(EXPORT.read_text(encoding="utf-8")), json.loads(outputs[0])
    assert after["data"]["series"]["live"]["status"] == "ready"
    after["data"]["series"]["live"] = before["data"]["series"]["live"]
    assert after == before
