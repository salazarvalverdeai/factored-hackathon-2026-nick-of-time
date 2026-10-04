"""Spec 01 — shared package skeleton, ids, the customer receipt and the eval schema hooks (AC-01, AC-04)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

import jsonschema
import pytest
import yaml
from pydantic import ValidationError

from contracts import tools
from nick_of_time import CONTRACT_VERSION, contracts as c, ids

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = json.loads((ROOT / "contracts/customer_receipt.schema.json").read_text())
EVAL = json.loads((ROOT / "eval/eval_case.schema.json").read_text())
NEVER_SEND = yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())["notifications"]["never_send"]


def test_ac_01_layout_package_and_removed_scaffold_folders():
    assert CONTRACT_VERSION == "1.1.0"
    assert (ROOT / "packages/nick_of_time/contracts.py").is_file() and (ROOT / "packages/nick_of_time/ids.py").is_file()
    assert not [d for d in ("audit", "classifier", "graph", "policy", "tools") if (ROOT / "apps/api" / d).exists()]


def test_ac_01_tool_models_are_re_exported_not_redeclared():
    assert "ToolError" in c.TOOL_MODELS
    for name in c.TOOL_MODELS:
        assert getattr(c, name) is getattr(tools, name), name


@pytest.mark.parametrize("kind", list(ids.PREFIX))
def test_ac_01_ids_have_the_contract_prefix_and_shape(kind):
    made = {ids.new_id(kind) for _ in range(200)}
    assert all(i.startswith(ids.PREFIX[kind]) and ids.is_valid(kind, i) for i in made)
    assert len(made) > 150                      # random, not a counter (case ids have 10^6 values)
    assert not ids.is_valid(kind, ids.PREFIX[kind] + "x")


def test_ac_01_receipt_schema_and_model_agree():
    jsonschema.Draft202012Validator.check_schema(RECEIPT)
    fields = c.CustomerReceipt.model_fields
    assert set(RECEIPT["properties"]) == set(fields)
    assert set(RECEIPT["required"]) == {n for n, f in fields.items() if f.is_required()}
    props = RECEIPT["properties"]
    assert props["receipt_id"]["pattern"] == ids.PATTERN["receipt"]
    assert props["case_id"]["pattern"] == ids.PATTERN["case"]
    action = props["actions"]["items"]["properties"]
    assert action["action_id"]["pattern"] == ids.PATTERN["action"]
    assert action["verification_id"]["pattern"] == ids.PATTERN["verification"]
    assert action["state"]["enum"] == list(get_args(c.ActionState))


def _keys(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    return {k for v in node for k in _keys(v)} if isinstance(node, list) else set()


def test_ac_01_receipt_never_carries_internals():
    assert set(NEVER_SEND) == {"transcript", "score", "policy_ids"}
    assert not {*NEVER_SEND, "policy_id"} & _keys(RECEIPT["properties"])
    leaked = {**RECEIPT["examples"][0], "score": 72}
    assert list(jsonschema.Draft202012Validator(RECEIPT).iter_errors(leaked))
    with pytest.raises(ValidationError):
        c.CustomerReceipt.model_validate(leaked)
    text = json.dumps(RECEIPT["examples"][0], ensure_ascii=False)
    assert not re.search(r"POL-|G-[A-Z]+-\d|score|puntaje", text)


def test_ac_04_sample_receipt_validates_against_the_schema():
    validator = jsonschema.Draft202012Validator(RECEIPT)
    sample = c.sample_receipt()
    assert sample.language == "es" and sample.deadline and sample.deadline.credit_deadline
    assert all(a.state == "verified" and a.verification_id for a in sample.actions)
    assert not list(validator.iter_errors(sample.model_dump(mode="json")))
    variant = sample.model_dump(mode="json")
    variant["amount"]["display"] = {"amount": "22500", "currency": "MXN", "rate": "18.0", "rate_source": "fixture",
                                    "as_of": "2026-06-03"}
    variant["actions"].append({"label": "Bloqueo sin confirmar", "action_id": ids.new_id("action"),
                               "state": "not_confirmed", "verification_id": None, "verified_at": None})
    variant["deadline"] = None
    assert not list(validator.iter_errors(variant))
    assert c.CustomerReceipt.model_validate(variant).model_dump(mode="json") == variant


def test_ac_01_eval_schema_has_the_receipt_hooks_and_turn_vocabulary():
    expected = EVAL["properties"]["expected"]["properties"]
    assert expected["decision"]["enum"] == list(get_args(c.Decision))
    assert expected["intent"]["enum"] == list(get_args(c.Intent))
    assert expected["receipt"]["required"] == ["issued", "has_deadline"]
    assert "customer_returns" in EVAL["properties"]["type"]["enum"]
    assert EVAL["properties"]["initial_state"]["properties"]["case_id"]["pattern"] == ids.PATTERN["case"]
    cases = [json.loads(line) for line in (ROOT / "eval/examples.jsonl").read_text().splitlines() if line.strip()]
    assert all("receipt" in case["expected"] for case in cases)
    assert any(case["type"] == "customer_returns" and case["initial_state"].get("case_id") for case in cases)
