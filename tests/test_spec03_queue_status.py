"""Spec 03 §6 (task 03c, [assumption] pending D-063): the queue status after the agent's writes, on both store
backends. A medium- or human-zone case opens in `review`; a high-zone case stays `new` until a read verifies its block,
which moves it to `verification` (`approval.manual_check_leaves_case_in`); a held or unblocked high-zone case stays
`new` until an analyst takes it. Every move is a `status_changed` event that `case_queue.transitions` allows."""
from __future__ import annotations

import pytest

from tests.test_spec01_store import RUN, backend, types  # noqa: F401
from tests.test_spec03_case_and_block import ANA, DEBIT, write_gold
from tests.test_spec03_case_reads import reads_run


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    return write_gold(tmp_path_factory.mktemp("data"))


def status(run, case_id):
    return run.store.queue_status(case_id)


@pytest.mark.parametrize("n, zone, expected", [(1, "high", "new"), (2, "medium", "review"), (3, "human", "review")])
def test_ac_09_d063_open_case_leaves_a_handoff_zone_case_in_review_and_a_high_zone_case_new(gold_dir, n, zone,
                                                                                            expected):
    run = reads_run(gold_dir)
    case = run.open(n, zone)
    assert status(run, case.case_id) == expected
    changes = [e.payload for e in run.store.events(case.case_id) if e.type == "status_changed"]
    assert changes == ([] if expected == "new" else [{"from": "new", "to": "review", "on": "2026-06-01"}])
    assert run("get_case", case_id=case.case_id).status_label == ("Recibido" if expected == "new" else "En revisión")


def test_ac_15_d063_a_duplicate_open_case_moves_nothing(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(2, "medium")
    before = types(run.store, case.case_id)
    assert run.open(2, "medium").duplicate_of == case.case_id and types(run.store, case.case_id) == before


def test_ac_04_d063_a_verified_block_moves_its_case_to_verification_once(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    block = run.block()
    assert status(run, case.case_id) == "new"                                   # accepted is not verified
    run("get_product_status", product_id=DEBIT)                                  # a plain read verifies nothing
    assert status(run, case.case_id) == "new"
    for _ in range(2):                                                           # a second verifying read: no error
        assert run("get_product_status", product_id=DEBIT, action_id=block.action_id).verification_id
    assert status(run, case.case_id) == "verification"
    assert types(run.store, case.case_id).count("status_changed") == 1


def test_ac_04_d063_a_block_that_is_no_longer_the_cards_status_moves_nothing(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    first = run.block()
    run.store.block_product(case.case_id, DEBIT, action_id="A-0000000000CC", actor="agent", trace_id="t")
    run("get_product_status", product_id=DEBIT, action_id=first.action_id)
    assert status(run, case.case_id) == "new"


def test_ac_10_d063_a_held_high_zone_case_stays_new_until_an_analyst_takes_it(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    run.call_requested(case.case_id)
    run.block()                                                                  # denied: POL-HUMAN-REQUEST
    assert status(run, case.case_id) == "new" and run.store.list_cases(ANA, run_id=RUN)[0].case_id == case.case_id
    run.analyst(case.case_id, "take", "review")
    assert status(run, case.case_id) == "review"


def test_ac_04_d063_a_verified_block_on_a_case_in_review_keeps_review(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    run.analyst(case.case_id, "take", "review")
    block = run.block()
    run("get_product_status", product_id=DEBIT, action_id=block.action_id)
    assert status(run, case.case_id) == "review"
