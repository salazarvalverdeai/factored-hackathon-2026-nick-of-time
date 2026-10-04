# Spec 01 — Integration contract + stubs

- **Feature:** the contract the three of us build against — folders, REST API, MCP tools, graph I/O, Postgres schema,
  customer receipt, evaluation hooks — plus stubs so nobody waits for anybody.
- **Status:** Draft
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** M
- **Challenge dimension:** AI Engineering, Technical Judgment
- **Depends on:** framework (#2) · **Enables:** 03, 05, 07, 08, 10, 13, 16 · **ADRs:** 0005, 0007, 0008, 0010, 0013, 0017
- **Issue:** #3 · **Approval:** all three (@salazarvalverdeai, @gianzk, @vldiego)

> Full profile: this spec *is* the contract. Contract version **1.0.0**; any change after approval is a PR that all
> three approve and that bumps the version (minor = additive, major = breaking).

---

## 1. Introduction
Option A (ADR 0008) splits the system into four deployables — **web**, **api**, **mcp**, **agent** — plus Postgres and
the read-only gold. Three people build them in parallel. This spec fixes every seam between them so each owner can
build and test alone against stubs, and the pieces fit when they meet.

```
browser ──► web (Next.js) ──► api (FastAPI) ──► LangGraph Platform: graph "dispute_intake" ──► mcp (FastMCP)
                                   │                                    │                         │
                                   └────────────► Postgres ◄────────────┼─────────────────────────┤
                                                                        └──► Bedrock               └──► gold (DuckDB, read-only)
```

## 2. User stories
- As **GianMarco**, I want the REST routes, their payloads and the Postgres schema fixed, so the web and api can be
  built before the agent exists.
- As **Diego**, I want the evaluation hooks and the final-state shape fixed, so the harness can run against a stub.
- As **Freddy**, I want the MCP tool contract and the graph I/O fixed, so the agent can be built against a fake MCP.

## 3. Acceptance criteria (EARS)
Copied from issue #3 (same numbers). Evidence: [T] test · [C] command · [U] screenshot · [D] file.

- **AC-01** — This spec shall fix the folder layout, the REST routes and their models, the MCP contract, the graph
  input and output (`TurnResult`), the Postgres schema, the `customer_receipt` contract, and `expected.receipt` plus the
  `customer_returns` type in `eval_case.schema.json`. · [D] this file
- **AC-02** — When the local stack starts (`docker compose -f infra/compose.dev.yml up`), `/api/health` and every route in
  §6.2 shall answer with this contract's shape, using fixture data. · [T] `tests/test_spec01_api_stub.py`
- **AC-03** — When the fake MCP server receives a call to any of the 7 tools, it shall answer with the model from
  `contracts/tools.py`. · [T] `tests/test_spec01_mcp_stub.py`
- **AC-04** — The echo graph shall return a valid `TurnResult` that includes a sample receipt that validates against
  `contracts/customer_receipt.schema.json`. · [T] `tests/test_spec01_graph_stub.py`
- **AC-05** — The spec PR shall carry the approvals of all three team members. · [U] PR review list
- **AC-06** — If a client sends a `session_id` or `customer_id` in a chat payload, then the api shall ignore it and use
  only the server-side session. · [T]

## 4. Functional requirements
- **FR-01** One shared Python package (`nick_of_time`) holds the contract models, the policy engine, the clock, the
  receipt builder and the Postgres store; every Python app imports it — nobody re-declares a contract model.
- **FR-02** Postgres is the only mutable state. Event tables are append-only; a case's status is its last
  `status_changed` event.
- **FR-03** The api is the only public entry for browsers. It proxies agent runs to Platform and injects the session.
- **FR-04** The mcp server is reachable only with an API key; every tool takes `session_id` and resolves the customer
  from Postgres.
- **FR-05** Evaluation hooks exist only when `EVAL_MODE=true` and are never deployed to production.
- **FR-06** Stubs implement every route and tool with fixtures so that each owner can develop offline.

## 5. Non-functional requirements
- **Performance:** api routes other than agent runs p95 < 300 ms; MCP tools p95 < 800 ms (`reliability.tool_timeout_ms`).
- **Security:** no secret in the repo or the browser; analyst routes require a Cognito JWT; customer routes require
  the `not_session` cookie (httpOnly, Secure, SameSite=Lax); MCP requires `X-API-Key`.
- **Observability:** every request carries `trace_id` (the LangGraph run id when there is one; otherwise a UUID) into
  `case_events`, `llm_calls` and `policy_denials`.
- **Time:** all business dates use `DEMO_TODAY` (ADR 0012); timestamps are UTC ISO-8601; dates `YYYY-MM-DD`.

## 6. Contracts

### 6.1 Repository layout and ownership
```
apps/
  web/                    Next.js app — @gianzk (page content: see specs 12, 04, E1)
  api/                    FastAPI app, package `api` — @gianzk
    migrations/           Postgres schema (Alembic) — @gianzk, schema fixed by §6.5
  mcp/                    FastMCP server, package `mcp_server` — @salazarvalverdeai
  agent/                  LangGraph graph, package `agent` — @salazarvalverdeai
packages/
  nick_of_time/           shared package — @salazarvalverdeai
    contracts.py          re-exports contracts/tools.py models + TurnResult + receipt models
    policy/               policy engine + regulatory clock (spec 02)
    store/                Postgres access used by api and mcp (tables of §6.5)
    receipt.py            deterministic receipt and handoff builders (ADR 0016)
    ids.py                identifier generation (§6.7)
contracts/                policies.yaml · tools.py · *.schema.json — source of truth (lead approves)
eval/                     cases, PROTOCOL.md, harness, results — @vldiego
infra/                    compose files, Caddyfile, deploy scripts — @gianzk
langgraph.json            Platform deployment of apps/agent — @salazarvalverdeai
```
The empty `apps/api/{audit,classifier,graph,policy,tools}/` folders from the scaffold are removed: the graph lives in
`apps/agent`, tools in `apps/mcp`, policy in `packages/nick_of_time/policy`.

### 6.2 REST API (`apps/api`, prefix `/api`)
OpenAPI is generated from the code at `/api/docs`; this table is the agreed contract. Errors always use
`{"code": "DENY|NOT_FOUND|SESSION_EXPIRED|UNAVAILABLE|INVALID", "policy_id": str|null, "message": str}`.

**Public and customer routes** (customer routes need the `not_session` cookie)

| Method | Path | Request | Response | Codes |
|---|---|---|---|---|
| GET | `/api/health` | — | `{status, version, git_sha, gold_version, policies_version, platform_revision, demo_today}` | 200 |
| GET | `/api/demo/customers` | — | `[{customer_id, display_name, country, segment, scenario, language}]` (6 demo customers, spec 09) | 200 |
| POST | `/api/sessions` | `{customer_id}` | `{session_id, otp_demo, expires_at}` — the OTP is shown on screen (mock, ADR 0017) | 201 / 404 |
| POST | `/api/sessions/{session_id}/verify` | `{otp}` | `{verified, expires_at}` + sets `not_session` cookie | 200 / 401 / 410 |
| * | `/api/agent/...` | LangGraph Server protocol subset: `POST threads`, `POST threads/{id}/runs/stream`, `GET threads/{id}/state` | proxied to Platform; `configurable.session_id` injected from the cookie; any client `session_id`/`customer_id` is dropped (AC-06) | 200 / 401 / 440 |
| GET | `/api/notifications` | — | `[{notification_id, case_id, event, channel, text, created_at}]` for the session's customer ("My notifications") | 200 / 440 |
| GET | `/api/cases/{case_id}` | — | `CaseView` (§6.6) if the case belongs to the session's customer | 200 / 403 / 404 / 440 |
| POST | `/api/cases/{case_id}/info` | `{text}` | `{event_id}` → event `customer_info_added` | 201 / 403 / 440 |
| POST | `/api/cases/{case_id}/call-request` | `{preferred_time?}` | `{event_id}` → event `call_requested` | 201 / 403 / 440 |
| POST | `/api/cases/{case_id}/channels/telegram` | — | `{deep_link, expires_at}` (one-time token, TTL 15 min) | 201 / 403 / 440 |
| POST | `/api/cases/{case_id}/channels/email` | `{email}` | `{confirmation_sent: true}` — confirmation link to that address | 202 / 400 / 403 / 440 |
| GET | `/api/channels/email/confirm` | `?token=` | redirect to `/case/{id}` with a confirmed banner | 302 / 410 |
| POST | `/api/telegram/webhook` | Telegram update; header `X-Telegram-Bot-Api-Secret-Token` | `{ok: true}` | 200 / 401 |

`440` = session expired (`SESSION_EXPIRED`), distinct from `401` (no session) so the UI can show "verify again".

**Analyst routes** (Cognito JWT in `Authorization: Bearer`; `actor_id` = token `sub`)

| Method | Path | Request | Response | Codes |
|---|---|---|---|---|
| GET | `/api/console/cases` | `?status=&zone=&country=` | `[CaseSummary]` (§6.6), sorted by SLA then zone | 200 / 401 |
| GET | `/api/console/cases/{case_id}` | — | `{case: CaseView, handoff: handoff.schema.json, events: [CaseEvent]}` | 200 / 401 / 404 |
| POST | `/api/cases/{case_id}/action` | `AnalystActionIn` (`contracts/tools.py`) | `AnalystActionOut` | 200 / 401 / 403 / 409 |
| GET | `/api/console/settings` | — | `{supervised_mode, score_provider, policies_version}` | 200 / 401 |
| PUT | `/api/console/settings` | `{supervised_mode}` | same as GET; event `settings_changed` with actor | 200 / 401 |

**Evaluation hooks** (only when `EVAL_MODE=true`; never in production) — see §6.8.

**Insight data for web pages:** static JSON files under `apps/web/public/data/` produced by scripts:
`evaluation_summary.json` (spec 10), `benchmark.json` (spec 15), `classifier.json` (spec 11), `pitch_numbers.json`,
`ops_kpis.json` (spec 14), `data_quality.json` (spec 12). Each file has `{generated_at, git_sha, source, data}`; the
shape of `data` is fixed in the producing spec.

### 6.3 MCP server (`apps/mcp`)
- **Endpoint:** `https://mcp.nickoftime.salazarvalverdeai.com/mcp`, streamable HTTP transport; header `X-API-Key`
  (value in SSM `/nickoftime/prod/MCP_API_KEY`). Locally `http://localhost:8100/mcp`.
- **Tools** — exactly the seven of `contracts/policies.yaml` `actors.customer.tools`, with the input/output models of
  `contracts/tools.py`:

| Tool | Input | Output | Writes |
|---|---|---|---|
| `search_transaction` | `SearchTransactionIn` | `SearchTransactionOut` | — |
| `get_fraud_score` | `GetFraudScoreIn` | `GetFraudScoreOut` | — |
| `compute_deadline` | `ComputeDeadlineIn` | `ComputeDeadlineOut` | — |
| `block_card` | `BlockCardIn` | `BlockCardOut` | `product_overrides`, `case_events` (`card_blocked`) |
| `open_case` | `OpenCaseIn` | `OpenCaseOut` | `cases`, `case_events` (`case_opened`) |
| `get_product_status` | `{session_id, product_id}` | `ProductStatusOut` | — |
| `get_case_status` | `{session_id, case_id}` | `CaseStatusOut` | — |

- **Errors:** every tool returns `ToolError` (`DENY`, `NOT_FOUND`, `SESSION_EXPIRED`, `UNAVAILABLE`) instead of raising;
  a `DENY` is also written to `policy_denials` with its `policy_id`.
- **Session:** each call loads `sessions` by `session_id`; expired or unverified → `SESSION_EXPIRED`. The
  `customer_id` never comes from the arguments.
- **Fault injection:** if the session row has `tool_faults` (set only by the eval seed, §6.8), the listed tools answer
  `UNAVAILABLE`.
- **Idempotency:** `block_card` and `open_case` store `idempotency_key` → result in `idempotency`; a repeated key
  returns the stored result without a second write.

### 6.4 Graph I/O (`apps/agent`, LangGraph Platform)
- **Graph id:** `dispute_intake` in `langgraph.json`. **Input:** `{"messages": [{"role": "user", "content": str}],
  "language": "es"|"pt"|null}`. **Config:** `configurable.session_id` (required, injected by the api) and
  `configurable.case_id` (optional, for a returning customer).
- **Output state** (`TurnResult`, also the last item of a streamed run):

```json
{
  "reply": "string — customer-facing, ES or PT",
  "language": "es | pt",
  "decision": "block_and_open_case | confirm | ask | handoff | deny | reauthenticate | escalate_unconfirmed_action | null",
  "zone": "high | medium | human | null",
  "intent": "unrecognized_charge | wrongful_charge | inquiry | out_of_scope | null",
  "intent_confidence": 0.0,
  "options": [{"id": "T-…", "label": "MXN 1,250.00 · 2026-05-28 · TIENDA X"}],
  "case_id": "K-… | null",
  "actions": [{"tool": "block_card", "action_id": "A-…", "accepted": true, "verified": true, "verification_id": "V-…"}],
  "receipt": "customer_receipt | null",
  "handoff": "handoff.schema.json object | null",
  "guardrails_triggered": ["G-IN-01"],
  "trace": [{"node": "understand", "status": "ok | deny | error", "ms": 412, "detail": "intent=unrecognized_charge conf=0.93"}],
  "trace_id": "uuid (Platform run id)"
}
```
- `receipt` is present whenever a case was opened; `handoff` whenever the case goes to `review`. Both are built by
  `nick_of_time.receipt` from the same verified facts (ADR 0016).

### 6.5 Postgres schema (owned by `apps/api/migrations`, used through `nick_of_time.store`)
Append-only tables are marked **AO** (no `UPDATE`/`DELETE`; enforced by grants and a test).

| Table | Columns (type) | Notes |
|---|---|---|
| `sessions` | `session_id` text PK · `customer_id` text · `otp_hash` text · `verified_at` timestamptz null · `expires_at` timestamptz · `language` text · `tool_faults` text[] · `created_at` | TTL 15 min |
| `cases` | `case_id` text PK · `customer_id` · `transaction_id` · `product_id` · `country` · `product_type` · `zone` · `dispute_type` · `credit_deadline` date null · `ruling_deadline` date null · `deadline_source` text · `trace_id` · `created_at` | static facts only |
| `case_events` **AO** | `event_id` text PK · `case_id` FK · `seq` int · `type` text · `actor` text · `payload` jsonb · `customer_visible` bool · `trace_id` · `created_at` | unique (`case_id`, `seq`) |
| `product_overrides` **AO** | `override_id` PK · `product_id` · `status` · `case_id` · `actor` · `created_at` | current status = latest row, else gold |
| `notifications` **AO** | `notification_id` PK · `case_id` · `customer_id` · `event` · `channel` (`log|telegram|email`) · `text` · `delivered` bool · `created_at` | |
| `customer_channels` **AO** | `channel_id` PK · `customer_id` · `channel` · `address` (chat id or e-mail) · `event` (`linked|confirmed|revoked`) · `created_at` | latest row per channel wins |
| `link_tokens` | `token` PK · `case_id` · `channel` · `expires_at` · `used_at` null | one-time |
| `idempotency` | `key` PK · `action` · `result` jsonb · `created_at` | |
| `policy_denials` **AO** | `denial_id` PK · `trace_id` · `session_id` · `policy_id` · `guardrail_id` · `detail` jsonb · `created_at` | |
| `llm_calls` **AO** | `call_id` PK · `trace_id` · `provider` · `model` · `tokens_in` · `tokens_out` · `latency_ms` · `cost_usd` numeric · `created_at` | |
| `settings_events` **AO** | `event_id` PK · `key` · `value` jsonb · `actor` · `created_at` | `supervised_mode` = latest |

**Case event types** (`case_events.type`, visible to the customer when marked ✓): `case_opened` ✓ · `card_blocked` ✓ ·
`block_verified` ✓ · `status_changed` ✓ · `handoff_emitted` · `analyst_action` · `customer_info_added` ✓ ·
`call_requested` ✓ · `notification_sent` · `receipt_issued` ✓ · `telegram_linked` ✓ · `email_confirmed` ✓.
Queue statuses (from `policies.yaml`): `new → verification | review → resolved → closed`.

### 6.6 View models (api)
- `CaseSummary`: `{case_id, customer_id, country, zone, queue_status, credit_deadline, ruling_deadline, sla_due_at,
  priority, tags, created_at}`.
- `CaseView`: `CaseSummary` + `{transaction: {transaction_id, amount, currency, date, merchant}, product_last4,
  receipt: customer_receipt|null, timeline: [{event_id, type, label, created_at}] (customer-visible only),
  deadline_countdown_days, channels: {telegram: bool, email: bool}}`.

### 6.7 Customer receipt (`contracts/customer_receipt.schema.json`, new)
```json
{
  "receipt_id": "RC-…", "case_id": "K-…", "language": "es | pt", "issued_at": "ISO-8601",
  "verified_facts": [{"fact": "string", "source_id": "T-… | P-… | V-… | K-…"}],
  "actions": [{"label": "Tarjeta bloqueada", "action_id": "A-…", "verified": true, "verified_at": "ISO-8601"}],
  "deadline": {"country": "MX", "product": "debit", "credit_deadline": "YYYY-MM-DD", "ruling_deadline": "YYYY-MM-DD", "deadline_source": "Banxico Circular 3/2012, art. 19 Bis 3"},
  "what_ai_did": "string (template)", "what_a_person_does": "string (template)",
  "next_steps": ["string"], "case_url": "https://nickoftime.salazarvalverdeai.com/case/K-…"
}
```
Required: `receipt_id, case_id, language, issued_at, verified_facts, actions, deadline, what_ai_did,
what_a_person_does`. Never contains score, policy ids or transcript (`notifications.never_send`).

**Identifiers** (`nick_of_time.ids`): case `K-` + 6 digits · action `A-` · verification `V-` · event `E-` ·
receipt `RC-` · notification `N-` · session `S-` + 16 url-safe chars · transaction `T-` and product `P-` come from gold.

### 6.8 Evaluation hooks (`EVAL_MODE=true` only)
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/eval/seed` | `eval_case.initial_state` | `{session_id, thread_id}` — creates the session (`verified|expired|none`), applies `fixtures` as overlays and `tool_faults` |
| GET | `/api/eval/final-state/{session_id}` | — | `FinalState` below |

`FinalState`: `{decision, zone, intent, product_status, case_open, case_id, queue_status, handoff_emitted,
receipt_issued, receipt_has_deadline, notifications: [event], guardrail_ids: [..], other_customer_data_exposed,
latency_ms, tokens_in, tokens_out, cost_usd}`. The harness drives turns through `/api/agent/...` with the seeded
session and compares `FinalState` against `expected`.

**Schema change (`eval/eval_case.schema.json`, minor):** add `"customer_returns"` to `type`; add
`expected.receipt: {"issued": bool, "has_deadline": bool}` and `initial_state.case_id` (for returning customers).

### 6.9 Configuration names
`DEMO_TODAY` · `DATABASE_URL` · `GOLD_PATH` / `GOLD_S3_URI` · `MCP_URL` · `MCP_API_KEY` · `LANGGRAPH_API_URL` ·
`LANGSMITH_API_KEY` · `LLM_PROVIDER` (`bedrock|anthropic|fake`) · `BEDROCK_MODEL_GRAPH` · `BEDROCK_MODEL_FAST` ·
`COGNITO_USER_POOL_ID` · `COGNITO_CLIENT_ID` · `TELEGRAM_BOT_TOKEN` · `TELEGRAM_WEBHOOK_SECRET` · `RESEND_API_KEY` ·
`EVAL_MODE`. Names only in `.env.example`; values in SSM (`/nickoftime/prod/*`) or the Platform deployment secrets.

## 7. Data model touched
Creates the Postgres schema of §6.5 and the receipt schema of §6.7; reads gold v1 (`gold/v1/` in S3, local
`data/gold/`) read-only; never reads `gold_eval`.

## 8. Assumptions and open questions (gate 1 — to close in this PR)
- **Q1 (all):** shared package name `nick_of_time` under `packages/` — OK?
- **Q2 (@gianzk):** `/chat` uses agent-chat-ui against the `/api/agent/...` proxy (LangGraph Server protocol), so the
  session is injected server-side — OK, or do you prefer a single `POST /api/chat/runs` SSE route?
- **Q3 (@gianzk):** Alembic for migrations under `apps/api/migrations` — OK?
- **Q4 (@vldiego):** `FinalState` and the seed hook are enough for the harness and the benchmark B2?
- **Q5 (all):** `440` for an expired session (vs `401` without session) — OK?
- Assumption: analysts and customers use the same origin (`nickoftime.salazarvalverdeai.com`); no CORS.
- Assumption: Platform reaches the MCP over the internet with the API key; locally `langgraph dev` + local MCP.

## 9. Out of scope
Real logic of policies (spec 02), tools (03), graph (04), backend persistence (05) and UIs (07, 08, 13, 16) —
only their seams and stubs.

## 10. Plan, tasks and verification
Implementation goes in `feat/01-integration-contract` after this spec is approved.
- [ ] T1 — `packages/nick_of_time` skeleton: `contracts.py` (re-export + `TurnResult`, `CustomerReceipt`, `FinalState`,
      view models), `ids.py` · covers AC-01
- [ ] T2 — `contracts/customer_receipt.schema.json` + `eval_case.schema.json` minor change + example cases updated ·
      covers AC-01, AC-04
- [ ] T3 — api stub: every route of §6.2 and §6.8 returning fixtures validated by the models · covers AC-02, AC-06
- [ ] T4 — fake MCP server: the 7 tools returning fixtures from `contracts/tools.py` models · covers AC-03
- [ ] T5 — echo graph `dispute_intake` returning a `TurnResult` with a sample receipt · covers AC-04
- [ ] T6 — `infra/compose.dev.yml` (api stub, mcp stub, postgres) and `.env.example` names of §6.9 · covers AC-02
- [ ] T7 — remove the empty `apps/api/{audit,classifier,graph,policy,tools}` folders
- [ ] T8 — tests `tests/test_spec01_*.py` citing AC-02, AC-03, AC-04, AC-06

**Closing checklist:** every AC has a passing test or check · status → Implemented · contract version recorded in
`/api/health` · lessons added to `CLAUDE.md`.
