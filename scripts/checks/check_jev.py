"""Access check for TypeSafe Jev: one typed "choice" question in Spanish and one in Portuguese.

    make check-jev

Request shape per https://docs.typesafe.ai/api.md (state + model + typed questions). If the API answers 422,
the validation detail is printed so the request can be adjusted.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from _common import fail, masked, ok, setting

KEY = setting("TYPESAFE_API_KEY")
MODEL = setting("JEV_MODEL", "jev-1.13.0")
URL = setting("JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
INTENTS = ["unrecognized_charge", "wrongful_charge", "inquiry", "out_of_scope"]
SAMPLES = {
    "es": "No reconozco un cargo de 1,250 pesos del 28 de mayo en una tienda que no conozco",
    "pt": "Não reconheço uma cobrança de 300 reais do dia 28 de maio numa loja que não conheço",
}

for language, text in SAMPLES.items():
    payload = {
        "model": MODEL,
        "state": text,
        "questions": {"intent": {"type": "choice",
                                 "question": "What does the bank customer want in this message?",
                                 "options": INTENTS}},
    }
    request = urllib.request.Request(
        URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        fail(f"[{language}] Jev answered HTTP {exc.code}: {detail} (key {masked(KEY)})")
    ms = (time.perf_counter() - started) * 1000
    answer = body.get("answers", {}).get("intent", {})
    ok(f"[{language}] model {body.get('model')} chose {answer.get('choice')} "
       f"(confidence {answer.get('confidence')}) in {ms:.0f} ms · usage {body.get('usage')}")
