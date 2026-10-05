"""Fake MCP server (spec 01 §6.3, T4, AC-03): the 16 customer tools answering fixtures [simulated].

Each tool publishes the JSON schema of its `contracts/tools.py` input model and answers its output model built from
`FIXTURES`. No gold, no Postgres, no network: the agent and the api develop against it until spec 03 replaces it.
- Session first: it knows one session, `SESSION_ID` (replay, today 2026-06-01); any other answers `ToolError`
  `SESSION_EXPIRED` with no data, as the real server does.
- Arguments: the fake validates them with the input model, so an unexpected one (a `customer_id` included) fails
  there and reaches the client as JSON-RPC error -32602; the real server answers `DENY` G-TOOL-01 instead (spec 03).
- Ids: a `transaction_id`, `product_id` or `case_id` other than the fixture's answers `ToolError` `NOT_FOUND`.
- Verifying reads (D-025): called with the `action_id` of a fixture write they verify, they return it with the `V-` of
  `VERIFICATIONS`; with any other `action_id`, or none, they are a plain status read (`read_at` only).
- A `request_call` with no `case_id` answers `CASELESS_CALL`: `case_id: null` and its own action and event ids, which no
  read verifies (D-026).
- No API key: never deploy it publicly; the real server requires `X-API-Key` (spec 03 AC-06).
Run: `PYTHONPATH=.:packages:apps/mcp python -m mcp_server.fake` → http://localhost:8100/mcp.
"""
from __future__ import annotations

import argparse
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools.base import Tool, ToolResult

from contracts.tools import CUSTOMER_TOOLS, VERIFIED_WITH, ToolError

SESSION_ID = "S-demoreplay000001"
_CASE, _TRX, _PRD = "K-104233", "TRX-FIXTURE0000000000001", "PRD-FIXTURE00001"   # the sample receipt's ids
_SOURCE = "Banxico Circular 3/2012, as amended by Circular 14/2018"
_LABEL = {"es": "Banxico, Circular 3/2012 (modificada por la Circular 14/2018)",        # the source in the session's
          "pt": "Banxico (México), Circular 3/2012 (modificada pela Circular 14/2018)"}  # language (1.5.0, DLANG)
_URL = ("https://www.gob.mx/condusef/prensa/cargos-no-reconocidos-en-tarjeta-de-debito-se-restituiran-en-dos-dias-"
        "habiles-bancarios?idiom=es")
_DEADLINE = {"credit_deadline": "2026-06-03", "deadline_source": _SOURCE, "deadline_source_label": _LABEL["es"],
             "deadline_source_url": _URL, "deadline_verified_on": "2026-10-04"}
_CARD = {"product_id": _PRD, "type": "debit", "last4": "4417", "status": "Blocked", "read_at": "2026-06-01T15:04:09Z"}
_TELEGRAM = {"channel": "telegram", "masked_address": "···4821"}
_EVENT = {"case_id": _CASE, "event_id": "E-5D0E7A21C9B4"}

FIXTURES: dict[str, dict[str, Any]] = {
    "get_customer_profile": {"first_name": "Ana", "language": "es", "country": "MX", "display_currency": "MXN",
                             "channels": [_TELEGRAM]},
    "search_transaction": {"candidates": [{
        "transaction_id": _TRX, "product_id": _PRD, "transaction_date": "2026-05-31", "amount": 1250.0,
        "currency": "USD", "amount_usd": 1250.0, "merchant": "TIENDA X", "transaction_status": "Approved"}]},
    "get_fraud_score": {"transaction_id": _TRX, "score": 72.0, "source": "dataset", "version": "gold-v1"},
    "compute_deadline": {"country": "MX", "product": "debit", "credit_deadline": "2026-06-03", "ruling_deadline": None,
                         "deadline_source": _SOURCE, "deadline_source_label": _LABEL["es"], "source_url": _URL,
                         "verified_on": "2026-10-04"},
    # writes stay "requested" and carry no V- id: the read of VERIFIED_WITH mints it when asked about the write (D-025)
    "open_case": {"action_id": "A-71C0D5E8A2F3", "case_id": _CASE, "country": "MX", **_DEADLINE},
    "block_card": {"action_id": "A-3E9F20B7C164", "product_id": _PRD},
    "get_product_status": {**_CARD, "action_id": "A-3E9F20B7C164", "verification_id": "V-8B2D41C7E0A9"},   # block_card
    "list_my_cards": {"cards": [_CARD], "read_at": _CARD["read_at"]},   # 1.4.0: the listing's reading time
    "get_case": {**_DEADLINE, "case_id": _CASE, "queue_status": "verification", "status_label": "Recibido",
                 "transaction": {"transaction_id": _TRX, "amount": 1250.0, "currency": "USD",
                                 "transaction_date": "2026-05-31", "merchant": "TIENDA X"},
                 "product_last4": "4417", "read_at": "2026-06-01T15:04:11Z",
                 "action_id": "A-71C0D5E8A2F3", "verification_id": "V-0C6A93F1B57D",           # open_case
                 "timeline": [{"event_id": "E-0B7F3A9C2D14", "type": "case_opened", "label": "Caso abierto",
                               "created_at": "2026-06-01T15:04:10Z"}]},
    "list_my_cases": {"cases": [{"case_id": _CASE, "queue_status": "verification", "status_label": "Recibido",
                                 "credit_deadline": "2026-06-03", "product_last4": "4417",
                                 "updated_at": "2026-06-01T15:04:10Z"}], "read_at": "2026-06-01T15:04:11Z"},
    "add_case_info": {"action_id": "A-2C8E61F0B3A7", **_EVENT},
    # D-008: replay today 2026-06-01 (Monday) + contact.callback_within_business_days (1) → 2026-06-02
    "request_call": {"action_id": "A-9A4D07E2C5B1", "case_id": _CASE, "event_id": "E-3B6C1D9F2A85",
                     "expected_contact_by": "2026-06-02"},
    # AC-19 (D-025): the case is active, so nothing is written; the ids are those of the open_case that holds it active
    "request_reevaluation": {"action_id": "A-71C0D5E8A2F3", "case_id": _CASE, "event_id": "E-0B7F3A9C2D14",
                             "outcome": "already_in_progress"},
    "convert_amount": {"converted": None},      # no verified rate yet, as in the sample receipt (ADR 0019)
    "send_case_summary": {"action_id": "A-D3E5F7091B2C", "notification_id": "N-7E2A9C4B1D30", **_TELEGRAM},
    "list_my_notifications": {"action_id": "A-D3E5F7091B2C", "verification_id": "V-4A1C9E7B3D52",   # send_case_summary
                              "read_at": "2026-06-01T15:04:12Z",
                              "notifications": [{"notification_id": "N-1F0D8B6A4C29", "case_id": _CASE,
                                                 "event": "case_opened", "channel": "log",
                                                 "delivery_status": "delivered",
                                                 "text": "Abrimos tu caso K-104233. Plazo legal: 2026-06-03.",
                                                 "created_at": "2026-06-01T15:04:10Z"}]},
}
# Built through the contract models, so a fixture that drifts from contracts/tools.py fails at import.
ANSWERS = {name: CUSTOMER_TOOLS[name][1].model_validate(data) for name, data in FIXTURES.items()}
KNOWN_IDS = {"transaction_id": _TRX, "product_id": _PRD, "case_id": _CASE}
# (read, action_id of the fixture write it verifies) → the V- that read mints (D-025): one pair per VERIFIED_WITH entry
# of contracts/tools.py. The request_reevaluation fixture returns open_case's action (AC-19), so it shares that pair.
VERIFICATIONS: dict[tuple[str, str], str] = {
    ("get_case", "A-71C0D5E8A2F3"): "V-0C6A93F1B57D",                 # open_case
    ("get_case", "A-2C8E61F0B3A7"): "V-1E4B7D0A9C36",                 # add_case_info
    ("get_case", "A-9A4D07E2C5B1"): "V-5C2F8A1E7B04",                 # request_call
    ("get_product_status", "A-3E9F20B7C164"): "V-8B2D41C7E0A9",       # block_card
    ("list_my_notifications", "A-D3E5F7091B2C"): "V-4A1C9E7B3D52",    # send_case_summary
}
# D-026: a general request (no case_id) writes a call_requests row, not a case event; no customer read verifies it.
CASELESS_CALL = {"action_id": "A-5E8B2F0C7D19", "event_id": "E-6A3D9B1F4C07", "case_id": None}


def _error(error: ToolError) -> ToolResult:
    return ToolResult(content=error.model_dump_json(), structured_content=error.model_dump(), is_error=True)


class FixtureTool(Tool):
    """A contract tool: input schema of `<Name>In`, output schema of `<Name>Out`, answers its fixture."""
    language: str = "es"                                          # the fake session's language: picks the source label

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        if arguments.get("session_id") != SESSION_ID:             # session first (spec 03 AC-02)
            return _error(ToolError(code="SESSION_EXPIRED", message="The session expired or does not exist."))
        CUSTOMER_TOOLS[self.name][0].model_validate(arguments)    # strict: extra="forbid" → JSON-RPC -32602
        if any(arguments.get(key) not in (None, known) for key, known in KNOWN_IDS.items()):
            return _error(ToolError(code="NOT_FOUND", message="No such transaction, card or case for this customer."))
        answer = ANSWERS[self.name]
        if self.name in VERIFIED_WITH.values():                     # a V- only for the write it was asked about
            verification_id = VERIFICATIONS.get((self.name, arguments.get("action_id")))
            answer = answer.model_copy(update={"action_id": arguments["action_id"] if verification_id else None,
                                               "verification_id": verification_id})
        if self.name == "request_call" and arguments.get("case_id") is None:   # a general request: no case (D-026)
            answer = answer.model_copy(update=CASELESS_CALL)
        if getattr(answer, "deadline_source_label", None):
            answer = answer.model_copy(update={"deadline_source_label": _LABEL[self.language]})
        return ToolResult(structured_content=answer.model_dump(mode="json"))


def build_server(language: str = "es") -> FastMCP:
    """The fake server for one session in `language` (es or pt), as the real one reads session.language."""
    server = FastMCP("nick-of-time-fake-mcp")
    for name, (model_in, model_out) in CUSTOMER_TOOLS.items():
        server.add_tool(FixtureTool(name=name, description=f"{name} — fake fixture (spec 01 §6.3)", language=language,
                                    parameters=model_in.model_json_schema(),
                                    output_schema=model_out.model_json_schema()))
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake MCP server with the 16 customer tools (spec 01 AC-03)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)      # spec 01 §6.3 local port; the compose stub uses 8001
    args = parser.parse_args()
    build_server().run(transport="http", host=args.host, port=args.port, path="/mcp")


if __name__ == "__main__":
    main()
