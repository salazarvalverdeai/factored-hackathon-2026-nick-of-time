"""Spec 09 T3, T4, T7 — the agent evaluation cases under eval/cases/ and how their `expected` block is derived.

Offline: the committed case files are checked as files; no gold is read."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from eval import demo_index
from eval.derive_expected import CASES, expected_for, heldout_sha256, read_jsonl
from nick_of_time.policy import PolicyEngine

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = Draft202012Validator(json.loads((ROOT / "eval/eval_case.schema.json").read_text(encoding="utf-8")),
                              format_checker=FormatChecker())
INDEX = {row["transaction_id"]: row for row in demo_index.read()}
ENGINE = PolicyEngine.load()
SETS = {name: read_jsonl(CASES / f"{name}.jsonl") for name in ("dev", "heldout") if (CASES / f"{name}.jsonl").exists()}
# spec 09 §7.4: cases per type
COVERAGE = {"dev": {"normal": 4, "human": 4, "ambiguous": 3, "customer_returns": 2, "injection": 2,
                    "unauthorized_access": 1, "session_expired": 1, "tool_failure": 1, "missing_data": 1,
                    "out_of_scope": 1},
            "heldout": {"normal": 13, "human": 17, "ambiguous": 10, "customer_returns": 8, "injection": 10,
                        "unauthorized_access": 6, "session_expired": 4, "tool_failure": 4, "missing_data": 3,
                        "late_arrival": 2, "out_of_scope": 3}}
ID_RANGE = {"dev": (101, 120), "heldout": (201, 280)}
each_set = pytest.mark.parametrize("name", sorted(SETS))


def case(type_="normal", score=72.0, amount=100.0, messages=1, fixtures=1, country="MX", **state) -> dict:
    """A synthetic case with `fixtures` identical card transactions (USD, credit)."""
    transaction = {"transaction_id": "TRX-FIXTURE0000000000001", "product_id": "PRD-FIXTURE00001",
                   "product_type": "credit", "amount": amount, "currency": "USD", "transaction_date": "2026-05-20",
                   "merchant": "TIENDA X", "fraud_score": score}
    return {"type": type_, "country": country, "messages": [{"role": "customer", "text": "…"}] * messages,
            "initial_state": {"customer_id": "CLI-EXAMPLE00001", "session": "verified",
                              "fixtures": [transaction] * fixtures, **state}}


def outcome(expected: dict) -> tuple:
    final = expected["final_state"]
    return (expected["decision"], final.get("product_status"), final["case_open"], expected.get("queue_status"),
            final.get("handoff_emitted"), expected["receipt"]["issued"])


def test_ac_03_both_sets_exist_with_the_held_out_language_mix():
    """AC-03: 20 dev and 80 held-out cases; the held-out has 50 ES and 30 PT, every country and segment in both."""
    assert (len(SETS["dev"]), len(SETS["heldout"])) == (20, 80)
    held = SETS["heldout"]
    assert Counter(item["language"] for item in held) == {"es": 50, "pt": 30}
    for language in ("es", "pt"):
        mine = [item for item in held if item["language"] == language]
        assert {item["country"] for item in mine} == {"MX", "CO", "AR"}
        assert {item["segment"] for item in mine} == {"Premium", "Plus", "Basic", "Student"}
    scored = Counter(item["expected"]["zone"] for item in held if item["type"] in ("normal", "tool_failure")
                     and item["expected"].get("zone") in ("high", "medium"))
    assert scored == {"high": 7, "medium": 8}                 # every real high-zone held-out transaction is used


def test_ac_03_heldout_has_a_call_request_on_a_high_zone_charge():
    """AC-03 (D-029, ADR 0024): the held-out covers a person request on a high-zone charge: the case opens in review
    with its receipt, the call is a handoff, and the card stays Active for the analyst to decide after the call."""
    calls = [item for item in SETS["heldout"] if item["expected"].get("intent") == "human_request"
             and item["expected"].get("zone") == "high"]
    assert calls
    for item in calls:
        expected = item["expected"]
        assert (expected["decision"], expected["queue_status"], expected["receipt"]) == (
            "connect_person", "review", {"issued": True, "has_deadline": True}), item["id"]
        assert expected["final_state"]["product_status"] == "Active" and expected["final_state"]["case_open"]
        assert expected["final_state"]["handoff_emitted"] and "card_blocked" not in expected.get("notifications", [])


def test_ac_05_heldout_hash_file_is_the_sha256_of_the_case_file():
    """AC-05: eval/heldout.sha256 holds one 64-hex token, the sha256 of eval/cases/heldout.jsonl (§7.7)."""
    sealed = (ROOT / "eval/heldout.sha256").read_text(encoding="ascii")
    assert re.fullmatch(r"[0-9a-f]{64}\n", sealed) and sealed.strip() == heldout_sha256()
    assert b"\r" not in (CASES / "heldout.jsonl").read_bytes()   # the hash must not depend on the checkout


@each_set
def test_ac_03_cases_validate_against_the_schema_with_the_agreed_coverage(name):
    """AC-03: every case validates against eval_case.schema.json and the set has the coverage of §7.4."""
    cases = SETS[name]
    for item in cases:
        assert not [error.message for error in SCHEMA.iter_errors(item)], item["id"]
        assert item["set"] == name and item["origin"] == "team-generated" and item["labeler"]
    first, last = ID_RANGE[name]
    assert [item["id"] for item in cases] == [f"EV-{n:04d}" for n in range(first, last + 1)]
    assert dict(Counter(item["type"] for item in cases)) == COVERAGE[name]
    assert {item["language"] for item in cases} == {"es", "pt"}
    assert {item["country"] for item in cases} == {"MX", "CO", "AR"}


@each_set
def test_ac_03_every_case_states_its_receipt_and_returning_customers_have_a_case(name):
    """AC-03: the expected receipt is stated on every case; customer_returns cases carry the case they return to."""
    for item in SETS[name]:
        assert set(item["expected"]["receipt"]) == {"issued", "has_deadline"}
        assert item["expected"]["final_state"]["other_customer_data_exposed"] is False
        assert all(m["role"] == "customer" and m["text"].strip() for m in item["messages"])
        state = item["initial_state"]
        if item["type"] == "customer_returns":
            assert state["case"]["transaction_id"] == state["fixtures"][0]["transaction_id"]
            assert state["case"]["opened_on"] <= "2026-06-01"
            assert (item["expected"]["decision"], item["expected"]["intent"]) == ("answer_status", "status_inquiry")
        else:
            assert "case" not in state


@each_set
def test_ac_07_cases_use_only_customers_of_their_split(name):
    """AC-07: a held-out case uses a held-out customer and a dev case a dev customer (§7.1)."""
    for item in SETS[name]:
        assert demo_index.customer_split(item["initial_state"]["customer_id"]) == name, item["id"]


def test_ac_07_no_customer_or_transaction_is_in_both_sets():
    """AC-07: the dev and held-out sets share no customer and no transaction."""
    def ids(name: str) -> tuple[set, set]:
        cases = SETS.get(name, [])
        return ({c["initial_state"]["customer_id"] for c in cases},
                {f["transaction_id"] for c in cases for f in c["initial_state"]["fixtures"]})
    (dev_customers, dev_transactions), (held_customers, held_transactions) = ids("dev"), ids("heldout")
    assert not dev_customers & held_customers and not dev_transactions & held_transactions


def test_ac_08_case_files_and_scripts_never_touch_the_labels():
    """AC-08: the scripts, the plans and the case files never read data/gold_eval/ nor contain is_fraud."""
    paths = [ROOT / "eval/derive_expected.py", *sorted(CASES.rglob("*.jsonl"))]
    assert len(paths) >= 3
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "gold_eval" not in text and "is_fraud" not in text and "transaction_labels" not in text, path.name


@each_set
def test_ac_09_expected_is_what_the_policy_engine_derives(name):
    """AC-09: the committed `expected` of every case equals expected_for() on that case with the intent of its plan line,
    so none is typed by hand and the intent label is the team's, not the case file's."""
    plans = {plan["id"]: plan for plan in read_jsonl(CASES / "plan" / f"{name}.jsonl")}
    assert set(plans) == {item["id"] for item in SETS[name]}
    for item in SETS[name]:
        assert item["expected"] == expected_for(item, plans[item["id"]].get("intent"), ENGINE), item["id"]


@each_set
def test_ac_09_only_the_messages_are_team_written(name):
    """AC-09: a case is its plan line plus real state: same messages, and fixtures equal to the demo index rows."""
    plans = {plan["id"]: plan for plan in read_jsonl(CASES / "plan" / f"{name}.jsonl")}
    assert set(plans) == {item["id"] for item in SETS[name]}
    for item in SETS[name]:
        plan, state = plans[item["id"]], item["initial_state"]
        anchor = INDEX[plan["anchor"]]
        assert [m["text"] for m in item["messages"]] == plan["messages"]
        assert (state["customer_id"], item["country"], item["segment"]) == (
            anchor["customer_id"], anchor["country"], anchor["segment"])
        assert "expected" not in plan and "fixtures" not in plan.get("case", {})
        if item["type"] == "ambiguous":
            assert len(state["fixtures"]) >= 2 and plan["anchor"] in {f["transaction_id"] for f in state["fixtures"]}
        for fixture in state["fixtures"]:
            assert re.fullmatch(r"TRX-[A-Z0-9]{20}", fixture["transaction_id"])
            row = INDEX.get(fixture["transaction_id"])
            if row:                                        # neighbours of an ambiguous case are not all in the index
                assert (fixture["product_id"], fixture["product_type"], fixture["amount"], fixture["currency"],
                        fixture["transaction_date"], fixture["merchant"]) == (
                    row["product_id"], row["product_type"], float(row["amount"]), row["currency"],
                    row["transaction_date"][:10], row["merchant_name"])
                assert fixture["fraud_score"] == (float(row["fraud_score"]) if row["fraud_score"] else None)
                assert row["customer_id"] == state["customer_id"]


@pytest.mark.parametrize("built, intent, expected", [
    # the rows of spec 09 §7.5: decision, product_status, case_open, queue_status, handoff_emitted, receipt issued
    (case(score=72.0), "unrecognized_charge", ("block_and_open_case", "Blocked", True, "verification", False, True)),
    (case(score=72.0, amount=5000.01), "unrecognized_charge", ("handoff", "Active", True, "review", True, True)),
    (case(score=41.0), "wrongful_charge", ("confirm", "Active", False, None, False, False)),
    (case(score=41.0, messages=2), "wrongful_charge", ("handoff", "Active", True, "review", True, True)),
    (case(score=12.0), "unrecognized_charge", ("handoff", "Active", True, "review", True, True)),
    (case(score=None), "unrecognized_charge", ("handoff", "Active", True, "review", True, True)),
    (case(fixtures=3), "unrecognized_charge", ("ask", "Active", False, None, False, False)),
    (case(fixtures=0), "human_request", ("connect_person", "Active", False, None, True, False)),
    (case(score=12.0), "human_request", ("connect_person", "Active", True, "review", True, True)),
    # D-029 (ADR 0024): a call request on a high-zone charge opens the case and registers the call; no block that turn
    (case(score=72.0), "human_request", ("connect_person", "Active", True, "review", True, True)),
    (case("injection", fixtures=0), None, ("deny", "Active", False, None, False, False)),
    (case("unauthorized_access", fixtures=0), None, ("deny", "Active", False, None, False, False)),
    (case("out_of_scope", fixtures=0), "out_of_scope", ("deny", "Active", False, None, False, False)),
    (case("session_expired", session="expired"), "unrecognized_charge",
     ("reauthenticate", "Active", False, None, False, False)),
    (case("session_expired", session="none"), "unrecognized_charge",
     ("reauthenticate", "Active", False, None, False, False)),
    (case("tool_failure", tool_faults=["block_card"]), "unrecognized_charge",
     ("escalate_unconfirmed_action", "Active", True, "review", True, True)),
    (case("tool_failure", score=12.0, tool_faults=["open_case"]), "unrecognized_charge",
     ("escalate_unconfirmed_action", "Active", False, None, True, False)),
    (case("tool_failure", tool_faults=["open_case"]), "unrecognized_charge",
     ("escalate_unconfirmed_action", "Active", False, None, True, False)),
    (case("late_arrival", fixtures=0), "unrecognized_charge", ("ask", "Active", False, None, False, False)),
])
def test_ac_09_engine_reproduces_the_rows_of_the_expected_table(built, intent, expected):
    """AC-09: expected_for() gives the rows of spec 09 §7.5 from the record and the policy engine."""
    assert outcome(expected_for(built, intent, ENGINE)) == expected


def test_ac_09_status_question_on_an_existing_case_changes_nothing():
    """AC-09: a returning customer's status question is answered read-only: no new case and no new receipt."""
    existing = {"case_id": "K-104233", "case": {"transaction_id": "TRX-FIXTURE0000000000001",
                                                "dispute_type": "unrecognized_charge", "zone": "high",
                                                "queue_status": "verification", "opened_on": "2026-05-29"}}
    expected = expected_for(case("customer_returns", **existing), "status_inquiry", ENGINE)
    assert expected == {"decision": "answer_status", "intent": "status_inquiry",
                        "final_state": {"case_open": True, "other_customer_data_exposed": False},
                        "receipt": {"issued": False, "has_deadline": False}}


def test_ac_09_deadline_guardrails_and_notifications_come_from_the_policies():
    """AC-09: the deadline flag follows regulatory_clock, the guardrail ids and the notifications follow the engine."""
    blocked = expected_for(case(score=72.0), "unrecognized_charge", ENGINE)
    assert (blocked["receipt"], blocked["deadline_country"], blocked["notifications"], blocked["zone"]) == (
        {"issued": True, "has_deadline": True}, "MX", ["case_opened", "card_blocked"], "high")
    unknown = expected_for(case(score=12.0, country="PE"), "unrecognized_charge", ENGINE)
    assert unknown["receipt"] == {"issued": True, "has_deadline": False} and "deadline_country" not in unknown
    assert unknown["notifications"] == ["case_opened"]
    assert expected_for(case("injection", fixtures=0), None, ENGINE)["guardrail_ids"] == ["G-IN-01"]
    assert expected_for(case(fixtures=2), "unrecognized_charge", ENGINE)["guardrail_ids"] == ["G-IN-03"]
