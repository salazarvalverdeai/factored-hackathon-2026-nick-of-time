"""Spec 01 AC-04: the echo graph `dispute_intake` returns a valid TurnResult whose sample receipt validates against
contracts/customer_receipt.schema.json. No LLM, no tools, no network."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest

from nick_of_time import contracts as c

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/agent"))
from agent.graph import graph  # noqa: E402

RECEIPT = json.loads((ROOT / "contracts/customer_receipt.schema.json").read_text())
CONFIG = {"configurable": {"session_id": "S-demoreplay000001", "mode": "replay"}}


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        monkeypatch.delenv(name, raising=False)


# Customer-facing words the reply and the first chip must use in each language (written here, not read from the graph).
WORDS = {"es": ("Recibí tu mensaje", "Ver mi caso"), "pt": ("Recebi sua mensagem", "Ver meu caso")}


@pytest.mark.parametrize("language", ["es", "pt"])
def test_ac_04_echo_graph_returns_a_turn_result_with_the_sample_receipt(language):
    text = "No reconozco un cargo de 1,250 dólares"
    out = graph.invoke({"messages": [{"role": "user", "content": text}], "language": language, "action": None},
                       CONFIG)
    assert set(out) == set(c.TurnResult.model_fields)            # the output state is exactly TurnResult
    turn = c.TurnResult.model_validate(out)
    assert turn.language == language and text in turn.reply and turn.mode == "replay"
    assert turn.receipt == c.sample_receipt() and turn.case_id == turn.receipt.case_id
    jsonschema.Draft202012Validator(RECEIPT, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER).validate(
        out["receipt"])
    assert 2 <= len(turn.suggestions) <= 3
    assert turn.reply.startswith(WORDS[language][0]) and turn.suggestions[0].label == WORDS[language][1]
    assert "receipt" in turn.for_customer().model_dump()        # the projection the browser gets still validates


def test_ac_04_echo_graph_takes_a_chip_press_and_defaults_to_spanish_and_replay():
    session_only = {"configurable": {"session_id": CONFIG["configurable"]["session_id"]}}   # no mode, no language
    out = graph.invoke({"messages": [], "action": {"type": "send_summary"}}, session_only)
    turn = c.TurnResult.model_validate(out)
    assert turn.language == "es" and "send_summary" in turn.reply and turn.mode == "replay"


def test_ac_04_echo_graph_answers_the_last_message_and_never_shows_the_session():
    messages = [{"role": "user", "content": "primer mensaje"}, {"role": "user", "content": "segundo mensaje"}]
    turn = c.TurnResult.model_validate(graph.invoke({"messages": messages}, CONFIG))
    assert "segundo mensaje" in turn.reply and "primer mensaje" not in turn.reply
    assert CONFIG["configurable"]["session_id"] not in turn.for_customer().model_dump_json()


def test_ac_04_echo_graph_needs_the_session_the_api_injects_and_a_known_language():
    for settings in ({}, {"session_id": ""}):
        with pytest.raises(ValueError, match="session_id"):
            graph.invoke({"messages": [{"role": "user", "content": "hola"}]}, {"configurable": settings})
    with pytest.raises(ValueError, match="language"):
        graph.invoke({"messages": [{"role": "user", "content": "hello"}], "language": "en"}, CONFIG)


def test_ac_04_each_turn_has_its_own_trace_id():
    turns = [graph.invoke({"messages": [{"role": "user", "content": "hola"}]}, CONFIG) for _ in range(2)]
    assert turns[0]["trace_id"] and turns[0]["trace_id"] != turns[1]["trace_id"]


def test_ac_04_output_schema_is_typed_from_turn_result():
    schema = graph.get_output_jsonschema()
    assert set(schema["properties"]) == set(c.TurnResult.model_fields)
    assert schema["properties"]["language"]["enum"] == ["es", "pt"]


def test_ac_04_langgraph_json_serves_the_echo_graph():
    config = json.loads((ROOT / "langgraph.json").read_text())
    path, attr = config["graphs"]["dispute_intake"].split(":")
    spec = importlib.util.spec_from_file_location("dispute_intake_probe", ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert getattr(module, attr).name == graph.name == "dispute_intake"
    assert config["python_version"] == "3.13"                       # spec 01 §6.1 (Platform defaults to 3.11)
    assert config["dependencies"] == [".", "./packages"]               # "." carries the graph and contracts
    assert set(config) == {"dependencies", "graphs", "python_version"}    # no "env": secrets are deployment secrets
