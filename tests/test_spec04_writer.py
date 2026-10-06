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
from tests.test_spec04_graph import Chat

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
