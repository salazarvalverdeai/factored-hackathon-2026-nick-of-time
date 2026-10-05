"""Spec 13 AC-01 and AC-08 (EV1): the automatic `case_opened` and `card_blocked` customer notifications, written by the
MCP read that verified the write (constitution #4: accepted ≠ verified), once per case and event, on MemoryStore and
PostgresStore (`-m postgres`). In-app always; a confirmed channel the template lists is queued, never in a demo run
(ADR 0026). Offline: no provider is called."""
from __future__ import annotations

import pytest

from tests.test_spec01_store import backend, new_store  # noqa: F401
from tests.test_spec03_case_and_block import ANA, DEBIT, RUN, session, write_gold
from tests.test_spec03_case_reads import reads_run

S_DEMO = "S-anademorun000001"
DEMO_RUN = "demo-20261005T120000Z-ABCDEF"


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    return write_gold(tmp_path_factory.mktemp("data"))


def notes(run, case_id, run_id=RUN):
    return [n for n in run.store.list_notifications(ANA, run_id=run_id) if n.case_id == case_id]


def test_ac_01_a_verified_open_case_writes_one_case_opened_notification_in_app(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    assert notes(run, case.case_id) == []                              # accepted, not yet verified: nothing told
    run("get_case", case_id=case.case_id, action_id=case.action_id)
    [note] = notes(run, case.case_id)
    assert (note.event, note.channel, note.trigger, note.delivery_status) == ("case_opened", "log", "auto", "delivered")
    assert case.case_id in note.text and "Plazo legal" in note.text


def test_ac_01_a_verified_block_writes_one_card_blocked_notification_with_the_card_last4(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    block = run.block()
    run("get_product_status", product_id=DEBIT, action_id=block.action_id)
    [note] = notes(run, case.case_id)
    assert (note.event, note.channel) == ("card_blocked", "log")
    assert "4417" in note.text and case.case_id in note.text


def test_ac_01_an_unverified_write_is_never_notified(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    first = run.block()
    run("get_case", case_id=case.case_id)                              # a plain read verifies nothing
    run.store.block_product(case.case_id, DEBIT, action_id="A-0000000000BB", actor="agent", trace_id="t")
    out = run("get_product_status", product_id=DEBIT, action_id=first.action_id)   # NotVerified: superseded
    assert out.verification_id is None and notes(run, case.case_id) == []


def test_ac_01_a_repeated_verifying_read_writes_no_second_notification(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    block = run.block()
    for _ in range(3):
        assert run("get_case", case_id=case.case_id, action_id=case.action_id).verification_id
        assert run("get_product_status", product_id=DEBIT, action_id=block.action_id).verification_id
    assert sorted(n.event for n in notes(run, case.case_id)) == ["card_blocked", "case_opened"]


def test_ac_01_a_confirmed_channel_the_template_lists_is_queued_masked(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    run.store.add_channel_event(case.case_id, "telegram", "987654321", "linked", actor="customer", trace_id="t")
    run("get_case", case_id=case.case_id, action_id=case.action_id)
    by_channel = {n.channel: n for n in notes(run, case.case_id)}
    assert set(by_channel) == {"log", "telegram"}
    assert by_channel["telegram"].delivery_status == "queued"           # the api's notifier sends it, not a read
    assert "987654321" not in (by_channel["telegram"].masked_address or "")


def test_ac_01_adr_0026_a_demo_run_notifies_in_app_only(gold_dir):
    run = reads_run(gold_dir)
    run.sessions[S_DEMO] = session(S_DEMO, ANA, run_id=DEMO_RUN)
    case = run.open(1, session_id=S_DEMO)
    run.store.add_channel_event(case.case_id, "telegram", "987654321", "linked", actor="customer", trace_id="t")
    run("get_case", S_DEMO, case_id=case.case_id, action_id=case.action_id)
    block = run.block(session_id=S_DEMO)
    run("get_product_status", S_DEMO, product_id=DEBIT, action_id=block.action_id)
    rows = notes(run, case.case_id, run_id=DEMO_RUN)
    assert sorted(n.event for n in rows) == ["card_blocked", "case_opened"]
    assert {n.channel for n in rows} == {"log"}


def test_ac_08_an_automatic_notification_carries_no_score_policy_id_or_transcript(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    block = run.block()
    run("get_case", case_id=case.case_id, action_id=case.action_id)
    run("get_product_status", product_id=DEBIT, action_id=block.action_id)
    rows = notes(run, case.case_id)
    assert len(rows) == 2
    for note in rows:
        assert "POL-" not in note.text and "score" not in note.text.lower() and "high" not in note.text
