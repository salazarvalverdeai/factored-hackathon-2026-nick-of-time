"""Set the Telegram bot's public profile: one English name, and description, short description and commands in
English (default) plus Spanish and Portuguese. Telegram shows each user the texts for their app language and falls back
to the default.

    make telegram-profile

Uses setMyName, setMyDescription, setMyShortDescription and setMyCommands with `language_code`
(https://core.telegram.org/bots/api#setmyname, checked 2026-10-04), then reads every value back. BotFather is still
needed for /newbot, /setprivacy and /setuserpic. Never prints the token.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "checks"))
from _common import fail, masked, ok, setting  # noqa: E402  (also loads the repo .env)

TOKEN = setting("TELEGRAM_BOT_TOKEN")
NAME = "Nick of Time · Case Updates"  # one name for every language
# "" is the default (English); Telegram limits: description ≤ 512, short description ≤ 120, command text ≤ 256.
TEXTS = {
    "": {
        "description": "Get a message every time your card dispute case changes status. Turn it on from your case "
                       "page. This bot only sends updates: it never asks for your card number, passwords or codes. "
                       "Nick of Time is a hackathon demo with synthetic data.",
        "short_description": "Status updates for your card dispute case · Nick of Time (hackathon demo)",
        "commands": {"start": "Get updates for your case", "stop": "Stop case updates"},
    },
    "es": {
        "description": "Recibe un mensaje cada vez que tu caso de disputa de tarjeta cambie de estado. Actívalo desde "
                       "la página de tu caso. Este bot solo envía avisos: nunca te pedirá el número de tu tarjeta, "
                       "contraseñas ni códigos. Nick of Time es una demo de hackathon con datos sintéticos.",
        "short_description": "Avisos del estado de tu caso de disputa · Nick of Time (demo de hackathon)",
        "commands": {"start": "Recibir avisos de tu caso", "stop": "Dejar de recibir avisos"},
    },
    "pt": {
        "description": "Receba uma mensagem sempre que o status do seu caso de contestação do cartão mudar. Ative pela "
                       "página do seu caso. Este bot só envia avisos: nunca vai pedir o número do seu cartão, senhas "
                       "nem códigos. Nick of Time é uma demo de hackathon com dados sintéticos.",
        "short_description": "Avisos do status do seu caso de contestação · Nick of Time (demo de hackathon)",
        "commands": {"start": "Receber avisos do seu caso", "stop": "Parar de receber avisos"},
    },
}


def call(method: str, payload: dict | None = None):
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read() or b"{}")
    if not body.get("ok"):
        fail(f"{method}: {body.get('description', 'unknown error')} (token {masked(TOKEN)})")
    return body["result"]


for lang, texts in TEXTS.items():
    assert len(texts["description"]) <= 512 and len(texts["short_description"]) <= 120, lang

me = call("getMe")
ok(f"token valid: bot @{me['username']}")
call("setMyName", {"name": NAME})
for lang, texts in TEXTS.items():
    commands = [{"command": c, "description": d} for c, d in texts["commands"].items()]
    call("setMyDescription", {"description": texts["description"], "language_code": lang})
    call("setMyShortDescription", {"short_description": texts["short_description"], "language_code": lang})
    call("setMyCommands", {"commands": commands, "language_code": lang})

    label = lang or "default"
    name = call("getMyName", {"language_code": lang})["name"] or f"{NAME} (default)"
    short = call("getMyShortDescription", {"language_code": lang})["short_description"]
    listed = [c["command"] for c in call("getMyCommands", {"language_code": lang})]
    if short != texts["short_description"] or listed != list(texts["commands"]):
        fail(f"[{label}] read-back differs from what was set")
    ok(f"[{label}] name '{name}' · short description set · commands /{' /'.join(listed)}")
