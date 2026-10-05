"""Access check for Resend: sends one test e-mail to an address you own.

    make check-resend ARGS="--to you@example.com"

Never use an address from the dataset (synthetic customers may map to real people).
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

from _common import fail, masked, ok, setting

KEY = setting("RESEND_API_KEY")
SENDER = setting("RESEND_FROM", "Nick of Time <updates@notify.nickoftime.salazarvalverdeai.com>")

parser = argparse.ArgumentParser()
parser.add_argument("--to", required=True, help="an address you own")
args = parser.parse_args()

payload = {
    "from": SENDER,
    "to": [args.to],
    "subject": "Nick of Time · prueba de acceso",
    "text": "Si recibes este correo, la configuración de Resend funciona. — Nick of Time (demo)",
}
request = urllib.request.Request(
    "https://api.resend.com/emails",
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
             "User-Agent": "nickoftime-access-check/1.0"},
)
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        body = json.load(response)
except urllib.error.HTTPError as exc:
    detail = exc.read().decode(errors="replace")[:300]
    fail(f"Resend answered HTTP {exc.code}: {detail} (key {masked(KEY)})")

ok(f"accepted by Resend (email id {body.get('id')}) from {SENDER} — check the inbox of the address you passed")
