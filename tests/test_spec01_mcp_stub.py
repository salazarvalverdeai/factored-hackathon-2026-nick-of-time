"""Spec 01 AC-03 and D-008: tools.py v1.1 holds the 16 customer tools, and the fake MCP server answers each one with
its contract model. Calls go through FastMCP's in-memory client: no network, no gold, no Postgres."""
from __future__ import annotations

import asyncio
import copy
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
from pydantic import ValidationError

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
    "request_call": {"case_id": fake._CASE},
    "request_reevaluation": {"case_id": fake._CASE, "reason": "No estoy de acuerdo"},
    "convert_amount": {"amount": 1250.0, "currency": "USD", "to_currency": "MXN"},
    "send_case_summary": {"case_id": fake._CASE, "channel": "telegram"},
}


def _args(name: str, session_id: str = fake.SESSION_ID, **extra) -> dict:
    key = {"idempotency_key": f"{session_id}:{name}"} if name in tools.VERIFIED_WITH else {}
    return {"session_id": session_id, **ARGS.get(name, {}), **key, **extra}


def _run(*calls: tuple[str, dict]) -> list:
    async def go():
        async with Client(fake.build_server()) as client:
            return [await client.call_tool(name, args, raise_on_error=False) for name, args in calls]
    return asyncio.run(go())


def _spec_table() -> list[list[str]]:
    section = SPEC_01.split("### 6.3")[1].split("### 6.4")[0]
    return [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.startswith("| `")]


def test_ac_03_tools_match_policies_and_the_spec_table():
    rows = _spec_table()
    assert [row[0].strip("`") for row in rows] == list(tools.CUSTOMER_TOOLS) == POLICIES["actors"]["customer"]["tools"]
    assert len(tools.CUSTOMER_TOOLS) == 16
    assert {row[0].strip("`"): row[-1].strip("`") for row in rows if row[-1] != "—"} == tools.VERIFIED_WITH
    assert {row[0].strip("`") for row in rows if row[1] in ("W", "N")} == set(tools.VERIFIED_WITH)
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


def test_ac_03_unknown_session_or_id_answers_a_tool_error_with_no_data():
    results = _run(*[(name, _args(name, "S-unknownsession01")) for name in tools.CUSTOMER_TOOLS],
                   ("get_case", _args("get_case", case_id="K-999999")),
                   ("get_product_status", _args("get_product_status", product_id="PRD-OTHERPRODUCT")))
    codes = [tools.ToolError.model_validate(r.structured_content).code for r in results if r.is_error]
    assert codes == ["SESSION_EXPIRED"] * 16 + ["NOT_FOUND"] * 2


def test_ac_03_customer_id_only_comes_from_the_session():
    for name, (model_in, _) in tools.CUSTOMER_TOOLS.items():
        assert "session_id" in model_in.model_fields and "customer_id" not in model_in.model_fields, name
        assert model_in.model_json_schema()["additionalProperties"] is False, name
    with pytest.raises(MCPError) as err:        # the fake's input-model check → JSON-RPC invalid params
        _run(("search_transaction", _args("search_transaction", customer_id="CLI-EXAMPLE00002")))
    assert err.value.code == -32602


def _id_paths(data, path=()):
    """Paths to every `*_id` string in a fixture, nested lists and objects included."""
    items = data.items() if isinstance(data, dict) else enumerate(data) if isinstance(data, list) else []
    for key, value in items:
        if isinstance(key, str) and key.endswith("_id") and isinstance(value, str):
            yield path + (key,)
        yield from _id_paths(value, path + (key,))


INPUT_IDS = [(name, field) for name, (model_in, _) in tools.CUSTOMER_TOOLS.items()
             for field in model_in.model_fields if field.endswith("_id") and field != "session_id"]
OUTPUT_IDS = [(name, path) for name, data in fake.FIXTURES.items() for path in _id_paths(data)]


@pytest.mark.parametrize(("name", "field"), INPUT_IDS)
def test_ac_03_every_input_id_has_its_shape(name, field):
    with pytest.raises(ValidationError):
        tools.CUSTOMER_TOOLS[name][0].model_validate(_args(name, **{field: "X-1"}))


@pytest.mark.parametrize(("name", "path"), OUTPUT_IDS, ids=lambda p: ".".join(map(str, p)) if type(p) is tuple else p)
def test_ac_03_every_output_id_has_its_shape(name, path):
    data = copy.deepcopy(fake.FIXTURES[name])
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = "X-1"
    with pytest.raises(ValidationError):
        tools.CUSTOMER_TOOLS[name][1].model_validate(data)


def test_ac_03_accepted_is_not_verified_in_any_tool_result():
    assert set(get_args(tools.WriteState)) == {"requested"} < set(get_args(c.ActionState))
    for name, (_, model_out) in tools.CUSTOMER_TOOLS.items():
        assert ("state" in model_out.model_fields) == (name in tools.VERIFIED_WITH), name
    for write, read in tools.VERIFIED_WITH.items():
        assert "verification_id" not in tools.CUSTOMER_TOOLS[write][1].model_fields, write   # D-025: the read mints it
        read_out = tools.CUSTOMER_TOOLS[read][1]
        assert {"verification_id", "read_at"} <= set(read_out.model_fields), read
        assert read_out.model_fields["verification_id"].is_required(), read
        assert fake.ANSWERS[write].state == "requested"
    with pytest.raises(ValidationError):
        tools.BlockCardOut(action_id="A-3E9F20B7C164", product_id=fake._PRD, state="verified")


@pytest.mark.parametrize("drop", ["deadline_source", "deadline_source_url", "deadline_verified_on"])
def test_ac_03_a_stored_deadline_travels_with_its_source(drop):
    for name in ("open_case", "get_case"):
        with pytest.raises(ValidationError, match="verified_on"):
            tools.CUSTOMER_TOOLS[name][1].model_validate({**fake.FIXTURES[name], drop: None})
    no_dates = {k: None for k in ("credit_deadline", "ruling_deadline", "deadline_source", "deadline_source_url",
                                  "deadline_verified_on")}
    tools.GetCaseOut.model_validate({**fake.FIXTURES["get_case"], **no_dates})


@pytest.mark.parametrize(("model", "data", "valid"), [
    (tools.SearchTransactionIn, {"window_days": 30}, True),
    (tools.SearchTransactionIn, {"window_days": 31}, False),
    (tools.SearchTransactionIn, {"window_days": -1}, False),
    (tools.SearchTransactionIn, {"currency": "usd"}, False),
    (tools.SearchTransactionIn, {"merchant": "X" * 101}, False),
    (tools.RequestCallIn, {"idempotency_key": "k"}, True),                     # case_id optional: a general request
    (tools.RequestReevaluationIn, {"idempotency_key": "k", "reason": "r"}, False),   # case_id required
])
def test_ac_03_input_bounds(model, data, valid):
    try:
        model.model_validate({"session_id": fake.SESSION_ID, **data})
    except ValidationError:
        assert not valid
    else:
        assert valid


def test_ac_03_search_returns_at_most_four_candidates_and_no_score():
    row = fake.FIXTURES["search_transaction"]["candidates"][0]
    tools.SearchTransactionOut.model_validate({"candidates": [row] * 4})
    with pytest.raises(ValidationError):
        tools.SearchTransactionOut.model_validate({"candidates": [row] * 5})
    assert not {"fraud_score", "split"} & set(tools.Transaction.model_fields)    # D-026: the zone uses get_fraud_score


@pytest.mark.parametrize(("outcome", "event_id", "valid"), [
    ("already_in_progress", None, True), ("already_in_progress", "E-5D0E7A21C9B4", False),
    ("back_to_review", "E-5D0E7A21C9B4", True), ("back_to_review", None, False),
    ("related_case_opened", None, False)])
def test_ac_03_reevaluation_writes_an_event_unless_already_in_progress(outcome, event_id, valid):
    data = {**fake.FIXTURES["request_reevaluation"], "outcome": outcome, "event_id": event_id}
    try:
        tools.RequestReevaluationOut.model_validate(data)
    except ValidationError:
        assert not valid
    else:
        assert valid


def test_d_008_request_call_returns_expected_contact_by():
    field = tools.RequestCallOut.model_fields["expected_contact_by"]
    assert tools.RequestCallResult is tools.RequestCallOut
    assert field.annotation == Optional[dt.date] and field.default is None   # null = no promise
    [result] = _run(("request_call", _args("request_call")))
    assert result.structured_content["expected_contact_by"] == "2026-06-02"   # replay today 2026-06-01 + 1 business day
    row = next(line for line in SPEC_01.splitlines() if "/call-request`" in line)
    assert "`{event_id, expected_contact_by}`" in row and "D-008" in row


def test_ac_01_handoff_evidence_uses_gold_and_contract_id_shapes():
    handoff = json.loads((ROOT / "contracts/handoff.schema.json").read_text())
    prefixes = set(handoff["properties"]["evidence"]["description"].replace(",", " ").split())
    assert {"TRX-", "PRD-", "CLI-", "A-", "V-", "RC-", "K-"} <= prefixes
    assert not {"T-", "P-", "R-"} & prefixes
