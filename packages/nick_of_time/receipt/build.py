"""Receipt and handoff card of a turn (spec 04 T5; AC-05, AC-11, AC-12, AC-21), built from tool results only, and the
grounding gate of spec 04 §4.3 (ADR 0016, G-OUT-01): whatever does not string-match a tool result or the policy is
dropped and counted. The gate runs the auditor's A4 rule (spec 18) on ids, dates and numbers, plus an exact time match
A4 does not make yet (it counts a timestamp by its date; spec 18 follow-up). `papers()` is the one entry point: it
builds and gates both documents, and each field's fate (drop the document, null it, leave it out) is read from the
contract schema, never from a list kept by hand."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any, Iterable, Optional

from nick_of_time.audit.checks import check_grounding, check_privacy
from nick_of_time.contracts import load_schema
from nick_of_time.receipt import amount_text, text

SCHEMAS = {"receipt": load_schema("customer_receipt.schema.json"), "handoff": load_schema("handoff.schema.json")}
REASONS = SCHEMAS["handoff"]["properties"]["handoff_reason"]["enum"]
STEP = re.compile(r"^\d+\. ")       # [assumption] a plan step's own number is the template's, not a fact
NO_CLOCK = "POL-CLOCK-UNKNOWN"
ALERT = "G-OUT-01"                  # a fact the gate dropped (ADR 0016)
# a time as a tool returns it (ISO) or as the customer sees it ('YYYY-MM-DD HH:MM UTC', D-051)
TIME = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2}| UTC)?")
SECONDS = re.compile(r"\d{2}:\d{2}:\d{2}")
RATIONALE = {"approve_block": "The card is not blocked and verified; a person decides the block.",
             "request_customer_info": "Zone human: a person reviews the charge with the customer."}


def when(value: Any) -> Optional[dt.datetime]:
    """A time as an aware UTC datetime; a time with no zone, or 'UTC', is UTC (D-051). None when it does not parse."""
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc)
    try:
        t = dt.datetime.fromisoformat(str(value).replace(" UTC", "+00:00").replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)


def stamp(value: Any) -> str:
    """A tool time as shown to the customer: UTC to the minute, 'YYYY-MM-DD HH:MM UTC' (D-051)."""
    return when(value).strftime("%Y-%m-%d %H:%M UTC")


def untimed(doc: Any, facts: list[Any]) -> bool:
    """True when `doc` states a time no tool returned: exact to the second when it shows seconds, else to the minute
    (a D-051 stamp), so a wrong HH:MM is caught although A4 counts a timestamp by its date (constitution #5)."""
    known = {when(m) for m in TIME.findall(json.dumps(facts, default=str))} - {None}
    minutes = {t.replace(second=0, microsecond=0) for t in known}
    return any(when(raw) not in (known if SECONDS.search(raw) else minutes)
               for raw in TIME.findall(json.dumps(doc, default=str, ensure_ascii=False)))


def bad(value: Any, facts: list[Any], policy: Iterable[str] = ()) -> bool:
    """True when `value` states an id, date, time or number that no tool result (or policy fact) states."""
    doc = value if isinstance(value, dict) else {"_": STEP.sub("", value) if isinstance(value, str) else value}
    return check_grounding(facts, handoff=doc, policy_facts=list(policy)).status == "finding" or untimed(doc, facts)


POLICY_ID = re.compile(r"\bPOL-[A-Z0-9]+(?:-[A-Z0-9]+)*", re.I)
# [assumption] internal names: snake_case (tool, decision, event and queue names) and guardrail ids; none is customer copy
INTERNAL = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b|\bG-[A-Z]+-\d+\b")
SCORE_WORD = re.compile(r"(?i)score|puntaje|puntuaci[oó]n|pontua[cç][aã]o|riesgo|risco|fraud|probabilidad|[íi]ndice")


def states(text: str, number: float) -> bool:
    """True when `text` holds `number` as a plain number ('87', '87.0' or '87,0')."""
    return any(float(m.replace(",", ".")) == number for m in re.findall(r"(?<![\d.,])\d+(?:[.,]\d+)?(?![\d])", text))


def never_send(text: str, template: str = "", *, score: Any = None, transcript: Iterable[str] = ()) -> list[str]:
    """What a customer-facing line leaks that `notifications.never_send` forbids (spec 04 §4.3, D-056 follow-up): a
    policy id of any shape, an internal name or a score word its template line did not have (a source URL may hold
    one), the score's value (near a score word, or bare when its template line did not state it) or a customer
    utterance of at least 20 characters. [] when clean. A utility for spec 15's `word` gate: no reworded line reaches
    a customer yet."""
    internal = set(INTERNAL.findall(text)) - set(INTERNAL.findall(template))
    hits = ["policy_id"] * bool(POLICY_ID.search(text)) + ["internal_name"] * bool(internal)
    value = score is not None and (check_privacy({"reply": text}, score=float(score)).status == "finding" or (
        states(text, float(score)) and not states(template, float(score))))
    if value or (SCORE_WORD.search(text) and not SCORE_WORD.search(template)):
        hits.append("score")
    said = [t.casefold() for t in transcript if len(t) >= 20]
    return hits + ["transcript"] * any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text.casefold()) for t in said)


def nullable(prop: dict[str, Any]) -> bool:
    """True when the schema property accepts null (a "null" type or a None in its enum)."""
    kind = prop.get("type")
    return (kind == "null" or isinstance(kind, list) and "null" in kind) or None in prop.get("enum", ())


def fates(schema: dict[str, Any]) -> dict[str, str]:
    """What the gate does with each ungrounded field of a document of `schema`: "drop" the whole document (required and
    not nullable), "null" it (nullable) or "omit" it (optional, not nullable). Read from the contract, so a required
    field cannot be forgotten in a hand-kept list."""
    required = set(schema.get("required", ()))
    return {key: "null" if nullable(prop) else "drop" if key in required else "omit"
            for key, prop in schema["properties"].items()}


def gate(doc: dict[str, Any], facts: list[Any], policy: Iterable[str] = (), *,
         schema: str) -> tuple[Optional[dict[str, Any]], int]:
    """The document minus every list item or field that is not grounded, and how many were dropped. An ungrounded field
    drops the whole document, becomes null or is left out, as `fates(SCHEMAS[schema])` says."""
    out, dropped, policy, fate = {}, 0, list(policy), fates(SCHEMAS[schema])
    for key, value in doc.items():
        if isinstance(value, list):
            out[key] = [item for item in value if not bad(item, facts, policy)]
            dropped += len(value) - len(out[key])
        elif value is not None and bad({key: value}, facts, policy):
            dropped += 1
            if fate[key] == "drop":
                return None, dropped
            if fate[key] == "null":
                out[key] = None
        else:
            out[key] = value
    return out, dropped


def returned(actions: list[dict[str, Any]], facts: list[Any]) -> set[str]:
    """The action ids among `actions` that a tool result states; a graph-minted id is in none (spec 04 §4.1)."""
    said = json.dumps(facts, default=str)
    return {a["action_id"] for a in actions if f'"{a["action_id"]}"' in said}


def papers(paper: dict[str, Any], facts: list[Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    """The turn's receipt and handoff card, each built from `paper` and passed through the gate against the turn's tool
    results `facts` (the handoff also against the score and the decision's rule and guardrail ids, since it never
    reaches the customer); and how many facts the gate dropped. The only way respond gets either document. A card the
    gate trimmed carries G-OUT-01 in its own guardrails_triggered, so the analyst sees that a fact was removed."""
    paper = {**paper, "returned": returned(paper["actions"], facts)}
    route = paper["route"]
    policy = [*route.get("rule_ids", []), *route.get("guardrail_ids", []), NO_CLOCK]
    draft, card = receipt(paper), handoff(paper)
    kept, dropped = gate(draft, facts, schema="receipt") if draft else (None, 0)
    shown_card, more = gate(card, [*facts, paper["score"] or {}], policy, schema="handoff") if card else (None, 0)
    if shown_card and more:
        shown_card["guardrails_triggered"] = [*shown_card["guardrails_triggered"], ALERT]
    return kept, shown_card, dropped + more


def shown(f: dict[str, Any]) -> list[dict[str, Any]]:
    """The turn's actions whose action_id a tool returned; a graph-minted id never reaches a receipt or a handoff
    (spec 04 §4.1)."""
    return [a for a in f["actions"] if a["action_id"] in f["returned"]]


def receipt(f: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The customer receipt (spec 01 §6.7, AC-21) once get_case verified the case opened this turn, else None (also
    for an existing case, duplicate_of, which already has its own)."""
    case, trx, opened, card, language = f["case"], f["trx"], f["opened"], f["card"], f["language"]
    if not case or opened.get("duplicate_of"):
        return None
    merchant = "transaction" if trx.get("merchant") else "transaction_no_merchant"
    facts = [{"fact": text(f"receipt.{merchant}", language, merchant=trx.get("merchant"),
                           amount=amount_text(trx["amount"]), currency=trx["currency"]),
              "source_id": trx["transaction_id"]},
             {"fact": text("act.case_opened", language, case_id=case["case_id"],
                           verification_id=case["verification_id"], verified_at=stamp(case["read_at"])),
              "source_id": case["case_id"]}]
    if card:
        facts.append({"fact": text("receipt.card_blocked", language, last4=card["last4"],
                                   verification_id=card["verification_id"], verified_at=stamp(card["read_at"])),
                      "source_id": card["verification_id"]})
    dates = {key: case.get(key) for key in ("credit_deadline", "ruling_deadline")}
    if f["dispute"] != "unrecognized_charge":   # D-030 (ADR 0023 item 5): a wrongful charge shows the ruling date only
        dates["credit_deadline"] = None
    deadline = {"country": opened["country"], "product": trx["product_type"], **dates,
                "deadline_source": case.get("deadline_source_label") or case["deadline_source"],   # DLANG
                "source_url": case["deadline_source_url"],
                "verified_on": case["deadline_verified_on"]} if any(dates.values()) else None
    tried_block = any(a["tool"] == "block_card" for a in f["actions"]) and not f["held"]
    did = "blocked" if card else "block_unconfirmed" if tried_block else "case_only"
    fx = f["display"] if f["display"] and f["display"]["currency"] != trx["currency"] else None
    actions = shown(f)
    return {
        "receipt_id": "RC-" + hashlib.sha256(f"{f['trace_id']}:{case['case_id']}".encode()).hexdigest()[:12].upper(),
        "case_id": case["case_id"], "language": language, "mode": f["mode"],
        # [assumption] issued at the last post-condition read of the turn: a tool time, never the system clock
        "issued_at": max((a for a in actions if a["state"] == "verified"), key=lambda a: when(a["read_at"]))["read_at"],
        "verified_facts": facts, "product_last4": trx["last4"],
        "amount": {"original": {"amount": amount_text(trx["amount"]), "currency": trx["currency"]}, "display": fx},
        "actions": [{"label": text(f"status.action_label.{a['tool']}", language), "action_id": a["action_id"],
                     "state": a["state"], "verification_id": a.get("verification_id"), "verified_at": a.get("read_at")}
                    for a in actions],
        "deadline": deadline, "what_ai_did": text(f"receipt.what_ai_did_{did}", language),
        "what_a_person_does": text("receipt.what_a_person_does", language), "next_steps": []}


def handoff(f: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The analyst's handoff card (handoff.schema.json) for a case a tool returned this turn, verified or not (a case
    get_case did not read back is flagged in open_questions); None without one, or for an existing case
    (duplicate_of), whose own card already exists [assumption, D-056]."""
    trx, opened, case, card, route, score = f["trx"], f["opened"], f["case"], f["card"], f["route"], f["score"]
    if not opened or opened.get("duplicate_of"):
        return None
    actions = shown(f)
    stored = case or opened                       # the stored deadlines: get_case's, else open_case's answer
    dates = {key: str(stored[key]) for key in ("credit_deadline", "ruling_deadline") if stored.get(key)}
    # [assumption, D-056] a session that expired mid-turn hands off as identity_unverified
    reason = {"escalate_unconfirmed_action": "tool_failure", "reauthenticate": "identity_unverified"}.get(
        f["decision"], route.get("handoff_reason"))
    proposal = ("approve_block" if route["zone"] in ("high", "medium") and not card
                else "request_customer_info" if route["zone"] == "human" else None)
    charge = f"{trx['currency']} {amount_text(trx['amount'])} on {trx['transaction_date']}"
    questions = [f"{a['tool']}: not confirmed" for a in f["actions"]
                 if a["state"] == "not_confirmed" and not (a["tool"] == "block_card" and f["held"])]
    questions += ["block_card: held by the open call request; decide it after the call"] if f["held"] else []
    questions += [f"case {opened['case_id']} not read back by get_case: confirm it exists before acting"] if not case else []
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
