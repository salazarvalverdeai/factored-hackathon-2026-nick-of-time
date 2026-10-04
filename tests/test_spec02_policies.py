"""Spec 02 T1 — the policies.yaml model and loader: version 2, rule ids and the firm rules checked at startup."""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nick_of_time.policy import Policies, load_policies
from nick_of_time.policy.model import POLICIES_PATH

ROOT = Path(__file__).resolve().parents[1]
RAW = yaml.safe_load(POLICIES_PATH.read_text())


def edited(path: str, value) -> dict:
    raw = copy.deepcopy(RAW)
    *parents, key = path.split(".")
    node = raw
    for name in parents:
        node = node[name]
    node[key] = value
    return raw


def test_ac_12_version_2_declares_every_rule_id_the_spec_cites():
    assert load_policies().version == RAW["version"] == 2
    spec_ids = set(re.findall(r"POL-[A-Z]+(?:-[A-Z]+)*", (ROOT / "specs/02-policy-engine.md").read_text()))
    assert spec_ids == set(RAW["rules"])               # no undocumented id, no id the file lacks
    guardrails = {g["id"] for g in RAW["guardrails"]}
    assert all(r["text"] and r.get("guardrail", "G-POL-01") in guardrails for r in RAW["rules"].values())


def test_ac_15_money_actions_are_the_three_the_spec_names_and_load_is_cached():
    """AC-15 and FR-01: supervised mode and tiers touch only money actions; the file is validated once per path."""
    assert RAW["approval"]["money_actions"] == ["block_card", "unblock_card", "provisional_credit"]
    assert RAW["approval"]["supervised_mode"] is False
    assert load_policies(POLICIES_PATH) is load_policies(POLICIES_PATH)


INVALID = [
    ("AC-05 default allow", "default", "allow"),
    ("AC-09 credit auto", "approval.per_action.provisional_credit.high", "auto"),
    ("AC-15 ticket not auto", "approval.per_action.open_case.medium", "manual_check"),
    ("AC-15 block not money", "approval.money_actions", ["unblock_card", "provisional_credit"]),
    ("AC-15 ticket as money", "approval.money_actions", ["open_case", "block_card", "unblock_card", "provisional_credit"]),
    ("AC-04 zone without mode", "approval.per_action.block_card", {"high": "manual_check", "medium": "human_required"}),
    ("AC-04 unknown mode", "approval.per_action.block_card.high", "maybe"),
    ("AC-01 gap between bands", "zones.medium.score_min", 31),
    ("AC-01 null outside human", "zones.human.include_null", False),
    ("AC-06 clock key in the gate", "amount_gate.deadline_days", 10),
    ("AC-06 tiers loosen", "amount_gate.tiers.above_high", "auto"),
    ("AC-06 low above high", "amount_gate.by_country.CO.low", 30_000_000),
    ("AC-06 no usd rate", "amount_gate.by_country.MX.usd_rate", 0),
    ("AC-12 unknown guardrail", "rules.POL-SESSION.guardrail", "G-XX-99"),
    ("AC-12 id without POL-", "rules.SESSION", {"text": "session"}),
    ("AC-12 unknown section", "extra_section", {}),
    ("AC-10 close not human_only", "approval.close", "auto"),
]


@pytest.mark.parametrize("ac, path, value", INVALID, ids=[case[0] for case in INVALID])
def test_ac_12_an_invalid_policies_file_fails_at_startup(ac, path, value):
    """FR-01 with AC-01, 04, 05, 06, 09, 10, 12 and 15: a broken file never reaches a decision."""
    with pytest.raises(ValidationError):
        Policies.model_validate(edited(path, value))
