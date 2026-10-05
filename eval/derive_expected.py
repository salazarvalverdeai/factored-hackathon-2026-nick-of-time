"""Agent evaluation cases (spec 09 T3, T4): builds eval/cases/<set>.jsonl from eval/cases/plan/<set>.jsonl.

A plan line holds what the team writes: the case type, the customer messages, the intent they carry and the row of
eval/demo_index.csv the case is about. This script adds the real state (the transaction fixtures) and the `expected`
block, which comes from the policy engine and is never typed by hand (AC-09).

Usage, from the repo root: PYTHONPATH=packages python -m eval.derive_expected dev|heldout|seal
`seal` writes eval/heldout.sha256, the sha256 of eval/cases/heldout.jsonl (AC-05). After the seal the held-out file
never changes (ADR 0021).
A plan line with `"fixtures": "cluster"` (ambiguous cases) reads the customer's neighbouring card transactions from
data/gold/, so it needs `make setup`; every other line needs only the index.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

import duckdb

from eval import demo_index
from nick_of_time.policy import DecisionInput, PolicyEngine

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "eval/cases"
DISPUTES = ("unrecognized_charge", "wrongful_charge")
CASE_KEYS = ("id", "language", "type", "origin", "set", "country", "segment", "initial_state", "messages", "expected",
             "notes", "labeler")
NEIGHBOURS = """
    SELECT transaction_id, product_id,
           CASE product_type WHEN 'Tarjeta Débito' THEN 'debit' ELSE 'credit' END AS product_type,
           round(amount, 2) AS amount, currency, strftime(transaction_date, '%Y-%m-%d') AS transaction_date,
           merchant_name AS merchant, fraud_score
    FROM read_parquet('{gold}/transactions_enriched.parquet')
    WHERE customer_id = ? AND product_type IN ('Tarjeta Débito', 'Tarjeta Crédito') AND transaction_status = 'Approved'
      AND transaction_date BETWEEN CAST(? AS TIMESTAMP) - INTERVAL 7 DAY AND CAST(? AS TIMESTAMP) + INTERVAL 7 DAY
    ORDER BY transaction_date, transaction_id"""


def expected_for(case: dict[str, Any], intent: Optional[str], engine: Optional[PolicyEngine] = None) -> dict[str, Any]:
    """The `expected` block of one case: the engine decides each scripted turn and the last decision is the outcome.

    The facts come from the case itself: its fixtures are the transactions the messages match, so one fixture is an
    identified charge and several are an ambiguous one. `intent` is the team's label of the messages (None when the
    case is refused before any intent matters).
    """
    engine = engine or PolicyEngine.load()
    state, fixtures = case["initial_state"], case["initial_state"].get("fixtures", [])
    target = fixtures[0] if len(fixtures) == 1 else {}
    returning = "case" in state
    score = target.get("fraud_score")
    facts = dict(
        session_state="verified" if state["session"] == "verified" else "expired",
        intent=intent or "out_of_scope", intent_confidence=1.0,
        dispute_detected=intent in DISPUTES or (intent in ("human_request", "status_inquiry") and bool(fixtures)
                                                and not returning),
        injection_flagged=case["type"] == "injection", cross_customer=case["type"] == "unauthorized_access",
        supervised_mode=False, candidates=len(fixtures),
        score=None if score is None else float(score), score_source=None if score is None else "dataset",
        amount=target.get("amount"), currency=target.get("currency"), country=case["country"],
        product_type=target.get("product_type"), active_case=returning if intent == "status_inquiry" else None)
    decision, asked, confirmed = None, 0, None
    for _ in case["messages"]:
        decision = engine.decide(DecisionInput(**facts, clarification_turns=asked, customer_confirmed=confirmed))
        asked += decision.decision == "ask"
        confirmed = True if decision.decision == "confirm" else confirmed     # the next message confirms the charge

    opened, blocked = "open_case" in decision.allowed_actions, "block_card" in decision.allowed_actions
    outcome, queue = decision.decision, decision.queue_status_after
    handoff = decision.handoff_reason is not None or decision.request_call is not None
    faults = state.get("tool_faults", [])
    if opened and "open_case" in faults:
        # reliability.on_failure: no case is confirmed, so nothing is reported as opened or blocked; a person gets it
        outcome, opened, blocked, handoff, queue = "escalate_unconfirmed_action", False, False, True, None
    elif blocked and "block_card" in faults:
        # the block is never reported; the case goes to a person with the action unconfirmed
        outcome, blocked, handoff, queue = "escalate_unconfirmed_action", False, True, "review"
    expected: dict[str, Any] = {"decision": outcome}
    if decision.zone:
        expected["zone"] = decision.zone
    if intent:
        expected["intent"] = intent
    if outcome == "answer_status":                 # read-only turn: the existing case stays as the seed left it
        expected["final_state"] = {"case_open": True, "other_customer_data_exposed": False}
        expected["receipt"] = {"issued": False, "has_deadline": False}
        return expected
    expected["final_state"] = {"product_status": "Blocked" if blocked else "Active", "case_open": opened,
                               "handoff_emitted": handoff, "other_customer_data_exposed": False}
    if queue:
        expected["queue_status"] = queue
    deadline = opened and case["country"] in engine.policies.regulatory_clock
    expected["receipt"] = {"issued": opened, "has_deadline": deadline}
    if deadline:
        expected["deadline_country"] = case["country"]
    if decision.guardrail_ids:
        expected["guardrail_ids"] = list(decision.guardrail_ids)
    if opened:
        expected["notifications"] = ["case_opened", *(["card_blocked"] if blocked else [])]
    return expected


def _fixture(row: dict[str, Any]) -> dict[str, Any]:
    """A transaction fixture from a row of the demo index."""
    return {"transaction_id": row["transaction_id"], "product_id": row["product_id"],
            "product_type": row["product_type"], "amount": float(row["amount"]), "currency": row["currency"],
            "transaction_date": row["transaction_date"][:10], "merchant": row["merchant_name"],
            "fraud_score": None if row["fraud_score"] is None else float(row["fraud_score"])}


def _cluster(anchor: dict[str, Any], gold: Path) -> list[dict[str, Any]]:
    """The customer's approved card transactions within 7 days either side of the anchor, read from gold."""
    con = duckdb.connect()
    try:
        cursor = con.execute(NEIGHBOURS.format(gold=gold.as_posix()),
                             [anchor["customer_id"], anchor["transaction_date"], anchor["transaction_date"]])
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        con.close()


def build_case(plan: dict[str, Any], set_name: str, index: dict[str, dict], gold: Path,
               engine: Optional[PolicyEngine] = None) -> dict[str, Any]:
    anchor = index[plan["anchor"]]
    if anchor["split"] != set_name:
        raise ValueError(f"{plan['id']}: {anchor['customer_id']} is a {anchor['split']} customer, not {set_name}")
    kind = plan.get("fixtures", "anchor")
    fixtures = {"anchor": lambda: [_fixture(anchor)], "none": lambda: [],
                "cluster": lambda: _cluster(anchor, gold)}[kind]()
    if kind == "cluster" and len(fixtures) < 2:
        raise ValueError(f"{plan['id']}: an ambiguous case needs at least two candidate transactions")
    state: dict[str, Any] = {"customer_id": anchor["customer_id"], "session": plan.get("session", "verified"),
                             "fixtures": fixtures}
    if plan.get("tool_faults"):
        state["tool_faults"] = plan["tool_faults"]
    if plan.get("case"):                           # returning customer: the case they already have, on the anchor
        zone = anchor["zone"]
        state["case_id"] = plan["case"]["case_id"]
        state["case"] = {"transaction_id": anchor["transaction_id"], "dispute_type": plan["case"]["dispute_type"],
                         "zone": zone, "queue_status": "verification" if zone == "high" else "review",
                         "opened_on": plan["case"]["opened_on"]}
    case = {"id": plan["id"], "language": plan["language"], "type": plan["type"], "origin": "team-generated",
            "set": set_name, "country": anchor["country"], "segment": anchor["segment"], "initial_state": state,
            "messages": [{"role": "customer", "text": text} for text in plan["messages"]]}
    case["expected"] = expected_for(case, plan.get("intent"), engine)
    case["notes"], case["labeler"] = plan["notes"], plan["labeler"]
    return {key: case[key] for key in CASE_KEYS}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(set_name: str, gold: Path = ROOT / "data/gold") -> list[dict[str, Any]]:
    index = {row["transaction_id"]: row for row in demo_index.read()}
    engine = PolicyEngine.load()
    return [build_case(plan, set_name, index, gold, engine) for plan in read_jsonl(CASES / "plan" / f"{set_name}.jsonl")]


def write(set_name: str) -> int:
    cases = build(set_name)
    text = "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)
    (CASES / f"{set_name}.jsonl").write_text(text, encoding="utf-8", newline="\n")
    return len(cases)


def heldout_sha256() -> str:
    return hashlib.sha256((CASES / "heldout.jsonl").read_bytes()).hexdigest()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) == 2 else ""
    if name == "seal":
        (ROOT / "eval/heldout.sha256").write_text(heldout_sha256() + "\n", encoding="ascii", newline="\n")
        print(f"eval/heldout.sha256: {heldout_sha256()}")
    elif name in ("dev", "heldout"):
        print(f"eval/cases/{name}.jsonl: {write(name)} cases")
    else:
        sys.exit("usage: python -m eval.derive_expected dev|heldout|seal")
