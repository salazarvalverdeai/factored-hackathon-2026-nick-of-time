"""Spec 01 — shared package skeleton, ids, the customer receipt and the eval schema hooks (AC-01, AC-04)."""
from __future__ import annotations

import ast
import copy
import datetime as dt
import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from typing import get_args

import jsonschema
import pytest
import yaml
from pydantic import BaseModel, ValidationError

import contracts as contracts_pkg
from contracts import tools
from nick_of_time import CONTRACT_VERSION, contracts as c, ids

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = json.loads((ROOT / "contracts/customer_receipt.schema.json").read_text())
EVAL = json.loads((ROOT / "eval/eval_case.schema.json").read_text())
POLICIES = yaml.safe_load((ROOT / "contracts/policies.yaml").read_text())
FORMATS = jsonschema.Draft202012Validator.FORMAT_CHECKER
VALIDATOR = jsonschema.Draft202012Validator(RECEIPT, format_checker=FORMATS)
SAMPLE = RECEIPT["examples"][0]
CASES = [json.loads(line) for line in (ROOT / "eval/examples.jsonl").read_text().splitlines() if line.strip()]
DROP = object()


def test_ac_01_layout_package_and_removed_scaffold_folders():
    assert CONTRACT_VERSION == "1.6.0"
    assert (ROOT / "packages/nick_of_time/contracts.py").is_file() and (ROOT / "packages/nick_of_time/ids.py").is_file()
    assert not [d for d in ("audit", "classifier", "graph", "policy", "tools") if (ROOT / "apps/api" / d).exists()]


def test_ac_01_tool_names_are_re_exported_not_redeclared():
    assert {"ToolError", "ScoreProvider"} <= set(c.TOOL_NAMES)
    for name in c.TOOL_NAMES:
        assert getattr(c, name) is getattr(tools, name), name


def test_ac_01_guard_rejects_a_name_declared_in_tools_and_here(tmp_path, monkeypatch):
    fake = tmp_path / "tools.py"
    fake.write_text("from typing import Literal\nZone = Literal['high']\ntype Mode = Literal['live']\n"
                    "class Money: ...\nfrom typing import TypeAlias\nActionState: TypeAlias = Literal['verified']\n")
    module = types.ModuleType("contracts.tools")
    module.__file__ = str(fake)
    exec(fake.read_text(), module.__dict__)
    monkeypatch.setitem(sys.modules, "contracts.tools", module)
    monkeypatch.setattr(contracts_pkg, "tools", module)
    spec = importlib.util.spec_from_file_location("nick_of_time._contracts_probe", c.__file__)
    with pytest.raises(ImportError, match=r"\['ActionState', 'Mode', 'Money', 'Zone'\]"):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))   # a fresh copy; the real module is untouched


def test_ac_01_guard_scan_runs_without_ast_type_alias(monkeypatch):
    """Python 3.11 (Platform's default runtime) has no ast.TypeAlias; the scan must not need it."""
    monkeypatch.delattr(ast, "TypeAlias")
    assert c._defined_names(Path(tools.__file__)) == set(c.TOOL_NAMES)


@pytest.mark.parametrize("kind", list(ids.PREFIX))
def test_ac_01_ids_have_the_contract_prefix_and_shape(kind):
    made = {ids.new_id(kind) for _ in range(200)}
    assert all(i.startswith(ids.PREFIX[kind]) and ids.is_valid(kind, i) for i in made)
    assert len(made) > 150                      # random, not a counter (case ids have 10^6 values)
    assert not ids.is_valid(kind, ids.PREFIX[kind] + "x")


def test_ac_01_gold_id_shapes():
    """Gold ids [data]: customers CLI- + 12 (3,077 of 150,000 have no digit), transactions TRX- + 20, products PRD- + 12."""
    patterns = ids.GOLD_PATTERN
    assert re.fullmatch(patterns["customer"], "CLI-EXAMPLE00001") and re.fullmatch(patterns["customer"], "CLI-ABCDEFGHIJKL")
    assert not any(re.fullmatch(patterns["customer"], bad) for bad in ("CLI-EXAMPLE0001", "CLI-example00001", "K-104233",
                                                                       "CLI-EXAMPLE000012"))
    assert re.fullmatch(patterns["transaction"], "TRX-SYN00000000000000001")
    assert not re.fullmatch(patterns["transaction"], "SYN-0001")


def test_ac_01_vocabularies_match_policies_and_the_eval_schema():
    assert list(get_args(c.Zone)) == list(POLICIES["zones"])
    assert list(get_args(c.QueueStatus)) == POLICIES["case_queue"]["states"]
    seeded_case = EVAL["properties"]["initial_state"]["properties"]["case"]["properties"]
    assert seeded_case["zone"]["enum"] == list(get_args(c.Zone))
    assert seeded_case["queue_status"]["enum"] == list(get_args(c.QueueStatus))
    expected = EVAL["properties"]["expected"]["properties"]
    assert expected["decision"]["enum"] == list(get_args(c.Decision))
    assert expected["intent"]["enum"] == list(get_args(c.Intent))
    assert expected["receipt"]["required"] == ["issued", "has_deadline"]
    assert "customer_returns" in EVAL["properties"]["type"]["enum"]
    assert EVAL["properties"]["initial_state"]["properties"]["case_id"]["pattern"] == ids.PATTERN["case"]
    assert all("receipt" in case["expected"] for case in CASES)
    assert any(case["type"] == "customer_returns" and case["initial_state"].get("case") for case in CASES)


def test_ac_01_eval_case_id_and_its_fixture_come_together():
    validator = jsonschema.Draft202012Validator(EVAL, format_checker=FORMATS)
    returning = next(case for case in CASES if case["type"] == "customer_returns")
    assert not list(validator.iter_errors(returning))
    for key in ("case", "case_id"):
        broken = copy.deepcopy(returning)
        del broken["initial_state"][key]
        assert list(validator.iter_errors(broken)), key


def _resolve(node: dict, root: dict) -> dict:
    """Follow a local $ref and unwrap Optional (anyOf with null); object-level anyOf rules stay as they are."""
    if "$ref" in node:
        node = root["$defs"][node["$ref"].rsplit("/", 1)[-1]]
    branches = [b for b in node.get("anyOf", []) if b.get("type") != "null"]
    return _resolve(branches[0], root) if "properties" not in node and len(branches) == 1 else node


def _shape(node: dict, root: dict, path: str = "$") -> dict[str, object]:
    """`required` and `additionalProperties` of every object, enum, pattern and format of every leaf, by path."""
    node = _resolve(node, root)
    if "properties" in node:
        out: dict[str, object] = {path: (sorted(node.get("required", [])), node.get("additionalProperties"))}
        for name, sub in node["properties"].items():
            out |= _shape(sub, root, f"{path}.{name}")
        return out
    if "items" in node:
        return _shape(node["items"], root, path + "[]")
    enum = node.get("enum", [node["const"]] if "const" in node else [])
    return {path: (sorted(e for e in enum if e is not None), node.get("pattern"), node.get("format"))}


def test_ac_01_receipt_schema_and_model_agree_at_every_level():
    jsonschema.Draft202012Validator.check_schema(RECEIPT)
    assert "date-time" in FORMATS.checkers and "date" in FORMATS.checkers   # rfc3339-validator is installed
    model = c.CustomerReceipt.model_json_schema()
    assert _shape(RECEIPT, RECEIPT) == _shape(model, model)       # the model takes its patterns from nick_of_time.ids


def _bare_datetimes(annotation) -> bool:
    if annotation is dt.datetime:
        return True
    return any(_bare_datetimes(arg) for arg in get_args(annotation)) or any(
        _bare_datetimes(meta) for meta in getattr(annotation, "__metadata__", ()))


def test_ac_01_every_timestamp_carries_its_utc_offset():
    models = [m for m in vars(c).values() if isinstance(m, type) and issubclass(m, BaseModel) and m.__module__ == c.__name__]
    assert len(models) > 20
    naive = [f"{m.__name__}.{name}" for m in models for name, field in m.model_fields.items()
             if _bare_datetimes(field.annotation)]
    assert not naive, f"use AwareDatetime: {naive}"


def _variant(path: str, value) -> dict:
    """The sample receipt with `path` (dot-separated, list indexes allowed) set to `value`, or removed with DROP."""
    data = copy.deepcopy(SAMPLE)
    *parents, last = [int(k) if k.isdigit() else k for k in path.split(".")]
    node = data
    for key in parents:
        node = node[key]
    if value is DROP:
        del node[last]
    else:
        node[last] = value
    return data


DISPLAY = {"amount": "22500", "currency": "MXN", "rate": "18.0", "rate_source": "fixture", "as_of": "2026-06-01"}
NEGATIVE = {
    "deadline without source_url": _variant("deadline.source_url", DROP),
    "deadline without verified_on": _variant("deadline.verified_on", DROP),
    "deadline with both dates null": _variant("deadline.credit_deadline", None),
    "credit_deadline is not a date": _variant("deadline.credit_deadline", "pronto"),
    "lower-case country": _variant("deadline.country", "mx"),
    "unknown product": _variant("deadline.product", "prepaid"),
    "verified_on is not a date": _variant("deadline.verified_on", "soon"),
    "empty source_url": _variant("deadline.source_url", ""),
    "plain http source_url": _variant("deadline.source_url", "http://example.org"),
    "extra key in deadline": _variant("deadline.score", 72),
    "missing deadline key": _variant("deadline", DROP),
    "fact without source_id": _variant("verified_facts.0.source_id", DROP),
    "empty source_id": _variant("verified_facts.0.source_id", ""),
    "customer id as a source": _variant("verified_facts.0.source_id", "CLI-EXAMPLE00001"),
    "short case id as a source": _variant("verified_facts.2.source_id", "K-1"),
    "non-hex verification id as a source": _variant("verified_facts.1.source_id", "V-x"),
    "empty fact": _variant("verified_facts.0.fact", ""),
    "verified action without verification_id": _variant("actions.0.verification_id", None),
    "verified action without the verification_id key": _variant("actions.0.verification_id", DROP),
    "bad verification id": _variant("actions.0.verification_id", "V-1"),
    "verified_at is not a date-time": _variant("actions.0.verified_at", "yesterday"),
    "issued_at is not a date-time": _variant("issued_at", "soon"),
    "naive issued_at": _variant("issued_at", "2026-06-01T15:04:12"),
    "verified action without verified_at": _variant("actions.0.verified_at", DROP),
    "unknown action state": _variant("actions.0.state", "done"),
    "bad action id": _variant("actions.0.action_id", "A-1"),
    "bad receipt id": _variant("receipt_id", "RC-1"),
    "bad case id": _variant("case_id", "K-12"),
    "language en": _variant("language", "en"),
    "product_last4 with 5 digits": _variant("product_last4", "44170"),
    "case_url that is not https": _variant("case_url", "javascript:alert(1)"),
    "extra score key": _variant("score", 72),
    "next_steps null": _variant("next_steps", None),
    "original amount not a decimal": _variant("amount.original.amount", "1,250.00"),
    "lower-case currency": _variant("amount.original.currency", "usd"),
    "display without rate_source": _variant("amount.display", {k: v for k, v in DISPLAY.items() if k != "rate_source"}),
}
NEGATIVE["deadline with both dates null"]["deadline"]["ruling_deadline"] = None

POSITIVE = {
    "sample": copy.deepcopy(SAMPLE),
    "no verified clock entry": _variant("deadline", None),
    "ruling deadline only": {**SAMPLE, "deadline": {**SAMPLE["deadline"], "credit_deadline": None,
                                                    "ruling_deadline": "2026-07-16"}},
    "optional fields absent": {k: v for k, v in SAMPLE.items() if k in RECEIPT["required"]},
    "optional fields null": {**SAMPLE, "mode": None, "product_last4": None, "amount": None, "case_url": None},
    "display amount absent": _variant("amount.display", DROP),
    "display amount with a rate": _variant("amount.display", DISPLAY),
    "unconfirmed action": _variant("actions.0", {"label": "Bloqueo sin confirmar", "action_id": "A-3E9F20B7C164",
                                                 "state": "not_confirmed", "verification_id": None,
                                                 "verified_at": None}),
    "action in progress": _variant("actions.0", {"label": "Bloqueando", "action_id": "A-3E9F20B7C164",
                                                 "state": "in_progress"}),
}


@pytest.mark.parametrize("data", NEGATIVE.values(), ids=NEGATIVE.keys())
def test_ac_01_schema_and_model_reject_the_same_bad_receipts(data):
    assert list(VALIDATOR.iter_errors(data))
    with pytest.raises(ValidationError):
        c.CustomerReceipt.model_validate(data)


@pytest.mark.parametrize("data", POSITIVE.values(), ids=POSITIVE.keys())
def test_ac_01_schema_and_model_accept_the_same_good_receipts(data):
    assert not list(VALIDATOR.iter_errors(data))
    dumped = c.CustomerReceipt.model_validate(data).model_dump(mode="json")
    assert not list(VALIDATOR.iter_errors(dumped))


def _keys(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    return {k for v in node for k in _keys(v)} if isinstance(node, list) else set()


def test_ac_01_receipt_never_carries_internals():
    never_send = POLICIES["notifications"]["never_send"]
    assert set(never_send) == {"transcript", "score", "policy_ids"}
    assert not {*never_send, "policy_id"} & _keys(RECEIPT["properties"])
    assert not re.search(r"POL-|G-[A-Z]+-\d|score|puntaje", json.dumps(SAMPLE, ensure_ascii=False))


def test_ac_04_sample_receipt_validates_against_the_schema():
    sample = c.sample_receipt()
    assert not list(VALIDATOR.iter_errors(sample.model_dump(mode="json")))
    assert sample.language == "es" and sample.mode == "replay"
    assert sample.issued_at.date() == dt.date(2026, 6, 1)                       # DEMO_TODAY (ADR 0020)
    assert sample.deadline and sample.deadline.credit_deadline == dt.date(2026, 6, 3)   # business day 2 (spec 02 §4.3)
    assert sample.amount and sample.amount.original.currency == "USD" and sample.amount.display is None
    assert all(a.state == "verified" and a.verification_id and a.verified_at for a in sample.actions)
    facts = {f.source_id.split("-")[0]: f for f in sample.verified_facts}
    assert facts["V"].source_id == sample.actions[0].verification_id and facts["K"].source_id == sample.case_id
    charged = dt.date.fromisoformat(re.search(r"\d{4}-\d{2}-\d{2}", facts["TRX"].fact).group())
    since_charge = sample.issued_at - dt.datetime.combine(charged, dt.time(), dt.UTC)
    assert dt.timedelta(0) < since_charge <= dt.timedelta(days=90)         # the 90-calendar-day window (spec 02 §4.3, ADR 0023)


NOW = "2026-06-01T15:04:12Z"                    # DEMO_TODAY (ADR 0020)
HANDOFF = {"case_id": "K-104233", "language": "es", "zone": "high", "request": "Cargo no reconocido USD 1,250.00",
           "verified_facts": [{"fact": "Tarjeta bloqueada", "source_id": "V-8B2D41C7E0A9"}],
           "actions": [{"tool": "block_card", "action_id": "A-3E9F20B7C164", "result": "Blocked", "verified": True,
                        "verification_id": "V-8B2D41C7E0A9"}],
           "evidence": ["TRX-FIXTURE0000000000001"], "open_questions": [],
           "deadline": {"country": "MX", "deadline_source": "Banxico Circular 3/2012", "credit_deadline": "2026-06-03",
                        "source_url": SAMPLE["deadline"]["source_url"], "verified_on": "2026-10-04"}, "trace_id": "run-1", "score": 72}
CHIPS = [{"id": "view_case", "label": "Ver mi caso", "kind": "link", "href": "/case/K-104233"},
         {"id": "send_summary", "label": "Enviarme el comprobante", "kind": "action", "action": {"type": "send_summary"}}]
ACTION = {"tool": "block_card", "action_id": "A-3E9F20B7C164", "state": "verified", "verification_id": "V-8B2D41C7E0A9",
          "read_at": NOW}
PROGRESS = {"step": "block_card", "label": "Bloqueando tu tarjeta…", "state": "verified", "at": NOW}
OPTIONS = [{"id": "TRX-FIXTURE0000000000021", "label": "BRL 380.00 · 2026-05-26"}] * POLICIES["clarify"][
    "max_candidate_transactions"]
USAGE = {"provider": "fake", "model": "fake", "tokens_in": 10, "tokens_out": 5, "latency_ms": 40, "cost_usd": 0.0}


def _turn(**extra) -> dict:
    return {"reply": "Tarjeta bloqueada. Caso abierto.", "language": "es", "decision": "block_and_open_case",
            "zone": "high", "intent": "unrecognized_charge", "intent_confidence": 0.93, "case_id": "K-104233",
            "actions": [ACTION], "suggestions": CHIPS, "progress": [PROGRESS],
            "receipt": c.sample_receipt().model_dump(mode="json"), "mode": "replay", "trace_id": "run-1", **extra}


BAD_TURNS = {
    "link chip without href": _turn(suggestions=[CHIPS[1], {"id": "x", "label": "Ver", "kind": "link"}]),
    "text chip with href": _turn(suggestions=[CHIPS[0], {"id": "x", "label": "Ver", "kind": "text", "href": "/a"}]),
    "href to another host": _turn(suggestions=[CHIPS[1], {**CHIPS[0], "href": "//evil.example"}]),
    "href with a backslash host": _turn(suggestions=[CHIPS[1], {**CHIPS[0], "href": "/\\evil.example"}]),
    "href with a tab": _turn(suggestions=[CHIPS[1], {**CHIPS[0], "href": "/\t/evil.example"}]),
    "href with a newline": _turn(suggestions=[CHIPS[1], {**CHIPS[0], "href": "/\n/evil.example"}]),
    "one chip": _turn(suggestions=CHIPS[:1]),
    "four chips": _turn(suggestions=CHIPS * 2),
    "unknown action state": _turn(actions=[{**ACTION, "state": "done"}], progress=[]),
    "verified without verification_id": _turn(actions=[{**ACTION, "verification_id": None}]),
    "verified without read_at": _turn(actions=[{**ACTION, "read_at": None}]),
    "verified progress without any action": _turn(actions=[]),
    "verified progress for a requested action": _turn(actions=[{**ACTION, "state": "requested"}]),
    "verified progress for another tool": _turn(progress=[{**PROGRESS, "step": "open_case"}]),
    "unknown progress state": _turn(progress=[{**PROGRESS, "state": "done"}]),
    "naive progress time": _turn(progress=[{**PROGRESS, "at": "2026-06-01T15:04:12"}]),
    "bad case id": _turn(case_id="K-1"),
    "intent_confidence above 1": _turn(intent_confidence=1.5),
    "negative intent_confidence": _turn(intent_confidence=-0.1),
    "more options than policies.yaml allows": _turn(options=OPTIONS + OPTIONS[:1]),
    "negative usage tokens": _turn(usage=[{**USAGE, "tokens_in": -1}]),
    "handoff deadline is not a date": _turn(handoff={**HANDOFF, "deadline": {**HANDOFF["deadline"],
                                                                             "credit_deadline": "pronto"}}),
    "handoff action verified without verification_id": _turn(handoff={
        **HANDOFF, "actions": [{k: v for k, v in HANDOFF["actions"][0].items() if k != "verification_id"}]}),
    "handoff action with a bad verification_id": _turn(handoff={
        **HANDOFF, "actions": [{**HANDOFF["actions"][0], "verification_id": "V-1"}]}),
    "handoff deadline with an http source_url": _turn(handoff={
        **HANDOFF, "deadline": {**HANDOFF["deadline"], "source_url": "http://example.org"}}),
    "handoff deadline verified_on is not a date": _turn(handoff={
        **HANDOFF, "deadline": {**HANDOFF["deadline"], "verified_on": "soon"}}),
    "handoff deadline without source_url": _turn(handoff={
        **HANDOFF, "deadline": {k: v for k, v in HANDOFF["deadline"].items() if k != "source_url"}}),
    "handoff deadline without verified_on": _turn(handoff={
        **HANDOFF, "deadline": {k: v for k, v in HANDOFF["deadline"].items() if k != "verified_on"}}),
    "negative usage cost": _turn(usage=[{**USAGE, "cost_usd": -0.01}]),
    "negative usage tokens_out": _turn(usage=[{**USAGE, "tokens_out": -1}]),
    "negative trace ms": _turn(trace=[{"node": "classify", "status": "ok", "ms": -1}]),
    "option id that is not a transaction id": _turn(options=[{**OPTIONS[0], "id": "SYN-0001"}]),
    "handoff that is not a card": _turn(handoff={"case_id": "K-104233"}),
    "customer_id from the client": _turn(customer_id="CLI-EXAMPLE00001"),
}


def test_ac_01_turn_result_follows_the_graph_contract():
    turn = c.TurnResult.model_validate(_turn(handoff=HANDOFF, options=OPTIONS, usage=[USAGE]))
    assert c.TurnResult.model_validate_json(turn.model_dump_json()) == turn
    assert c.MAX_OPTIONS == POLICIES["clarify"]["max_candidate_transactions"]
    c.TurnResult.model_validate(_turn(actions=[], progress=[{**PROGRESS, "state": "in_progress"}]))
    unverified = {**HANDOFF["actions"][0], "verified": False}
    del unverified["verification_id"]
    clock_unknown = {"country": "UY", "deadline_source": "POL-CLOCK-UNKNOWN"}      # no verified legal date
    c.TurnResult.model_validate(_turn(handoff={**HANDOFF, "actions": [unverified], "deadline": clock_unknown}))


def test_ac_01_handoff_patterns_come_from_ids():
    handoff = json.loads((ROOT / "contracts/handoff.schema.json").read_text())
    action = handoff["properties"]["actions"]["items"]["then"]["properties"]["verification_id"]["pattern"]
    assert action == ids.PATTERN["verification"]
    assert handoff["properties"]["deadline"]["properties"]["source_url"]["pattern"] == c.HTTPS_URL


@pytest.mark.parametrize("data", BAD_TURNS.values(), ids=BAD_TURNS.keys())
def test_ac_01_turn_result_rejects_off_contract_output(data):
    with pytest.raises(ValidationError):
        c.TurnResult.model_validate(data)


FINAL = {"run_id": "EV-0001:S1:3", "arm": "S1", "decision": "block_and_open_case", "case_open": True,
         "handoff_emitted": False, "receipt_issued": True, "receipt_has_deadline": True,
         "other_customer_data_exposed": False, "action_states": {"block_card": "verified"},
         "totals": {"latency_ms": 2140, "tokens_in": 1830, "tokens_out": 210, "cost_usd": 0.0031},
         "run_meta": {"git_sha": "abc123", "policies_version": 2, "provider": "fake"}}
BAD_FINALS = {
    "live mode": {"mode": "live"},
    "negative total cost": {"totals": {**FINAL["totals"], "cost_usd": -0.01}},
    "turn 0": {"turns": [{**FINAL["totals"], "turn": 0}]},
    "bad transaction id": {"transaction_id": "TRX-1"},
    "bad product id": {"product_id": "PRD-1"},
    "bad candidate transaction id": {"candidate_transaction_ids": ["SYN-0001"]},
    "negative turn latency": {"turns": [{**FINAL["totals"], "turn": 1, "latency_ms": -1}]},
}


def test_ac_01_final_state_is_always_replay():
    assert c.FinalState.model_validate({**FINAL, "turns": [{**FINAL["totals"], "turn": 1}]}).mode == "replay"


@pytest.mark.parametrize("bad", BAD_FINALS.values(), ids=BAD_FINALS.keys())
def test_ac_01_final_state_rejects_off_contract_runs(bad):
    with pytest.raises(ValidationError):
        c.FinalState.model_validate({**FINAL, **bad})


CASE = {"case_id": "K-104233", "customer_id": "CLI-EXAMPLE00001", "country": "MX", "zone": "high",
        "queue_status": "verification", "credit_deadline": "2026-06-03", "created_at": NOW, "priority": "high",
        "tags": ["mx_debit"], "sla_due_at": NOW, "status_label": "En verificación", "mode": "replay",
        "product_last4": "4417", "deadline_source": SAMPLE["deadline"]["deadline_source"],
        "deadline_source_url": SAMPLE["deadline"]["source_url"], "deadline_verified_on": "2026-10-04",
        "transaction": {"transaction_id": "TRX-FIXTURE0000000000001", "amount": 1250.0, "currency": "USD",
                        "date": "2026-05-31"},
        "receipt": c.sample_receipt().model_dump(mode="json"),
        "timeline": [{"event_id": "E-0A1B2C3D4E5F", "type": "case_opened", "label": "Caso abierto", "created_at": NOW}],
        "notifications": [{"notification_id": "N-0A1B2C3D4E5F", "channel": "log", "delivery_status": "delivered",
                           "created_at": NOW}]}


def test_ac_01_customer_projections_never_carry_internals():
    """D-013: customer routes emit CustomerTurn and CustomerCaseView only (notifications.never_send)."""
    denial = {"policy_id": "POL-DEFAULT-DENY", "guardrail_id": "G-POL-01", "detail": "Solicitud rechazada."}
    turn = c.TurnResult.model_validate(_turn(handoff=HANDOFF, denials=[denial]))
    assert "score" in turn.model_dump_json() and "POL-" in turn.model_dump_json()   # the internal output has both
    customer_turn = json.loads(turn.for_customer().model_dump_json())
    assert not {"handoff", "usage", "trace", "zone"} & set(customer_turn)
    assert customer_turn["denials"] == [{"guardrail_id": "G-POL-01", "detail": "Solicitud rechazada."}]
    case = c.CaseView.model_validate(CASE).for_customer().model_dump(mode="json")
    assert not {"zone", "priority", "tags", "sla_due_at", "customer_id"} & set(case)
    assert case["deadline_source_url"] == SAMPLE["deadline"]["source_url"]       # a legal date keeps its source
    for payload in (customer_turn, case):                                        # G- guardrail ids may stay (§6.4)
        assert not re.search(r"score|(?<!G-)POL-", json.dumps(payload))


BAD_VIEWS = [
    (c.CaseView, {k: v for k, v in CASE.items() if k != "transaction"}),
    (c.CaseView, {**CASE, "related_case_id": "K-1"}),
    (c.CaseView, {**CASE, "product_last4": "44170"}),
    (c.CaseView, {**CASE, "timeline": [{**CASE["timeline"][0], "event_id": "E-1"}]}),
    (c.CaseView, {**CASE, "notifications": [{**CASE["notifications"][0], "notification_id": "N-1"}]}),
    (c.CaseView, {**CASE, "notifications": [{**CASE["notifications"][0], "delivery_status": "read"}]}),
    (c.CaseView, {**CASE, "priority": "urgent"}),
    (c.CaseView, {**CASE, "created_at": "2026-06-01T15:04:12"}),
    (c.CaseView, {k: v for k, v in CASE.items() if k != "deadline_source_url"}),
    (c.CaseView, {**CASE, "deadline_source_url": "http://example.org"}),
    (c.CaseView, {k: v for k, v in CASE.items() if k != "deadline_source"}),
    (c.CaseView, {k: v for k, v in CASE.items() if k != "deadline_verified_on"}),
    (c.CaseView, {**{k: v for k, v in CASE.items() if k not in ("deadline_source_url", "credit_deadline")},
                  "ruling_deadline": "2026-07-16"}),
    (c.CaseView, {**CASE, "transaction": {**CASE["transaction"], "transaction_id": "SYN-0001"}}),
    (c.ProductView, {"product_id": "PRD-1", "type": "debit", "last4": "4417", "status": "Blocked", "read_at": NOW}),
    (c.CustomerCaseSummary, {"case_id": "K-104233", "status_label": "x", "updated_at": NOW, "related_case_id": "K-1"}),
    (c.CustomerCaseSummary, {"case_id": "K-104233", "status_label": "x", "updated_at": NOW, "product_last4": "44170"}),
    (c.ProductView, {"product_id": "PRD-FIXTURE00001", "type": "debit", "last4": "44", "status": "Blocked",
                     "read_at": NOW}),
    (c.ProductView, {"product_id": "PRD-FIXTURE00001", "type": "debit", "last4": "4417", "status": "Blocked",
                     "verification_id": "V-1", "read_at": NOW}),
]


def test_ac_01_view_models_accept_the_contract_shape():
    view = c.CaseView.model_validate(CASE)
    assert view.channels.telegram is False and view.transaction.synthetic is False
    c.CustomerCaseSummary.model_validate({"case_id": "K-104233", "status_label": "En verificación", "updated_at": NOW})
    c.ProductView.model_validate({"product_id": "PRD-FIXTURE00001", "type": "debit", "last4": "4417",
                                  "status": "Blocked", "verification_id": "V-8B2D41C7E0A9", "read_at": NOW})


@pytest.mark.parametrize(("model", "data"), BAD_VIEWS)
def test_ac_01_view_models_reject_off_contract_data(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)
