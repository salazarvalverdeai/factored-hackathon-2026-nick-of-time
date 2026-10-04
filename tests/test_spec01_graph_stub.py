"""Spec 01 AC-04: the echo graph `dispute_intake` returns a valid TurnResult whose sample receipt validates against
contracts/customer_receipt.schema.json. No LLM, no tools, no network."""
from __future__ import annotations

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
    assert "receipt" in turn.for_customer().model_dump()        # the projection the browser gets still validates


def test_ac_04_echo_graph_takes_a_chip_press_and_defaults_to_spanish():
    out = graph.invoke({"messages": [], "action": {"type": "send_summary"}}, CONFIG)
    turn = c.TurnResult.model_validate(out)
    assert turn.language == "es" and "send_summary" in turn.reply


def test_ac_04_echo_graph_needs_the_session_the_api_injects():
    with pytest.raises(ValueError, match="session_id"):
        graph.invoke({"messages": [{"role": "user", "content": "hola"}]}, {"configurable": {}})
    assert graph.name == "dispute_intake"
