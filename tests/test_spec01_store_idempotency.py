"""Spec 01 — the store's idempotency accessor (T9, §6.5; spec 03 AC-03, AC-15). Every test runs on both backends with
the store suite's fixture: MemoryStore, and PostgresStore in a fresh schema when TEST_DATABASE_URL is set."""
from __future__ import annotations

import pytest

from nick_of_time import ids
from nick_of_time.store import Store, StoreError
from tests.test_spec01_store import RUN, at_once, backend, new_store, open_case, postgres_only, types  # noqa: F401

NUL, SURROGATE = chr(0), chr(0xD800)


def block(store: Store, case, key: str = "k1"):
    """A `block_card` as the tool runs it: one write per key, its result the action id."""
    def write():
        action_id = ids.new_id("action")
        store.block_product(case.case_id, case.product_id, action_id=action_id, actor="agent", trace_id="t")
        return {"action_id": action_id}
    return store.once(key, action="block_card", customer_id=case.customer_id, run_id=case.run_id, write=write)


def test_ac_15_spec03_the_same_key_returns_the_stored_result_and_writes_once():
    """T9, spec 03 AC-03 and AC-15: a repeated key replays the first result with no second write."""
    store = new_store()
    case = open_case(store, run_id=RUN)
    first, second = block(store, case), block(store, case)
    assert (first.replayed, second.replayed) == (False, True) and first.result == second.result
    assert types(store, case.case_id).count("card_blocked") == 1
    assert block(store, case, "k2").replayed is False and types(store, case.case_id).count("card_blocked") == 2


def test_ac_15_spec03_a_key_is_scoped_to_its_customer_run_and_action():
    """T9: another customer or run never replays this result; the same key for another action is refused."""
    store, calls = new_store(), []

    def once(customer_id="CLI-000001", run_id=RUN, action="open_case"):
        return store.once("k", action=action, customer_id=customer_id, run_id=run_id,
                          write=lambda: calls.append(1) or {"n": len(calls)})

    assert once().result == {"n": 1} and once().replayed
    assert [once(customer_id="CLI-000002").result, once(run_id=None).result, once(customer_id=None).result,
            once(run_id="EV-0002:S1:1").result] == [{"n": 2}, {"n": 3}, {"n": 4}, {"n": 5}]
    with pytest.raises(StoreError):
        once(action="block_card")
    assert len(calls) == 5


def test_ac_15_spec03_a_refused_write_is_not_remembered_and_the_stored_result_is_a_copy():
    """T9: a write that raises stores nothing, so the key can be tried again; callers cannot edit the stored row."""
    store = new_store()
    scope = dict(action="open_case", customer_id="CLI-000001", run_id=None)

    def refuse():
        raise StoreError("refused")

    with pytest.raises(StoreError):
        store.once("k", write=refuse, **scope)
    first = store.once("k", write=lambda: {"case_id": "C-1", "deadlines": [1]}, **scope)
    first.result["deadlines"].append(2)
    assert store.once("k", write=refuse, **scope).result == {"case_id": "C-1", "deadlines": [1]}


@pytest.mark.parametrize("bad", [dict(key=""), dict(key=" "), dict(key=7), dict(key="k" + NUL), dict(key=SURROGATE),
                                 dict(action=""), dict(action="a" + NUL), dict(customer_id="CLI:1"),
                                 dict(customer_id=""), dict(customer_id=SURROGATE), dict(run_id=""),
                                 dict(run_id="r" + NUL)])
def test_t9_a_bad_idempotent_call_is_a_store_error_and_never_runs_the_write(bad):
    """T9: bad input is a StoreError on both backends, before `write` runs (NUL and lone surrogates included)."""
    store, calls = new_store(), []
    args = dict(key="k", action="open_case", customer_id="CLI-000001", run_id=None) | bad
    with pytest.raises(StoreError):
        store.once(args.pop("key"), write=lambda: calls.append(1) or {}, **args)
    assert calls == []


@pytest.mark.parametrize("result", [{"x": float("nan")}, {"x": NUL}, {"x": {1, 2}}, ["not", "an", "object"], None])
def test_t9_a_result_that_is_not_a_json_object_is_refused_and_not_stored(result):
    """T9: the write's result must be a JSON object, as `jsonb` and the tools' results are."""
    store = new_store()
    scope = dict(action="open_case", customer_id="CLI-000001", run_id=None)
    with pytest.raises(StoreError):
        store.once("k", write=lambda: result, **scope)
    assert store.once("k", write=lambda: {"ok": True}, **scope).replayed is False


def test_t9_eight_writers_one_key_write_once(backend):  # noqa: F811
    """[postgres] spec 03 AC-15, T9: 8 connections call `once` with one key at once: one block, one shared result
    (without the key's advisory lock every one writes)."""
    postgres_only(backend)
    stores = [new_store() for _ in range(8)]
    case = open_case(stores[0], run_id=RUN)
    for key in ("a", "b", "c"):
        results = at_once([lambda s=s: block(s, case, key) for s in stores])
        assert [r for r in results if isinstance(r, StoreError)] == []
        assert sorted(r.replayed for r in results) == [False] + [True] * 7
        assert len({r.result["action_id"] for r in results}) == 1
    assert types(stores[0], case.case_id).count("card_blocked") == 3
