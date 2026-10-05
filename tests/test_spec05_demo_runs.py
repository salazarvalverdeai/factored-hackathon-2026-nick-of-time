"""Spec 05 AC-14 and AC-16, store and MCP side (lead decision D-068, ADR 0026): the session row carries the visitor's
typed `display_name`, which `get_customer_profile` greets with (else gold's first name), and the analyst console reads
demo-run cases (`demo_runs=True`) while a demo session reads only its own run. Memory and Postgres (`-m postgres`)."""
from __future__ import annotations

import datetime as dt
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

from nick_of_time import ids
from nick_of_time.policy import load_policies
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore
from tests.test_spec01_store import PG_URL, scratch_schema
from tests.test_spec05_catalog import ANA, CARD, TRX, gold  # noqa: F401  (gold is a fixture)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/mcp"))
from mcp_server import gate, reads  # noqa: E402
from mcp_server.__main__ import StoreSessions  # noqa: E402
from mcp_server.gold import Gold  # noqa: E402

START = dt.datetime(2026, 6, 1, 15, tzinfo=dt.UTC)
SESSION = {"otp_hash": "h", "expires_at": START + dt.timedelta(minutes=15), "verified_at": START, "language": "es",
           "mode": "replay", "customer_id": ANA}
RUN_A, RUN_B = "demo-20260601T150000Z-ABCDEF", "demo-20260601T150001Z-GHIJKL"
BACKENDS = ["memory", pytest.param("postgres", marks=[pytest.mark.postgres, pytest.mark.skipif(
    not PG_URL, reason="needs a PostgreSQL server at TEST_DATABASE_URL")])]


def stores(backend):
    return scratch_schema() if backend == "postgres" else nullcontext(None)


@pytest.mark.parametrize("backend", BACKENDS)
def test_ac_14_the_profile_greets_with_the_typed_name_else_the_gold_name_through_the_session_row(gold, backend):  # noqa: F811
    with stores(backend) as build:
        store = build(now=lambda: START) if build else MemoryStore(now=lambda: START)
        typed = store.create_session(**SESSION, display_name="Visitante", run_id=RUN_A)
        plain = store.create_session(**SESSION)
        profile, rows = reads.read_handlers(Gold(gold), load_policies())["get_customer_profile"], StoreSessions(store)
        for sid, name in ((typed.session_id, "Visitante"), (plain.session_id, "Ana")):
            out = profile(gate.Call(tool="get_customer_profile", session=rows.get(sid), trace_id="t"), None)
            assert (out.first_name, out.country) == (name, "MX")


@pytest.mark.parametrize("backend", BACKENDS)
def test_ac_16_a_demo_run_sees_only_its_own_cases_and_blocks_and_the_console_sees_every_demo_run(backend):
    with stores(backend) as build:
        store = build(now=lambda: START) if build else MemoryStore(now=lambda: START)
        case = store.create_case(NewCase(
            customer_id=ANA, transaction_id=TRX, product_id=CARD, country="MX", product_type="debit", zone="high",
            dispute_type="unrecognized_charge", opened_on=dt.date(2026, 6, 1), mode="replay", run_id=RUN_A,
            trace_id="t"), actor="agent", action_id=ids.new_id("action")).case_id
        store.block_product(case, CARD, action_id=ids.new_id("action"), actor="agent", trace_id="t")
        assert [c.case_id for c in store.list_cases(ANA, run_id=RUN_A)] == [case]
        assert store.list_cases(ANA, run_id=RUN_B) == [] and store.get_case(case, run_id=RUN_B, customer_id=ANA) is None
        assert store.product_status(CARD, run_id=RUN_B) is None
        assert store.list_all_cases(run_id=None) == [] and store.get_case(case, run_id=None, customer_id=None) is None
        assert [c.case_id for c in store.list_all_cases(run_id=None, demo_runs=True)] == [case]
        assert store.get_case(case, run_id=None, customer_id=None, demo_runs=True).run_id == RUN_A
        eval_case = store.create_case(NewCase(**{**store.get_case(case, run_id=RUN_A, customer_id=ANA).model_dump(
            include=set(NewCase.model_fields)), "run_id": "EV-0101:S1:1"}), actor="agent",
            action_id=ids.new_id("action")).case_id
        assert eval_case not in [c.case_id for c in store.list_all_cases(run_id=None, demo_runs=True)]
