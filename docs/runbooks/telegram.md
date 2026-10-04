# Runbook · Telegram bot

Customer notifications on every case status (spec 13, [ADR 0013](../adr/0013-customer-receives-proof-receipt-case-page-notifications.md)).
Facts verified against the official [Bot API](https://core.telegram.org/bots/api#setwebhook) and
[bot features](https://core.telegram.org/bots/features#deep-linking) documentation on 2026-10-04.

## 1. Create the bot (owner: lead)
1. In Telegram, open **@BotFather** (verified) → `/newbot`.
2. Name: **`Nick of Time · Case Updates`**. Username: **`NickOfTimeUpdatesBot`** (5–32 characters, must end in `bot`,
   case-insensitive). **Done on 2026-10-04:** the bot is [@NickOfTimeUpdatesBot](https://t.me/NickOfTimeUpdatesBot).
3. BotFather returns the **token**. Do not paste it anywhere except step 2.
4. In BotFather: `/setprivacy` → Enable (private chats only) and `/setuserpic` → `telegram-avatar-640.png` from the
   brand kit. The rest of the profile is set by `make telegram-profile` (step 3).

### Names and texts
The name is English for everyone. Description, short description ("About") and command texts are English by default,
with Spanish and Portuguese versions that Telegram shows according to the user's app language
([`language_code`](https://core.telegram.org/bots/api#setmydescription)). The texts live in
[`scripts/telegram_profile.py`](../../scripts/telegram_profile.py).

| Field (limit) | Default (EN) |
|---|---|
| Name (64) | Nick of Time · Case Updates |
| Short description (120) | Status updates for your card dispute case · Nick of Time (hackathon demo) |
| Description (512) | Get a message every time your card dispute case changes status. Turn it on from your case page. This bot only sends updates: it never asks for your card number, passwords or codes. Nick of Time is a hackathon demo with synthetic data. |
| `/start` | Get updates for your case |
| `/stop` | Stop case updates |

The description tells customers the bot never asks for card data: a bank bot that people learn to trust is also what
phishing copies, so the one rule they need is stated up front.

## 2. Store the values
Production (SSM):
```bash
aws ssm put-parameter --profile nickoftime --region us-east-2 --type SecureString \
  --name /nickoftime/prod/TELEGRAM_BOT_TOKEN --value '<token>' --tags Key=Project,Value=nickoftime
```
`/nickoftime/prod/TELEGRAM_WEBHOOK_SECRET` already exists (random, `A-Z a-z 0-9 _ -`).

Local `.env`:
```
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_BOT_USERNAME=NickOfTimeUpdatesBot
TELEGRAM_WEBHOOK_SECRET=<value from SSM>
```

## 3. Profile and access check
```bash
make telegram-profile
# OK    token valid: bot @NickOfTimeUpdatesBot
# OK    [default] name 'Nick of Time · Case Updates' · short description set · commands /start /stop
# OK    [es] …   OK    [pt] …
```
Then:
1. Open `https://t.me/<bot_username>` and send `/start` (a bot cannot message a user who has not started it).
2. Run:
```bash
make check-telegram ARGS=--send-test
# OK    token valid: bot @NickOfTimeUpdatesBot (id …)
# WARN  no webhook set yet (expected until spec 13 deploys /api/telegram/webhook)
# OK    test message delivered (message id …)
```
After the webhook is registered, `getUpdates` is disabled: use `make check-telegram ARGS="--send-test --chat-id <id>"`.

## How the product uses it (spec 13)
- **Linking:** one-time token (TTL 15 min) → `https://t.me/<bot>?start=<token>`; the parameter allows up to 64
  characters of `A-Z a-z 0-9 _ -`; the bot receives `/start <token>` and stores the `chat_id` (`telegram_linked`).
- **Webhook:** `setWebhook` to `https://nickoftime.salazarvalverdeai.com/api/telegram/webhook` with `secret_token`;
  Telegram sends it in `X-Telegram-Bot-Api-Secret-Token`; a mismatch returns 401. HTTPS only, ports 443/80/88/8443.
- **Unlinking:** `/stop` revokes the `chat_id`. Messages never include the score, policy ids or the transcript.

## If the token leaks
BotFather → `/revoke` → new token → update SSM and `.env` → rerun the check.
