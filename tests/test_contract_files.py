"""Contract files agree with each other: policies.yaml, contracts/tools.py, handoff and eval schemas, eval examples."""
from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import jsonschema
import yaml

from contracts import tools

ROOT = Path(__file__).resolve().parents[1]
POLICIES = yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())
HANDOFF = json.loads((ROOT / "contracts/handoff.schema.json").read_text())
EVAL = json.loads((ROOT / "eval/eval_case.schema.json").read_text())

CUSTOMER_TOOLS = list(tools.CUSTOMER_TOOLS)     # tools.py v1.1: the 16 tools of spec 01 §6.3
ANALYST_TOOLS = ["list_cases", "get_case", "approve_credit", "approve_block", "unblock_card", "request_customer_info",
                 "mark_ambiguous", "close_case", "reopen_case", "supervised_mode"]
MODES = ["auto", "manual_check", "human_required"]


def literal(model, field: str) -> list:
    return list(get_args(model.model_fields[field].annotation))


def test_actors_use_the_agreed_tool_names():
    assert POLICIES["actors"]["customer"]["tools"] == CUSTOMER_TOOLS
    assert POLICIES["actors"]["analyst"]["tools"] == ANALYST_TOOLS
    assert set(POLICIES["identity"]["require_otp_for"]) <= set(CUSTOMER_TOOLS)


def test_zones_queue_and_events_match_everywhere():
    zones = list(POLICIES["zones"])
    assert zones == HANDOFF["properties"]["zone"]["enum"] == literal(tools.OpenCaseIn, "zone")
    assert EVAL["properties"]["expected"]["properties"]["zone"]["enum"] == zones + [None]
    for mode in POLICIES["approval"]["per_action"].values():
        assert list(mode) == zones and set(mode.values()) <= set(MODES)

    states = POLICIES["case_queue"]["states"]
    assert states == HANDOFF["properties"]["queue_status"]["enum"] == literal(tools.AnalystActionOut, "new_status")
    assert states == EVAL["properties"]["expected"]["properties"]["queue_status"]["enum"]
    assert set(POLICIES["case_queue"]["transitions"]) == set(states)

    events = list(POLICIES["notifications"]["events"])
    assert events == literal(tools.NotifyCustomerIn, "event")
    assert events == EVAL["properties"]["expected"]["properties"]["notifications"]["items"]["enum"]

    assert list(POLICIES["scoring"]["providers"]) == literal(tools.GetFraudScoreOut, "source")


def test_amount_gate_only_picks_the_approval_mode():
    gate = POLICIES["amount_gate"]
    assert list(gate["tiers"].values()) == MODES
    assert set(gate["by_country"]) == {"MX", "CO", "AR", "BR"}
    for country in gate["by_country"].values():
        assert 0 < country["low"] < country["high"]
    assert not {"regulatory_clock", "deadline", "days"} & set(gate)


def test_regulatory_clock_cites_a_source_per_country():
    clock = POLICIES["regulatory_clock"]
    rules = [clock["MX"]["debit"], clock["MX"]["credit"], clock["AR"], clock["CO"], clock["BR"]]
    assert all(rule.get("source") for rule in rules)
    assert clock["MX"]["debit"]["provisional_credit_business_days"] == 2
    assert POLICIES["approval"]["per_action"]["provisional_credit"] == dict.fromkeys(POLICIES["zones"], "human_required")


def test_guardrails_have_unique_ids_and_known_tests():
    ids = [g["id"] for g in POLICIES["guardrails"]]
    assert len(ids) == len(set(ids)) == 15
    eval_types = set(EVAL["properties"]["type"]["enum"]) | {"all", "inspection"}
    assert {g["test"] for g in POLICIES["guardrails"]} <= eval_types


def test_schemas_are_valid_and_examples_follow_the_eval_schema():
    jsonschema.Draft202012Validator.check_schema(HANDOFF)
    jsonschema.Draft202012Validator.check_schema(EVAL)
    validator = jsonschema.Draft202012Validator(EVAL)
    cases = [json.loads(line) for line in (ROOT / "eval/examples.jsonl").read_text().splitlines() if line.strip()]
    assert cases
    for case in cases:
        errors = [e.message for e in validator.iter_errors(case)]
        assert not errors, (case["id"], errors)
