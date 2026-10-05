"""Customer-facing text of the agent (spec 04 §4.2 `respond`, §4.5 chips) from `contracts/messages.yaml`.

Templates only, filled with tool facts (ADR 0016). Chips come from the rule table below, never from the LLM (AC-29);
the action payload and the route of a chip are set here, by server code (AC-32). The receipt itself lands in T5.
"""
from __future__ import annotations

from functools import cache
from typing import Any, Optional

import yaml

from nick_of_time.contracts import CONTRACTS_DIR, Suggestion
from nick_of_time.nlu.text import fold


@cache
def messages() -> dict[str, Any]:
    return yaml.safe_load((CONTRACTS_DIR / "messages.yaml").read_text(encoding="utf-8"))


def text(key: str, language: str, **facts: Any) -> str:
    """The `language` text of the template at dotted `key`, e.g. text("refuse.deny", "pt")."""
    node = messages()
    for part in key.split("."):
        node = node[part]
    return node[language].format(**facts)


# Server-side payload of each action chip (spec 01 §6.4) and route of each link chip.
ACTION = {"none_of_these": {"type": "choose_option", "value": "none"}, "talk_to_person": {"type": "request_call"},
          "confirm_yes": {"type": "confirm", "value": "yes"}, "confirm_no": {"type": "confirm", "value": "no"},
          "send_summary": {"type": "send_summary"}, "request_call": {"type": "request_call"},
          "request_reevaluation": {"type": "request_reevaluation"}}
REAUTH_HREF = "/login"          # [assumption] the web's sign-in route (apps/web/app/login)

# §4.5 rows the graph reaches so far (T2, T3, T6); T4 and T5 add theirs. At most 3 chips, a person always reachable except
# right after connect_person.
ROWS: dict[str, tuple[str, ...]] = {
    "greet": ("report_unrecognized", "report_duplicate", "check_case"),
    "ask_details": ("show_recent", "dont_remember_amount", "talk_to_person"),
    "ask_options": ("none_of_these", "show_recent", "talk_to_person"),            # candidates shown as cards
    "confirm": ("confirm_yes", "confirm_no", "talk_to_person"),
    "case_active": ("view_case", "add_info", "request_call"),                     # AC-23: the existing case
    "read_failed": ("show_recent", "talk_to_person", "check_case"),   # the first chip searches again
    "planned": ("check_case", "report_another", "talk_to_person"),   # [assumption] a plan with no act yet, until T4
    "deny": ("report_unrecognized", "check_case", "talk_to_person"),
    "reauthenticate": ("reauthenticate", "talk_to_person"),
    "connect_person": ("report_another", "check_case", "report_duplicate"),     # no case: F-007 adds 2 text chips
    "connect_person_case": ("view_case", "report_another"),
    "connect_failed": ("talk_to_person", "check_case", "report_unrecognized"),     # the first chip retries the call
    # answer_status (task 04e). case_active above is also the active-case row; AC-24's re-evaluation row is not used
    # yet, so a finished case (or a status question with dispute words, F-010) offers to report another charge.
    "case_done": ("view_case", "report_another", "request_call"),
    "card_status": ("check_case", "report_unrecognized", "talk_to_person"),
    "status_none": ("report_unrecognized", "report_duplicate", "talk_to_person"),
    "status_failed": ("check_case", "talk_to_person", "report_unrecognized"),     # the first chip reads again
}

# What a typed (or pressed) text chip stands for when it was offered in the last reply (AC-32, proposed AC-33):
# its intent, or None for "the dispute already being clarified" (the pending question).
TEXT_CHIP_INTENT: dict[str, Optional[str]] = {
    "report_unrecognized": "unrecognized_charge", "report_duplicate": "wrongful_charge",
    "report_another": "unrecognized_charge", "check_case": "status_inquiry",
    "add_info": "status_inquiry",               # adds information to the active case (add_case_info, T6)
    "show_recent": None, "dont_remember_amount": None,
}


def amount_text(amount: float) -> str:
    """The tool's amount as written in replies: two decimals when that is exact, else every digit it has (AC-25)."""
    fixed = f"{amount:.2f}"
    return fixed if float(fixed) == amount else repr(amount)


def option_label(trx: dict[str, Any]) -> str:
    """An option card from search_transaction facts only (spec 01 §6.4 `options`): amount · date · merchant."""
    parts = [f"{trx['currency']} {amount_text(trx['amount'])}", str(trx["transaction_date"]), trx.get("merchant")]
    return " · ".join(part for part in parts if part)


def chip(chip_id: str, language: str, case_id: Optional[str] = None) -> Suggestion:
    leaf = messages()["suggest"][chip_id]
    href = (f"/case/{case_id}" if chip_id == "view_case" else REAUTH_HREF) if leaf["kind"] == "link" else None
    return Suggestion(id=chip_id, label=leaf[language], kind=leaf["kind"],
                      action=ACTION[chip_id] if leaf["kind"] == "action" else None, href=href)


def suggestions(row: str, language: str, case_id: Optional[str] = None) -> list[Suggestion]:
    return [chip(chip_id, language, case_id) for chip_id in ROWS[row]]


def offered_text_chip(message: str, offered: list[dict[str, Any]]) -> Optional[str]:
    """The id of the text chip offered in the last reply whose label equals `message` (case, accents and spacing
    ignored), or None."""
    def same(t: str) -> str:
        return fold(t).strip(" ¿?¡!.")
    for item in offered:
        if item.get("kind") == "text" and same(item["label"]) == same(message):
            return item["id"] if item["id"] in TEXT_CHIP_INTENT else None
    return None
