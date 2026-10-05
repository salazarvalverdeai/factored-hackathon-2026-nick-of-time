"""Spec 02 T5 — the decision table: zone × country × supervised mode × amount tier × product, with the score
boundaries 29/30/49/50 and null, against an oracle written from §4.1 and §4.2 (not from the engine's code)."""
from __future__ import annotations

import itertools

import pytest
import yaml

from nick_of_time.policy import DecisionInput, PolicyEngine
from nick_of_time.policy.model import POLICIES_PATH

ENGINE = PolicyEngine.load()
RAW = yaml.safe_load(POLICIES_PATH.read_text())
GUARD = {rule: body.get("guardrail") for rule, body in RAW["rules"].items()}
MODES = ["auto", "manual_check", "human_required"]
# score → zone (§4.1 rules 6–9): the boundaries 29/30/49/50, the ends 0/100, a fraction under each edge, and null
SCORES = {0.0: "human", 29.0: "human", 29.99: "human", 30.0: "medium", 49.0: "medium", 49.99: "medium",
          50.0: "high", 100.0: "high", None: "human"}
COUNTRIES = ["MX", "CO", "AR", "BR", "PE", "CL"]
# USD amounts on the tier edges; every gated country sets low ≈ 1,000 USD and high ≈ 5,000 USD (§4.2)
AMOUNTS = {1000.0: "auto", 1000.01: "manual_check", 5000.0: "manual_check", 5000.01: "human_required"}
CELLS = list(itertools.product(SCORES, COUNTRIES, [False, True], AMOUNTS, ["debit", "credit"], [None, True]))


def test_ac_06_the_table_premise_matches_the_gate_in_policies():
    """AC-06: the tier edges the table uses are the file's (1,000 and 5,000 USD); PE and CL have no gate."""
    for country, gate in RAW["amount_gate"]["by_country"].items():
        assert (gate["low"] / gate["usd_rate"], gate["high"] / gate["usd_rate"]) == (1000.0, 5000.0), country
    assert set(RAW["amount_gate"]["by_country"]) == {"MX", "CO", "AR", "BR"}


def oracle(score, country, supervised, amount, confirmed) -> dict:
    """§4.1 rules 6–9 and §4.2, written out: what a verified, confident, one-card dispute turn must decide."""
    zone = SCORES[score]
    gated = country in RAW["amount_gate"]["by_country"]
    tier, tier_rule = (AMOUNTS[amount], "POL-AMOUNT-GATE") if gated else ("human_required", "POL-AMOUNT-UNKNOWN")
    base = {"high": "manual_check", "medium": "human_required", "human": "human_required"}[zone]
    raisers = [rule for rule, mode in ((tier_rule, tier), ("POL-SUPERVISED", "human_required" if supervised else "auto"))
               if MODES.index(mode) > MODES.index(base)]
    rules = ["POL-SCORE-NULL" if score is None else f"POL-ZONE-{zone.upper()}", *raisers]
    want = dict(zone=zone, approval_modes={"open_case": "auto", "provisional_credit": "human_required",
                                           "unblock_card": "human_required",
                                           "block_card": "human_required" if raisers else base})
    if zone == "medium" and confirmed is None:
        return dict(want, decision="confirm", rule_ids=rules, allowed_actions=[], queue_status_after=None,
                    handoff_reason=None)
    rules.append("POL-TICKET-ALWAYS")
    if zone == "high" and not raisers:
        return dict(want, decision="block_and_open_case", rule_ids=rules, allowed_actions=["open_case", "block_card"],
                    queue_status_after="verification", handoff_reason=None)
    reason = {"medium": "zone_medium", "human": "zone_human"}.get(zone) or (
        "amount_over_case_gate" if tier == "human_required" else "supervised_mode")
    return dict(want, decision="handoff", rule_ids=rules, allowed_actions=["open_case"], queue_status_after="review",
                handoff_reason=reason)


def turn(score, country, supervised, amount, product, confirmed) -> DecisionInput:
    return DecisionInput(session_state="verified", intent="unrecognized_charge", intent_confidence=0.93, candidates=1,
                         dispute_detected=False, injection_flagged=False, cross_customer=False,
                         supervised_mode=supervised, score=score, score_source="dataset" if score is not None else None,
                         amount=amount, currency="USD", country=country, product_type=product,
                         customer_confirmed=confirmed)


@pytest.mark.parametrize("score,country,supervised,amount,product,confirmed", CELLS)
def test_ac_01_02_04_06_09_12_every_cell_of_the_decision_table(score, country, supervised, amount, product, confirmed):
    """AC-01 (bands and their edges), AC-02 (null → human, case still opened), AC-04 (supervised → human_required),
    AC-06 (the tier moves only the block mode), AC-09 (credit always human_required), AC-12 (rule ids, guardrails,
    version), AC-15 (open_case stays auto): the engine agrees with the oracle in every cell."""
    got = ENGINE.decide(turn(score, country, supervised, amount, product, confirmed))
    want = oracle(score, country, supervised, amount, confirmed)
    assert {key: getattr(got, key) for key in want} == want
    assert got.guardrail_ids == list(dict.fromkeys(GUARD[r] for r in want["rule_ids"] if GUARD[r]))
    assert got.policies_version == RAW["version"] and got.request_call is None


def test_ac_13_the_whole_table_is_deterministic():
    """AC-13: the same input gives the same output, cell by cell, on a second engine loaded from the same file."""
    other = PolicyEngine.load()
    for cell in CELLS[::7]:
        assert ENGINE.decide(turn(*cell)).model_dump() == other.decide(turn(*cell)).model_dump()
