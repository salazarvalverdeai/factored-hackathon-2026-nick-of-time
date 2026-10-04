"""D-008 / spec 03 AC-18 / spec 04 AC-28: request_call returns expected_contact_by from a policy key."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
KEY = "callback_within_business_hours"


def test_d008_policy_key_exists_and_is_positive_number():
    policies = yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())
    assert policies["contact"][KEY] > 0


def test_d008_spec_03_and_04_use_the_policy_key_and_field():
    spec03 = (ROOT / "specs/03-mcp-tools.md").read_text()
    spec04 = (ROOT / "specs/04-agent-graph.md").read_text()
    assert f"contact.{KEY}" in spec03 and "expected_contact_by" in spec03
    assert "expected_contact_by" in spec04 and "D-008" in spec04


def test_d008_messages_allow_the_placeholder():
    text = (ROOT / "contracts/messages.yaml").read_text()
    assert "expected_contact_by (request_call" in text
