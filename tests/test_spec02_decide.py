"""Spec 02 T2 — decide() and check(): every row of §4.1, the approval modes of §4.2 and their boundaries."""
from __future__ import annotations

import copy
import itertools
import json
import math
import unicodedata
from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from nick_of_time.policy import Allow, DecisionInput, Deny, Policies, PolicyDecision, PolicyEngine
from nick_of_time.policy.engine import HandoffReason
from nick_of_time.policy.model import POLICIES_PATH

ENGINE = PolicyEngine.load()
RAW = yaml.safe_load(POLICIES_PATH.read_text())
ROOT = Path(__file__).resolve().parents[1]
ZONES = ["high", "medium", "human"]
SCORE_OF = {"high": 72.0, "medium": 40.0, "human": 10.0}
MONEY = ["block_card", "unblock_card", "provisional_credit"]
COUNTRIES = ["MX", "CO", "AR", "BR", "PE", "CL"]
GATED = {"MX", "CO", "AR", "BR"}                     # amount_gate.by_country; PE and CL have no tier [assumption]
FLAGS = ["dispute_detected", "injection_flagged", "cross_customer", "supervised_mode"]
BASE = {"session_state": "verified", "intent": "unrecognized_charge", "intent_confidence": 0.93, "candidates": 1,
        "score": 72.0, "score_source": "dataset", "amount": 1250.0, "currency": "USD", "country": "MX",
        "product_type": "debit", **dict.fromkeys(FLAGS, False)}    # EV-0001: verified, MX debit, one candidate, high


def turn(**overrides) -> DecisionInput:
    return DecisionInput(**{**BASE, **overrides})


def supervised_by_file() -> PolicyEngine:
    raw = copy.deepcopy(RAW)
    raw["approval"]["supervised_mode"] = True
    return PolicyEngine(Policies.model_validate(raw))


def row(name, overrides, decision, rules, guards=(), zone=None, allowed=(), reason=None, queue=None, call=None):
    return pytest.param(overrides, dict(decision=decision, zone=zone, allowed_actions=list(allowed),
                                        handoff_reason=reason, request_call=call, queue_status_after=queue,
                                        rule_ids=rules, guardrail_ids=list(guards)), id=name)


OPEN, BLOCK, HUMAN = ["open_case"], ["open_case", "block_card"], dict(zone="human", allowed=["open_case"], queue="review")
ROWS = [
    row("1", dict(session_state="expired", intent="human_request"), "reauthenticate", ["POL-SESSION"], ["G-SES-01"]),
    row("2", dict(injection_flagged=True), "deny", ["POL-INJECTION"], ["G-IN-01"]),
    row("3", dict(cross_customer=True), "deny", ["POL-CROSS-CUSTOMER"], ["G-SES-02"]),
    row("3a", dict(intent="human_request"), "connect_person", ["POL-HUMAN-REQUEST"], call="active_or_general"),
    row("3a-charge-high", dict(intent="human_request", dispute_detected=True), "block_and_open_case",
        ["POL-HUMAN-REQUEST", "POL-ZONE-HIGH", "POL-TICKET-ALWAYS"], zone="high", allowed=BLOCK, queue="verification",
        call="opened_case"),
    row("3a-charge-over-gate", dict(intent="human_request", dispute_detected=True, amount=5000.01), "connect_person",
        ["POL-HUMAN-REQUEST", "POL-ZONE-HIGH", "POL-AMOUNT-GATE", "POL-TICKET-ALWAYS"], ["G-TOOL-02"], zone="high",
        allowed=OPEN, reason="amount_over_case_gate", queue="review", call="opened_case"),
    row("3a-charge-supervised", dict(intent="human_request", dispute_detected=True, supervised_mode=True),
        "connect_person", ["POL-HUMAN-REQUEST", "POL-ZONE-HIGH", "POL-SUPERVISED", "POL-TICKET-ALWAYS"], ["G-TOOL-02"],
        zone="high", allowed=OPEN, reason="supervised_mode", queue="review", call="opened_case"),
    row("3a-charge-medium", dict(intent="human_request", dispute_detected=True, score=40.0), "connect_person",
        ["POL-HUMAN-REQUEST", "POL-ZONE-MEDIUM", "POL-TICKET-ALWAYS"], zone="medium", allowed=OPEN,
        reason="zone_medium", queue="review", call="opened_case"),
    row("3a-charge-human", dict(intent="human_request", dispute_detected=True, score=10.0), "connect_person",
        ["POL-HUMAN-REQUEST", "POL-ZONE-HUMAN", "POL-TICKET-ALWAYS"], reason="zone_human", call="opened_case", **HUMAN),
    row("3a-charge-unclear", dict(intent="human_request", dispute_detected=True, candidates=2), "connect_person",
        ["POL-HUMAN-REQUEST"], call="active_or_general"),
    row("3a-charge-not-found", dict(intent="human_request", dispute_detected=True, candidates=0), "connect_person",
        ["POL-HUMAN-REQUEST"], call="active_or_general"),
    row("3a-charge-not-card", dict(intent="human_request", dispute_detected=True, product_type="Cuenta Ahorro"),
        "connect_person", ["POL-HUMAN-REQUEST"], call="active_or_general"),
    row("3a-charge-rejected", dict(intent="human_request", dispute_detected=True, score=40.0, customer_confirmed=False),
        "connect_person", ["POL-HUMAN-REQUEST"], call="active_or_general"),
    row("3b", dict(intent="status_inquiry"), "answer_status", ["POL-STATUS"]),
    row("3b-no-case", dict(intent="status_inquiry", active_case=False), "answer_status", ["POL-STATUS"]),
    row("3b-charge", dict(intent="status_inquiry", dispute_detected=True), "answer_status", ["POL-STATUS"]),
    row("3b-charge-active", dict(intent="status_inquiry", dispute_detected=True, active_case=True), "answer_status",
        ["POL-STATUS"]),
    row("3b-charge-no-case", dict(intent="status_inquiry", dispute_detected=True, active_case=False),
        "block_and_open_case", ["POL-STATUS", "POL-ZONE-HIGH", "POL-TICKET-ALWAYS"], zone="high", allowed=BLOCK,
        queue="verification"),
    row("3b-charge-no-case-not-card", dict(intent="status_inquiry", dispute_detected=True, active_case=False,
                                           product_type="Cuenta Ahorro"), "deny", ["POL-STATUS", "POL-OUT-OF-SCOPE"],
        ["G-IN-04"]),
    row("4-intent", dict(intent="out_of_scope"), "deny", ["POL-OUT-OF-SCOPE"], ["G-IN-04"]),
    row("4-intent-at-tau", dict(intent="out_of_scope", intent_confidence=0.80), "deny", ["POL-OUT-OF-SCOPE"],
        ["G-IN-04"]),
    row("4-intent-unsure", dict(intent="out_of_scope", intent_confidence=0.79), "ask", ["POL-CLARIFY"], ["G-IN-03"]),
    row("4-product", dict(product_type="Cuenta Ahorro"), "deny", ["POL-OUT-OF-SCOPE"], ["G-IN-04"]),
    row("5", dict(intent_confidence=0.5), "ask", ["POL-CLARIFY"], ["G-IN-03"]),
    row("5b", dict(candidates=2, clarification_turns=2), "handoff", ["POL-CLARIFY-EXHAUSTED"], ["G-IN-03"],
        reason="clarification_exhausted", call="general"),
    row("6-null", dict(score=None), "handoff", ["POL-SCORE-NULL", "POL-TICKET-ALWAYS"], reason="zone_human", **HUMAN),
    row("6-llm", dict(score_source="llm"), "handoff", ["POL-SCORE-LLM", "POL-TICKET-ALWAYS"], reason="zone_human",
        **HUMAN),
    row("6-source", dict(score_source="customer"), "handoff", ["POL-SCORE-SOURCE", "POL-TICKET-ALWAYS"],
        reason="zone_human", **HUMAN),
    row("6-synthetic", dict(score_source="synthetic"), "block_and_open_case", ["POL-ZONE-HIGH", "POL-TICKET-ALWAYS"],
        zone="high", allowed=BLOCK, queue="verification"),
    row("7", {}, "block_and_open_case", ["POL-ZONE-HIGH", "POL-TICKET-ALWAYS"], zone="high", allowed=BLOCK,
        queue="verification"),
    row("7-over-gate", dict(amount=5000.01), "handoff", ["POL-ZONE-HIGH", "POL-AMOUNT-GATE", "POL-TICKET-ALWAYS"],
        ["G-TOOL-02"], zone="high", allowed=OPEN, reason="amount_over_case_gate", queue="review"),
    row("7-no-gate", dict(country="PE", currency="PEN"), "handoff",
        ["POL-ZONE-HIGH", "POL-AMOUNT-UNKNOWN", "POL-TICKET-ALWAYS"], ["G-TOOL-02"], zone="high", allowed=OPEN,
        reason="amount_over_case_gate", queue="review"),
    row("7-supervised", dict(supervised_mode=True), "handoff", ["POL-ZONE-HIGH", "POL-SUPERVISED", "POL-TICKET-ALWAYS"],
        ["G-TOOL-02"], zone="high", allowed=OPEN, reason="supervised_mode", queue="review"),
    row("7-over-gate-supervised", dict(amount=5000.01, supervised_mode=True), "handoff",
        ["POL-ZONE-HIGH", "POL-AMOUNT-GATE", "POL-SUPERVISED", "POL-TICKET-ALWAYS"], ["G-TOOL-02"], zone="high",
        allowed=OPEN, reason="amount_over_case_gate", queue="review"),
    row("8", dict(score=40.0), "confirm", ["POL-ZONE-MEDIUM"], zone="medium"),
    row("8-confirmed", dict(score=40.0, customer_confirmed=True), "handoff", ["POL-ZONE-MEDIUM", "POL-TICKET-ALWAYS"],
        zone="medium", allowed=OPEN, reason="zone_medium", queue="review"),
    row("8-declined", dict(score=40.0, customer_confirmed=False), "ask", ["POL-ZONE-MEDIUM", "POL-CLARIFY"],
        ["G-IN-03"]),
    row("9", dict(score=10.0), "handoff", ["POL-ZONE-HUMAN", "POL-TICKET-ALWAYS"], reason="zone_human", **HUMAN),
]


@pytest.mark.parametrize("overrides, expected", ROWS)
def test_ac_12_every_rule_row_decides_and_cites_its_ids_and_version(overrides, expected):
    d = ENGINE.decide(turn(**overrides))
    assert d.model_dump(include=set(expected)) == expected
    assert d.policies_version == 2 and set(d.rule_ids) <= set(RAW["rules"]) and bool(d.approval_modes) == bool(d.zone)


@pytest.mark.parametrize("overrides, expected", ROWS)
def test_ac_05_decide_and_the_tools_re_check_agree_on_what_runs(overrides, expected):
    t, d = turn(**overrides), ENGINE.decide(turn(**overrides))
    checked = {action for action in RAW["approval"]["per_action"] if d.zone and isinstance(ENGINE.check(
        action, d.zone, amount=t.amount, currency=t.currency, country=t.country, supervised_mode=t.supervised_mode), Allow)}
    assert not d.allowed_actions or set(d.allowed_actions) == checked


PATHS = [dict(), dict(intent="human_request", dispute_detected=True),
         dict(intent="status_inquiry", dispute_detected=True, active_case=False)]


def test_ac_12_every_handoff_and_every_case_left_in_review_carries_a_reason():
    """D-024 D3 and D-020: a reason ⇔ a handoff or a case left in review, over the dispute path, a call request and a
    status question that report a charge, zones, sources, amounts, countries, supervised mode and confirmation."""
    for path, score, source, amount, country, supervised, confirmed, candidates, turns in itertools.product(
            PATHS, [72.0, 40.0, 10.0, None], ["dataset", "llm", "customer"], [10.0, 5000.01, None], ["MX", "PE"],
            [False, True], [None, True, False], [0, 1, 2], [0, 2]):
        d = ENGINE.decide(turn(score=score, score_source=source, amount=amount, country=country, candidates=candidates,
                               supervised_mode=supervised, customer_confirmed=confirmed, clarification_turns=turns,
                               **path))
        assert (d.handoff_reason is not None) == (d.decision == "handoff" or d.queue_status_after == "review"), d


def test_ac_12_handoff_reasons_are_the_schema_vocabulary():
    schema = json.loads((ROOT / "contracts/handoff.schema.json").read_text())
    assert list(get_args(HandoffReason)) == schema["properties"]["handoff_reason"]["enum"] == RAW["handoff"]["triggers"]


@pytest.mark.parametrize("path, value", [("rules", {k: v for k, v in RAW["rules"].items() if k != "POL-SCORE-NULL"}),
                                         ("handoff", {**RAW["handoff"], "triggers": ["zone_human", "tool_failure"]})])
def test_ac_12_the_engine_refuses_to_start_without_an_id_or_reason_it_emits(path, value):
    with pytest.raises(ValueError, match="lacks"):
        PolicyEngine(Policies.model_validate({**RAW, path: value}))


@pytest.mark.parametrize("winner, overrides", [
    ("POL-SESSION", dict(session_state="unverified", injection_flagged=True, cross_customer=True, intent="human_request")),
    ("POL-INJECTION", dict(injection_flagged=True, cross_customer=True, intent="human_request")),
    ("POL-CROSS-CUSTOMER", dict(cross_customer=True, intent="human_request")),
    ("POL-HUMAN-REQUEST", dict(intent="human_request", intent_confidence=0.1, product_type="Prestamo")),
    ("POL-STATUS", dict(intent="status_inquiry", intent_confidence=0.1, product_type="Prestamo")),
    ("POL-OUT-OF-SCOPE", dict(product_type="Prestamo", intent_confidence=0.1, score=None)),
    ("POL-CLARIFY", dict(candidates=3, score=None, supervised_mode=True))])
def test_ac_12_the_first_terminal_rule_wins(winner, overrides):
    """FR-02: rules run in the §4.1 order and stop at the first terminal one; screen() is rules 1–4 only."""
    assert ENGINE.decide(turn(**overrides)).rule_ids == [winner]
    assert ENGINE.screen(turn(**overrides)) == (None if winner == "POL-CLARIFY" else ENGINE.decide(turn(**overrides)))


@pytest.mark.parametrize("amount, country", [(10.0, "MX"), (5000.01, "MX"), (10.0, "PE")])
@pytest.mark.parametrize("supervised", [False, True])
@pytest.mark.parametrize("score", [72.0, 40.0, 10.0, None])
def test_ac_12_a_call_request_with_a_charge_adds_the_call_and_never_removes_protection(score, supervised, amount,
                                                                                       country):
    """D-020 and D-029: rule 3a is not terminal when the message also reports a charge. The case opened for it gets the
    call and follows its zone like a confirmed dispute: the high zone still blocks, or hands off with a reason."""
    t = turn(intent="human_request", dispute_detected=True, score=score, supervised_mode=supervised, amount=amount,
             country=country)
    d = ENGINE.decide(t)
    plain = ENGINE.decide(turn(score=score, supervised_mode=supervised, amount=amount, country=country,
                               customer_confirmed=True))
    same = {"zone", "approval_modes", "allowed_actions", "handoff_reason", "queue_status_after", "guardrail_ids"}
    assert ENGINE.screen(t) is None and d.request_call == "opened_case"
    assert d.model_dump(include=same) == plain.model_dump(include=same)
    assert d.rule_ids == ["POL-HUMAN-REQUEST", *plain.rule_ids] and d.approval_modes["open_case"] == "auto"
    assert d.decision == ("block_and_open_case" if plain.decision == "block_and_open_case" else "connect_person")


@pytest.mark.parametrize("dispute", [dict(), dict(candidates=2), dict(intent_confidence=0.5), dict(score=40.0),
                                     dict(score=40.0, customer_confirmed=False), dict(score=40.0, customer_confirmed=True),
                                     dict(product_type="Prestamo"), dict(candidates=0, clarification_turns=2),
                                     dict(score=10.0), dict(amount=5000.01)])
def test_ac_12_a_status_question_with_a_charge_and_no_active_case_goes_on_like_a_dispute(dispute):
    """Rule 3b with a charge (D-020): with no active case the turn goes on like a dispute, citing POL-STATUS first;
    with an active case, or when it is not known yet, the status is answered."""
    t = turn(intent="status_inquiry", dispute_detected=True, active_case=False, **dispute)
    d, plain = ENGINE.decide(t), ENGINE.decide(turn(**dispute))
    assert d.rule_ids == ["POL-STATUS", *plain.rule_ids]
    assert d.model_dump(exclude={"rule_ids"}) == plain.model_dump(exclude={"rule_ids"})
    assert ENGINE.screen(t) == (d if "POL-OUT-OF-SCOPE" in d.rule_ids else None)
    for active in (None, True):
        status = ENGINE.decide(turn(intent="status_inquiry", dispute_detected=True, active_case=active, **dispute))
        assert (status.decision, status.rule_ids) == ("answer_status", ["POL-STATUS"])


@pytest.mark.parametrize("switch", [None, 0, 1, "false", "off"])
def test_ac_04_check_refuses_a_supervised_switch_that_is_not_a_bool(switch):
    """A switch read as None (for example a missing console setting) is not "off": check() fails closed, loudly."""
    with pytest.raises(TypeError, match="supervised_mode"):
        ENGINE.check("block_card", "high", supervised_mode=switch, amount=10.0, currency="USD", country="MX")


@pytest.mark.parametrize("field", FLAGS)
def test_ac_05_a_missing_safety_flag_fails_closed(field):
    with pytest.raises(ValidationError):
        DecisionInput(**{k: v for k, v in BASE.items() if k != field})
    with pytest.raises(TypeError):
        ENGINE.check("block_card", "high", amount=10.0, currency="USD", country="MX")


@pytest.mark.parametrize("state", ["expired", "unverified", "none", "", "Verified"])
def test_ac_07_an_unverified_session_reauthenticates_before_any_other_rule(state):
    d = ENGINE.decide(turn(session_state=state, injection_flagged=True, cross_customer=True, intent="human_request",
                           dispute_detected=True, score=None, candidates=0))
    assert (d.decision, d.rule_ids, d.guardrail_ids, d.zone, d.allowed_actions, d.approval_modes, d.request_call) == (
        "reauthenticate", ["POL-SESSION"], ["G-SES-01"], None, [], {}, None)


@pytest.mark.parametrize("product", ["debit", "credit"])
@pytest.mark.parametrize("country", COUNTRIES)
@pytest.mark.parametrize("score, zone", [(100, "high"), (50, "high"), (49.99, "medium"), (49, "medium"),
                                         (30, "medium"), (29.99, "human"), (29, "human"), (0, "human")])
def test_ac_01_the_zone_follows_the_score_band_in_every_country_and_product(score, zone, country, product):
    d = ENGINE.decide(turn(score=score, country=country, product_type=product, amount=10.0))
    gated = country in GATED
    assert (d.zone, d.rule_ids[0]) == (zone, f"POL-ZONE-{zone.upper()}")
    assert (d.decision, d.handoff_reason) == {"high": ("block_and_open_case", None) if gated else
                                              ("handoff", "amount_over_case_gate"),
                                              "medium": ("confirm", None), "human": ("handoff", "zone_human")}[zone]


@pytest.mark.parametrize("label, product", [("Tarjeta Débito", "debit"), ("Tarjeta Crédito", "credit"),
                                            (unicodedata.normalize("NFD", "Tarjeta Débito"), "debit")])
def test_ac_01_gold_card_labels_map_to_the_product(label, product):
    assert turn(product_type=label).product_type == product
    assert ENGINE.decide(turn(product_type=label)) == ENGINE.decide(turn(product_type=product))


@pytest.mark.parametrize("bad", [dict(score=-0.01), dict(score=100.01), dict(score=math.nan), dict(score=72.0, score_source=None),
                                 dict(score_source="LLM"), dict(customer_id="CLI-X"), dict(zone="high"),
                                 dict(country="mx"), dict(country="MEX"), dict(currency="usd"), dict(currency="US"),
                                 dict(candidates=1, product_type=None)])
def test_ac_01_the_zone_comes_only_from_get_fraud_score_never_from_the_text(bad):
    """FR-03 and constitution #3: no score without its tool source, no zone or customer_id, well-formed codes."""
    with pytest.raises(ValidationError):
        turn(**bad)


@pytest.mark.parametrize("candidates", [0, 2])
@pytest.mark.parametrize("product", [None, "Cuenta Ahorro", "debit"])
def test_ac_08_the_product_is_judged_only_once_one_transaction_is_identified(candidates, product):
    """Assumption 4: with 0 or 2 candidates, rule 4's product branch cannot fire; rule 5 asks."""
    assert ENGINE.decide(turn(candidates=candidates, product_type=product)).rule_ids == ["POL-CLARIFY"]


@pytest.mark.parametrize("country", COUNTRIES)
@pytest.mark.parametrize("score, source, ids", [
    (None, "dataset", ["POL-SCORE-NULL"]), (None, None, ["POL-SCORE-NULL"]), (None, "llm", ["POL-SCORE-NULL", "POL-SCORE-LLM"]),
    (100.0, "llm", ["POL-SCORE-LLM"]), (40.0, "llm", ["POL-SCORE-LLM"]), (10.0, "llm", ["POL-SCORE-LLM"]),
    (72.0, "customer", ["POL-SCORE-SOURCE"]), (40.0, "manual", ["POL-SCORE-SOURCE"]),
    (None, "customer", ["POL-SCORE-NULL", "POL-SCORE-SOURCE"])])
def test_ac_02_a_null_llm_or_non_deciding_score_is_zone_human_and_still_opens_a_case(score, source, ids, country):
    d = ENGINE.decide(turn(score=score, score_source=source, country=country))
    assert (d.decision, d.zone, d.handoff_reason, d.queue_status_after) == ("handoff", "human", "zone_human", "review")
    assert d.rule_ids == [*ids, "POL-TICKET-ALWAYS"] and d.allowed_actions == ["open_case"]


@pytest.mark.parametrize("source", ["dataset", "rules", "model", "synthetic"])
def test_ac_02_only_the_deciding_sources_place_a_zone(source):
    """D-027: a live-mode synthetic score decides like the dataset score (labeled [simulated] downstream)."""
    assert ENGINE.decide(turn(score_source=source)).zone == "high"


@pytest.mark.parametrize("amount", [10.0, 1000.01, 5000.01])
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("engine, flag", [(ENGINE, True), (supervised_by_file(), False)], ids=["input", "file"])
def test_ac_04_supervised_mode_makes_every_money_action_human_required(engine, flag, zone, amount):
    """The file's switch cannot be loosened by the input (§5 security)."""
    d = engine.decide(turn(score=SCORE_OF[zone], amount=amount, supervised_mode=flag, customer_confirmed=True))
    assert {a: d.approval_modes[a] for a in MONEY} == dict.fromkeys(MONEY, "human_required")
    assert (d.decision, d.allowed_actions) == ("handoff", ["open_case"])
    checks = [engine.check(a, zone, amount=amount, currency="USD", country="MX", supervised_mode=flag) for a in MONEY]
    assert all(isinstance(c, Deny) for c in checks)
    assert checks[0].policy_id == ("POL-SUPERVISED" if zone == "high" else "POL-DEFAULT-DENY")


@pytest.mark.parametrize("amount", [None, 10.0, 1e9])
@pytest.mark.parametrize("supervised", [False, True])
@pytest.mark.parametrize("zone", ZONES)
def test_ac_15_open_case_stays_auto_under_supervised_mode_and_any_amount(zone, supervised, amount):
    d = ENGINE.decide(turn(score=SCORE_OF[zone], amount=amount, supervised_mode=supervised, customer_confirmed=True))
    assert d.approval_modes["open_case"] == "auto" and "open_case" in d.allowed_actions
    assert "POL-TICKET-ALWAYS" in d.rule_ids
    assert ENGINE.check("open_case", zone, amount=amount, currency="USD", country="MX", supervised_mode=supervised) == \
        Allow(action="open_case", mode="auto", rule_ids=["POL-TICKET-ALWAYS"], policies_version=2)


@pytest.mark.parametrize("action, zone", [
    ("close_case", "high"), ("approve_credit", "high"), ("transfer_funds", "high"), ("", "high"), ("open_case", "low"),
    ("block_card", ""), ("block_card", "medium"), ("block_card", "human"),
    *[(action, zone) for action in ("provisional_credit", "unblock_card") for zone in ZONES]])
def test_ac_05_an_action_no_rule_allows_is_denied_by_default(action, zone):
    assert ENGINE.check(action, zone, amount=10.0, currency="USD", country="MX", supervised_mode=False) == Deny(
        action=action, policy_id="POL-DEFAULT-DENY", guardrail_id="G-POL-01", rule_ids=["POL-DEFAULT-DENY"],
        policies_version=2)


EDGES = {"MX": ("MXN", 18_000, 90_000), "CO": ("COP", 4_000_000, 20_000_000), "AR": ("ARS", 350_000, 1_750_000),
         "BR": ("BRL", 5_500, 27_500)}
TIERS = [  # country, currency, amount, tier: every boundary of amount_gate.by_country, in USD and in local currency
    *[(c, "USD", amount, tier) for c in EDGES for amount, tier in
      ((0, "auto"), (1000, "auto"), (1000.01, "manual_check"), (5000, "manual_check"), (5000.01, "human_required"))],
    *[(c, cur, amount, tier) for c, (cur, low, high) in EDGES.items() for amount, tier in
      ((low, "auto"), (low + 0.01, "manual_check"), (high, "manual_check"), (high + 0.01, "human_required"))]]


@pytest.mark.parametrize("country, currency, amount, tier", TIERS)
def test_ac_06_the_amount_tier_changes_only_the_block_mode_never_the_zone_or_a_deadline(country, currency, amount, tier):
    assert ENGINE.amount_tier(amount, currency, country) == tier
    d = ENGINE.decide(turn(country=country, currency=currency, amount=amount))
    below = ENGINE.decide(turn(amount=10.0))
    assert (d.zone, d.rule_ids[0]) == ("high", "POL-ZONE-HIGH")
    assert {**d.approval_modes, "block_card": None} == {**below.approval_modes, "block_card": None}
    assert d.approval_modes["block_card"] == ("human_required" if tier == "human_required" else "manual_check")
    assert d.decision == ("handoff" if tier == "human_required" else "block_and_open_case")
    assert not [f for model in (PolicyDecision, Allow, Deny) for f in model.model_fields if "deadline" in f]


@pytest.mark.parametrize("country, currency, amount", [
    ("MX", "EUR", 1), ("MX", None, 1), ("MX", "USD", None), ("MX", "USD", -0.01), ("MX", "USD", math.nan),
    ("MX", "USD", math.inf), ("CO", "MXN", 1), ("PE", "PEN", 1), ("CL", "CLP", 1), (None, "USD", 1)])
def test_ac_06_with_no_tier_a_person_decides_citing_pol_amount_unknown(country, currency, amount):
    assert ENGINE.amount_tier(amount, currency, country) == "human_required"
    d = ENGINE.decide(turn(country=country, currency=currency, amount=amount))
    assert (d.decision, d.handoff_reason) == ("handoff", "amount_over_case_gate")
    assert d.rule_ids == ["POL-ZONE-HIGH", "POL-AMOUNT-UNKNOWN", "POL-TICKET-ALWAYS"]
    deny = ENGINE.check("block_card", "high", amount=amount, currency=currency, country=country, supervised_mode=False)
    assert (deny.policy_id, deny.guardrail_id) == ("POL-AMOUNT-UNKNOWN", "G-TOOL-02")


@pytest.mark.parametrize("intent", ["unrecognized_charge", "wrongful_charge"])
@pytest.mark.parametrize("confidence, candidates, asks", [
    (0.0, 1, True), (0.7999, 1, True), (0.80, 1, False), (1.0, 1, False),
    (0.93, 0, True), (0.93, 2, True), (0.93, 3, True), (0.93, 4, True), (0.93, 50, True)])
def test_ac_08_low_confidence_or_not_exactly_one_candidate_asks(intent, confidence, candidates, asks):
    d = ENGINE.decide(turn(intent=intent, intent_confidence=confidence, candidates=candidates))
    assert (d.decision == "ask", d.rule_ids == ["POL-CLARIFY"]) == (asks, asks)
    assert not asks or (d.zone, d.allowed_actions, d.queue_status_after) == (None, [], None)


@pytest.mark.parametrize("turns, decision", [(0, "ask"), (1, "ask"), (2, "handoff"), (3, "handoff")])
@pytest.mark.parametrize("unclear", [dict(intent_confidence=0.5), dict(candidates=0), dict(candidates=2),
                                     dict(score=40.0, customer_confirmed=False),
                                     dict(intent="out_of_scope", intent_confidence=0.5)])
def test_ac_08_after_two_clarification_turns_it_hands_off(unclear, turns, decision):
    """clarification_turns = clarification questions already sent; exhausted → handoff with a general call (D2)."""
    d = ENGINE.decide(turn(clarification_turns=turns, **unclear))
    exhausted = decision == "handoff"
    assert (d.decision, d.allowed_actions, d.queue_status_after) == (decision, [], None)
    assert (d.handoff_reason, d.request_call) == (("clarification_exhausted", "general") if exhausted else (None, None))
    assert d.rule_ids[-1] == ("POL-CLARIFY-EXHAUSTED" if exhausted else "POL-CLARIFY")


@pytest.mark.parametrize("supervised", [False, True])
@pytest.mark.parametrize("amount", [None, 0.0, 1000.0, 5000.0, 5000.01])
@pytest.mark.parametrize("zone", [*ZONES, "null"])
def test_ac_09_provisional_credit_is_human_required_in_every_zone_tier_and_mode(zone, amount, supervised):
    d = ENGINE.decide(turn(score=SCORE_OF.get(zone), amount=amount, supervised_mode=supervised, customer_confirmed=True))
    assert d.approval_modes["provisional_credit"] == "human_required" and "provisional_credit" not in d.allowed_actions
    assert isinstance(ENGINE.check("provisional_credit", d.zone, amount=amount, currency="USD", country="MX",
                                   supervised_mode=supervised), Deny)
