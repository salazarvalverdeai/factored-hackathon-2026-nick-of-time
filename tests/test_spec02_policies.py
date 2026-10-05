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


def test_ac_02_the_handoff_card_can_carry_the_score_source_and_version():
    """D-033: record_source_in_audit sends the source and version to the card, so a synthetic score is labeled."""
    schema = json.loads((ROOT / "contracts/handoff.schema.json").read_text())
    assert schema["properties"]["score_source"]["enum"] == list(RAW["scoring"]["providers"])
    assert schema["properties"]["score_version"]["type"] == "string"
    assert not {"score_source", "score_version"} & set(schema["required"])


@pytest.mark.parametrize("contact, loads", [(None, True), ({"callback_within_business_days": 1}, True),
                                            ({"callback_within_business_days": None}, True),
                                            ({"callback_within_business_days": 0}, False),
                                            ({"callback_within_business_days": "1"}, False),
                                            ({"callback_hours": 4}, False)])
def test_ac_12_the_contact_section_of_pr_50_loads(contact, loads):
    """FR-01: #50 adds a top-level contact section (D-008); the strict model types it, so merge order does not matter."""
    raw = RAW if contact is None else {**RAW, "contact": contact}
    if not loads:
        with pytest.raises(ValidationError):
            Policies.model_validate(raw)
        return
    policies = Policies.model_validate(raw)
    got = policies.contact.callback_within_business_days if policies.contact else None
    assert got == (contact or {}).get("callback_within_business_days")


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
    ("AC-01 human band starts above 0", "zones.human.score_min", 1),
    ("AC-01 gap between medium and high", "zones.high.score_min", 51),
    ("AC-02 null score outside human", "scoring.null_score_zone", "medium"),
    ("AC-02 source not audited", "scoring.record_source_in_audit", False),
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
    ("AC-04 manual_check leaves the case in review", "approval.manual_check_leaves_case_in", "review"),
    ("AC-05 block in the human zone", "approval.per_action.block_card.human", "auto"),
    ("AC-05 block in the medium zone without a person", "approval.per_action.block_card.medium", "manual_check"),
    ("AC-05 high zone never blocks", "approval.per_action.block_card.high", "human_required"),
    ("AC-05 unblock without a person", "approval.per_action.unblock_card.high", "auto"),
    ("AC-08 tau of zero", "clarify.intent_confidence_min", 0),
    ("AC-08 tau above one", "clarify.intent_confidence_min", 1.2),
    ("AC-12 raw transcript in the handoff", "handoff.never_include_raw_transcript", False),
    ("AC-12 version zero", "version", 0),
]


@pytest.mark.parametrize("ac, path, value", INVALID, ids=[case[0] for case in INVALID])
def test_ac_12_an_invalid_policies_file_fails_at_startup(ac, path, value):
    """FR-01 with AC-01, 02, 04, 05, 06, 09, 10, 12 and 15: a broken file never reaches a decision."""
    with pytest.raises(ValidationError):
        Policies.model_validate(edited(path, value))
