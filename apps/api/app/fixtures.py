"""Fixture data for the api stub (spec 01 T3). Everything here is [simulated]; ids follow `nick_of_time.ids`."""
from __future__ import annotations

import datetime as dt

import yaml

from nick_of_time.contracts import (CONTRACTS_DIR, CaseSummary, CaseView, CustomerCaseSummary, ProductView, TurnResult,
                                    sample_receipt)

MESSAGES = yaml.safe_load((CONTRACTS_DIR / "messages.yaml").read_text())
POLICIES = yaml.safe_load((CONTRACTS_DIR / "policies.yaml").read_text())   # decisions live there (constitution #2)
POLICIES_VERSION = POLICIES["version"]
SESSION_TTL_MINUTES = POLICIES["identity"]["session_ttl_minutes"]
REPLAY_TODAY = dt.date(2026, 6, 1)               # ADR 0020 default of DEMO_TODAY, which applies to replay sessions only
OTP = "123456"                                   # mock OTP shown on screen (ADR 0017)
CASE_ID = "K-104233"
OTHER_CASE_ID = "K-104299"                       # belongs to another customer: 403 for the demo customer
PRODUCT_ID = "PRD-FIXTURE00001"
TRANSACTION_ID = "TRX-FIXTURE0000000000001"
NOW = dt.datetime(2026, 6, 1, 15, 4, 12, tzinfo=dt.timezone.utc)

CUSTOMERS = [
    {"customer_id": f"CLI-DEMO{i:04d}", "display_name": name, "country": cc, "segment": seg, "scenario": sc,
     "language": lang}
    for i, (name, cc, seg, sc, lang) in enumerate([
        ("Ana (MX debit)", "MX", "mass", "high-score unrecognized charge", "es"),
        ("Bruno (BR credit)", "BR", "premium", "medium-score wrongful charge", "pt"),
        ("Carla (AR debit)", "AR", "mass", "no score: human zone", "es"),
        ("Diego (CO credit)", "CO", "mass", "status inquiry on an open case", "es"),
        ("Elena (MX credit)", "MX", "premium", "returning customer", "es"),
        ("Fabio (BR debit)", "BR", "mass", "expired session", "pt"),
    ], start=1)
]
OWNER = CUSTOMERS[0]["customer_id"]
RESOLVED_CASE_ID = "K-104240"                    # the demo customer's resolved case: reevaluation 201, close_case 200
CASE_OWNERS = {CASE_ID: OWNER, RESOLVED_CASE_ID: OWNER, OTHER_CASE_ID: CUSTOMERS[1]["customer_id"]}

_SRC = {"deadline_source": "Banxico Circular 3/2012, as amended by Circular 14/2018",
        "deadline_source_url": "https://www.gob.mx/condusef/prensa/cargos-no-reconocidos-en-tarjeta-de-debito-se-"
                               "restituiran-en-dos-dias-habiles-bancarios?idiom=es",
        "deadline_verified_on": dt.date(2026, 10, 4)}


def case_view(case_id: str = CASE_ID, mode: str = "replay", today: dt.date = REPLAY_TODAY) -> CaseView:
    credit = dt.date(2026, 6, 3)
    return CaseView(
        case_id=case_id, customer_id=CASE_OWNERS.get(case_id, OWNER), country="MX", zone="high",
        queue_status="resolved" if case_id == RESOLVED_CASE_ID else "verification", credit_deadline=credit, ruling_deadline=None, created_at=NOW,
        sla_due_at=NOW + dt.timedelta(days=2), priority="high", tags=["fixture"],
        transaction={"transaction_id": TRANSACTION_ID, "amount": 1250.0, "currency": "USD", "date": "2026-05-31",
                     "merchant": "TIENDA X", "synthetic": False},
        product_last4="4417", status_label="Verifying the block", mode=mode, receipt=sample_receipt(),
        timeline=[{"event_id": "E-000000000001", "type": "case_opened", "label": "Case opened", "created_at": NOW}],
        deadline_countdown_days=(credit - today).days, channels={"telegram": False, "email": False},
        notifications=[{"notification_id": "N-000000000001", "channel": "log", "masked_address": None,
                        "delivery_status": "delivered", "created_at": NOW}], **_SRC)


def case_summary() -> CaseSummary:
    return CaseSummary.model_validate(case_view().model_dump(include=set(CaseSummary.model_fields)))


def my_cases() -> list[CustomerCaseSummary]:
    return [CustomerCaseSummary(case_id=CASE_ID, status_label="Verifying the block", credit_deadline="2026-06-03",
                                product_last4="4417", updated_at=NOW)]


def my_products() -> list[ProductView]:
    return [ProductView(product_id=PRODUCT_ID, type="debit", last4="4417", status="Blocked",
                        verification_id="V-8B2D41C7E0A9", read_at=NOW)]


def notifications() -> list[dict]:
    return [{"notification_id": "N-000000000001", "case_id": CASE_ID, "event": "case_opened", "channel": "log",
             "masked_address": None, "text": "Abrimos el caso K-104233.", "delivery_status": "delivered",
             "created_at": NOW.isoformat()}]


def turn_result() -> TurnResult:
    """A full graph output, internal fields included, so tests prove the customer projection strips them."""
    return TurnResult(
        reply="Bloqueamos tu tarjeta y abrimos el caso K-104233.", language="es", decision="block_and_open_case",
        intent="unrecognized_charge", case_id=CASE_ID, receipt=sample_receipt(), mode="replay", trace_id="tr-fixture",
        suggestions=[{"id": "s1", "label": "Ver mi caso", "kind": "link", "href": f"/case/{CASE_ID}"},
                     {"id": "s2", "label": "Hablar con una persona", "kind": "action",
                      "action": {"type": "request_call"}}],
        zone="high", denials=[{"policy_id": "POL-FIXTURE-01", "guardrail_id": "G-IN-01", "detail": "fixture"}])


def final_state(run_id: str, arm: str) -> dict:
    return {"run_id": run_id, "arm": arm, "decision": "block_and_open_case", "zone": "high",
            "intent": "unrecognized_charge", "transaction_id": TRANSACTION_ID, "product_id": PRODUCT_ID,
            "product_status": "Blocked", "case_open": True, "case_id": CASE_ID, "queue_status": "verification",
            "handoff_emitted": True, "receipt_issued": True, "receipt_has_deadline": True,
            "notifications": ["case_opened"], "other_customer_data_exposed": False,
            "action_states": {"block_card": "verified"},
            "totals": {"latency_ms": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
            "run_meta": {"git_sha": "stub", "policies_version": POLICIES_VERSION, "provider": "fake"}}


HANDOFF = {"case_id": CASE_ID, "language": "es", "zone": "high", "request": "Cargo no reconocido de USD 1,250.00",
           "verified_facts": [{"fact": "Tarjeta bloqueada", "source_id": "V-8B2D41C7E0A9"}], "actions": [],
           "evidence": [CASE_ID], "open_questions": [], "trace_id": "tr-fixture",
           "deadline": {"country": "MX", "product": "debit", "credit_deadline": "2026-06-03",
                        "deadline_source": _SRC["deadline_source"], "source_url": _SRC["deadline_source_url"],
                        "verified_on": _SRC["deadline_verified_on"].isoformat()}}
