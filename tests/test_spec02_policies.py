"""Spec 02 T1 — the policies.yaml model and loader: version 2, rule ids and the firm rules checked at startup."""
from __future__ import annotations

import copy
import json
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


def ids_in(path: Path) -> set[str]:
    return set(re.findall(r"POL-[A-Z]+(?:-[A-Z]+)*", path.read_text()))


def test_ac_12_version_2_declares_every_rule_id_the_spec_cites():
    assert load_policies().version == RAW["version"] == 2
    assert ids_in(ROOT / "specs/02-policy-engine.md") <= set(RAW["rules"])
    cited = set().union(*(ids_in(spec) for spec in (ROOT / "specs").glob("*.md")))
    assert set(RAW["rules"]) <= cited                  # every id in the file is documented by some spec
    guardrails = {g["id"] for g in RAW["guardrails"]}
    assert all(r["text"] and r.get("guardrail", "G-POL-01") in guardrails for r in RAW["rules"].values())


def test_ac_15_money_actions_are_the_three_the_spec_names_and_load_is_cached():
    """AC-15 and FR-01: supervised mode and tiers touch only money actions; the file is validated once per path."""
    assert RAW["approval"]["money_actions"] == ["block_card", "unblock_card", "provisional_credit"]
    assert RAW["approval"]["supervised_mode"] is False
    assert load_policies(POLICIES_PATH) is load_policies(POLICIES_PATH)


def test_ac_02_the_deciding_sources_are_pinned_and_never_llm():
    """AC-02: only these sources place a score in a zone (D-027: synthetic decides in live mode, labeled [simulated])."""
    scoring = load_policies().scoring
    assert scoring.deciding_sources == ("dataset", "rules", "model", "synthetic")
    assert set(scoring.deciding_sources) | {"llm"} == set(scoring.providers)


def test_ac_12_the_frozen_policies_still_serialize_as_the_file():
    """§5 observability: model_dump_json works on the frozen model and, without defaults, gives back the YAML."""
    policies = load_policies()
    assert json.loads(policies.model_dump_json(exclude_unset=True)) == json.loads(json.dumps(RAW, default=str))
    assert Policies.model_validate_json(policies.model_dump_json()) == policies
    assert isinstance(policies.model_dump()["approval"]["per_action"], dict)


def test_ac_12_handoff_reasons_match_the_handoff_schema():
    schema = json.loads((ROOT / "contracts/handoff.schema.json").read_text())
    assert RAW["handoff"]["triggers"] == schema["properties"]["handoff_reason"]["enum"]


def test_ac_05_the_loaded_policies_are_frozen_all_the_way_down():
    """AC-05 and §5 security: no caller can loosen a rule at runtime, at any depth."""
    policies = load_policies()
    with pytest.raises(TypeError):
        policies.approval.per_action["block_card"]["high"] = "auto"
    with pytest.raises(TypeError):
        policies.rules["POL-NEW"] = policies.rules["POL-SESSION"]
    with pytest.raises(AttributeError):
        policies.approval.money_actions.remove("block_card")
    with pytest.raises(ValidationError):
        policies.approval.supervised_mode = False


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
    ("AC-01 high band stops at 99", "zones.high.score_max", 99),
    ("AC-02 llm score decides", "scoring.deciding_sources", ["dataset", "llm"]),
    ("AC-02 no deciding source", "scoring.deciding_sources", []),
    ("AC-02 deciding source without provider", "scoring.deciding_sources", ["dataset", "customer"]),
    ("AC-12 provider without entry", "scoring.provider", "magic"),
    ("AC-06 clock key in the gate", "amount_gate.deadline_days", 10),
    ("AC-06 tiers loosen", "amount_gate.tiers.above_high", "auto"),
    ("AC-06 low above high", "amount_gate.by_country.CO.low", 30_000_000),
    ("AC-06 low equals high", "amount_gate.by_country.CO.low", 20_000_000),
    ("AC-06 no usd rate", "amount_gate.by_country.MX.usd_rate", 0),
    ("AC-12 unknown guardrail", "rules.POL-SESSION.guardrail", "G-XX-99"),
    ("AC-12 id without POL-", "rules.SESSION", {"text": "session"}),
    ("AC-12 unknown section", "extra_section", {}),
    ("AC-10 close not human_only", "approval.close", "auto"),
]


@pytest.mark.parametrize("ac, path, value", INVALID, ids=[case[0] for case in INVALID])
def test_ac_12_an_invalid_policies_file_fails_at_startup(ac, path, value):
    """FR-01 with AC-01, 02, 04, 05, 06, 09, 10, 12 and 15: a broken file never reaches a decision."""
    with pytest.raises(ValidationError):
        Policies.model_validate(edited(path, value))
