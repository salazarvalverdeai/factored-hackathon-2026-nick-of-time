"""Public demo sessions (lead decision D-068, ADR 0026): the scenario picker, the visitor's typed name and the run id
that gives every demo session a clean slate.

A scenario is one spec 09 demo customer (`eval/demo/customers.json`, served by the catalog) tagged with the dev and
sample cases (spec 09) written for that customer. Held-out cases are never read: a file or a set named `heldout` or
`test` is refused before it is opened. The visitor picks a scenario id or `auto`; the customer behind it is chosen
here, server-side, and the client never names one (constitution #3).
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import re
import secrets
import unicodedata
from pathlib import Path
from typing import Any, Optional

from nick_of_time.nlu.injection import injection_flagged
from nick_of_time.store import DEMO_RUN_PREFIX

EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"                # /srv/eval/... in the image
CASE_FILES = (EVAL_DIR / "cases/dev.jsonl", EVAL_DIR / "demo/sample_cases.jsonl")
ALLOWED_SETS = {"dev", "sample"}
FORBIDDEN = re.compile(r"heldout|held[-_ ]out|test", re.I)
NAME = re.compile(r"[^\W\d_]+(?:(?:[ '’-]+|\. +)[^\W\d_]+)*\.?")      # words joined by space ' ’ - or ". "
NAME_MAX = 40


def read_cases(path: Path) -> list[dict[str, Any]]:
    """The dev or sample rows of `path`; a held-out or test file or folder is refused without being opened (spec 09),
    and a row of another set is dropped."""
    path = Path(path)
    if FORBIDDEN.search(path.name) or FORBIDDEN.search(path.parent.name):
        raise ValueError(f"{path.name}: held-out and test cases are never read by the api")
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r.get("set", "sample" if "label" in r else None) in ALLOWED_SETS]


def scenarios(customers: list[dict[str, Any]], names: dict[str, Optional[str]],
              case_files: tuple[Path, ...] = CASE_FILES) -> list[dict[str, Any]]:
    """One scenario per demo customer, in file order, with the ids and types of its dev/sample cases."""
    cases: dict[str, list[dict[str, Any]]] = {}
    for path in case_files:
        for row in read_cases(path):
            owner = row.get("customer_id") or (row.get("initial_state") or {}).get("customer_id")
            cases.setdefault(owner, []).append(row)
    out, seen = [], {}
    for c in customers:
        seen[c["country"]] = seen.get(c["country"], 0) + 1
        mine = cases.get(c["customer_id"], [])
        out.append({"scenario_id": f"SCN-{c['country']}-{seen[c['country']]}", "title": c["scenario"],
                    "country": c["country"], "language": c["language"], "segment": c["segment"],
                    "customer_name": names.get(c["customer_id"]), "cases": [r["id"] for r in mine],
                    "tags": sorted({r.get("type") or r.get("label") for r in mine} - {None}),
                    "customer_id": c["customer_id"]})
    return out


def public(scenario: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in scenario.items() if k != "customer_id"}


def choose(all_scenarios: list[dict[str, Any]], scenario: Optional[str], country: Optional[str],
           language: str) -> Optional[dict[str, Any]]:
    """The scenario asked for (it must match the country when one is given), or for `auto`/none a random one of the
    country (any country when none is given), preferring the visitor's language. None when nothing matches."""
    if scenario not in (None, "auto"):
        found = next((s for s in all_scenarios if s["scenario_id"] == scenario), None)
        return found if found and country in (None, found["country"]) else None
    in_country = [s for s in all_scenarios if country in (None, s["country"])]
    pool = [s for s in in_country if s["language"] == language] or in_country
    return secrets.choice(pool) if pool else None


def clean_name(raw: Optional[str]) -> Optional[str]:
    """The typed name, trimmed, or None when blank; ValueError for anything that is not a plain name of at most 40
    characters: digits (a card number, a document), a URL, an e-mail, control characters or an injection attempt."""
    if raw is None:
        return None
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not name:
        return None
    if len(name) > NAME_MAX:
        raise ValueError(f"display_name is longer than {NAME_MAX} characters")
    if any(unicodedata.category(ch).startswith("C") for ch in raw) or not NAME.fullmatch(name):
        raise ValueError("display_name must be a plain name: letters, spaces, apostrophes, dots and hyphens only")
    if injection_flagged(name):
        raise ValueError("display_name must be a plain name")
    return name


def new_run_id(now: dt.datetime) -> str:
    """`demo-<UTC yyyymmddThhmmssZ>-<6 base32>`: a fresh run per demo session, so nothing of another run is seen."""
    stamp = now.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{DEMO_RUN_PREFIX}{stamp}-{base64.b32encode(secrets.token_bytes(5)).decode()[:6]}"
