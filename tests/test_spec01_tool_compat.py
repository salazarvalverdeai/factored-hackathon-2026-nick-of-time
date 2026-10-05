"""Spec 01 §6.3 compatibility (AC-03): a consumer ignores an output field it does not know, so an additive minor version
of the MCP server (deployed on merge) never fails the agent revision still on Platform; inputs stay strict (G-TOOL-01)
and the published schemas stay closed (the snapshot of test_spec01_mcp_stub is unchanged)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts import tools
from tests.test_spec01_mcp_stub import fake

NEW = {"a_field_of_a_later_minor_version": "x"}


@pytest.mark.parametrize("name", list(tools.CUSTOMER_TOOLS))
def test_ac_03_an_output_with_an_unknown_field_parses_and_drops_it(name):
    model_out = tools.CUSTOMER_TOOLS[name][1]
    out = model_out.model_validate({**fake.FIXTURES[name], **NEW})
    assert out == model_out.model_validate(fake.FIXTURES[name]) and "a_field_of_a_later_minor_version" not in out.model_dump()


def test_ac_03_a_nested_output_part_with_an_unknown_field_parses_too():
    case = fake.FIXTURES["get_case"]
    out = tools.GetCaseOut.model_validate({**case, "transaction": {**case["transaction"], **NEW}})
    assert out.transaction.model_dump() == tools.GetCaseOut.model_validate(case).transaction.model_dump()


@pytest.mark.parametrize("name", list(tools.CUSTOMER_TOOLS))
def test_ac_03_an_input_with_an_unknown_field_is_still_refused(name):
    model_in = tools.CUSTOMER_TOOLS[name][0]
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        model_in.model_validate({"session_id": fake.SESSION_ID, "customer_id": "CLI-SOMEONEELSE", **NEW})


@pytest.mark.parametrize("name", list(tools.CUSTOMER_TOOLS))
def test_ac_03_the_published_schemas_stay_closed(name):
    model_in, model_out = tools.CUSTOMER_TOOLS[name]
    for schema in (model_in.model_json_schema(), model_out.model_json_schema()):
        assert schema["additionalProperties"] is False
        assert all(d.get("additionalProperties") is False for d in schema.get("$defs", {}).values()
                   if d.get("type") == "object")
