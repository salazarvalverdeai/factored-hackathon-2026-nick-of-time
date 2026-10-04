"""Spec 01 §6.5 — `packages/nick_of_time/store/schema.sql` mirrors the spec table (AC-01, T10, D-014, D-023).

[assumption] CI has no Postgres yet, so the tables load into DuckDB (Postgres-like DDL, `jsonb` aliased to JSON) as
the syntax and constraint check, and the Postgres-only trigger section is checked as text. The `postgres`-marked test
applies the whole file to a real server when `TEST_DATABASE_URL` is set; the CI service job comes with task 03a.
"""
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import get_args

import duckdb
import pytest

from data.pipeline import contracts as gold
from nick_of_time.store import CUSTOMER_VISIBLE, EventType

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "packages/nick_of_time/store/schema.sql").read_text()
TABLES_SQL, POSTGRES_ONLY = SQL.split("-- postgres-only")
SPEC = (ROOT / "specs/01-integration-contract.md").read_text()
SECTION = SPEC.split("### 6.5")[1].split("### 6.6")[0]
SPEC_TYPES = {"text": "VARCHAR", "text[]": "VARCHAR[]", "timestamptz": "TIMESTAMP WITH TIME ZONE", "date": "DATE",
              "int": "INTEGER", "bool": "BOOLEAN", "jsonb": "JSON", "numeric": "DECIMAL(18,3)"}
UNTYPED = {"created_at": "TIMESTAMP WITH TIME ZONE", "generated_at": "TIMESTAMP WITH TIME ZONE",
           "expires_at": "TIMESTAMP WITH TIME ZONE", "used_at": "TIMESTAMP WITH TIME ZONE",
           "tokens_in": "INTEGER", "tokens_out": "INTEGER", "latency_ms": "INTEGER"}      # else text (§6.5 convention)

CASE = ("insert into cases (case_id, customer_id, transaction_id, product_id, country, product_type, zone, "
        "dispute_type, opened_on, credit_deadline, deadline_source, deadline_source_url, deadline_verified_on, mode, trace_id) "
        "values ('{id}', 'CLI-1', 'TRX-1', 'PRD-1', 'MX', 'debit', 'high', 'unrecognized_charge', '2026-06-01', "
        "'2026-06-03', {source}, 'replay', 't')")
EVENT = ("insert into case_events (event_id, case_id, seq, type, actor, customer_visible, trace_id) "
         "values ('{id}', '{case}', 1, '{type}', 'agent', true, 't')")
NOTIFICATION = ("insert into notifications (notification_id, case_id, customer_id, event, channel, text, trigger) "
                "values ('{id}', 'K-000001', 'CLI-1', 'case_opened', '{channel}', 'Abrimos tu caso.', '{trigger}')")
DELIVERY = ("insert into notification_deliveries (delivery_id, notification_id, status) "
            "values ('{id}', '{n}', '{status}')")
DENIAL = ("insert into policy_denials (denial_id, trace_id, actor, policy_id, guardrail_id, detail) "
          "values ('{id}', 't', '{actor}', 'POL-QUEUE-TRANSITION', 'G-POL-01', '{{}}')")
SOURCE = "'Banxico', 'https://www.banxico.org.mx/', '2026-10-04'"
GOOD = [CASE.format(id="K-000001", source=SOURCE), EVENT.format(id="E-1", case="K-000001", type="case_opened"),
        NOTIFICATION.format(id="N-1", channel="log", trigger="auto"),
        DENIAL.format(id="P-0", actor="analyst:sub-1")]                   # no session: an analyst-side denial
BAD = [EVENT.format(id="E-2", case="K-000001", type="customer_info_added"),     # duplicate (case_id, seq)
       EVENT.format(id="E-3", case="K-999999", type="case_opened"),             # no such case
       EVENT.format(id="E-4", case="K-000001", type="case_closed"),             # not an event type of §6.5
       CASE.format(id="K-000002", source="null, null, null"),                   # a legal date without its source
       CASE.format(id="K-000003", source="'Banxico', 'http://www.banxico.org.mx/', '2026-10-04'"),
       CASE.format(id="K-000004", source="'Banxico', 'https://www.banxico.org.mx/', null"),   # no verified_on
       "insert into sessions (session_id, otp_hash, expires_at, language, mode) "
       "values ('S-1', 'h', now(), 'es', 'demo')",
       DELIVERY.format(id="D-1", n="N-404", status="sent"),                      # no such notification
       DELIVERY.format(id="D-2", n="N-1", status="opened"),
       NOTIFICATION.format(id="N-2", channel="sms", trigger="auto"),
       NOTIFICATION.format(id="N-3", channel="log", trigger="cron"),
       "insert into customer_channels (channel_id, customer_id, channel, address, event) "
       "values ('C-1', 'CLI-1', 'email', 'a@example.com', 'deleted')",
       DENIAL.format(id="P-1", actor="bot")]


def spec_table() -> dict[str, dict]:
    """{table: {"ao": bool, "columns": [(name, duckdb type, nullable, pk)]}} parsed from the §6.5 markdown table."""
    tables = {}
    for line in SECTION.splitlines():
        if not line.startswith("| `"):
            continue
        cells = re.split(r"(?<!\\)\|", line)                              # `\|` inside a cell is not a border
        name = re.search(r"`(\w+)`", cells[1]).group(1)
        columns = []
        for item in cells[2].split(" · "):
            if item.strip().startswith("same columns as gold"):         # demo_transactions (gold contract, no is_fraud)
                pk = re.search(r"`(\w+)` PK", item).group(1)
                columns += [(c, gold.duckdb_type("transactions", c), c not in gold.required_columns("transactions"),
                             c == pk) for c in gold.columns("transactions") if c != "is_fraud"]
                continue
            column = re.match(r"\s*`(\w+)`\s*([\w\[\]]*)", item)
            words = item[column.end(1) + 1:]
            kind = SPEC_TYPES.get(column.group(2)) or UNTYPED.get(column.group(1), "VARCHAR")
            columns.append((column.group(1), kind, bool(re.search(r"\bnull\b", words)), " PK" in words))
        tables[name] = {"ao": "**AO**" in cells[1], "columns": columns}
    return tables


@pytest.fixture(scope="module")
def db():
    con = duckdb.connect()
    con.execute("create type jsonb as json")
    con.execute(TABLES_SQL)
    yield con
    con.close()


def test_ac_01_schema_sql_has_the_spec_tables_columns_types_and_keys(db):
    """Same tables, columns in order, types, nullability (D-014 `deadline_verified_on` date null) and primary keys."""
    spec = spec_table()
    rows = db.execute("select table_name, column_name, data_type, is_nullable = 'YES' from information_schema.columns "
                      "order by table_name, ordinal_position").fetchall()
    pks = dict(db.execute("select table_name, constraint_column_names[1] from duckdb_constraints() "
                          "where constraint_type = 'PRIMARY KEY'").fetchall())
    assert {r[0] for r in rows} == set(spec) and len(spec) == 13
    for table, wanted in spec.items():
        got = [(c, kind, nullable, pks[table] == c) for t, c, kind, nullable in rows if t == table]
        assert got == wanted["columns"], table
    assert ("cases", "deadline_verified_on", "DATE", True) in rows and "is_fraud" not in SQL
    assert ("cases", "opened_on", "DATE", False) in rows and ("policy_denials", "session_id", "VARCHAR", True) in rows


def test_ac_01_schema_sql_keeps_the_spec_constraints(db):
    """unique (case_id, seq), the FKs of §6.5, one bad row per listed vocabulary, and the deadline rule (D-014)."""
    links = db.execute("select table_name, constraint_type, constraint_column_names from duckdb_constraints() "
                       "where constraint_type in ('FOREIGN KEY', 'UNIQUE') order by 1, 2").fetchall()
    assert links == [("case_events", "FOREIGN KEY", ["case_id"]), ("case_events", "UNIQUE", ["case_id", "seq"]),
                     ("notification_deliveries", "FOREIGN KEY", ["notification_id"])]
    for statement in GOOD:
        db.execute(statement)
    for statement in BAD:
        with pytest.raises(duckdb.ConstraintException):
            db.execute(statement)


def test_ac_01_event_types_and_visibility_match_the_spec_and_the_store():
    text = SECTION.split("**Case event types**")[1].split("Queue statuses")[0]
    check = re.search(r"type text not null check \(type in \((.*?)\)\),", SQL, re.S).group(1)
    assert re.findall(r"`(\w+)`", text) == list(get_args(EventType)) == re.findall(r"'(\w+)'", check)
    assert set(re.findall(r"`(\w+)` ✓", text)) == CUSTOMER_VISIBLE


def append_only_tables() -> set[str]:
    return {name for name, table in spec_table().items() if table["ao"]}


def test_ac_01_append_only_tables_refuse_update_delete_and_truncate():
    """§6.5 AO tables (cases insert-only, D-023) are exactly the trigger's list; it fires before every statement."""
    guarded = set(re.findall(r"'(\w+)'", re.search(r"array\[(.*?)\]", POSTGRES_ONLY, re.S).group(1)))
    assert guarded == append_only_tables() and len(guarded) == 9 and "cases" in guarded
    assert "before update or delete or truncate on %I '\n" in POSTGRES_ONLY
    assert "'for each statement execute function forbid_append_only_change()', t || '_append_only', t)" in POSTGRES_ONLY
    assert "raise exception '% is append-only: % is not allowed', tg_table_name, tg_op;" in POSTGRES_ONLY


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs a PostgreSQL server at TEST_DATABASE_URL")
def test_ac_01_schema_sql_on_postgres_keeps_constraints_and_refuses_changes():
    """T10 on a real server: the whole file applies; bad rows fail; UPDATE, DELETE and TRUNCATE fail on AO tables."""
    psycopg = pytest.importorskip("psycopg")
    schema = "t01c_" + secrets.token_hex(4)
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as con:
        con.execute(f"create schema {schema}")
        try:
            con.execute(f"set search_path to {schema}")
            con.execute(SQL)
            for statement in GOOD:
                con.execute(statement)
            for statement in BAD:
                with pytest.raises(psycopg.errors.IntegrityError):
                    con.execute(statement)
            for table in sorted(append_only_tables()):
                for op in (f"update {table} set created_at = created_at", f"delete from {table}", f"truncate {table}"):
                    with pytest.raises(psycopg.Error) as refused:
                        con.execute(op)
                    assert "append-only" in str(refused.value) or op.startswith("truncate"), op   # FK may stop it
            con.execute("update sessions set language = language")              # other tables stay writable
        finally:
            con.execute(f"drop schema {schema} cascade")
