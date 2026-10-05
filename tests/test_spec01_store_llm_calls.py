"""Spec 01 §6.5 `llm_calls` (AO) for spec 04 AC-14 (a run returns its LLM usage so the api can write the rows) and spec
18 AC-10 (one row per billed judge call). Every test runs on both backends with the store suite's fixture: MemoryStore,
and PostgresStore in a fresh schema when TEST_DATABASE_URL is set (`-m postgres`; offline it skips)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from nick_of_time.store import Store, StoreError
from tests.test_spec01_store import RUN, backend, new_store, ticking_store  # noqa: F401

NUL, SURROGATE = chr(0), chr(0xD800)


def call(store: Store, **changes):
    fields = dict(trace_id="t", provider="bedrock", model="claude-haiku-4-5", tokens_in=120, tokens_out=40,
                  latency_ms=850, cost_usd=0.0012, run_id=RUN)
    return store.add_llm_call(**{**fields, **changes})


def test_ac_14_spec04_a_billed_call_is_one_row_with_its_usage_run_and_store_clock():
    """Spec 04 AC-14, spec 18 AC-10, §6.5: a fresh `LC-` id, the store's clock, the cost kept as a decimal; listed by
    run and trace, oldest first; runs never mix, and a run's tokens and cost sum alone (D-023)."""
    store = ticking_store()
    first, second = call(store, trace_id="run-1"), call(store, trace_id="run-1", tokens_in=7, cost_usd=Decimal("0.5"))
    other = call(store, trace_id="run-2", run_id=None, cost_usd=0)
    assert first.call_id.startswith("LC-") and len({first.call_id, second.call_id, other.call_id}) == 3
    assert first.created_at == dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC) and first.run_id == RUN
    assert (first.provider, first.model, first.tokens_in, first.tokens_out, first.latency_ms) == (
        "bedrock", "claude-haiku-4-5", 120, 40, 850)
    assert first.cost_usd == Decimal("0.0012") and isinstance(first.cost_usd, Decimal)
    assert store.list_llm_calls(run_id=RUN) == [first, second]
    assert store.list_llm_calls(run_id=RUN, trace_id="run-2") == []
    assert store.list_llm_calls(run_id=None) == [other] == store.list_llm_calls(run_id=None, trace_id="run-2")
    assert sum(c.cost_usd for c in store.list_llm_calls(run_id=RUN)) == Decimal("0.5012")


def test_ac_14_spec04_a_bad_call_is_refused_before_writing_and_the_interface_is_append_only():
    """§6.5: counts are non-negative integers, the cost is finite and non-negative, text holds no NUL or lone
    surrogate; every refusal is a StoreError and writes nothing; the interface has no update or delete."""
    store = new_store()
    bad_rows = [dict(trace_id=""), dict(provider=""), dict(model=""), dict(tokens_in=-1), dict(tokens_out=1.5),
                dict(latency_ms="5"), dict(tokens_in=True), dict(tokens_in=2**31), dict(cost_usd=-0.01),
                dict(cost_usd=float("nan")), dict(cost_usd=float("inf")), dict(cost_usd="x"), dict(extra=1),
                dict(trace_id="t" + NUL), dict(model="m" + SURROGATE), dict(run_id="r" + NUL)]
    for bad in bad_rows:
        with pytest.raises(StoreError):
            call(store, **bad)
    with pytest.raises(StoreError):
        store.list_llm_calls(run_id="r" + NUL)
    assert store.list_llm_calls(run_id=RUN) == [] == store.list_llm_calls(run_id=None)
    assert [n for n in dir(Store) if "llm_call" in n] == ["add_llm_call", "list_llm_calls"]
    assert [n for n in dir(type(store)) if "llm_call" in n] == ["add_llm_call", "list_llm_calls"]


def test_t9_llm_calls_that_tie_on_created_at_come_back_by_call_id():
    """§6.5, T9: on both backends, calls that share an instant keep one order, `call_id` ascending in the C collation."""
    store = new_store(now=lambda: dt.datetime(2026, 6, 1, 15, tzinfo=dt.UTC))
    rows = [call(store) for _ in range(8)]
    assert [c.call_id for c in store.list_llm_calls(run_id=RUN)] == sorted(c.call_id for c in rows)
