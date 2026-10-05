"""Task DLANG (spec 04 AC-10 and AC-05; spec 03 §6 compute_deadline; spec 02 §4.3; contract 1.5.0): the legal source
the customer reads is the clock entry's `source_label` in the session's language, returned by the tool, never
translated by the agent; the analyst's handoff keeps the stored `source`, and the grounding gate drops nothing."""
from __future__ import annotations

import re

import pytest

from nick_of_time.policy import clock, load_policies
from tests.test_spec03_deadline import COUNTRIES, FIRST, Run, gold_dir  # noqa: F401  (gold_dir is a fixture)
from tests.test_spec04_act import EV_0001
from tests.test_spec04_decide import server
from tests.test_spec04_graph import Chat, fake, intake

ENGLISH = re.compile(r"\b(as amended|amended|and|by|numerals?)\b")
NUMBERS = re.compile(r"\d+(?:[./]\d+)*")
ROWS = {(country, product, entry.source): entry for country, products in load_policies().regulatory_clock.items()
        for product, rows in products.items() for entry in rows}
CASE = fake.FIXTURES["get_case"]


def label(source: str, language: str) -> str:
    return getattr(next(e for e in ROWS.values() if e.source == source).source_label, language)


@pytest.mark.parametrize("key", ROWS, ids=lambda key: "-".join(key[:2]) + ":" + key[2][:12])
def test_ac_10_every_clock_row_has_an_es_and_a_pt_label_of_the_same_source(key):
    """Every row (MX debit and credit, AR, CO, BR; PE and CL have none) names its source in es and pt, with no English
    and the same legal numbers as `source` (the same act, same source_url), so the label adds no fact of its own."""
    entry = ROWS[key]
    for language in ("es", "pt"):
        text = getattr(entry.source_label, language)
        assert text and not ENGLISH.search(text), (key, language)
        assert set(NUMBERS.findall(text)) == set(NUMBERS.findall(entry.source)), (key, language)
    assert {"PE", "CL"}.isdisjoint(load_policies().regulatory_clock)       # POL-CLOCK-UNKNOWN: no source to show


def test_ac_10_source_label_reads_the_entry_in_the_language_and_nothing_for_an_unknown_source():
    mx = ROWS["MX", "debit", "Banxico Circular 3/2012, arts. 19 Bis 3 and 19 Bis 4 (as amended by Circular 14/2018)"]
    assert clock.source_label(mx.source, "es") == mx.source_label.es
    assert clock.source_label(mx.source, "pt") == mx.source_label.pt
    assert clock.source_label(mx.source, "en") == mx.source_label.es                        # es by default
    assert clock.source_label("Banxico Circular 3/2012, as amended by Circular 14/2018", "es") is None   # old case
    assert clock.source_label(None, "es") is None


@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_10_compute_deadline_returns_the_label_in_the_sessions_language_for_every_row(gold_dir, language):  # noqa: F811
    """Spec 03 §6: compute_deadline adds `deadline_source_label`; `deadline_source` stays the analyst's name."""
    run, seen = Run(gold_dir, language=language), set()
    for n, customer in [(1, None), (2, None), (4, None), *((FIRST[c], c) for c in COUNTRIES)]:
        out = run(n, customer) if customer else run(n)
        if out.__class__.__name__ != "ComputeDeadlineOut":
            continue                                                         # a country with no row (PE, CL)
        assert out.deadline_source_label == label(out.deadline_source, language)
        assert not ENGLISH.search(out.deadline_source_label)
        seen.add(out.deadline_source)
    assert seen == {source for _, _, source in ROWS}                         # every row was read


@pytest.mark.parametrize("key", ROWS, ids=lambda key: "-".join(key[:2]) + ":" + key[2][:12])
@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_10_the_customers_deadline_lines_show_the_label_and_no_english(key, language):
    """The reply's verified lines (act) and a status read (status) print the label get_case returned, never `source`."""
    entry = ROWS[key]
    case = {**CASE, "deadline_source": entry.source, "deadline_source_label": getattr(entry.source_label, language),
            "ruling_deadline": "2026-07-16"}
    lines = [line for line in intake.verified_lines(case, None, None, language) if "2026-07-16" in line]
    lines += [intake.msg.text("status.ruling_deadline", language, **intake.sourced(case))]
    for line in lines:
        assert getattr(entry.source_label, language) in line and not ENGLISH.search(line.split("http")[0]), line


@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_05_end_to_end_the_receipt_shows_the_label_the_handoff_keeps_the_source_and_nothing_is_dropped(language):
    """Chat.say asserts the gate dropped 0 facts (AC-05); the receipt's source is get_case's label, the handoff's the
    stored source, and no customer line carries the English name."""
    mx = next(e for (c, p, _), e in ROWS.items() if (c, p) == ("MX", "debit"))
    case = {**CASE, "deadline_source": mx.source, "deadline_source_label": getattr(mx.source_label, language)}
    turn = Chat(mcp_transport=server(get_case=case)).say(EV_0001, language=language)
    assert turn.receipt.deadline.deadline_source == case["deadline_source_label"]
    assert turn.handoff["deadline"]["deadline_source"] == mx.source
    deadline = next(line for line in turn.reply.splitlines() if "2026-06-03" in line)
    assert case["deadline_source_label"] in deadline and mx.source not in turn.reply


@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_10_the_fake_server_answers_the_label_in_its_sessions_language(language):
    """The fake MCP reads its session's language as the real one does (the charge's active case is reported)."""
    turn = Chat(mcp_transport=fake.build_server(language)).say(EV_0001, language=language)
    other = fake._LABEL["pt" if language == "es" else "es"]
    assert fake._LABEL[language] in turn.reply and other not in turn.reply
