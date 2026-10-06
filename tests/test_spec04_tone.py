"""Spec 04 AC-44 (lead request 2026-10-06, tone): `nlu.tone` reads the customer's tone by rules (ES/PT, no LLM); a
non-calm tone adds one acknowledgement progress label and one opening line, and changes nothing else. Offline: fake MCP
(FastMCP in-memory), no LLM (arm S0)."""
from __future__ import annotations

import json

import pytest
import yaml

from nick_of_time.contracts import CONTRACTS_DIR
from nick_of_time.nlu import tone
from tests.test_spec04_decide import server
from tests.test_spec04_graph import Chat
from tests.test_spec04_progress import EV_0001, EV_0001_PT, progress, stream

TONE = yaml.safe_load((CONTRACTS_DIR / "messages.yaml").read_text(encoding="utf-8"))["tone"]


@pytest.mark.parametrize("text, expected", [
    ("No reconozco un cargo de 1250 USD en TIENDA X", "calm"),
    ("Ya pagué esa compra y me la volvieron a cobrar", "calm"),             # "ya" mid-sentence is not urgency
    ("Já paguei essa compra", "calm"),
    ("Agora vejo uma cobrança que não fiz", "calm"),
    ("Es urgente, no reconozco un cargo", "urgent"),
    ("Bloqueen mi tarjeta ya!", "urgent"),
    ("Necesito ayuda ahora mismo", "urgent"),
    ("Por favor, rápido", "urgent"),
    ("É urgente, não reconheço essa cobrança", "urgent"),
    ("Preciso disso agora mesmo", "urgent"),
    ("Bloqueia meu cartão já!", "urgent"),
    ("NO RECONOZCO ESTE CARGO", "urgent"),                                 # shouting, no frustration word
    ("No reconozco este cargo!!", "urgent"),
    ("Otra vez me cobran esto, nadie me ayuda", "frustrated"),
    ("Estoy harto, es una estafa", "frustrated"),
    ("De novo essa cobrança, ninguém me ajuda", "frustrated"),
    ("Isso é golpe", "frustrated"),
    ("Es urgente y estoy cansado de esto", "frustrated"),                  # frustration wins over urgency
    ("É urgente, de novo isso", "frustrated"),
    ("", "calm"),
])
def test_ac_44_tone_by_rules_es_pt(text, expected):
    assert tone(text) == expected


def test_ac_44_tone_lines_are_digit_free_es_pt():
    for key in ("urgent", "frustrated"):
        assert set(TONE[key]) == {"es", "pt"}
        assert not any(c.isdigit() for c in TONE[key]["es"] + TONE[key]["pt"])


@pytest.mark.parametrize("language, calm, loud, key", [
    ("es", EV_0001, "¡Es urgente! " + EV_0001, "urgent"),
    ("es", EV_0001, "Otra vez, nadie me ayuda. " + EV_0001, "frustrated"),
    ("pt", EV_0001_PT, "É urgente! " + EV_0001_PT, "urgent"),
])
def test_ac_44_tone_changes_no_decision_action_or_receipt(language, calm, loud, key):
    base = Chat(mcp_transport=server(), mode="replay").say(calm, language)
    felt = Chat(mcp_transport=server(), mode="replay").say(loud, language)
    for field in ("decision", "intent", "zone", "case_id"):
        assert getattr(felt, field) == getattr(base, field), field
    assert [(a.tool, a.state) for a in felt.actions] == [(a.tool, a.state) for a in base.actions]
    assert [s.id for s in felt.suggestions] == [s.id for s in base.suggestions]
    assert (felt.receipt is None) == (base.receipt is None)
    if base.receipt:
        moving = {"issued_at", "verified_at", "at", "trace_id", "receipt_id"}

        def same(receipt):
            return {k: v for k, v in receipt.model_dump(mode="json").items() if k not in moving}
        assert same(felt.receipt) == same(base.receipt)
    lines = felt.reply.splitlines()
    assert lines[0] == TONE[key][language]                                  # the template reply opens with the line
    assert lines[1:] == base.reply.splitlines()


@pytest.mark.parametrize("language, text, key", [("es", "¡Es urgente! " + EV_0001, "urgent"),
                                                 ("pt", "De novo! " + EV_0001_PT, "frustrated")])
def test_ac_44_one_tone_progress_label_when_not_calm(language, text, key):
    items = progress(stream(Chat(mcp_transport=server(), mode="replay"), text, language))
    tones = [i for i in items if i.step == "tone"]
    assert len(tones) == 1 and tones[0].label == TONE[key][language] and tones[0].state == "in_progress"


def test_ac_44_no_tone_label_when_calm():
    items = progress(stream(Chat(mcp_transport=server(), mode="replay"), EV_0001, "es"))
    assert "tone" not in [i.step for i in items]


@pytest.mark.parametrize("text, expected", [(EV_0001, "calm"), ("¡Es urgente! " + EV_0001, "urgent")])
def test_ac_44_the_llm_writer_gets_the_tone_and_its_prompt_asks_for_a_digit_free_acknowledgement(text, expected):
    from tests.test_spec04_writer import Writer, chat, rewrite, run
    writer = Writer(rewrite())
    _, turn = run(chat(writer), text)
    payload = json.loads(writer.calls[0]["user"])
    assert payload["tone"] == expected
    assert "`tone`" in writer.calls[0]["system"] and "no digits" in writer.calls[0]["system"]
    assert not any(TONE[key]["es"] in turn.reply for key in TONE)             # the writer words it, not the template
