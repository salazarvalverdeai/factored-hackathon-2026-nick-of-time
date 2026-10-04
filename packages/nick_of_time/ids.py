"""Identifier generation (spec 01 §6.7).

Transaction and product ids are never generated here: they come from gold unchanged (`TRX-…`, `PRD-…`).
"""
from __future__ import annotations

import re
import secrets
from typing import Literal

Kind = Literal["case", "action", "verification", "event", "receipt", "notification", "session"]

PREFIX: dict[str, str] = {"case": "K-", "action": "A-", "verification": "V-", "event": "E-", "receipt": "RC-",
                          "notification": "N-", "session": "S-"}

# Spec 01 fixes "K-" + 6 digits and "S-" + 16 url-safe characters. [assumption] The other kinds use 12 upper-case hex
# characters (48 random bits). A case id has only 10^6 values, so the store retries on a primary-key conflict.
PATTERN: dict[str, str] = {
    "case": r"^K-[0-9]{6}$",
    "session": r"^S-[A-Za-z0-9_-]{16}$",
    **{kind: rf"^{PREFIX[kind]}[0-9A-F]{{12}}$"
       for kind in ("action", "verification", "event", "receipt", "notification")},
}


def new_id(kind: Kind) -> str:
    """A fresh random identifier of the given kind; always matches PATTERN[kind]."""
    if kind == "case":
        return f"K-{secrets.randbelow(10**6):06d}"
    if kind == "session":
        return "S-" + secrets.token_urlsafe(12)       # 12 bytes → 16 url-safe characters
    return PREFIX[kind] + secrets.token_hex(6).upper()


def is_valid(kind: Kind, value: str) -> bool:
    return re.fullmatch(PATTERN[kind], value) is not None
