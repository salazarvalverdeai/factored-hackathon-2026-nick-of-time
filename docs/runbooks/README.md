# Runbooks

Step-by-step guides to enable each external service. Every runbook ends the same way:

1. **Production value → AWS SSM** (`/nickoftime/prod/*`, SecureString). Paste secrets only into the command, never into
   chats, issues or files.
2. **Local value → your `.env`** (never committed; names listed in [`.env.example`](../../.env.example)).
3. **Access check → `make check-<service>`**. It reads `.env`, calls the service once, prints `OK`/`FAIL` and never
   prints a secret.

| Service | Runbook | Used by | Check |
|---|---|---|---|
| Amazon Bedrock (Claude) | [bedrock.md](bedrock.md) | specs 04, 11, 15 | `make check-bedrock` |
| Telegram bot | [telegram.md](telegram.md) | spec 13 | `make check-telegram ARGS=--send-test` |
| Resend (e-mail) | [resend.md](resend.md) | spec 13 | `make check-resend ARGS="--to you@example.com"` |
| TypeSafe Jev | [jev.md](jev.md) | specs 11, 15 | `make check-jev` |

**Values that already exist in SSM** (MCP key, webhook secret, Cognito ids, and later the bot token, Resend and Jev
keys) are copied into your `.env` with `make env-pull`; it never prints a value and never pulls the `cognito/*`
passwords.

Inventory of what exists and where each credential lives: [`docs/infrastructure.md`](../infrastructure.md).
