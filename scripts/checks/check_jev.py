"""Access check for TypeSafe Jev: lists the models the key can use, then asks one typed "choice" question in Spanish
and one in Portuguese.

    make check-jev

Request shape per https://docs.typesafe.ai/api.md (checked 2026-10-04): a question has `type`, `instructions` and
`criteria`; for a choice, `criteria` maps each option to its description. If the API answers 422, the validation
detail is printed so the request can be adjusted.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from _common import fail, masked, ok, setting

KEY = setting("TYPESAFE_API_KEY")
MODEL = setting("JEV_MODEL", "jev-1.13.0")
BASE = setting("JEV_API_URL", "https://api.typesafe.ai/v1")
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
           "User-Agent": "nickoftime-access-check/1.0"}
# The five intents of spec 11 (§3); descriptions are the criteria Jev scores each option against.
INTENTS = {
    "unrecognized_charge": "The customer does not recognize a charge on their card (possible fraud).",
    "wrongful_charge": "The customer recognizes the merchant but the charge is wrong: duplicated, wrong amount, "
                       "not delivered or cancelled.",
    "status_inquiry": "The customer asks about the status of an existing case, dispute or card block.",
    "human_request": "The customer asks to talk to a person or a human agent.",
    "out_of_scope": "Anything that is not about disputing a card charge.",
}
SAMPLES = {
    "es": "No reconozco un cargo de 1,250 pesos del 28 de mayo en una tienda que no conozco",
    "pt": "Não reconheço uma cobrança de 300 reais do dia 28 de maio numa loja que não conheço",
}


def call(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        fail(f"{path} answered HTTP {exc.code}: {detail} (key {masked(KEY)})")


names = [model["name"] for model in call("/models").get("models", [])]
ok(f"key accepted · models listed: {', '.join(names)} · pinned: {MODEL}")

for language, text in SAMPLES.items():
    payload = {
        "model": MODEL,
        "state": text,
        "questions": {"intent": {"type": "choice",
                                 "instructions": "What does the bank customer want in this message?",
                                 "criteria": INTENTS}},
    }
    started = time.perf_counter()
    body = call("/systemone", payload)
    ms = (time.perf_counter() - started) * 1000
    answer = body.get("answers", {}).get("intent", {})
    ok(f"[{language}] model {body.get('model')} chose {answer.get('choice')} "
       f"(confidence {answer.get('confidence')}) in {ms:.0f} ms · usage {body.get('usage')}")
