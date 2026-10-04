"""Spec 01 AC-03 and D-008: tools.py v1.1 holds the 16 customer tools, and the fake MCP server answers each one with
its contract model. Calls go through FastMCP's in-memory client: no network, no gold, no Postgres."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional, get_args

import jsonschema
import pytest
import yaml
from fastmcp import Client
from mcp.shared.exceptions import MCPError

from contracts import tools
from nick_of_time import contracts as c

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server import fake  # noqa: E402

POLICIES = yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())
SPEC_01 = (ROOT / "specs/01-integration-contract.md").read_text()
ARGS = {   # the smallest valid input of each tool, besides session_id
    "search_transaction": {"amount": 1250, "approx_date": "2026-05-31"},
    "get_fraud_score": {"transaction_id": fake._TRX}, "compute_deadline": {"transaction_id": fake._TRX},
    "open_case": {"transaction_id": fake._TRX, "dispute_type": "unrecognized_charge", "zone": "high"},
    "block_card": {"product_id": fake._PRD, "reason": "high_zone_dispute"},
    "get_product_status": {"product_id": fake._PRD}, "get_case": {"case_id": fake._CASE},
    "add_case_info": {"case_id": fake._CASE, "text": "El cargo es de una tienda en la que nunca compré."},
    "request_call": {"case_id": fake._CASE}, "request_reevaluation": {"case_id": fake._CASE, "reason": "No estoy de acuerdo"},
    "convert_amount": {"amount": 1250.0, "currency": "USD", "to_currency": "MXN"},
    "send_case_summary": {"case_id": fake._CASE, "channel": "telegram"},
}


def _args(name: str, session_id: str = fake.SESSION_ID) -> dict:
    extra = {"idempotency_key": f"{session_id}:{name}"} if name in tools.VERIFIED_WITH else {}
    return {"session_id": session_id, **ARGS.get(name, {}), **extra}


def _run(*calls: tuple[str, dict]) -> list:
    async def go():
        async with Client(fake.build_server()) as client:
            return [await client.call_tool(name, args, raise_on_error=False) for name, args in calls]
    return asyncio.run(go())


def test_ac_03_policies_list_exactly_the_16_contract_tools():
    assert POLICIES["actors"]["customer"]["tools"] == list(tools.CUSTOMER_TOOLS)
    assert len(tools.CUSTOMER_TOOLS) == 16
    assert set(tools.VERIFIED_WITH) < set(tools.CUSTOMER_TOOLS) and set(tools.VERIFIED_WITH.values()) < set(
        tools.CUSTOMER_TOOLS)
    assert {"CUSTOMER_TOOLS", "RequestCallResult", "GetCaseOut"} <= set(c.TOOL_NAMES)   # re-exported (FR-01)


def test_ac_03_server_publishes_each_tool_with_its_contract_schemas():
    async def go():
        async with Client(fake.build_server()) as client:
            return await client.list_tools()
    listed = {t.name: t for t in asyncio.run(go())}
    assert list(listed) == list(tools.CUSTOMER_TOOLS)
    for name, (model_in, model_out) in tools.CUSTOMER_TOOLS.items():
        assert listed[name].input_schema == model_in.model_json_schema()
        published, schema = listed[name].output_schema, model_out.model_json_schema()   # FastMCP inlines $defs
        assert (set(published["properties"]), published.get("required")) == (set(schema["properties"]),
                                                                              schema.get("required"))
        jsonschema.validate(fake.ANSWERS[name].model_dump(mode="json"), published)


@pytest.mark.parametrize("name", list(tools.CUSTOMER_TOOLS))
def test_ac_03_fake_answers_every_tool_with_its_contract_model(name):
    model_in, model_out = tools.CUSTOMER_TOOLS[name]
    model_in.model_validate(_args(name))
    [result] = _run((name, _args(name)))
    assert not result.is_error
    assert model_out.model_validate(result.structured_content) == fake.ANSWERS[name]


def test_ac_03_unknown_session_answers_session_expired_with_no_data():
    results = _run(*[(name, _args(name, "S-unknownsession01")) for name in tools.CUSTOMER_TOOLS])
    for result in results:
        assert result.is_error and set(result.structured_content) == {"code", "policy_id", "message"}
        assert tools.ToolError.model_validate(result.structured_content).code == "SESSION_EXPIRED"


def test_ac_03_customer_id_only_comes_from_the_session():
    for name, (model_in, _) in tools.CUSTOMER_TOOLS.items():
        assert "session_id" in model_in.model_fields and "customer_id" not in model_in.model_fields, name
        assert model_in.model_json_schema()["additionalProperties"] is False, name
    try:
        [result] = _run(("search_transaction", {**_args("search_transaction"), "customer_id": "CLI-EXAMPLE00002"}))
    except MCPError:
        return                                      # rejected by the protocol's input-schema check
    assert result.is_error


def test_ac_03_accepted_is_not_verified_in_any_tool_result():
    assert set(get_args(tools.WriteState)) == {"requested"} and set(get_args(tools.WriteState)) < set(
        get_args(c.ActionState))
    for name, (_, model_out) in tools.CUSTOMER_TOOLS.items():
        assert ("state" in model_out.model_fields) == (name in tools.VERIFIED_WITH), name
    for write, read in tools.VERIFIED_WITH.items():
        read_out = tools.CUSTOMER_TOOLS[read][1]
        assert {"verification_id", "read_at"} <= set(read_out.model_fields), read
        assert read_out.model_fields["verification_id"].is_required(), read
        assert fake.ANSWERS[write].state == "requested"
    # open_case and block_card name the V- id their read reports (spec 18 A3), and still say "requested"
    assert fake.ANSWERS["open_case"].verification_id == fake.ANSWERS["get_case"].verification_id
    assert fake.ANSWERS["block_card"].verification_id == fake.ANSWERS["get_product_status"].verification_id
    with pytest.raises(ValueError):
        tools.BlockCardOut(action_id="A-3E9F20B7C164", product_id=fake._PRD, state="verified")


def test_d_008_request_call_returns_expected_contact_by():
    field = tools.RequestCallOut.model_fields["expected_contact_by"]
    assert tools.RequestCallResult is tools.RequestCallOut
    assert field.annotation == Optional[dt.date] and field.default is None   # null = no promise
    [result] = _run(("request_call", _args("request_call")))
    assert result.structured_content["expected_contact_by"] == "2026-06-02"   # replay today 2026-06-01 + 1 business day
    row = next(line for line in SPEC_01.splitlines() if "/call-request`" in line)
    assert "`{event_id, expected_contact_by}`" in row and "D-008" in row


def test_ac_01_handoff_evidence_uses_gold_id_shapes():
    handoff = json.loads((ROOT / "contracts/handoff.schema.json").read_text())
    evidence = handoff["properties"]["evidence"]["description"]
    assert {"TRX-", "PRD-", "CLI-"} <= set(evidence.replace(",", " ").split())
    assert "T-," not in evidence and "P-," not in evidence
