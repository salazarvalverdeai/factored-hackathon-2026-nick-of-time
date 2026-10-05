"""Spec 01 §6.5 — `packages/nick_of_time/store/schema.sql` mirrors the spec table (AC-01, T10, D-014, D-023).

[assumption] CI has no Postgres yet, so the tables load into DuckDB (Postgres-like DDL, `jsonb` aliased to JSON) as
the syntax and constraint check, and the Postgres-only trigger section is checked as text. The `postgres`-marked test
applies the whole file to a real server when `TEST_DATABASE_URL` is set; the CI service job comes with task 03a.
"""
from __future__ import annotations

import codecs
import os
import re
import secrets
from pathlib import Path
from typing import get_args

import duckdb
import pytest

from data.pipeline import contracts as gold
from nick_of_time.store import (ACTOR, CUSTOMER_VISIBLE, TRANSITIONS, WRITE_EVENTS, EventType, NewCase,
                                ProductOverride)

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "packages/nick_of_time/store/schema.sql").read_text()
TABLES_SQL, POSTGRES_ONLY = SQL.split("-- postgres-only")
SPEC = (ROOT / "specs/01-integration-contract.md").read_text()
SECTION = SPEC.split("### 6.5")[1].split("### 6.6")[0]
SPEC_TYPES = {"text": "VARCHAR", "text[]": "VARCHAR[]", "timestamptz": "TIMESTAMP WITH TIME ZONE", "date": "DATE",
              "int": "INTEGER", "bigint": "BIGINT", "bool": "BOOLEAN", "jsonb": "JSON", "numeric": "DECIMAL(18,3)"}
UNTYPED = {"created_at": "TIMESTAMP WITH TIME ZONE", "generated_at": "TIMESTAMP WITH TIME ZONE",
           "expires_at": "TIMESTAMP WITH TIME ZONE", "used_at": "TIMESTAMP WITH TIME ZONE",
           "tokens_in": "INTEGER", "tokens_out": "INTEGER", "latency_ms": "INTEGER"}      # else text (§6.5 convention)

CASE = ("insert into cases (case_id, customer_id, transaction_id, product_id, country, product_type, zone, "
        "dispute_type, opened_on, credit_deadline, ruling_deadline, deadline_source, deadline_source_url, "
        "deadline_verified_on, mode, trace_id) values ('{id}', 'CLI-1', 'TRX-1', 'PRD-1', 'MX', '{product}', "
        "'{zone}', '{dispute}', '2026-06-01', {dates}, {source}, '{mode}', 't')")
CREDIT, RULING, NO_DATES = "'2026-06-03', null", "null, '2026-07-01'", "null, null"
ACTION = '{{"action_id": "A-00000000000{n}"}}'
OVERRIDE = ("insert into product_overrides (override_id, product_id, status, case_id, actor) "
            "values ('{id}', 'PRD-1', '{status}', 'K-000001', '{actor}')")
NOTIFICATION = ("insert into notifications (notification_id, case_id, customer_id, event, channel, text, trigger) "
                "values ('{id}', 'K-000001', 'CLI-1', 'case_opened', '{channel}', 'Abrimos tu caso.', '{trigger}')")
DELIVERY = ("insert into notification_deliveries (delivery_id, notification_id, status) "
            "values ('{id}', '{n}', '{status}')")
DENIAL = ("insert into policy_denials (denial_id, trace_id, actor, policy_id, guardrail_id, detail) "
          "values ('{id}', 't', '{actor}', 'POL-QUEUE-TRANSITION', 'G-POL-01', '{{}}')")
SOURCE = "'Banxico', 'https://www.banxico.org.mx/', '2026-10-04'"
READ = '{"action_id": "A-000000000001", "verification_id": "V-000000000001", "read_at": "2026-06-01T15:00:00+00:00"}'


def case(id: str, dates: str = CREDIT, source: str = SOURCE, product: str = "debit", zone: str = "high",
         dispute: str = "unrecognized_charge", mode: str = "replay") -> str:
    return CASE.format(id=id, dates=dates, source=source, product=product, zone=zone, dispute=dispute, mode=mode)


def event(id: str, case: str, seq: int, type: str, payload: str = "{}", actor: str = "agent",
          visible: bool | None = None) -> str:
    visible = type in CUSTOMER_VISIBLE if visible is None else visible
    return ("insert into case_events (event_id, case_id, seq, type, actor, payload, customer_visible, trace_id) "
            f"values ('{id}', '{case}', {seq}, '{type}', '{actor}', '{payload}', {str(visible).lower()}, 't')")


GOOD = [case("K-000001"),
        case("K-000010", dates=RULING),                                        # a ruling date alone, with provenance
        case("K-000011", dates=NO_DATES, source="null, null, null", product="credit", zone="human",
             dispute="wrongful_charge", mode="live"),                         # no legal date, no provenance
        event("E-1", "K-000001", 1, "case_opened", ACTION.format(n=1)),
        event("E-5", "K-000001", 2, "action_verified", READ),
        event("E-6", "K-000001", 3, "handoff_emitted"),
        event("E-10", "K-000001", 4, "status_changed", '{"from": "new", "to": "review"}', actor="analyst:sub-1"),
        event("E-11", "K-000001", 5, "notification_sent", '{"notification_id": "N-1"}', actor="system"),
        event("E-20", "K-000001", 6, "status_changed", '{"from": "review", "to": "resolved"}', actor="analyst:sub-1"),
        event("E-21", "K-000001", 7, "block_verified", ACTION.format(n=1)),
        NOTIFICATION.format(id="N-1", channel="log", trigger="auto"),
        OVERRIDE.format(id="A-000000000009", status="Blocked", actor="agent"),
        DENIAL.format(id="P-0", actor="analyst:sub-1")]                   # no session: an analyst-side denial
BAD = [event("E-2", "K-000001", 1, "handoff_emitted"),                       # duplicate (case_id, seq)
       event("E-3", "K-999999", 1, "case_opened", ACTION.format(n=2)),       # no such case
       event("E-4", "K-000001", 9, "case_closed"),                           # not a §6.5 type
       event("E-7", "K-000011", 0, "handoff_emitted"),                       # seq starts at 1
       # the store's rules as rows: a write without its action id, a status change without a known status, an actor
       # outside agent|customer|system|analyst:<sub>, visibility off the ✓ list
       event("E-12", "K-000011", 1, "customer_info_added", '{"text": "x"}'),
       event("E-13", "K-000011", 1, "status_changed", '{"from": "new"}'),
       event("E-14", "K-000011", 1, "status_changed", '{"from": "new", "to": "archived"}'),
       event("E-15", "K-000011", 1, "handoff_emitted", actor="analyst:"),
       event("E-16", "K-000011", 1, "handoff_emitted", actor="analyst: "),
       event("E-17", "K-000011", 1, "handoff_emitted", actor="bot"),
       event("E-18", "K-000011", 1, "action_verified", READ, visible=True),
       event("E-19", "K-000011", 1, "receipt_issued", visible=False),
       event("E-22", "K-000011", 1, "handoff_emitted", actor="analyst:\t"),
       # an action id is an A- id; a read carries its action and V- id; only a person acts, takes, resolves, closes
       event("E-23", "K-000011", 1, "customer_info_added", '{"action_id": ""}'),
       event("E-24", "K-000011", 1, "customer_info_added", '{"action_id": "x"}'),
       event("E-34", "K-000011", 1, "customer_info_added", '{"action_id": "A-000000000001x"}'),
       event("E-25", "K-000011", 1, "notification_sent", '{"notification_id": "N-1", "action_id": "A-1"}'),
       event("E-26", "K-000011", 1, "action_verified", ACTION.format(n=1)),
       event("E-27", "K-000011", 1, "action_verified", '{"action_id": "A-000000000001", "verification_id": "V-1"}'),
       event("E-28", "K-000011", 1, "block_verified", '{"product_id": "PRD-1"}'),
       event("E-29", "K-000011", 1, "analyst_action", '{"action": "take"}'),
       event("E-30", "K-000011", 1, "assigned", actor="customer"),
       event("E-31", "K-000011", 1, "status_changed", '{"from": "review", "to": "resolved"}'),
       event("E-32", "K-000011", 1, "status_changed", '{"from": "resolved", "to": "closed"}', actor="system"),
       # D-014: a legal date travels with its source, an https URL and verified_on; none is ever empty or http
       case("K-000002", source="null, null, null"),
       case("K-000003", source="'Banxico', 'http://www.banxico.org.mx/', '2026-10-04'"),
       case("K-000004", source="'Banxico', 'https://www.banxico.org.mx/', null"),
       case("K-000005", source="'Banxico', null, '2026-10-04'"),
       case("K-000006", source="null, 'https://www.banxico.org.mx/', '2026-10-04'"),
       case("K-000007", dates=RULING, source="null, null, null"),
       case("K-000008", dates=NO_DATES, source="'', null, null"),
       case("K-000009", dates=NO_DATES, source="null, 'http://www.banxico.org.mx/', null"),
       case("K-000012", source="'Banxico', 'https://', '2026-10-04'"),         # a URL with no host
       case("K-000017", source="'Banxico', 'https:// x', '2026-10-04'"),       # a space in the URL
       case("K-000018", source="'Banxico', 'https://a b', '2026-10-04'"),
       # the NewCase Literals
       case("K-000013", mode="demo"), case("K-000014", zone="low"), case("K-000015", product="prepaid"),
       case("K-000016", dispute="other"),
       OVERRIDE.format(id="A-00000000000A", status="Gone", actor="agent"),
       OVERRIDE.format(id="A-00000000000B", status="Blocked", actor="analyst:"),
       OVERRIDE.format(id="A-00000000000C", status="Blocked", actor="analyst:\t"),
       DENIAL.format(id="P-3", actor="analyst: "),
       DENIAL.format(id="P-6", actor="analyst:\t"),
       DENIAL.format(id="P-4", actor="system"),                                  # the denial actors are a closed list
       "insert into sessions (session_id, otp_hash, expires_at, language, mode) "
       "values ('S-1', 'h', now(), 'es', 'demo')",
       DELIVERY.format(id="D-1", n="N-404", status="sent"),                      # no such notification
       DELIVERY.format(id="D-2", n="N-1", status="opened"),
       NOTIFICATION.format(id="N-2", channel="sms", trigger="auto"),
       NOTIFICATION.format(id="N-3", channel="log", trigger="cron"),
       "insert into customer_channels (channel_id, customer_id, channel, address, event) "
       "values ('C-1', 'CLI-1', 'email', 'a@example.com', 'deleted')",
       DENIAL.format(id="P-1", actor="bot"),
       DENIAL.format(id="P-2", actor="analyst:")]                                # an analyst with no sub
# A no-break space is blank too, as for the store's ACTOR: the CHECKs spell the class out, so no locale changes it.
NBSP_SUB = "analyst:\u00a0"
BAD += [event("E-33", "K-000011", 1, "handoff_emitted", actor=NBSP_SUB),
        OVERRIDE.format(id="A-00000000000D", status="Blocked", actor=NBSP_SUB), DENIAL.format(id="P-5", actor=NBSP_SUB),
        event("E-35", "K-000011", 1, "handoff_emitted", actor="analyst:x\n"),   # no newline in a sub, as in ACTOR
        DENIAL.format(id="P-7", actor="analyst:\nx")]
# Postgres only (DuckDB has no partial index): a write's action id cannot come back in another write (D-025).
BAD_ON_POSTGRES = [event("E-8", "K-000001", 8, "card_blocked", ACTION.format(n=1)),
                   event("E-9", "K-000010", 1, "customer_info_added", ACTION.format(n=1))]


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
    con.execute("create sequence row_no")             # DuckDB: no identity column; RE2 writes a \uXXXX escape as \x{XXXX}
    con.execute(re.sub(r"\\u([0-9a-f]{4})", r"\\x{\1}", TABLES_SQL).replace("generated always as identity",
                                                                       "default nextval('row_no')")
                .replace("'(?p)^", "'^"))                     # RE2's `.` already skips newlines
    yield con
    con.close()


def test_ac_01_schema_sql_has_the_spec_tables_columns_types_and_keys(db):
    """Same tables, columns in order, types, nullability (D-014 `deadline_verified_on` date null) and primary keys."""
    spec = spec_table()
    rows = db.execute("select table_name, column_name, data_type, is_nullable = 'YES' from information_schema.columns "
                      "order by table_name, ordinal_position").fetchall()
    pks = dict(db.execute("select table_name, constraint_column_names[1] from duckdb_constraints() "
                          "where constraint_type = 'PRIMARY KEY'").fetchall())
    assert {r[0] for r in rows} == set(spec) and len(spec) == 14    # call_requests: task 03d (D-026)
    for table, wanted in spec.items():
        got = [(c, kind, nullable, pks[table] == c) for t, c, kind, nullable in rows if t == table]
        assert got == wanted["columns"], table
    assert ("cases", "deadline_verified_on", "DATE", True) in rows and "is_fraud" not in SQL
    assert ("cases", "opened_on", "DATE", False) in rows and ("policy_denials", "session_id", "VARCHAR", True) in rows


def test_ac_01_schema_sql_keeps_the_spec_constraints(db):
    """unique (case_id, seq), seq ≥ 1, the FKs of §6.5, one bad row per listed vocabulary, and the deadline rule
    (D-014) with one bad row per missing, empty or http provenance field."""
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
    assert guarded == append_only_tables() and len(guarded) == 11 and "cases" in guarded
    assert "before update or delete or truncate on %I '\n" in POSTGRES_ONLY
    assert "'for each statement execute function forbid_append_only_change()', t || '_append_only', t)" in POSTGRES_ONLY
    assert "raise exception '% is append-only: % is not allowed', tg_table_name, tg_op;" in POSTGRES_ONLY


def sql_list(pattern: str) -> set[str]:
    return set(re.findall(r"'(\w+)'", re.search(pattern, TABLES_SQL, re.S).group(1)))


def test_d025_schema_vocabularies_match_the_store_models():
    """Each SQL list is the model's own: the always-write types, the status targets of case_queue.transitions, the
    hidden events, the override statuses and the NewCase Literals."""
    assert sql_list(r"check \(type not in \((.*?)\)\s+or \(payload ->> 'action_id'\) is not null\)") == \
        WRITE_EVENTS - {"notification_sent"} | {"action_verified", "block_verified"}   # a summary only on request
    assert re.fullmatch(ACTOR, NBSP_SUB) is None and re.fullmatch(ACTOR, "analyst:sub-1")   # the SQL mirrors ACTOR
    targets = {to for allowed in TRANSITIONS.values() for to in allowed}
    assert sql_list(r"coalesce\(payload ->> 'to', ''\) in \((.*?)\)\)") == targets
    assert sql_list(r"customer_visible = \(type not in \((.*?)\)\)\)") == set(get_args(EventType)) - CUSTOMER_VISIBLE
    assert sql_list(r"status text not null check \(status in \((.*?)\)\),\n  case_id") == \
        set(get_args(ProductOverride.model_fields["status"].annotation))
    for column in ("mode", "zone", "product_type", "dispute_type"):
        literal = NewCase.model_fields[column].annotation
        assert sql_list(rf"\n  {column} text not null check \({column} in \((.*?)\)\)") == set(get_args(literal))


def test_t10_actor_checks_spell_out_the_whitespace_of_the_store_actor():
    """The three actor CHECKs share one "sub not blank" class, exactly Python's str.isspace() set (ACTOR's \\s), so
    the schema and the store agree on any server locale (a glibc en_US \\S takes a no-break space as a character)."""
    classes = re.findall(r"actor ~ '\(\?p\)\^analyst:\.\*\[\^(.*?)\]\.\*\$'", TABLES_SQL)
    assert len(classes) == 3 and len(set(classes)) == 1
    blank = set()
    for first, last in re.findall(r"(\\[tnvfr]|\\u[0-9a-f]{4}| )(?:-(\\u[0-9a-f]{4}))?", classes[0]):
        low, high = (ord(codecs.decode(c, "unicode_escape")) for c in (first, last or first))
        blank |= {chr(c) for c in range(low, high + 1)}
    assert blank == {chr(c) for c in range(0x110000) if chr(c).isspace()}


def test_d025_an_action_id_is_unique_over_the_store_write_events():
    """The partial unique index covers exactly the store's WRITE_EVENTS (checked on a server by the postgres test)."""
    index = re.search(r"create unique index (?:if not exists )?case_events_action_id_once on case_events \(\(payload ->> 'action_id'\)\)"
                      r"\s+where type in \((.*?)\);", POSTGRES_ONLY, re.S)
    assert set(re.findall(r"'(\w+)'", index.group(1))) == WRITE_EVENTS


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
            for statement in BAD_ON_POSTGRES:
                with pytest.raises(psycopg.errors.UniqueViolation, match="case_events_action_id_once"):
                    con.execute(statement)
            for table in sorted(append_only_tables()):
                for op in (f"update {table} set created_at = created_at", f"delete from {table}", f"truncate {table}"):
                    with pytest.raises(psycopg.Error) as refused:
                        con.execute(op)
                    assert "append-only" in str(refused.value) or op.startswith("truncate"), op   # FK may stop it
            con.execute("update sessions set language = language")              # other tables stay writable
        finally:
            con.execute(f"drop schema {schema} cascade")
