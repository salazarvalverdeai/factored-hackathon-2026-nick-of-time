"""Spec 03 T5: `get_product_status`, `list_my_cards`, `get_case`, `list_my_cases` through the real gate over the T4 gold
fixture and the store (MemoryStore, and PostgresStore when TEST_DATABASE_URL is set): the overlay status (AC-04),
fresh readings with `read_at`, stored deadlines, labels and timeline (AC-16), verification only of the read's own
write (D-025), cross-customer probes (D-052), and the latency benchmark on the fixture (AC-13). Offline."""
from __future__ import annotations

import datetime as dt
import itertools
import json

import pytest

from contracts import tools
from nick_of_time.policy import clock
from tests.test_spec01_store import backend, new_store, types  # noqa: F401
from tests.test_spec03_case_and_block import (ANA, BRUNO_CARD, CREDIT, DEBIT, S_BRUNO, S_OTHER_RUN, Run, session,
                                              write_gold)
from mcp_server import bench, case_reads  # noqa: E402  (apps/mcp is on sys.path through the T4 test module)

S_PT = "S-anaportugues0001"
TICKS = itertools.count()


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    return write_gold(tmp_path_factory.mktemp("data"))


def tick() -> dt.datetime:
    return dt.datetime(2026, 6, 1, 15, 0, tzinfo=dt.UTC) + dt.timedelta(seconds=next(TICKS))


def reads_run(gold_dir, store=None) -> Run:
    run = Run(gold_dir, store=store, extra=lambda r: case_reads.case_reads_handlers(r.gold, None, r.store, cards=r.cards, now=tick))
    run.sessions[S_PT] = session(S_PT, ANA, language="pt")
    return run


def plain(out) -> bool:
    return out.action_id is None and out.verification_id is None and out.read_at is not None


# ---------- AC-04: the block as an overlay ----------
def test_ac_04_after_block_card_get_product_status_reads_blocked_and_verifies_that_block(gold_dir):
    run = reads_run(gold_dir)
    assert run("get_product_status", product_id=DEBIT).status == "Active"           # gold, before any block
    run.open(1)
    block = run.block()
    out = run("get_product_status", product_id=DEBIT, action_id=block.action_id)
    assert (out.status, out.action_id, out.last4, out.type) == ("Blocked", block.action_id, "4417", "debit")
    assert out.verification_id.startswith("V-")
    assert plain(run("get_product_status", product_id=DEBIT)) and run("get_product_status", product_id=DEBIT).status \
        == "Blocked"
    assert run("get_product_status", S_OTHER_RUN, product_id=DEBIT).status == "Active"   # another run: gold
    assert run.cards.card(ANA, DEBIT).status == "Active"                              # gold never written


def test_ac_04_d025_a_read_verifies_only_its_own_write_whose_post_condition_holds(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    other = run.open(4)
    block = run.block()
    bruno = run.open(5, session_id=S_BRUNO)
    assert plain(run("get_product_status", product_id=DEBIT, action_id=case.action_id))    # open_case: get_case's
    assert plain(run("get_product_status", product_id=CREDIT, action_id=block.action_id))  # another card
    assert plain(run("get_product_status", product_id=DEBIT, action_id=bruno.action_id))   # another customer's
    assert plain(run("get_product_status", product_id=DEBIT, action_id="A-000000000000"))  # unknown
    assert plain(run("get_case", case_id=case.case_id, action_id=block.action_id))        # block: not get_case's
    assert plain(run("get_case", case_id=case.case_id, action_id=other.action_id))        # another case's opening
    assert types(run.store, case.case_id).count("action_verified") == 0
    assert types(run.store, other.case_id).count("action_verified") == 0


def test_ac_04_d025_a_block_that_is_no_longer_the_cards_latest_reads_plain_and_the_card_stays_blocked(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    first = run.block()
    run.store.block_product(case.case_id, DEBIT, action_id="A-0000000000BB", actor="agent", trace_id="t")
    out = run("get_product_status", product_id=DEBIT, action_id=first.action_id)      # NotVerified
    assert plain(out) and out.status == "Blocked"
    assert types(run.store, case.case_id).count("action_verified") == 0


# ---------- AC-16: fresh readings ----------
def test_ac_16_get_product_status_reads_the_store_on_every_call(gold_dir):
    run = reads_run(gold_dir)
    case = run.open(1)
    first = run("get_product_status", product_id=DEBIT)
    run.store.block_product(case.case_id, DEBIT, action_id="A-0000000000AA", actor="agent", trace_id="t")
    second = run("get_product_status", product_id=DEBIT)
    assert (first.status, second.status) == ("Active", "Blocked") and second.read_at > first.read_at


def test_ac_16_list_my_cards_lists_the_customers_cards_with_read_at_and_verifies_nothing(gold_dir):
    run = reads_run(gold_dir)
    run.open(1)
    run.block()
    out = run("list_my_cards")
    assert [(c.product_id, c.type, c.last4, c.status) for c in out.cards] == [
        (CREDIT, "credit", "0004", "Active"), (DEBIT, "debit", "4417", "Blocked")]          # no savings account
    assert out.read_at and all(plain(card) for card in out.cards)
    assert "4111111111114417" not in json.dumps(out.model_dump(mode="json"))             # AC-11: last 4 only


def test_ac_16_get_case_returns_stored_facts_label_timeline_and_verifies_its_open_case(gold_dir, monkeypatch):
    run = reads_run(gold_dir)
    opened = run.open(1)
    block = run.block()
    run("get_product_status", product_id=DEBIT, action_id=block.action_id)              # writes block_verified
    run.person_requested(opened.case_id)                                                 # handoff: not visible

    def never(*args, **kwargs):
        raise AssertionError("get_case recomputed a deadline")
    monkeypatch.setattr(clock, "deadline", never)
    out = run("get_case", case_id=opened.case_id, action_id=opened.action_id)
    assert (out.case_id, out.queue_status, out.status_label, out.taken_by_person) == (
        opened.case_id, "new", "Recibido", False)
    assert (out.credit_deadline, out.deadline_source_url) == (opened.credit_deadline, opened.deadline_source_url)
    assert (out.action_id, out.transaction.transaction_id, out.product_last4) == (opened.action_id, "TRX-" + "0" * 19
                                                                                  + "1", "4417")
    assert out.verification_id.startswith("V-")
    assert [(e.type, e.label) for e in out.timeline] == [("case_opened", "Caso abierto"),
                                                         ("card_blocked", "Bloqueo de la tarjeta solicitado"),
                                                         ("block_verified", "Bloqueo de la tarjeta verificado")]
    assert plain(run("get_case", case_id=opened.case_id))


def test_ac_16_get_case_shows_a_person_took_it_and_the_related_cases_in_both_directions(gold_dir):
    run = reads_run(gold_dir)
    first = run.open(1)
    run.analyst(first.case_id, "take", "review")
    taken = run("get_case", S_PT, case_id=first.case_id)
    assert (taken.taken_by_person, taken.status_label, taken.timeline[-1].label) == (True, "Em análise",
                                                                                     "Situação atualizada")
    for action, to in (("resolve", "resolved"), ("close_case", "closed")):
        run.analyst(first.case_id, action, to)
    second = run.open(1, related_case_id=first.case_id)
    assert run("get_case", case_id=second.case_id).related_case_id == first.case_id
    old = run("get_case", case_id=first.case_id)
    assert (old.related_case_id, old.status_label) == (second.case_id, "Cerrado")


def test_ac_16_d052_another_customers_case_is_not_found_and_logged(gold_dir):
    run = reads_run(gold_dir)
    bruno = run.open(5, session_id=S_BRUNO)
    probe, unknown = run("get_case", case_id=bruno.case_id), run("get_case", case_id="K-999999")
    card_probe, card_unknown = run("get_product_status", product_id=BRUNO_CARD), run(
        "get_product_status", product_id="PRD-UNKNOWN00001")
    assert probe == unknown and probe.code == "NOT_FOUND" and probe.policy_id is None
    assert card_probe == card_unknown and card_probe.code == "NOT_FOUND"
    assert [(d.policy_id, d.guardrail_id) for d in run.denials] == [("POL-CROSS-CUSTOMER", "G-SES-02")] * 2


def test_ac_16_list_my_cases_puts_active_first_with_labels_deadlines_and_updated_at(gold_dir):
    run = reads_run(gold_dir)
    assert run("list_my_cases").cases == []
    closed = run.open(1)
    for action, to in (("take", "review"), ("resolve", "resolved"), ("close_case", "closed")):
        run.analyst(closed.case_id, action, to)
    active = run.open(4)
    out = run("list_my_cases")
    assert [(c.case_id, c.queue_status, c.status_label, c.product_last4) for c in out.cases] == [
        (active.case_id, "new", "Recibido", "0004"), (closed.case_id, "closed", "Cerrado", "4417")]
    assert out.cases[0].ruling_deadline == active.ruling_deadline and out.read_at
    assert out.cases[1].updated_at == run.store.events(closed.case_id)[-1].created_at   # status_changed: visible


def test_ac_16_list_my_cases_updated_at_moves_only_with_customer_visible_events(gold_dir):
    run = reads_run(gold_dir, store=new_store(now=tick))                               # every event a second later
    case = run.open(1)
    opened_at = run.store.events(case.case_id)[0].created_at
    run.person_requested(case.case_id)                                                  # handoff_emitted: internal
    run.analyst(case.case_id, "mark_ambiguous")                                         # analyst_action: internal
    run("get_case", case_id=case.case_id, action_id=case.action_id)                     # action_verified: internal
    assert run.store.events(case.case_id)[-1].created_at > opened_at
    assert run("list_my_cases").cases[0].updated_at == opened_at
    assert run("list_my_cases", S_OTHER_RUN).cases == []                                   # another run


def test_ac_16_every_read_tool_has_a_handler_answering_its_contract_model(gold_dir):
    handlers = reads_run(gold_dir).gate._handlers
    assert {"get_product_status", "list_my_cards", "get_case", "list_my_cases"} <= set(handlers)
    assert [m.__name__ for m in (tools.CUSTOMER_TOOLS[name][1] for name in sorted(handlers) if name in (
        "get_case", "list_my_cards"))] == ["GetCaseOut", "ListMyCardsOut"]


# ---------- AC-13: latency benchmark ----------
def test_ac_13_the_benchmark_runs_offline_on_the_fixture_and_labels_its_numbers(gold_dir):
    result = bench.run(gold_dir, customers=5)
    lines, ok = bench.report(result, 800)
    assert ok and result["customers"] == 2 and all(line.startswith("[data]") for line in lines)
    assert {"open_case", "block_card", "get_case", "get_product_status", "list_my_cards", "list_my_cases",
            "search_transaction"} <= set(result["timings"])
    assert bench.p95([1.0]) == 1.0 and bench.p95([float(n) for n in range(1, 101)]) == pytest.approx(95.05)
