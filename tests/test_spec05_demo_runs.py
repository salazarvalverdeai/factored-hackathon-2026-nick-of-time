"""Spec 05 AC-14 and AC-16, store and MCP side (lead decision D-068, ADR 0026): the session row carries the visitor's
typed `display_name`, which `get_customer_profile` greets with (else gold's first name), and the analyst console reads
demo-run cases (`demo_runs=True`) while a demo session reads only its own run. A demo customer is shared by every
visitor, so a demo run lists no Telegram or e-mail channel and `send_case_summary` is refused there. Memory and Postgres
(`-m postgres`)."""
from __future__ import annotations

import datetime as dt
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path

import pytest

from contracts import tools
from nick_of_time import ids
from nick_of_time.policy import load_policies
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore
from tests.test_spec01_store import PG_URL, scratch_schema
from tests.test_spec05_catalog import ANA, CARD, TRX, gold  # noqa: F401  (gold is a fixture)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/mcp"))
from mcp_server import gate, notify, reads  # noqa: E402
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


def open_case(store, run_id):
    return store.create_case(NewCase(
        customer_id=ANA, transaction_id=TRX, product_id=CARD, country="MX", product_type="debit", zone="high",
        dispute_type="unrecognized_charge", opened_on=dt.date(2026, 6, 1), mode="replay", run_id=run_id,
        trace_id="t"), actor="agent", action_id=ids.new_id("action")).case_id


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
        case = open_case(store, RUN_A)
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


@pytest.mark.parametrize("backend", BACKENDS)
def test_ac_16_a_demo_run_lists_no_channel_and_refuses_summaries_while_production_keeps_them(gold, backend):  # noqa: F811
    with stores(backend) as build:
        store = build(now=lambda: START) if build else MemoryStore(now=lambda: START)
        production = open_case(store, None)                  # the customer confirmed Telegram on a production case
        store.add_channel_event(production, "telegram", "987654321", "linked", actor="system", trace_id="t")
        sent = []
        profile = reads.read_handlers(Gold(gold), load_policies(), channels=store.channels)["get_customer_profile"]
        summary = notify.notify_handlers(store, sender=lambda *a: sent.append(a) or "m-1")["send_case_summary"]
        for run_id, listed in ((RUN_A, []), (None, [{"channel": "telegram", "masked_address": "···4321"}])):
            row = StoreSessions(store).get(store.create_session(**SESSION, run_id=run_id).session_id)
            call = gate.Call(tool="get_customer_profile", session=row, trace_id="t")
            assert [c.model_dump() for c in profile(call, None).channels] == listed
            case = open_case(store, RUN_B) if run_id else production
            args = tools.SendCaseSummaryIn(session_id=row.session_id, case_id=case, channel="telegram",
                                           idempotency_key=f"k-{run_id}")
            out = summary(SimpleNamespace(tool="send_case_summary", session=row, trace_id="t"), args)
            if run_id:                                       # a demo run: refused, nothing written or sent
                assert out == notify.DEMO_NO_CHANNELS and out.code == "DENY"
                assert store.list_notifications(ANA, run_id=RUN_A) == [] and sent == []
            else:
                assert out.masked_address == "···4321" and len(sent) == 1
