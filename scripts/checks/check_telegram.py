"""Access check for the Telegram bot.

    make check-telegram                       # token valid, bot username, webhook status
    make check-telegram ARGS=--send-test      # also sends a test message to the last chat that sent /start
                                              # (works before the webhook is set; after that pass --chat-id)
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

from _common import fail, masked, ok, setting, warn

TOKEN = setting("TELEGRAM_BOT_TOKEN")
EXPECTED_USERNAME = setting("TELEGRAM_BOT_USERNAME", required=False)


def call(method: str, payload: dict | None = None) -> dict:
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


parser = argparse.ArgumentParser()
parser.add_argument("--send-test", action="store_true")
parser.add_argument("--chat-id", type=int)
args = parser.parse_args()

me = call("getMe")
ok(f"token valid: bot @{me['username']} (id {me['id']})")
if EXPECTED_USERNAME and me["username"].lower() != EXPECTED_USERNAME.lower().lstrip("@"):
    fail(f"TELEGRAM_BOT_USERNAME is {EXPECTED_USERNAME} but the token belongs to @{me['username']}")

hook = call("getWebhookInfo")
if hook.get("url"):
    ok(f"webhook set to {hook['url']} · pending updates {hook.get('pending_update_count', 0)}")
    if hook.get("last_error_message"):
        warn(f"last webhook error: {hook['last_error_message']}")
else:
    warn("no webhook set yet (expected until spec 13 deploys /api/telegram/webhook)")

if args.send_test:
    chat_id = args.chat_id
    if chat_id is None:
        if hook.get("url"):
            fail("a webhook is set, so getUpdates is disabled: pass --chat-id")
        updates = call("getUpdates", {"limit": 20})
        starts = [u["message"]["chat"]["id"] for u in updates
                  if u.get("message", {}).get("text", "").startswith("/start")]
        if not starts:
            fail(f"no /start found: open https://t.me/{me['username']} and send /start, then retry")
        chat_id = starts[-1]
    sent = call("sendMessage", {"chat_id": chat_id, "text": "Nick of Time · prueba de acceso OK ✅"})
    ok(f"test message delivered (message id {sent['message_id']})")
