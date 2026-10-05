"""Spec 03 §6 (task 03c, [assumption] pending D-063/D-066): the queue status after the agent's writes, on both store
backends. `open_case` opens a case in `review` when the engine's own `queue_status_after` for it is `review` (medium or
human zone, a high-zone block a person must approve); `block_card`'s write moves a `new` case to `verification`. Both
moves commit or roll back with their write (inside `once`); reads never move a case."""
from __future__ import annotations

import pytest

from contracts import tools
from nick_of_time.store import StoreError
from tests.test_spec01_store import RUN, backend, types  # noqa: F401
from tests.test_spec03_case_and_block import ANA, DEBIT, S_BRUNO, denied, write_gold
from tests.test_spec03_case_reads import reads_run
from mcp_server import gate  # noqa: E402  (apps/mcp is on sys.path through the T4 test module)


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    return write_gold(tmp_path_factory.mktemp("data"))


def status(run, case_id):
    return run.store.queue_status(case_id)


def moves(run, case_id):
    return [e.payload["to"] for e in run.store.events(case_id) if e.type == "status_changed"]


def failing(run, monkeypatch, error):
    """`change_status` raises `error` until the returned switch is cleared (a plain function, so the in-memory
    store's rollback copy never holds a bound method)."""
    real, on = run.store.change_status, [True]

    def change_status(*args, **kwargs):
        if on:
            raise error
        return real(*args, **kwargs)
    monkeypatch.setattr(run.store, "change_status", change_status)
    return on


@pytest.mark.parametrize("n, zone, expected", [(1, "high", "new"), (2, "medium", "review"), (3, "human", "review"),
                                               (7, "high", "review")])   # 7: above the MX gate, a person blocks
def test_ac_09_d063_open_case_opens_in_review_when_the_engine_leaves_the_case_in_review(gold_dir, n, zone, expected):
    run = reads_run(gold_dir)
    case = run.open(n, zone)
    assert status(run, case.case_id) == expected and moves(run, case.case_id) == ([] if expected == "new" else
                                                                                   ["review"])
    assert run("get_case", case_id=case.case_id).status_label == ("Recibido" if expected == "new" else "En revisión")


def test_ac_15_d063_a_duplicate_open_case_moves_nothing(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(2, "medium")
    before = types(run.store, case.case_id)
    assert run.open(2, "medium").duplicate_of == case.case_id and types(run.store, case.case_id) == before


def test_ac_09_d063_the_review_move_rolls_back_with_the_case_on_an_outage(gold_dir, monkeypatch):
    run = reads_run(gold_dir)
    switch = failing(run, monkeypatch, StoreError("connection lost"))
    assert run("open_case", transaction_id="TRX-" + "0" * 19 + "2", dispute_type="unrecognized_charge",
               zone="medium", idempotency_key="k") == gate.UNAVAILABLE
    assert run.store.list_cases(ANA, run_id=RUN) == []             # no case left behind without its status
    switch.clear()
    case = run.open(2, "medium", idempotency_key="k")              # the key stored nothing: the retry writes
    assert moves(run, case.case_id) == ["review"]


def test_ac_04_d063_block_cards_write_moves_its_case_to_verification_exactly_once(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    first = run.block(idempotency_key="b1")
    assert status(run, case.case_id) == "verification"
    assert run.block(idempotency_key="b1") == first                # a replay writes nothing
    assert isinstance(run.block(idempotency_key="b2"), tools.BlockCardOut)
    assert moves(run, case.case_id) == ["verification"]


def test_ac_04_d063_a_move_made_meanwhile_by_another_writer_is_not_an_error(gold_dir, monkeypatch):
    run = reads_run(gold_dir)
    case = run.open(1)
    real = run.store.change_status

    def racing(case_id, to, **kwargs):
        real(case_id, to, **kwargs)                                 # another writer moved it first
        return real(case_id, to, **kwargs)                          # ours is refused by case_queue.transitions
    monkeypatch.setattr(run.store, "change_status", racing)
    assert isinstance(run.block(), tools.BlockCardOut)
    assert moves(run, case.case_id) == ["verification"] and types(run.store, case.case_id).count("card_blocked") == 1


@pytest.mark.parametrize("failure", [StoreError("connection lost"), OSError("connection reset")])
def test_ac_04_d063_an_outage_during_the_move_fails_the_block_and_stores_nothing(gold_dir, monkeypatch, failure):
    run = reads_run(gold_dir)
    case = run.open(1)
    switch = failing(run, monkeypatch, failure)
    assert run.block(idempotency_key="b") == gate.UNAVAILABLE
    assert types(run.store, case.case_id) == ["case_opened"] and run.store.product_status(DEBIT, run_id=RUN) is None
    switch.clear()
    assert isinstance(run.block(idempotency_key="b"), tools.BlockCardOut) and moves(run, case.case_id) == [
        "verification"]


def test_ac_16_d063_reads_never_move_a_case_own_foreign_or_unrelated(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    bruno = run.open(5, session_id=S_BRUNO)
    for tool, args in (("get_case", {"case_id": case.case_id, "action_id": case.action_id}),
                       ("get_case", {"case_id": case.case_id}), ("get_product_status", {"product_id": DEBIT}),
                       ("get_product_status", {"product_id": DEBIT, "action_id": case.action_id}),
                       ("list_my_cards", {}), ("list_my_cases", {}), ("get_case", {"case_id": bruno.case_id})):
        run(tool, **args)
    assert moves(run, case.case_id) == [] and moves(run, bruno.case_id) == []
    block = run.block()
    run("get_product_status", product_id=DEBIT, action_id=block.action_id)    # the verifying read of the block
    assert moves(run, case.case_id) == ["verification"]           # only the write's move


def test_ac_10_d063_a_held_high_zone_case_is_not_moved_by_a_denied_block(gold_dir):
    """A denied block moves nothing. The D-029 call-request case is moved to `review` by request_call itself (task
    03d1, PR #124); this test writes the `call_requested` event directly, so only the denied block is under test."""
    run = reads_run(gold_dir)
    case = run.open(1)
    run.call_requested(case.case_id)
    assert denied(run.block(), "POL-HUMAN-REQUEST") and moves(run, case.case_id) == []
