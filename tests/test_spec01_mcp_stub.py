"""Spec 01 AC-03, D-008, D-025, D-026 and D-027: tools.py v1.1 holds the 16 customer tools, and the fake MCP server
answers each one with its contract model. Calls go through FastMCP's in-memory client: no network, no gold, no
Postgres."""
from __future__ import annotations

import asyncio
import copy
import datetime as dt
import json
import os
import re
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
from nick_of_time.ids import PATTERN

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/mcp"))
from mcp_server import fake  # noqa: E402

POLICIES = yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())
SNAPSHOT = ROOT / "tests/snapshots/tools_v1_1_schemas.json"
SPEC_01 = (ROOT / "specs/01-integration-contract.md").read_text()
ARGS = {   # the smallest valid input of each tool, besides session_id
    "search_transaction": {"amount": 1250, "approx_date": "2026-05-31"},
    "get_fraud_score": {"transaction_id": fake._TRX}, "compute_deadline": {"transaction_id": fake._TRX},
    "open_case": {"transaction_id": fake._TRX, "dispute_type": "unrecognized_charge", "zone": "high"},
    "block_card": {"product_id": fake._PRD, "reason": "high_zone_dispute"},
    "get_product_status": {"product_id": fake._PRD, "action_id": fake.FIXTURES["block_card"]["action_id"]},
    "get_case": {"case_id": fake._CASE, "action_id": fake.FIXTURES["open_case"]["action_id"]},
    "add_case_info": {"case_id": fake._CASE, "text": "El cargo es de una tienda en la que nunca compré."},
    "request_call": {"case_id": fake._CASE},
    "request_reevaluation": {"case_id": fake._CASE, "reason": "No estoy de acuerdo"},
    "convert_amount": {"amount": 1250.0, "currency": "USD", "to_currency": "MXN"},
    "send_case_summary": {"case_id": fake._CASE, "channel": "telegram"},
    "list_my_notifications": {"action_id": fake.FIXTURES["send_case_summary"]["action_id"]},
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
    unknown = "S-unknownsession01"
    results = _run(*[(name, _args(name, unknown)) for name in tools.CUSTOMER_TOOLS],
                   ("get_case", _args("get_case", unknown, case_id="K-999999")),   # session before ids: no oracle
                   ("get_case", _args("get_case", case_id="K-999999")),
                   ("get_product_status", _args("get_product_status", product_id="PRD-OTHERPRODUCT")))
    assert all(r.is_error and set(r.structured_content) <= set(tools.ToolError.model_fields) for r in results)
    codes = [tools.ToolError.model_validate(r.structured_content).code for r in results]
    assert codes == ["SESSION_EXPIRED"] * 17 + ["NOT_FOUND"] * 2


def test_ac_03_customer_id_only_comes_from_the_session():
    for name, (model_in, _) in tools.CUSTOMER_TOOLS.items():
        assert "session_id" in model_in.model_fields and "customer_id" not in model_in.model_fields, name
        assert model_in.model_json_schema()["additionalProperties"] is False, name
    unknown = _args("search_transaction", "S-unknownsession01", customer_id="CLI-EXAMPLE00002")
    [result] = _run(("search_transaction", unknown))           # session first (spec 03 AC-02), then the arguments
    assert tools.ToolError.model_validate(result.structured_content).code == "SESSION_EXPIRED"
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
             for field in model_in.model_fields if field.endswith("_id")]
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


def _patterns(schema):
    """Every string `pattern` in a JSON schema, $defs and nested objects included."""
    if isinstance(schema, dict):
        if isinstance(schema.get("pattern"), str):
            yield schema["pattern"]
        for value in schema.values():
            yield from _patterns(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from _patterns(item)


def test_ac_03_accepted_is_not_verified_in_any_tool_result():
    assert set(get_args(tools.WriteState)) == {"requested"} < set(get_args(c.ActionState))
    for name, (_, model_out) in tools.CUSTOMER_TOOLS.items():
        assert ("state" in model_out.model_fields) == (name in tools.VERIFIED_WITH), name
    for write, read in tools.VERIFIED_WITH.items():
        assert "verification_id" not in tools.CUSTOMER_TOOLS[write][1].model_fields, write   # D-025: the read mints it
        assert PATTERN["verification"] not in set(_patterns(tools.CUSTOMER_TOOLS[write][1].model_json_schema())), write
        read_in, read_out = tools.CUSTOMER_TOOLS[read]
        assert "action_id" in read_in.model_fields, read
        assert {"action_id", "verification_id", "read_at"} <= set(read_out.model_fields), read
        assert fake.ANSWERS[write].state == "requested"
    with pytest.raises(ValidationError):
        tools.BlockCardOut(action_id="A-3E9F20B7C164", product_id=fake._PRD, state="verified")


# Identity, score, zone, policy and audit internals, by name fragment (synonyms included): constitution #3 and #7,
# spec 03 AC-11, policies.yaml notifications.never_send.
LEAK = re.compile(r"customer|score|zone|risk|polic|transcript|mail|phone|document|address|birth|last_name|surname|"
                  r"fraud|split|session|trace")
ALLOWED = {("GetFraudScoreOut", "score")}        # the agent reads it to compute the zone; plus any masked_address


def _fields(schema):
    """(model, field) for every property of a model's JSON schema and of its $defs."""
    for field in schema.get("properties", {}):
        yield schema.get("title"), field
    for sub in schema.get("$defs", {}).values():
        yield from _fields(sub)


@pytest.mark.parametrize("name", list(tools.CUSTOMER_TOOLS))
def test_ac_03_no_output_exposes_identity_score_zone_or_policy(name):
    fields = set(_fields(tools.CUSTOMER_TOOLS[name][1].model_json_schema()))
    leaks = {(model, field) for model, field in fields
             if LEAK.search(field) and field != "masked_address" and (model, field) not in ALLOWED}
    assert not leaks
    assert (("GetFraudScoreOut", "score") in fields) == (name == "get_fraud_score")


def _contract_snapshot() -> dict:
    tools_ = {name: {"in": model_in.model_json_schema(), "out": model_out.model_json_schema()}
              for name, (model_in, model_out) in tools.CUSTOMER_TOOLS.items()}
    return json.loads(json.dumps({"customer_tools": tools_, "verified_with": tools.VERIFIED_WITH,
                                  "tool_error": tools.ToolError.model_json_schema()}))


def test_ac_03_tool_schemas_match_the_checked_in_snapshot():
    """Rule 9: any change to a tool's In/Out schema is a visible diff of tests/snapshots/tools_v1_1_schemas.json.
    Regenerate it on purpose with UPDATE_TOOL_SNAPSHOT=1 and get the lead's approval."""
    current = _contract_snapshot()
    if os.environ.get("UPDATE_TOOL_SNAPSHOT") == "1":
        SNAPSHOT.write_text(json.dumps(current, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    assert json.loads(SNAPSHOT.read_text()) == current
    assert list(current["customer_tools"]) == list(tools.CUSTOMER_TOOLS)


READS = sorted(set(tools.VERIFIED_WITH.values()))
# The (read, write action) pairs the fake must verify, derived from the contract: one per VERIFIED_WITH entry.
PAIRS = sorted({(read, fake.FIXTURES[write]["action_id"]) for write, read in tools.VERIFIED_WITH.items()})


def _reading(read: str, action_id: Optional[str]) -> dict:
    args = {key: value for key, value in _args(read).items() if key != "action_id"}
    return args if action_id is None else {**args, "action_id": action_id}


@pytest.mark.parametrize("read", READS)
def test_d_025_a_verifying_read_names_the_write_it_verified(read):
    """AC-03 / D-025: action_id and verification_id come both or neither; a plain status read has read_at only."""
    model_in, model_out = tools.CUSTOMER_TOOLS[read]
    assert not model_in.model_fields["action_id"].is_required()
    first_write = next(write for write, by in tools.VERIFIED_WITH.items() if by == read)
    fixture = fake.FIXTURES[read]           # get_case → open_case, get_product_status → block_card, ...
    assert fixture["action_id"] == fake.FIXTURES[first_write]["action_id"]
    assert fake.VERIFICATIONS[(read, fixture["action_id"])] == fixture["verification_id"]
    for drop in ("action_id", "verification_id"):
        with pytest.raises(ValidationError, match="both or neither"):
            model_out.model_validate({**fixture, drop: None})
    plain = model_out.model_validate({**fixture, "action_id": None, "verification_id": None})
    assert plain.read_at is not None


@pytest.mark.parametrize(("read", "action_id"), PAIRS)
def test_d_025_the_fake_verifies_each_write_by_its_read(read, action_id):
    assert set(fake.VERIFICATIONS) == set(PAIRS)                               # the VERIFIED_WITH table of tools.py
    assert len(set(fake.VERIFICATIONS.values())) == len(PAIRS)                 # one V- per (read, write)
    [result] = _run((read, _reading(read, action_id)))
    got = result.structured_content
    assert (got["action_id"], got["verification_id"]) == (action_id, fake.VERIFICATIONS[(read, action_id)])
    assert got["read_at"]


@pytest.mark.parametrize(("read", "asked"), [(read, asked) for read in READS for asked in ("none", "foreign")])
def test_d_025_a_plain_or_foreign_read_verifies_nothing(read, asked):
    foreign = next(action for other, action in PAIRS if other != read)         # a write another read verifies
    [result] = _run((read, _reading(read, None if asked == "none" else foreign)))
    got = result.structured_content
    assert (got["action_id"], got["verification_id"]) == (None, None) and got["read_at"]


def test_d_025_list_my_cards_verifies_no_write():
    [result] = _run(("list_my_cards", _args("list_my_cards")))
    assert [(card["action_id"], card["verification_id"]) for card in result.structured_content["cards"]] == [
        (None, None)]
    with pytest.raises(ValidationError, match="verifies no write"):
        tools.ListMyCardsOut.model_validate({"cards": [fake.FIXTURES["get_product_status"]],
                                             "read_at": fake.FIXTURES["list_my_cards"]["read_at"]})


@pytest.mark.parametrize("case_id", ["absent", None])
def test_d_026_a_call_request_with_no_case_is_its_own_unverified_action(case_id):
    args = {key: value for key, value in _args("request_call").items() if key != "case_id"}
    if case_id is None:
        args["case_id"] = None                  # LLM tool calls often send an explicit null
    [result] = _run(("request_call", args))
    answer = tools.RequestCallOut.model_validate(result.structured_content)
    assert (answer.case_id, answer.state, answer.expected_contact_by) == (None, "requested", dt.date(2026, 6, 2))
    assert "verification_id" not in result.structured_content
    assert answer.action_id not in {action for _, action in fake.VERIFICATIONS}            # outside VERIFICATIONS
    assert answer.event_id != fake.FIXTURES["request_call"]["event_id"]
    [read] = _run(("get_case", _args("get_case", action_id=answer.action_id)))
    assert (read.structured_content["action_id"], read.structured_content["verification_id"]) == (None, None)
    spec_03 = (ROOT / "specs/03-mcp-tools.md").read_text().split("## 6.")[1].split("## 7.")[0]
    assert "call_requests" in spec_03 and "only as `requested`" in spec_03 and "03d" in spec_03
    row = next(line for line in SPEC_01.splitlines() if line.startswith("| `request_call`"))
    assert "D-026" in row and "call_requests" in row


def test_ac_18_a_second_call_request_returns_the_original_ids():
    """D-025 default: the second request of a case writes nothing and returns the first one's ids."""
    results = _run(("request_call", _args("request_call", idempotency_key="call-1")),
                   ("request_call", _args("request_call", idempotency_key="call-2")))
    original = (fake.FIXTURES["request_call"]["action_id"], fake.FIXTURES["request_call"]["event_id"])
    assert [(r.structured_content["action_id"], r.structured_content["event_id"]) for r in results] == [original] * 2


def test_ac_19_already_in_progress_returns_the_original_write_ids():
    """D-025 default: nothing is written, so the answer carries the ids of the write that holds the case active."""
    answer = fake.ANSWERS["request_reevaluation"]
    opened = next(event for event in fake.FIXTURES["get_case"]["timeline"] if event["type"] == "case_opened")
    assert answer.outcome == "already_in_progress"
    assert (answer.action_id, answer.event_id) == (fake.FIXTURES["open_case"]["action_id"], opened["event_id"])
    assert all(tools.RequestReevaluationOut.model_fields[field].is_required() for field in ("action_id", "event_id"))
    [read] = _run(("get_case", _args("get_case", action_id=answer.action_id)))
    assert read.structured_content["verification_id"] == fake.VERIFICATIONS[("get_case", answer.action_id)]
    row = next(line for line in (ROOT / "specs/03-mcp-tools.md").read_text().splitlines()
               if line.startswith("| `request_reevaluation`"))
    assert "already in review" in row and "never as a new verified action" in row     # spec 04 follows (04c)


def test_d_027_synthetic_is_a_score_source():
    providers = POLICIES["scoring"]["providers"]
    assert "synthetic" in get_args(tools.GetFraudScoreOut.model_fields["source"].annotation)
    assert providers["synthetic"]["version"] == "synthetic-v0"
    tools.GetFraudScoreOut.model_validate({**fake.FIXTURES["get_fraud_score"], "source": "synthetic",
                                           "version": "synthetic-v0"})


MISSING = object()
AWARE, NAIVE = "2026-06-01T15:04:11-06:00", "2026-06-01T15:04:11"
BASES = {"convert_amount": {"converted": {"amount": "22500.00", "currency": "MXN", "rate": "18.0",
                                          "rate_source": "Banxico FIX", "as_of": "2026-06-01"}},
         "get_case:no_source": {**fake.FIXTURES["get_case"], "credit_deadline": None, "deadline_source": None,
                                "deadline_source_url": None, "deadline_verified_on": None}}
SHAPES = [   # (tool, field path, a valid value, an invalid value): output fields no fixture id covers
    ("open_case", "duplicate_of", "K-104233", "104233"),
    ("request_reevaluation", "event_id", "E-5D0E7A21C9B4", "E-5d0e7a21c9b4"),
    ("get_case", "transaction.currency", "MXN", "usd"),
    ("get_case", "deadline_source_url", "https://www.banxico.org.mx/", "http://www.banxico.org.mx/"),
    ("get_product_status", "last4", "0001", "441"),
    ("get_case", "read_at", AWARE, NAIVE), ("get_case", "read_at", AWARE, MISSING),          # AC-16
    ("list_my_cases", "read_at", AWARE, NAIVE), ("list_my_cases", "read_at", AWARE, MISSING),
    ("compute_deadline", "source_url", fake._URL, "http://www.gob.mx/condusef"),              # ADR 0019
    ("compute_deadline", "source_url", fake._URL, MISSING), ("compute_deadline", "verified_on", "2026-10-04", MISSING),
    ("get_fraud_score", "score", 100.0, 100.5), ("get_fraud_score", "score", 0.0, -5.0),
    ("get_fraud_score", "score", None, float("nan")),
    ("convert_amount", "converted.rate", "18.0", "18,0"),
    ("get_case", "timeline.0.created_at", AWARE, NAIVE),
    ("list_my_notifications", "notifications.0.created_at", AWARE, NAIVE),
    ("get_case:no_source", "ruling_deadline", None, "2026-06-20"),                         # ADR 0019, D-014
]


@pytest.mark.parametrize(("name", "field", "good", "bad"), SHAPES,
                         ids=[f"{n}.{f}={'missing' if b is MISSING else b}" for n, f, _, b in SHAPES])
def test_ac_03_output_fields_keep_their_shape(name, field, good, bad):
    tool = name.split(":")[0]
    def with_value(value):
        data = copy.deepcopy(BASES.get(name, fake.FIXTURES[tool]))
        *parents, key = field.split(".")
        node = data
        for parent in parents:
            node = node[int(parent) if parent.isdigit() else parent]
        if value is MISSING:
            node.pop(key, None)
        else:
            node[key] = value
        return data
    model = tools.CUSTOMER_TOOLS[tool][1]
    model.model_validate(with_value(good))
    with pytest.raises(ValidationError):
        model.model_validate(with_value(bad))


def test_ac_03_enums_keep_their_source_vocabulary():
    def values(model, field):
        return get_args(model.model_fields[field].annotation)
    assert values(tools.GetCaseOut, "queue_status") == values(tools.MyCase, "queue_status") == tuple(
        POLICIES["case_queue"]["states"])
    assert values(tools.NotificationItem, "delivery_status") == values(c.CaseNotification, "delivery_status")
    assert values(tools.GetCustomerProfileOut, "language") == get_args(c.Language)
    assert values(tools.BlockCardIn, "reason") == ("high_zone_dispute", "confirmed_dispute")   # tools.py v1.1


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
    (tools.OpenCaseIn, {**ARGS["open_case"], "idempotency_key": "k"}, True),
    (tools.OpenCaseIn, {**ARGS["open_case"], "idempotency_key": ""}, False),
    (tools.AddCaseInfoIn, {"idempotency_key": "k", "case_id": fake._CASE, "text": "x" * 1000}, True),   # AC-17
    (tools.AddCaseInfoIn, {"idempotency_key": "k", "case_id": fake._CASE, "text": "x" * 1001}, False),
    (tools.SearchTransactionIn, {"amount": 1250.0}, True),
    (tools.SearchTransactionIn, {"amount": float("nan")}, False),
    (tools.SearchTransactionIn, {"amount": float("inf")}, False),
    (tools.ConvertAmountIn, {"amount": 1250.0, "currency": "USD"}, True),
    (tools.ConvertAmountIn, {"amount": float("nan"), "currency": "USD"}, False),
    (tools.ConvertAmountIn, {"amount": float("-inf"), "currency": "USD"}, False),
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


def test_ac_03_mcp_image_serves_on_the_container_port_and_keeps_secrets_out():
    lines = (ROOT / "apps/mcp/Dockerfile").read_text().splitlines()
    cmd = json.loads(next(line for line in lines if line.startswith("CMD "))[4:])
    assert [line for line in lines if line.startswith("FROM ")] == ["FROM python:3.13-slim"]      # spec 01 §6.1
    assert [line.split()[1:] for line in lines if line.startswith("COPY ")] == [
        ["packages/", "packages/"], ["contracts/", "contracts/"], ["apps/mcp/", "apps/mcp/"]]
    assert "PYTHONPATH=/app:/app/packages:/app/apps/mcp" in next(line for line in lines if "PYTHONPATH=" in line)
    assert "EXPOSE 8001" in lines and "(container port 8001, spec 06)" in SPEC_01
    assert cmd[cmd.index("--host") + 1] == "0.0.0.0" and cmd[cmd.index("--port") + 1] == "8001"
    ignored = {line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines()
               if line.strip() and not line.startswith("#")}
    notes = (ROOT / ".gitignore").read_text().split("# personal drafts")[1].split("\n\n")[0].splitlines()[1:]
    assert {".venv", "data", "**/data/gold_eval", "**/*.parquet", "**/*.duckdb", "**/.env*", "**/*.pem", ".git",
            ".claude", "revision", "**/.next", "**/.DS_Store"} | set(notes) <= ignored
    assert notes and "**/data" not in ignored      # apps/web/app/data is source
    assert not [line for line in ignored if line.startswith("!")]       # a negation would put a file back
