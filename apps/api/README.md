# `apps/api` — FastAPI backend (spec 05)

`/api` in front of the case store: sessions with a mock OTP, case projections, analyst actions, notifications,
Telegram / e-mail channels and the proxy to the agent on LangGraph Platform. Routes and shapes: spec 01 §6.2.
Without a store (`DATABASE_URL` unset) `app.main:app` serves the fixture stub of spec 01.

```bash
make test                              # offline: MemoryStore, a local RSA key for the JWTs, fake Platform and notifier
DATABASE_URL=postgresql://… uvicorn app.main:app --app-dir apps/api    # store-backed api (schema: packages/nick_of_time/store/schema.sql)
```

| Variable | Used for |
|---|---|
| `DATABASE_URL` | Postgres of case state and audit (ADR 0010); selects the store-backed app |
| `COGNITO_ISSUER`, `COGNITO_CLIENT_ID` | analyst JWT check (issuer `https://cognito-idp.<region>.amazonaws.com/<pool id>`); unset = every analyst route answers 401 |
| `LANGGRAPH_URL`, `LANGSMITH_API_KEY`, `LANGGRAPH_ASSISTANT` | agent proxy; the key is sent only in the api's requests to Platform, never to the browser |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_NAME`, `TELEGRAM_WEBHOOK_SECRET`, `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, `EMAIL_FROM`, `PUBLIC_URL` | channels (spec 13) |
| `LINK_SIGNING_KEY` | signs the Telegram deep-link and e-mail confirmation tokens (falls back to the webhook secret) |
| `DEFAULT_SESSION_MODE`, `DEMO_TODAY`, `SCORE_PROVIDER`, `OTP_FIXED` | demo and time-mode knobs (ADR 0020); `OTP_FIXED` pins the mock OTP |

## Accounts

Customers are the six simulated demo customers (`GET /api/demo/customers`) with a mock OTP shown on screen
(ADR 0017). Analysts sign in with Cognito (user pool `nickoftime-analysts`, admin-created users only):

| Account | Role | Where it is used |
|---|---|---|
| `freddy`, `gianmarco`, `diego` | team analysts | `/console`, analyst actions |
| `judge` | the judges' account | the same console, for the evaluation |

Passwords are never written in the repository. The judge's password is stored in SSM
(`/nickoftime/prod/cognito/judge-password`) and goes only in the submission e-mail.
