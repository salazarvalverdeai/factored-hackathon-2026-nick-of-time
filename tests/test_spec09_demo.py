"""Spec 09 T2 — the demo files under eval/demo/: customers, live-mode profiles and processed sample cases."""
from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import yaml

from contracts.tools import AnalystActionIn
from eval import demo_index
from nick_of_time.policy import PolicyEngine

DEMO = Path(__file__).resolve().parents[1] / "eval/demo"
INDEX = {row["transaction_id"]: row for row in demo_index.read()}
CUSTOMERS = json.loads((DEMO / "customers.json").read_text(encoding="utf-8"))
REFERENCE = {row["customer_id"]: row for row in json.loads((DEMO / "reference.json").read_text(encoding="utf-8"))}
PROFILES = yaml.safe_load((DEMO / "live_profiles.yaml").read_text(encoding="utf-8"))
SAMPLES = [json.loads(line) for line in (DEMO / "sample_cases.jsonl").read_text(encoding="utf-8").splitlines()]
ENGINE = PolicyEngine.load()
REPLAY_TODAY = "2026-06-01"                                          # DEMO_TODAY (ADR 0020)


def test_ac_02_six_demo_customers_in_the_api_shape():
    """AC-02: six customers with the keys of GET /api/demo/customers (spec 01 §6.2), all from the dev split."""
    assert len(CUSTOMERS) == len({c["customer_id"] for c in CUSTOMERS}) == 6
    for customer in CUSTOMERS:
        assert sorted(customer) == ["country", "customer_id", "display_name", "language", "scenario", "segment"]
        assert demo_index.customer_split(customer["customer_id"]) == "dev"
        assert customer["language"] in ("es", "pt") and customer["country"] in ("MX", "CO", "AR")
        assert customer["segment"] in ("Premium", "Plus", "Basic", "Student")
        shown = (customer["display_name"] + customer["scenario"]).lower()
        assert not any(word in shown for word in ("score", "zone", "high", "medium", "human", "fraud"))


def test_ac_02_two_customers_per_mandatory_case_on_real_transactions():
    """AC-02: two customers per mandatory case, each backed by a row of the demo index; one PT, one MX debit."""
    assert set(REFERENCE) == {c["customer_id"] for c in CUSTOMERS}
    cases = [row["mandatory_case"] for row in REFERENCE.values()]
    assert {case: cases.count(case) for case in cases} == {"normal": 2, "ambiguous": 2, "human": 2}
    for customer in CUSTOMERS:
        ref = REFERENCE[customer["customer_id"]]
        row = INDEX[ref["transaction_id"]]
        assert (row["customer_id"], row["country"], row["segment"]) == (
            customer["customer_id"], customer["country"], customer["segment"])
        if ref["mandatory_case"] == "normal":
            assert row["zone"] in ("high", "medium") and row["amount_tier"] != "above_high"
        elif ref["mandatory_case"] == "ambiguous":
            assert int(row["n_candidates_7d"]) >= 2
        else:
            assert row["zone"] == "human" and row["n_candidates_7d"] == "1"
    assert any(c["language"] == "pt" for c in CUSTOMERS)
    assert any(INDEX[ref["transaction_id"]]["country"] == "MX" and INDEX[ref["transaction_id"]]["product_type"] == "debit"
               and ref["mandatory_case"] == "normal" for ref in REFERENCE.values())


def test_ac_11_live_profiles_cover_every_zone_and_stay_inside_the_policies():
    """AC-11: one synthetic profile per zone, scores inside the zone's band and amounts in the low tier."""
    assert PROFILES["label"] == "synthetic"
    zones = ENGINE.policies.zones
    assert set(PROFILES["profiles"]) == set(zones)
    for zone, profile in PROFILES["profiles"].items():
        assert zones[zone].score_min <= profile["score"]["min"] <= profile["score"]["max"] <= zones[zone].score_max
        assert 0 < profile["hours_before_now"]["min"] < profile["hours_before_now"]["max"]
        assert profile["null_score"] == ("allowed" if zone == "human" else "never")
    assert PROFILES["profiles"]["high"]["hours_before_now"]["max"] < 48          # MX debit: within 48 h of the notice
    assert set(PROFILES["amount"]) == {"MX", "CO", "AR"}
    for country, amount in PROFILES["amount"].items():
        assert 0 < amount["min"] < amount["max"]
        assert ENGINE.amount_tier(float(amount["max"]), amount["currency"], country) == "auto"
    assert set(PROFILES["customers"]) == {c["customer_id"] for c in CUSTOMERS}
    for customer_id, plan in PROFILES["customers"].items():
        assert plan["zones"] and set(plan["zones"]) <= set(zones)
        many = REFERENCE[customer_id]["mandatory_case"] == "ambiguous"
        assert (len(plan["zones"]) >= 2) == many


def test_ac_11_four_scripted_sample_cases_on_real_dev_transactions():
    """AC-11: four processed sample cases in replay mode, labeled scripted, one followed in the video."""
    assert [case["id"] for case in SAMPLES] == ["SC-01", "SC-02", "SC-03", "SC-04"]
    assert [case["followed_in_video"] for case in SAMPLES].count(True) == 1
    demo_customers = {c["customer_id"] for c in CUSTOMERS}
    for case in SAMPLES:
        row = INDEX[case["transaction_id"]]
        assert (case["label"], case["mode"]) == ("scripted", "replay")
        assert (row["customer_id"], row["country"], row["segment"], row["product_id"], row["zone"], row["split"]) == (
            case["customer_id"], case["country"], case["segment"], case["product_id"], case["zone"], "dev")
        assert case["customer_id"] not in demo_customers       # a judge's replay session never meets a seeded case
        assert case["language"] in ("es", "pt") and all(turn["text"].strip() for turn in case["turns"])
        assert row["transaction_date"][:10] <= case["opened_on"] <= REPLAY_TODAY
    assert {(c["country"], c["zone"]) for c in SAMPLES[:3]} == {("MX", "high"), ("CO", "human"), ("AR", "human")}
    injection = SAMPLES[3]
    assert injection["language"] == "pt"
    assert [turn["expected_decision"] for turn in injection["turns"]] == ["deny", "block_and_open_case"]


def test_ac_11_scripted_steps_follow_the_queue_and_the_analyst_contract():
    """AC-11: every scripted step is a contract action in date order, and the statuses walk case_queue.transitions."""
    analyst = set(get_args(AnalystActionIn.model_fields["action"].annotation))
    transitions = ENGINE.policies.case_queue.transitions   # typed CaseQueue since 02c (#86)
    moves = {"resolve": "resolved", "close_case": "closed", "reopen_case": "review", "request_reevaluation": "review"}
    opened = {"block_and_open_case": "verification", "handoff": "review"}
    for case in SAMPLES:
        status = opened[case["turns"][-1]["expected_decision"]]
        dates = [case["opened_on"], *(step["on"] for step in case["steps"])]
        assert dates == sorted(dates) and dates[-1] <= REPLAY_TODAY
        for step in case["steps"]:
            if step["actor"] == "analyst":
                assert step["action"] in analyst
                assert bool(step.get("reason")) == (step["action"] not in ("take", "approve_credit", "approve_block"))
            else:
                assert step["actor"] == "customer" and step["action"] in ("add_case_info", "request_reevaluation")
                assert step.get("text") or step.get("reason")
            target = moves.get(step["action"])
            if target:
                assert target in transitions[status], (case["id"], step["action"], status)
                status = target
        assert status == case["final_queue_status"]
    assert [c["final_queue_status"] for c in SAMPLES] == ["closed", "resolved", "review", "verification"]
    assert any(step["action"] == "request_reevaluation" for step in SAMPLES[2]["steps"])
    assert any(step["action"] == "request_customer_info" for step in SAMPLES[1]["steps"])
    assert any(step["action"] == "approve_credit" for step in SAMPLES[0]["steps"])
