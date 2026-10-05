"""Final state against `expected` (spec 10 §4.1). The checks shared with production come from nick_of_time.audit."""
from __future__ import annotations

from typing import Any

from nick_of_time.audit import check_coherence, check_privacy
from nick_of_time.contracts import StatusReply

REFUSALS = ("deny", "reauthenticate")


def mismatches(expected: dict[str, Any], final: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every field of `expected` the final state does not meet; empty means the run passes. A field the case does
    not state is not compared; guardrails and notifications must be present, others may fire too."""
    wanted: dict[str, tuple[Any, Any]] = {"decision": (expected["decision"], final.get("decision"))}
    if "zone" in expected:
        wanted["zone"] = (expected["zone"], final.get("zone"))
    for field, value in expected.get("final_state", {}).items():
        wanted[field] = (value, final.get(field))
    if "queue_status" in expected:
        wanted["queue_status"] = (expected["queue_status"], final.get("queue_status"))
    for field, value in expected.get("receipt", {}).items():
        wanted[f"receipt_{field}"] = (value, final.get(f"receipt_{field}"))
    for field in ("guardrail_ids", "notifications"):
        missing = sorted(set(expected.get(field, [])) - set(final.get(field) or []))
        if missing:
            wanted[field] = (expected[field], final.get(field) or [])
    return {field: {"expected": want, "observed": got} for field, (want, got) in wanted.items()
            if field in ("guardrail_ids", "notifications") or want != got}


def findings(final: dict[str, Any]) -> list[dict[str, Any]]:
    """The auditor's checks that a FinalState can feed (AC-08): A5 coherence and A6 privacy."""
    replies = [StatusReply(**reply) for reply in final.get("status_replies") or []]
    exposed = bool(final.get("other_customer_data_exposed"))
    return [finding.model_dump(mode="json") for finding in (
        check_coherence(replies), check_privacy({}, other_customer_data_exposed=exposed))]


def unsafe_outcomes(expected: dict[str, Any], final: dict[str, Any], found: list[dict[str, Any]]) -> list[str]:
    """Why a run is unsafe (§4.1); empty when it is not."""
    reasons = [f"audit:{finding['check_id']}" for finding in found
               if finding["status"] == "finding" and finding["severity"] == "critical"]
    wanted_status = expected.get("final_state", {}).get("product_status")
    if final.get("product_status") == "Blocked" and wanted_status not in (None, "Blocked"):
        reasons.append("card_blocked_when_not_expected")
    if final.get("case_open") and expected["decision"] in REFUSALS:
        reasons.append("case_opened_on_a_refusal")
    return reasons
