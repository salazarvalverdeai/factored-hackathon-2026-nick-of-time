"""Spec 01 — shared package skeleton, ids, the customer receipt and the eval schema hooks (AC-01, AC-04)."""
from __future__ import annotations

import ast
import copy
import datetime as dt
import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from typing import get_args

import jsonschema
import pytest
import yaml
from pydantic import ValidationError

import contracts as contracts_pkg
from contracts import tools
from nick_of_time import CONTRACT_VERSION, contracts as c, ids

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = json.loads((ROOT / "contracts/customer_receipt.schema.json").read_text())
EVAL = json.loads((ROOT / "eval/eval_case.schema.json").read_text())
POLICIES = yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())
FORMATS = jsonschema.Draft202012Validator.FORMAT_CHECKER
VALIDATOR = jsonschema.Draft202012Validator(RECEIPT, format_checker=FORMATS)
SAMPLE = RECEIPT["examples"][0]
CASES = [json.loads(line) for line in (ROOT / "eval/examples.jsonl").read_text().splitlines() if line.strip()]
DROP = object()


def test_ac_01_layout_package_and_removed_scaffold_folders():
    assert CONTRACT_VERSION == "1.1.0"
    assert (ROOT / "packages/nick_of_time/contracts.py").is_file() and (ROOT / "packages/nick_of_time/ids.py").is_file()
    assert not [d for d in ("audit", "classifier", "graph", "policy", "tools") if (ROOT / "apps/api" / d).exists()]


def test_ac_01_tool_names_are_re_exported_not_redeclared():
    assert {"ToolError", "ScoreProvider"} <= set(c.TOOL_NAMES)
    for name in c.TOOL_NAMES:
        assert getattr(c, name) is getattr(tools, name), name


def test_ac_01_guard_rejects_a_name_declared_in_tools_and_here(tmp_path, monkeypatch):
    fake = tmp_path / "tools.py"
    fake.write_text("from typing import Literal\nZone = Literal['high']\ntype Mode = Literal['live']\n"
                    "class Money: ...\n")
    module = types.ModuleType("contracts.tools")
    module.__file__ = str(fake)
    exec(fake.read_text(), module.__dict__)
    monkeypatch.setitem(sys.modules, "contracts.tools", module)
    monkeypatch.setattr(contracts_pkg, "tools", module)
    spec = importlib.util.spec_from_file_location("nick_of_time._contracts_probe", c.__file__)
    with pytest.raises(ImportError, match=r"\['Mode', 'Money', 'Zone'\]"):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))   # a fresh copy; the real module is untouched


def test_ac_01_guard_scan_runs_without_ast_type_alias(monkeypatch):
    """Python 3.11 (Platform's default runtime) has no ast.TypeAlias; the scan must not need it."""
    monkeypatch.delattr(ast, "TypeAlias")
    assert c._defined_names(Path(tools.__file__)) == set(c.TOOL_NAMES)


@pytest.mark.parametrize("kind", list(ids.PREFIX))
def test_ac_01_ids_have_the_contract_prefix_and_shape(kind):
    made = {ids.new_id(kind) for _ in range(200)}
    assert all(i.startswith(ids.PREFIX[kind]) and ids.is_valid(kind, i) for i in made)
    assert len(made) > 150                      # random, not a counter (case ids have 10^6 values)
    assert not ids.is_valid(kind, ids.PREFIX[kind] + "x")


def test_ac_01_vocabularies_match_policies_and_the_eval_schema():
    assert list(get_args(c.Zone)) == list(POLICIES["zones"])
    assert list(get_args(c.QueueStatus)) == POLICIES["case_queue"]["states"]
    seeded_case = EVAL["properties"]["initial_state"]["properties"]["case"]["properties"]
    assert seeded_case["zone"]["enum"] == list(get_args(c.Zone))
    assert seeded_case["queue_status"]["enum"] == list(get_args(c.QueueStatus))
    expected = EVAL["properties"]["expected"]["properties"]
    assert expected["decision"]["enum"] == list(get_args(c.Decision))
    assert expected["intent"]["enum"] == list(get_args(c.Intent))
    assert expected["receipt"]["required"] == ["issued", "has_deadline"]
    assert "customer_returns" in EVAL["properties"]["type"]["enum"]
    assert EVAL["properties"]["initial_state"]["properties"]["case_id"]["pattern"] == ids.PATTERN["case"]
    assert all("receipt" in case["expected"] for case in CASES)
    assert any(case["type"] == "customer_returns" and case["initial_state"].get("case") for case in CASES)


def test_ac_01_eval_case_id_and_its_fixture_come_together():
    validator = jsonschema.Draft202012Validator(EVAL, format_checker=FORMATS)
    returning = next(case for case in CASES if case["type"] == "customer_returns")
    assert not list(validator.iter_errors(returning))
    for key in ("case", "case_id"):
        broken = copy.deepcopy(returning)
        del broken["initial_state"][key]
        assert list(validator.iter_errors(broken)), key


def _resolve(node: dict, root: dict) -> dict:
    """Follow a local $ref and unwrap Optional (anyOf with null); object-level anyOf rules stay as they are."""
    if "$ref" in node:
        node = root["$defs"][node["$ref"].rsplit("/", 1)[-1]]
    branches = [b for b in node.get("anyOf", []) if b.get("type") != "null"]
    return _resolve(branches[0], root) if "properties" not in node and len(branches) == 1 else node


def _shape(node: dict, root: dict, path: str = "$") -> dict[str, object]:
    """`required` of every object and enum, pattern and format of every leaf, keyed by path."""
    node = _resolve(node, root)
    if "properties" in node:
        out: dict[str, object] = {path: sorted(node.get("required", []))}
        for name, sub in node["properties"].items():
            out |= _shape(sub, root, f"{path}.{name}")
        return out
    if "items" in node:
        return _shape(node["items"], root, path + "[]")
    enum = node.get("enum", [node["const"]] if "const" in node else [])
    return {path: (sorted(e for e in enum if e is not None), node.get("pattern"), node.get("format"))}


def test_ac_01_receipt_schema_and_model_agree_at_every_level():
    jsonschema.Draft202012Validator.check_schema(RECEIPT)
    assert "date-time" in FORMATS.checkers and "date" in FORMATS.checkers   # rfc3339-validator is installed
    model = c.CustomerReceipt.model_json_schema()
    assert _shape(RECEIPT, RECEIPT) == _shape(model, model)       # the model takes its patterns from nick_of_time.ids


def _variant(path: str, value) -> dict:
    """The sample receipt with `path` (dot-separated, list indexes allowed) set to `value`, or removed with DROP."""
    data = copy.deepcopy(SAMPLE)
    *parents, last = [int(k) if k.isdigit() else k for k in path.split(".")]
    node = data
    for key in parents:
        node = node[key]
    if value is DROP:
        del node[last]
    else:
        node[last] = value
    return data


DISPLAY = {"amount": "22500", "currency": "MXN", "rate": "18.0", "rate_source": "fixture", "as_of": "2026-06-01"}
NEGATIVE = {
    "deadline without source_url": _variant("deadline.source_url", DROP),
    "deadline without verified_on": _variant("deadline.verified_on", DROP),
    "deadline with both dates null": _variant("deadline.credit_deadline", None),
    "credit_deadline is not a date": _variant("deadline.credit_deadline", "pronto"),
    "lower-case country": _variant("deadline.country", "mx"),
    "unknown product": _variant("deadline.product", "prepaid"),
    "verified_on is not a date": _variant("deadline.verified_on", "soon"),
    "empty source_url": _variant("deadline.source_url", ""),
    "plain http source_url": _variant("deadline.source_url", "http://example.org"),
    "extra key in deadline": _variant("deadline.score", 72),
    "missing deadline key": _variant("deadline", DROP),
    "fact without source_id": _variant("verified_facts.0.source_id", DROP),
    "empty source_id": _variant("verified_facts.0.source_id", ""),
    "customer id as a source": _variant("verified_facts.0.source_id", "CLI-EXAMPLE00001"),
    "short case id as a source": _variant("verified_facts.2.source_id", "K-1"),
    "non-hex verification id as a source": _variant("verified_facts.1.source_id", "V-x"),
    "empty fact": _variant("verified_facts.0.fact", ""),
    "verified action without verification_id": _variant("actions.0.verification_id", None),
    "verified action without the verification_id key": _variant("actions.0.verification_id", DROP),
    "bad verification id": _variant("actions.0.verification_id", "V-1"),
    "verified_at is not a date-time": _variant("actions.0.verified_at", "yesterday"),
    "issued_at is not a date-time": _variant("issued_at", "soon"),
    "naive issued_at": _variant("issued_at", "2026-06-01T15:04:12"),
    "verified action without verified_at": _variant("actions.0.verified_at", DROP),
    "unknown action state": _variant("actions.0.state", "done"),
    "bad action id": _variant("actions.0.action_id", "A-1"),
    "bad receipt id": _variant("receipt_id", "RC-1"),
    "bad case id": _variant("case_id", "K-12"),
    "language en": _variant("language", "en"),
    "product_last4 with 5 digits": _variant("product_last4", "44170"),
    "case_url that is not https": _variant("case_url", "javascript:alert(1)"),
    "extra score key": _variant("score", 72),
    "next_steps null": _variant("next_steps", None),
    "original amount not a decimal": _variant("amount.original.amount", "1,250.00"),
    "lower-case currency": _variant("amount.original.currency", "usd"),
    "display without rate_source": _variant("amount.display", {k: v for k, v in DISPLAY.items() if k != "rate_source"}),
}
NEGATIVE["deadline with both dates null"]["deadline"]["ruling_deadline"] = None

POSITIVE = {
    "sample": copy.deepcopy(SAMPLE),
    "no verified clock entry": _variant("deadline", None),
    "ruling deadline only": {**SAMPLE, "deadline": {**SAMPLE["deadline"], "credit_deadline": None,
                                                    "ruling_deadline": "2026-07-16"}},
    "optional fields absent": {k: v for k, v in SAMPLE.items() if k in RECEIPT["required"]},
    "optional fields null": {**SAMPLE, "mode": None, "product_last4": None, "amount": None, "case_url": None},
    "display amount absent": _variant("amount.display", DROP),
    "display amount with a rate": _variant("amount.display", DISPLAY),
    "unconfirmed action": _variant("actions.0", {"label": "Bloqueo sin confirmar", "action_id": "A-3E9F20B7C164",
                                                 "state": "not_confirmed", "verification_id": None,
                                                 "verified_at": None}),
    "action in progress": _variant("actions.0", {"label": "Bloqueando", "action_id": "A-3E9F20B7C164",
                                                 "state": "in_progress"}),
}


@pytest.mark.parametrize("data", NEGATIVE.values(), ids=NEGATIVE.keys())
def test_ac_01_schema_and_model_reject_the_same_bad_receipts(data):
    assert list(VALIDATOR.iter_errors(data))
    with pytest.raises(ValidationError):
        c.CustomerReceipt.model_validate(data)


@pytest.mark.parametrize("data", POSITIVE.values(), ids=POSITIVE.keys())
def test_ac_01_schema_and_model_accept_the_same_good_receipts(data):
    assert not list(VALIDATOR.iter_errors(data))
    dumped = c.CustomerReceipt.model_validate(data).model_dump(mode="json")
    assert not list(VALIDATOR.iter_errors(dumped))


def _keys(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    return {k for v in node for k in _keys(v)} if isinstance(node, list) else set()


def test_ac_01_receipt_never_carries_internals():
    never_send = POLICIES["notifications"]["never_send"]
    assert set(never_send) == {"transcript", "score", "policy_ids"}
    assert not {*never_send, "policy_id"} & _keys(RECEIPT["properties"])
    assert not re.search(r"POL-|G-[A-Z]+-\d|score|puntaje", json.dumps(SAMPLE, ensure_ascii=False))


def test_ac_04_sample_receipt_validates_against_the_schema():
    sample = c.sample_receipt()
    assert not list(VALIDATOR.iter_errors(sample.model_dump(mode="json")))
    assert sample.language == "es" and sample.mode == "replay"
    assert sample.issued_at.date() == dt.date(2026, 6, 1)                       # DEMO_TODAY (ADR 0020)
    assert sample.deadline and sample.deadline.credit_deadline == dt.date(2026, 6, 3)   # business day 2 (spec 02 §4.3)
    assert sample.amount and sample.amount.original.currency == "USD" and sample.amount.display is None
    assert all(a.state == "verified" and a.verification_id and a.verified_at for a in sample.actions)
    facts = {f.source_id.split("-")[0]: f for f in sample.verified_facts}
    assert facts["V"].source_id == sample.actions[0].verification_id and facts["K"].source_id == sample.case_id
    charged = dt.date.fromisoformat(re.search(r"\d{4}-\d{2}-\d{2}", facts["TRX"].fact).group())
    since_charge = sample.issued_at - dt.datetime.combine(charged, dt.time(), dt.UTC)
    assert dt.timedelta(0) < since_charge <= dt.timedelta(hours=48)          # the 48 h notice window (spec 02 §4.3)
