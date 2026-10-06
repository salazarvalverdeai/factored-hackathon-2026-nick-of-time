"""Spec 04 AC-37, AC-39, AC-40 (§4.6 writer, ADR 0030) and spec 01 AC-10 (§6.4.1 `text` chunks). The writer is a
scripted fake client (CLAUDE.md: never a real LLM in CI) that rewrites the template lines it is given, so every test
runs the real graph, gate and stream on the fake MCP. Arm S0: the writer is the only LLM of the turn."""
from __future__ import annotations

import asyncio
import json
import re
import time

import pytest

from nick_of_time import receipt as msg
from nick_of_time.config import SONNET, price, resolve
from nick_of_time.contracts import TurnResult
from nick_of_time.events import TextChunk
from nick_of_time.llm import FakeClient, ProviderUnavailable
from nick_of_time.llm import writer as wording
from tests.test_spec04_decide import server
from tests.test_spec04_graph import Chat, fake_budget

EV_0001 = "No reconozco un cargo de 1250 USD en TIENDA X"        # MX, debit, score 72 (high), replay
CALM = "Con calma: "


class Writer(FakeClient):
    """A fake writer whose text is `fn(payload)`: it sees the same JSON the real writer gets."""

    def __init__(self, fn):
        super().__init__(SONNET, script=[], prices=price(resolve("S2")))
        self.fn = fn

    def _call(self, system, user, schema, tool_name, max_tokens, mode, temperature):
        self.calls.append({"system": system, "user": user})
        text = self.fn(json.loads(user))
        return {"text": text, "tool_input": None, "stop_reason": "end_turn", "tokens_in": len(system + user) // 4,
                "tokens_out": len(text) // 4}


def rewrite(corrupt: str | None = None, chips: str = "") -> callable:
    """Digit-free lines get a new opening (released as written); lines with a digit are copied, except the first one
    holding `corrupt`, whose figure is changed (ungrounded); then the chips line."""
    def fn(payload):
        out, spoiled = [], False
        for item in payload["lines"]:
            n, text = item["n"], item["text"]
            if corrupt and corrupt in text and not spoiled:
                out.append(f"[{n}] {text.replace(corrupt, '9' + corrupt[1:])}")
                spoiled = True
            else:
                out.append(f"[{n}] {text if re.search(r'[0-9]', text) else CALM + text}")
        return "\n".join(out + ([f"[chips] {chips}"] if chips else []))
    return fn


def run(chat: Chat, text: str | None, language: str = "es") -> tuple[list[tuple[str, dict]], TurnResult]:
    payload = {"messages": [{"role": "user", "content": text}] if text else [], "language": language, "action": None}

    async def go():
        return [(mode, chunk) async for mode, chunk in chat.graph.astream(payload, chat.config,
                                                                        stream_mode=["custom", "values"])]
    with fake_budget():
        chunks = asyncio.run(go())
    return chunks, TurnResult.model_validate({k: v for k, v in chunks[-1][1].items() if k in TurnResult.model_fields})


def texts(chunks) -> list[TextChunk]:
    return [TextChunk.model_validate(c) for m, c in chunks if m == "custom" and c.get("kind") == "text"]


def chat(client=None, **settings) -> Chat:
    return Chat(mcp_transport=server(), mode="replay", writer="llm", writer_client=client, **settings)


def template_turn(text: str | None = None) -> TurnResult:
    return run(Chat(mcp_transport=server(), mode="replay"), text)[1]


def test_ac_37_spec01_ac_10_the_writer_streams_text_chunks_and_holds_an_ungrounded_figure_line():
    writer = Writer(rewrite(corrupt="1250"))
    chunks, turn = run(chat(writer), EV_0001)
    sent = texts(chunks)
    assert sent and len({c.message_id for c in sent}) == 1                       # one message per reply
    assert "".join(c.delta for c in sent) == turn.reply                          # final reply = released lines
    payload = json.loads(writer.calls[0]["user"])
    template = [item["text"] for item in payload["lines"]]
    spoiled = next(line for line in template if "1250" in line)
    # the changed figure never left; its template line did, in its place
    assert not any("9250" in c.delta for c in sent) and "9250" not in turn.reply
    assert spoiled in turn.reply.splitlines()
    assert "G-OUT-01" in turn.guardrails_triggered and turn.trace[-1].detail.startswith("G-OUT-01: 1")
    # every digit-free line was reworded; every other figure line was released as the writer wrote it
    for line in template:
        assert (CALM + line if not re.search(r"[0-9]", line) else line) in turn.reply.splitlines()
    # the writer saw the gated template lines only: no score, zone or rule id (§4.6)
    assert not re.search(r"score|POL-|zone|zona|72", writer.calls[0]["user"].replace(spoiled, ""), re.I)
    # its billed call is a usage row the api writes to llm_calls (AC-14)
    assert [(u.model, u.cost_usd > 0) for u in turn.usage] == [(SONNET, True)]
    # the receipt and the handoff card stay tool-built: the same as with the template writer
    assert turn.receipt.verified_facts and turn.handoff


@pytest.mark.parametrize("failure", [ProviderUnavailable("throttled"), RuntimeError("boom")])
def test_ac_37_any_writer_error_gives_the_whole_template_reply_and_no_text(failure):
    def fail(_payload):
        raise failure
    chunks, turn = run(chat(Writer(fail)), None)                # the greeting turn: no ids, so replies compare
    golden = template_turn()
    assert not texts(chunks) and turn.usage == []
    assert (turn.reply, turn.suggestions) == (golden.reply, golden.suggestions)
    assert turn.trace[-1].detail.startswith("writer -> template: ") and turn.trace[-1].status == "error"


def test_ac_37_a_writer_past_its_timeout_gives_the_template(monkeypatch):
    monkeypatch.setattr(wording, "TIMEOUT_S", 0.05)

    def slow(payload):
        time.sleep(0.5)
        return "[1] tarde"
    _, turn = run(chat(Writer(slow)), None)
    assert turn.reply == template_turn().reply and turn.trace[-1].detail == "writer -> template: timeout"


def test_ac_37_past_the_daily_cap_the_writer_is_not_called():
    writer = Writer(rewrite())
    _, turn = run(chat(writer, llm_day_spent_usd=10.0, llm_day_cap_usd=10.0), None)
    assert writer.calls == [] and turn.reply == template_turn().reply and "G-OPS-01" in turn.guardrails_triggered


def test_ac_39_the_writer_picks_and_words_chips_from_the_allowed_row_and_a_person_stays():
    chips = ("check_case: Ver cómo va mi caso | view_case: Abrir mi caso | report_duplicate: "
             + "x" * 41 + " | report_unrecognized: Ver https://banco.example")
    _, turn = run(chat(Writer(rewrite(chips=chips))), None)       # greet row: no case, so view_case is not allowed
    allowed = msg.allowed("greet")
    assert [(s.id, s.label) for s in turn.suggestions] == [("check_case", "Ver cómo va mi caso"),
                                                          ("talk_to_person", "Hablar con una persona")]
    assert {s.id for s in turn.suggestions} <= set(allowed)


def test_ac_39_fewer_than_two_surviving_chips_use_the_row_as_today():
    _, turn = run(chat(Writer(rewrite(chips="send_summary: Mándame el comprobante"))), None)
    assert turn.suggestions == template_turn().suggestions


@pytest.mark.parametrize("chosen, expected", [
    ([("talk_to_person", "Una persona"), ("show_recent", "Mis cargos")], [("show_recent", "Mis cargos"),
                                                                           ("talk_to_person", "Una persona")]),
    ([("check_case", "Mi caso"), ("talk_to_person", "Una persona")], None),           # check_case: not in the row
    ([("show_recent", "Últimos cargos"), ("dont_remember_amount", "No sé el monto"), ("none_of_these", "Ninguno")],
     [("show_recent", "Últimos cargos"), ("dont_remember_amount", "No sé el monto"),
      ("talk_to_person", "Hablar con una persona")]),
    ([("show_recent", "Ver 3 cargos"), ("talk_to_person", "Persona")], None),            # a digit: dropped
])
def test_ac_39_suggestions_filter_keeps_the_allowed_set_and_the_person(chosen, expected):
    got = msg.suggestions("ask_details", "es", None, chosen)
    template = msg.suggestions("ask_details", "es")
    assert [(s.id, s.label) for s in got] == (expected or [(s.id, s.label) for s in template])
    assert any(s.id in msg.PERSON for s in got)


@pytest.mark.parametrize("text", [None, EV_0001])
def test_ac_40_the_template_writer_is_unchanged_and_never_calls_the_writer(text):
    writer = Writer(rewrite())
    chunks, turn = run(Chat(mcp_transport=server(), mode="replay", writer="template", writer_client=writer), text)
    default = template_turn(text)
    assert writer.calls == [] and not texts(chunks) and turn.usage == []
    strip = re.compile(r"K-\d+|V-\w+|\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC")     # ids and stamps differ between runs
    assert strip.sub("", turn.reply) == strip.sub("", default.reply)
    assert [s.id for s in turn.suggestions] == [s.id for s in default.suggestions]
    # golden: the template rows are what suggestions() gave before ADR 0030 (first 3 of the row, a person added)
    assert [s.id for s in msg.suggestions("ask_details", "es")] == ["show_recent", "dont_remember_amount",
                                                                    "talk_to_person"]
    assert [s.id for s in msg.suggestions("greet", "es")] == ["report_unrecognized", "report_duplicate", "check_case"]


def test_ac_37_bedrock_streams_each_delta_and_reports_the_billed_usage():
    """The production path (ConverseStream) on a stubbed boto client: no network."""
    from nick_of_time.llm.bedrock import BedrockClient

    class Stub:
        def converse_stream(self, **request):
            self.request = request
            return {"stream": [{"messageStart": {"role": "assistant"}},
                               {"contentBlockDelta": {"delta": {"text": "[1] Hola"}}},
                               {"contentBlockDelta": {"delta": {"text": ", Ana.\n[chips] "}}},
                               {"messageStop": {"stopReason": "end_turn"}},
                               {"metadata": {"usage": {"inputTokens": 120, "outputTokens": 9}}}]}
    stub, pieces = Stub(), []
    client = BedrockClient(SONNET, boto_client=stub, prices=price(resolve("S2")))
    result = client.stream("system", "user", pieces.append, max_tokens=50)
    assert pieces == ["[1] Hola", ", Ana.\n[chips] "] and result.text == "".join(pieces)
    assert (result.tokens_in, result.tokens_out, result.stop_reason) == (120, 9, "end_turn") and result.cost_usd > 0
    assert stub.request["modelId"] == SONNET and "toolConfig" not in stub.request


# ---- the block gate (spec 01 AC-10, spec 04 AC-37/AC-40 follow-up: P0 found with real Sonnet 4.6 on demo turns) ----
URL = "https://www.gob.mx/condusef/prensa/cargos-no-reconocidos?idiom=es"
SOURCE = "Banxico, Circular 3/2012 (modificada por la Circular 14/2018)"
FACTS = [{"transaction_id": "TRX-0001", "amount": 1366.10, "currency": "USD", "merchant": "TIENDA X"},
         {"case_id": "K-845156", "verification_id": "V-273C5CAD141B", "read_at": "2026-06-01T15:04:11Z",
          "credit_deadline": "2026-06-03", "deadline_source": SOURCE, "deadline_source_url": URL,
          "verified_on": "2026-10-04"}]
SHOWN = ["V-273C5CAD141B", "2026-06-01T15:04:11Z", SOURCE, URL, "2026-10-04"]     # what the turn's cards show
TEMPLATE_ES = [
    "Voy a hacer lo siguiente:",
    "1. Abrir un caso con los datos de este cargo (TIENDA X, 1366.10 USD).",
    "2. Verificar que el caso quedó registrado.",
    "3. Mostrarte el plazo legal y su fuente.",
    "Caso K-845156 abierto y verificado (verificación V-273C5CAD141B, 2026-06-01 15:04 UTC).",
    f"Plazo legal del banco para pronunciarse sobre los fondos en disputa: 2026-06-03. Fuente: {SOURCE} ({URL}, "
    "verificada el 2026-10-04)."]
TEMPLATE_PT = [
    "Caso K-845156 aberto e verificado (verificação V-273C5CAD141B, 2026-06-01 15:04 UTC).",
    f"Prazo legal do banco para se pronunciar sobre os valores contestados: 2026-06-03. Fonte: {SOURCE} ({URL}, "
    "verificada em 2026-10-04)."]
# the raw Sonnet 4.6 output of the demo turn: the system prompt then asked for "any number, date or id in a line of
# its own", so the model split its sentences and the line gate dropped the amount, the case id and the date
RAW_ES = ("[1,2,3,4] Gerardo, esto es lo que hice por ti: abrí un caso con el cargo de\n**1366.10 USD**,\n"
          "te muestro la fecha límite legal, y verifiqué que todo quedó registrado.\n\n"
          "[5] El caso quedó abierto y verificado:\n- Caso: **K-845156**\n- Verificación: **V-273C5CAD141B**\n"
          "- Fecha: 2026-06-01 15:04 UTC\n\n"
          "[6] Por ley, el plazo del banco para pronunciarse sobre los fondos es el\n**2026-06-03**\n"
          "(fuente: Banxico, Circular 3/2012).\n"
          "[chips] check_case: Ver mi caso | talk_to_person: Hablar con una persona")
FIGURES = ["1366.10", "K-845156", "2026-06-03"]


def gate(template, shown=SHOWN):
    sent: list[str] = []
    return wording.Gate(template, FACTS, sent.append, shown=shown), sent


def feed(g, raw: str, size: int = 7) -> None:
    for i in range(0, len(raw), size):                       # token-sized deltas, as ConverseStream sends them
        g.feed(raw[i:i + size])


def test_spec01_ac_10_ac_37_a_block_split_across_lines_is_released_whole_and_keeps_every_fact():
    g, sent = gate(TEMPLATE_ES)
    feed(g, RAW_ES)
    out = g.finish()
    reply = "\n".join(out)
    assert all(figure in reply for figure in FIGURES)                       # no fact of the template lost
    assert ("Gerardo, esto es lo que hice por ti: abrí un caso con el cargo de 1366.10 USD, te muestro la fecha "
            "límite legal, y verifiqué que todo quedó registrado.") in out
    assert ("Por ley, el plazo del banco para pronunciarse sobre los fondos es el 2026-06-03 (fuente: Banxico, "
            "Circular 3/2012).") in out
    assert "**" not in reply and "**" not in "".join(sent)                  # markdown stripped
    # the list items that only repeat a card (verification id, UTC time) are left out; the case id stays
    assert "El caso quedó abierto y verificado:\n- Caso: K-845156" in out
    assert not re.search(r"V-273C5CAD141B|UTC|https?://", reply)
    assert g.dropped == 0 and g.chips == [("check_case", "Ver mi caso"), ("talk_to_person", "Hablar con una persona")]
    assert "".join(sent) == reply                                           # the stream is the final reply


def test_spec01_ac_10_digit_free_text_streams_before_its_block_completes_and_the_rest_waits_for_the_gate():
    g, sent = gate(TEMPLATE_ES)
    feed(g, "[1,2,3,4] Gerardo, esto es lo que hice por ti: abrí un caso con el cargo de")
    assert "".join(sent) == "Gerardo, esto es lo que hice por ti: abrí un caso con el cargo de"
    feed(g, "\n**1366.10 USD**,\nte muestro la fecha")
    assert "".join(sent) == "Gerardo, esto es lo que hice por ti: abrí un caso con el cargo de"   # held: a digit
    feed(g, " límite legal, y verifiqué que todo quedó registrado.\n\n[5] Tu")
    assert "1366.10 USD, te muestro la fecha límite legal" in "".join(sent)                    # gated, released
    assert "".join(sent).endswith("\nTu")                                                      # next block streams


def test_spec01_ac_10_ac_37_a_pt_block_that_drops_the_case_id_gives_its_template_line_back():
    g, _ = gate(TEMPLATE_PT)
    feed(g, "[1] Pronto, Ana. Seu caso foi aberto e confirmado no sistema.\n"
            "[2] Por lei, o banco tem até\n2026-06-03 para se pronunciar sobre os valores.\n[chips] x: y")
    out = g.finish()
    assert out == [TEMPLATE_PT[0], "Por lei, o banco tem até 2026-06-03 para se pronunciar sobre os valores."]
    assert g.dropped == 1 and "K-845156" in "\n".join(out)                  # G-OUT-01, the fact came back


def test_ac_37_an_ungrounded_figure_in_a_split_block_still_fails_and_its_template_lines_come_back():
    g, _ = gate(TEMPLATE_ES)
    feed(g, "[5] Tu caso\n**K-845157**\nquedó abierto.\n")
    out = g.finish()
    assert TEMPLATE_ES[4] in out and g.dropped == 1 and "K-845157" not in "\n".join(out)


def test_ac_37_cards_carry_verification_ids_times_and_links_so_the_text_need_not_repeat_them():
    good = ("[1] Listo, Gerardo. Tu caso K-845156 quedó abierto y confirmado en el sistema.\n"
            "[2] Una persona del banco lo revisa y decide; por ley, el banco tiene hasta el 2026-06-03 para "
            "pronunciarse sobre los fondos.\n")
    g, _ = gate(TEMPLATE_ES[4:])
    feed(g, good)
    reply = "\n".join(g.finish())
    assert g.dropped == 0 and len(g.out) == 2 and not re.search(r"V-\w+|UTC|https?://|2026-10-04", reply)
    # with no card showing them, the verification id is a fact the text must keep: the template line comes back
    g, _ = gate(TEMPLATE_ES[4:], shown=())
    feed(g, good)
    assert TEMPLATE_ES[4] in g.finish() and g.dropped >= 1


def test_ac_37_markdown_emphasis_is_stripped_from_streamed_digit_free_text():
    g, sent = gate(["Hola."])
    feed(g, "[1] Hola, **Gerardo**, estoy __aquí__.", size=3)
    assert g.finish() == ["Hola, Gerardo, estoy aquí."] and "".join(sent) == "Hola, Gerardo, estoy aquí."


def test_ac_37_the_prompt_asks_for_whole_blocks_no_markdown_and_carries_es_and_pt_examples():
    assert "line of its own" not in wording.SYSTEM and "never split across lines" in wording.SYSTEM
    assert "no markdown" in wording.SYSTEM and "never list verification ids, UTC times or links" in wording.SYSTEM
    assert "Tu caso K-000001" in wording.SYSTEM and "Seu caso K-000001" in wording.SYSTEM


def test_ac_37_d_086_the_prompt_sets_tu_in_every_spanish_country_and_voce_in_portuguese():
    """D-086 (lead, 2026-10-06): one register per language, whatever the customer's country."""
    prompt = wording.SYSTEM
    assert "with tú in every country, MX, CO and AR alike, never vos or usted" in prompt
    assert "Brazilian Portuguese with você" in prompt


def test_ac_37_on_the_graph_the_cards_spare_the_text_the_verification_ids_and_the_writer_sees_them_named():
    def concise(payload):
        out = []
        for item in payload["lines"]:
            n, text = item["n"], item["text"]
            if case := re.match(r"Caso (K-\d+) abierto", text):
                out.append(f"[{n}] Tu caso {case.group(1)} quedó abierto y confirmado.")
            elif deadline := re.search(r"en disputa: (\d{4}-\d{2}-\d{2})\.", text):
                out.append(f"[{n}] Por ley, el banco tiene hasta el\n**{deadline.group(1)}**\npara pronunciarse.")
            elif last4 := re.match(r"Tarjeta terminada en (\d{4}): bloqueada", text):
                out.append(f"[{n}] Tu tarjeta terminada en {last4.group(1)} quedó bloqueada y confirmada.")
            else:
                out.append(f"[{n}] {text}")
        return "\n".join(out)
    writer = Writer(concise)
    chunks, turn = run(chat(writer), EV_0001)
    assert json.loads(writer.calls[0]["user"])["cards"]                     # the writer is told what the cards show
    assert "G-OUT-01" not in turn.guardrails_triggered
    assert not re.search(r"V-\w+|UTC|https?://|\*\*", turn.reply)
    assert re.search(r"Tu caso K-\d+ quedó abierto", turn.reply) and "hasta el 2026-06-03 para" in turn.reply
    assert "".join(c.delta for c in texts(chunks)) == turn.reply


# ---- long dates (spec 01 AC-10, spec 04 AC-37): the long form of an ISO date is the same fact ----
def long_gate(template, language):
    sent: list[str] = []
    return wording.Gate(template, FACTS, sent.append, shown=SHOWN, language=language), sent


def test_spec01_ac_10_ac_37_a_long_es_date_keeps_the_iso_template_date_without_fallback():
    g, _ = long_gate(TEMPLATE_ES[-1:], "es")
    g.take("[1] Por ley, el banco tiene hasta el 3 de junio de 2026 para pronunciarse sobre los fondos.")
    out = g.finish()
    assert out == ["Por ley, el banco tiene hasta el 3 de junio de 2026 para pronunciarse sobre los fondos."]
    assert g.dropped == 0


def test_spec01_ac_10_ac_37_a_long_pt_date_keeps_the_iso_template_date_without_fallback():
    g, _ = long_gate(TEMPLATE_PT[-1:], "pt")
    g.take("[1] Por lei, o banco tem até 3 de junho de 2026 para se pronunciar sobre os valores.")
    assert g.finish() == ["Por lei, o banco tem até 3 de junho de 2026 para se pronunciar sobre os valores."]
    assert g.dropped == 0


@pytest.mark.parametrize("language, text", [
    ("es", "Por ley, el banco tiene hasta el 4 de junio de 2026 para pronunciarse."),    # wrong day
    ("es", "Por ley, el banco tiene hasta el 3 de junio para pronunciarse."),            # no year
    ("es", "Por ley, el banco tiene hasta el 3 de junho de 2026 para pronunciarse."),    # other language's month
    ("pt", "Por lei, o banco tem até 3 de junho de 2025 para se pronunciar.")])           # wrong year
def test_spec01_ac_10_ac_37_a_wrong_or_partial_long_date_falls_back_to_the_template(language, text):
    template = TEMPLATE_ES if language == "es" else TEMPLATE_PT
    g, _ = long_gate(template[-1:], language)
    g.take(f"[1] {text}")
    assert g.finish() == template[-1:] and g.dropped == 1


def test_spec04_ac_37_an_ungrounded_long_date_fails_the_grounding_check_and_a_grounded_one_passes():
    facts = [{"credit_deadline": "2026-06-03"}]
    assert wording.build.bad(wording.isoed("Hasta el 3 de junio de 2026.", "es"), facts) is False
    assert wording.build.bad(wording.isoed("Hasta el 9 de junio de 2026.", "es"), facts) is True
    assert wording.build.bad(wording.isoed("Hasta el 3 de junio de 2026.", "es"), [{"credit_deadline": "2026-07-03"}])
    assert wording.states("el 3 de junio de 2026", "2026-06-03", "es")
    assert not wording.states("el 3 de junho de 2026", "2026-06-03", "es")
