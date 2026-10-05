"""Spec 01 contract 1.4.0: the follow-ups the lead confirmed on 2026-10-05 (D-052, the idempotency key of the store,
`ListMyCardsOut.read_at`) and the D-033 fields it records as already on main. Offline: no network, no gold."""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from contracts import tools
from nick_of_time import CONTRACT_VERSION

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server import fake  # noqa: E402

POLICIES = yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())
SPEC_01 = (ROOT / "specs/01-integration-contract.md").read_text()
CASES = {case["id"]: case for case in map(json.loads, (ROOT / "eval/examples.jsonl").read_text().splitlines())}
GUARDRAILS = {g["id"]: g for g in POLICIES["guardrails"]}


def test_ac_01_contract_version_is_1_4_0_in_the_package_and_the_spec():
    assert CONTRACT_VERSION == "1.4.0"
    assert "Contract version **1.4.0**" in SPEC_01 and "(contract 1.4.0," in SPEC_01
    for decision in ("D-052", "D-029", "D-033", "`ListMyCardsOut.read_at`", "`person_requested`", "01g2", "01g3"):
        assert decision in SPEC_01.split("## 1. Introduction")[0], decision     # the 1.4.0 entry names each item


def test_d_052_another_customers_record_is_not_found_and_still_a_recorded_denial():
    """D-052: NOT_FOUND to the customer (no existence oracle), a policy_denials row with POL-CROSS-CUSTOMER / G-SES-02,
    written best-effort. This checks the contract text; the behavior is tested with the gate in spec 03 (PR #106,
    test_ac_01_another_customers_transaction_is_not_found_and_logged_never_leaked and
    test_ac_01_a_failing_denial_sink_still_gives_a_probe_the_unknown_ids_answer)."""
    # [assumption] the rule's text stays "-> deny" (the decision is still a denial): its line touches PR #80's
    # POL-HUMAN-REQUEST line, so the answer's form lives in scope.cross_customer_request and G-SES-02 instead
    assert POLICIES["rules"]["POL-CROSS-CUSTOMER"]["guardrail"] == "G-SES-02"
    assert POLICIES["scope"]["cross_customer_request"] == "deny_and_log"
    impl = GUARDRAILS["G-SES-02"]["impl"]
    assert "NOT_FOUND" in impl and "POL-CROSS-CUSTOMER" in impl and "DENY with policy_id" not in impl
    assert "`NOT_FOUND` as an unknown id" in SPEC_01 and "`POL-CROSS-CUSTOMER` and G-SES-02 (D-052" in SPEC_01
    assert "That write is best-effort" in SPEC_01


def test_d_052_ev_0003_expects_a_refusal_recorded_with_pol_cross_customer():
    case = CASES["EV-0003"]
    assert case["expected"]["decision"] == "deny"
    assert case["expected"]["final_state"]["other_customer_data_exposed"] is False
    assert all(word in case["notes"] for word in ("NOT_FOUND", "POL-CROSS-CUSTOMER", "G-SES-02", "D-052"))
    assert "DENY with policy_id" not in case["notes"]


def test_d_052_live_search_is_unavailable_until_the_clock_lands():
    assert "`search_transaction` answers `UNAVAILABLE` in `live` mode" in SPEC_01


def _stored_key(key: str, customer_id: str, run_id: str | None) -> str:
    """Render policies.yaml reliability.idempotency_key: `[...]` is present only when its placeholder has a value."""
    template = POLICIES["reliability"]["idempotency_key"]
    values = {"key": key, "customer_id": customer_id, "run_id": run_id}
    template = re.sub(r"\[([^\]]*)\]", lambda m: m.group(1) if run_id is not None else "", template)
    return template.format(**values)


def test_ac_03_idempotency_key_is_the_one_store_once_stores():
    """1.4.0: the key is scoped by run and customer, as store.once keys it (spec 01 §6.5), never by session."""
    template = POLICIES["reliability"]["idempotency_key"]
    assert template == "[{run_id}:]c={customer_id}:{key}"
    assert set(re.findall(r"{(\w+)}", template)) == {"run_id", "customer_id", "key"}
    assert _stored_key("k1", "CLI-EXAMPLE00001", "R-1") == "R-1:c=CLI-EXAMPLE00001:k1"
    assert _stored_key("k1", "CLI-EXAMPLE00001", None) == "c=CLI-EXAMPLE00001:k1"
    try:                                     # the store's accessor (task 01g), once it is on main
        from nick_of_time.store.accounts import idempotency_key
    except ImportError:
        return
    for run_id in ("R-1", None):
        assert idempotency_key("k1", "block_card", "CLI-EXAMPLE00001", run_id) == _stored_key(
            "k1", "CLI-EXAMPLE00001", run_id)


def test_ac_03_list_my_cards_carries_its_own_read_at():
    """1.4.0 (review of PR #104): the listing has a reading time even with no cards; each card keeps its own."""
    answer = fake.ANSWERS["list_my_cards"]
    assert answer.read_at == dt.datetime(2026, 6, 1, 15, 4, 9, tzinfo=dt.timezone.utc)
    assert all(card.read_at for card in answer.cards)        # the per-card path read by the status node stays valid
    empty = tools.ListMyCardsOut.model_validate({"cards": [], "read_at": "2026-06-01T15:04:09Z"})
    assert empty.cards == [] and empty.read_at.tzinfo is not None
    assert "read_at" in tools.ListMyCardsOut.model_json_schema()["required"]


@pytest.mark.parametrize("payload", [{"cards": []}, {"cards": [], "read_at": "2026-06-01T15:04:09"}])
def test_ac_03_list_my_cards_without_an_aware_read_at_is_refused(payload):
    with pytest.raises(ValidationError, match="read_at"):
        tools.ListMyCardsOut.model_validate(payload)


def test_d_025_the_listing_read_at_does_not_let_a_card_verify_a_write():
    with pytest.raises(ValidationError, match="verifies no write"):
        tools.ListMyCardsOut.model_validate({"cards": [fake.FIXTURES["get_product_status"]],
                                             "read_at": "2026-06-01T15:04:09Z"})


def test_d_033_handoff_card_already_carries_score_source_and_version():
    schema = json.loads((ROOT / "contracts/handoff.schema.json").read_text())
    assert {"score_source", "score_version"} <= set(schema["properties"])
    assert set(schema["properties"]["score_source"]["enum"]) == set(POLICIES["scoring"]["providers"])
