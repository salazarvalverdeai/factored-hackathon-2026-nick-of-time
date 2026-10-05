"""Receipt and handoff card of a turn (spec 04 T5; AC-05, AC-11, AC-12, AC-21), built from tool results only, and the
grounding gate of spec 04 §4.3 (ADR 0016, G-OUT-01): whatever does not string-match a tool result or the policy is
dropped and counted. The gate runs the auditor's A4 rule (spec 18), so the runtime and the auditor agree on a fact."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Optional

from nick_of_time.audit.checks import check_grounding
from nick_of_time.contracts import load_schema
from nick_of_time.receipt import amount_text, text

REASONS = load_schema("handoff.schema.json")["properties"]["handoff_reason"]["enum"]
STEP = re.compile(r"^\d+\. ")       # [assumption] a plan step's own number is the template's, not a fact
NO_CLOCK = "POL-CLOCK-UNKNOWN"
RATIONALE = {"approve_block": "The card is not blocked and verified; a person decides the block.",
             "request_customer_info": "Zone human: a person reviews the charge with the customer."}


def bad(value: Any, facts: list[Any], policy: Iterable[str] = ()) -> bool:
    """True when `value` states an id, date or number that no tool result (or policy fact) states."""
    doc = value if isinstance(value, dict) else {"_": STEP.sub("", value) if isinstance(value, str) else value}
    return check_grounding(facts, handoff=doc, policy_facts=list(policy)).status == "finding"


def gate(doc: dict[str, Any], facts: list[Any], policy: Iterable[str] = (), *, required: Iterable[str] = (),
         nullable: bool = True) -> tuple[Optional[dict[str, Any]], int]:
    """The document minus every list item or field that is not grounded, and how many were dropped. An ungrounded
    required field drops the whole document; an optional one becomes null (`nullable`) or is left out."""
    out, dropped, policy = {}, 0, list(policy)
    for key, value in doc.items():
        if isinstance(value, list):
            out[key] = [item for item in value if not bad(item, facts, policy)]
            dropped += len(value) - len(out[key])
        elif value is not None and bad({key: value}, facts, policy):
            dropped += 1
            if key in required:
                return None, dropped
            if nullable:
                out[key] = None
        else:
            out[key] = value
    return out, dropped


def shown(f: dict[str, Any]) -> list[dict[str, Any]]:
    """The turn's actions whose action_id a tool returned; a graph-minted id never reaches a receipt or a handoff
    (spec 04 §4.1)."""
    return [a for a in f["actions"] if a["action_id"] in f["returned"]]


def receipt(f: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The customer receipt (spec 01 §6.7, AC-21) once get_case verified the case opened this turn, else None."""
    case, trx, opened, card, language = f["case"], f["trx"], f["opened"], f["card"], f["language"]
    if not case:
        return None
    merchant = "transaction" if trx.get("merchant") else "transaction_no_merchant"
    facts = [{"fact": text(f"receipt.{merchant}", language, merchant=trx.get("merchant"),
                           amount=amount_text(trx["amount"]), currency=trx["currency"]),
              "source_id": trx["transaction_id"]},
             {"fact": text("act.case_opened", language, case_id=case["case_id"],
                           verification_id=case["verification_id"], verified_at=case["read_at"]),
              "source_id": case["case_id"]}]
    if card:
        facts.append({"fact": text("receipt.card_blocked", language, last4=card["last4"],
                                   verification_id=card["verification_id"], verified_at=card["read_at"]),
                      "source_id": card["verification_id"]})
    dates = {key: case.get(key) for key in ("credit_deadline", "ruling_deadline")}
    if f["dispute"] != "unrecognized_charge":   # D-030 (ADR 0023 item 5): a wrongful charge shows the ruling date only
        dates["credit_deadline"] = None
    deadline = {"country": opened["country"], "product": trx["product_type"], **dates,
                "deadline_source": case["deadline_source"], "source_url": case["deadline_source_url"],
                "verified_on": case["deadline_verified_on"]} if any(dates.values()) else None
    tried_block = any(a["tool"] == "block_card" for a in f["actions"]) and not f["held"]
    did = "blocked" if card else "block_unconfirmed" if tried_block else "case_only"
    fx = f["display"] if f["display"] and f["display"]["currency"] != trx["currency"] else None
    actions = shown(f)
    return {
        "receipt_id": "RC-" + hashlib.sha256(f"{f['trace_id']}:{case['case_id']}".encode()).hexdigest()[:12].upper(),
        "case_id": case["case_id"], "language": language, "mode": f["mode"],
        # [assumption] issued at the last post-condition read of the turn: a tool time, never the system clock
        "issued_at": max(a["read_at"] for a in actions if a["state"] == "verified"),
        "verified_facts": facts, "product_last4": trx["last4"],
        "amount": {"original": {"amount": amount_text(trx["amount"]), "currency": trx["currency"]}, "display": fx},
        "actions": [{"label": text(f"status.action_label.{a['tool']}", language), "action_id": a["action_id"],
                     "state": a["state"], "verification_id": a.get("verification_id"), "verified_at": a.get("read_at")}
                    for a in actions],
        "deadline": deadline, "what_ai_did": text(f"receipt.what_ai_did_{did}", language),
        "what_a_person_does": text("receipt.what_a_person_does", language), "next_steps": []}


def handoff(f: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The analyst's handoff card (handoff.schema.json) for a case a tool returned this turn, verified or not; None
    without one, or for an existing case (duplicate_of), whose own card already exists [assumption]."""
    trx, opened, case, card, route, score = f["trx"], f["opened"], f["case"], f["card"], f["route"], f["score"]
    if not opened or opened.get("duplicate_of"):
        return None
    actions = shown(f)
    stored = case or opened                       # the stored deadlines: get_case's, else open_case's answer
    dates = {key: str(stored[key]) for key in ("credit_deadline", "ruling_deadline") if stored.get(key)}
    reason = "tool_failure" if f["decision"] == "escalate_unconfirmed_action" else route.get("handoff_reason")
    proposal = ("approve_block" if route["zone"] in ("high", "medium") and not card
                else "request_customer_info" if route["zone"] == "human" else None)
    charge = f"{trx['currency']} {amount_text(trx['amount'])} on {trx['transaction_date']}"
    questions = [f"{a['tool']}: not confirmed" for a in f["actions"]
                 if a["state"] == "not_confirmed" and not (a["tool"] == "block_card" and f["held"])]
    questions += ["block_card: held by the open call request; decide it after the call"] if f["held"] else []
    questions += [f"no verified legal deadline ({NO_CLOCK})"] if not dates else []
    ids = [trx["transaction_id"], trx["product_id"], opened["case_id"], *(a["action_id"] for a in actions),
           *(a["verification_id"] for a in actions if a.get("verification_id"))]
    return {
        "case_id": opened["case_id"], "language": f["language"], "zone": route["zone"],
        **({"handoff_reason": reason} if reason in REASONS else {}),
        "request": " · ".join(filter(None, [f["dispute"], charge, trx.get("merchant")])),
        "verified_facts": [
            {"fact": f"{f['dispute']}: {charge}", "source_id": trx["transaction_id"]},
            {"fact": f"{trx['product_type']} card ending {trx['last4']}", "source_id": trx["product_id"]},
            *([{"fact": f"case {case['case_id']} read by get_case", "source_id": case["verification_id"]}] if case else []),
            *([{"fact": f"card ending {card['last4']} Blocked, read by get_product_status",
                "source_id": card["verification_id"]}] if card else []),
            {"fact": f"decision {route['decision']}, zone {route['zone']}", "source_id": route["rule_ids"][0]}],
        "actions": [{"tool": a["tool"], "action_id": a["action_id"], "result": a["state"],
                     "verified": a["state"] == "verified",
                     **({"verification_id": a["verification_id"]} if a["state"] == "verified" else {})}
                    for a in actions],
        "evidence": list(dict.fromkeys(ids)), "open_questions": questions,
        **({"copilot_proposal": {"action": proposal, "rationale": RATIONALE[proposal], "requires_human": True}}
           if proposal else {}),
        "deadline": {"country": opened["country"], "product": trx["product_type"],
                     "deadline_source": stored.get("deadline_source") or NO_CLOCK, **dates,
                     **({"source_url": stored["deadline_source_url"], "verified_on": str(stored["deadline_verified_on"])}
                        if dates else {})},
        "trace_id": f["trace_id"],
        # D-033: the score with its source and version; the console shows a synthetic one as [simulated]
        **({"score": score["score"], "score_source": score["source"], "score_version": score["version"]}
           if score else {"score": None}),
        **({"intent_confidence": f["intent_confidence"]} if f["intent_confidence"] is not None else {}),
        **({"queue_status": case["queue_status"]} if case else {}),
        "guardrails_triggered": f["guardrails"]}
