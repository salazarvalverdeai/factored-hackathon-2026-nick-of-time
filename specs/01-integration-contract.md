# Spec 01 — Integration contract + stubs

- **Feature:** the contract the three of us build against — folders, REST API, MCP tools, graph I/O, Postgres schema,
  customer receipt, evaluation hooks — plus stubs so nobody waits for anybody.
- **Status:** Draft (contract 1.6.0, updated 2026-10-05: 16 customer tools, two time modes, action states, delivery
  status, the store's §6.5 rules, the lead's 2026-10-05 follow-ups)
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** M
- **Challenge dimension:** AI Engineering, Technical Judgment
- **Depends on:** framework (#2) · **Enables:** 03, 05, 07, 08, 10, 13, 16 · **ADRs:** 0005, 0007, 0008, 0010, 0013, 0017, 0019,
  0020
- **Issue:** #3 · **Approval:** all three (@salazarvalverdeai, @gianzk, @vldiego)

> Full profile: this spec *is* the contract. Contract version **1.6.0** (1.0.0 was the first review draft; 1.1.0 adds
> the approved improvements #12–#16 before approval; 1.2.0 is additive: the handoff rules of §6.4, `GOLD_PATTERN`, the
> `zone_medium` and `supervised_mode` handoff reasons; 1.3.0 is additive, from task 01c, §6.5: the `action_verified`
> event type, `cases.opened_on` and the `on` business date of `status_changed` (D-023), an `action_id` on each customer
> write with the `V-` id minted only by its verifying read and post-condition, `block_verified` from that read,
> `verifications` and `action_write` (D-025, D-035), the analyst-action table (D-034) and the store's write rules;
> and `schema.sql` as the §6.5 DDL with its typing and null convention, `cases` insert-only (AO), `policy_denials`
> `session_id` null, `actor` and `run_id`, `llm_calls.run_id` (D-023), the unique action-id index and the row checks;
> 1.4.0 holds the follow-ups the lead confirmed on 2026-10-05: (1) D-052, a tool asked for another customer's record
> answers `NOT_FOUND` as for an unknown id and the refusal is still a `policy_denials` row with `POL-CROSS-CUSTOMER`
> and G-SES-02 (§6.3), and `search_transaction` answers `UNAVAILABLE` in `live` mode until `clock.today` lands;
> (2) `reliability.idempotency_key` in `policies.yaml` is the key `store.once` stores, `[{run_id}:]c={customer_id}:{key}`
> (§6.3, §6.5), from task 01g3 (PR #99), no decision id; (3) `ListMyCardsOut.read_at`, the listing's own reading
> time, set even with no cards, from the review of PR #104; (4) the `person_requested` handoff reason (D-029), which
> lands with PR #80; (5) the store's §6.5 additions of tasks 01g2 and 01g3 (PRs #87, #99): `idempotency` append-only
> with `args_hash` (a key replayed with other arguments is refused), `row_no` and the latest-row rule (highest
> `row_no`, never the latest `created_at`), `read` on `action_verified`, and the refusal of NUL and lone surrogates; and
> D-033's `score_source` and `score_version` in `handoff.schema.json`, already on main); 1.5.0 is additive, task DLANG:
> `deadline_source_label` on `ComputeDeadlineOut` and on the case deadlines of `get_case` (`open_case` leaves it
> null), the clock entry's `source_label` (`policies.yaml`) in the session's language, `es` by default, so the customer
> reads the legal source in Spanish or Portuguese from a tool result; `deadline_source` keeps the analyst's name;
> 1.6.0 is additive, D-068 (ADR 0026): the demo fields of `POST /api/sessions` (`display_name`,
> `language`, `country`, `scenario`), `GET /api/demo/scenarios` and `GET /api/sessions/{id}/recent-transactions`
> (§6.2), `sessions.display_name` and the `demo-…` `run_id` of every public session (§6.5), and demo runs with no
> Telegram or e-mail channel (§6.8).
> Any change after approval is a PR that all three approve and that bumps the version (minor = additive, major =
> breaking).

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
- **AC-03** — When the fake MCP server receives a call to any of the 16 tools of §6.3, it shall answer with the model
  from `contracts/tools.py`. · [T] `tests/test_spec01_mcp_stub.py`
- **AC-04** — The echo graph shall return a valid `TurnResult` that includes a sample receipt that validates against
  `contracts/customer_receipt.schema.json`. · [T] `tests/test_spec01_graph_stub.py`
- **AC-05** — The spec PR shall carry the approvals of all three team members. · [U] PR review list
- **AC-06** — If a client sends a `session_id` or `customer_id` in a chat payload, then the api shall ignore it and use
  only the server-side session. · [T]
- **AC-07** — When a session is created, its mode (`replay` or `live`) shall be stored and never change; every business
  date served for that session shall come from `clock.today(mode)`. · [T]
- **AC-08** — While a session is in `live` mode, `search_transaction` shall also return the customer's rows of
  `demo_transactions`, each flagged `synthetic: true`; the eval seed shall always create `replay` sessions. · [T]

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
- **Time:** all business dates use `clock.today(mode)` — `DEMO_TODAY` in `replay`, the real date in the customer's
  country time zone in `live` (ADR 0020; it supersedes ADR 0012). Timestamps are UTC ISO-8601; dates
  `YYYY-MM-DD`.

## 6. Contracts

### 6.1 Repository layout and ownership
```
apps/
  web/                    Next.js app — @gianzk (page content: see specs 12, 04, E1)
  api/                    FastAPI app, package `app` (`apps/api/app`) — @gianzk
    migrations/           Postgres schema (Alembic) — @gianzk, schema fixed by §6.5
  mcp/                    FastMCP server, package `mcp_server` — @salazarvalverdeai
  agent/                  LangGraph graph, package `agent` — @salazarvalverdeai
packages/
  nick_of_time/           shared package — @salazarvalverdeai
    contracts.py          re-exports contracts/tools.py models + TurnResult + receipt models
    policy/               policy engine + regulatory clock (spec 02)
    store/                `Store` interface used by api and mcp, in-memory backend, `postgres.py`, `accounts.py`
                          (sessions, denials, channels), `schema.sql` (§6.5)
    receipt.py            deterministic receipt and handoff builders (ADR 0016)
    ids.py                identifier generation (§6.7)
contracts/                policies.yaml · tools.py · *.schema.json — source of truth (lead approves)
eval/                     cases, PROTOCOL.md, harness, results — @vldiego
infra/                    compose files, Caddyfile, deploy scripts — @gianzk
langgraph.json            Platform deployment of apps/agent — @salazarvalverdeai
```
The empty `apps/api/{audit,classifier,graph,policy,tools}/` folders from the scaffold are removed: the graph lives in
`apps/agent`, tools in `apps/mcp`, policy in `packages/nick_of_time/policy`.
Every Python app runs on 3.13, the version CI tests, so `langgraph.json` sets `"python_version": "3.13"` (Platform
otherwise builds on 3.11). Every deployment of a Python app ships `contracts/`, because the package reads its JSON
schemas and `policies.yaml` at runtime.

### 6.2 REST API (`apps/api`, prefix `/api`)
OpenAPI is generated from the code at `/api/docs` (schema at `/api/openapi.json`); this table is the agreed contract. Errors always use
`{"code": "DENY|NOT_FOUND|SESSION_EXPIRED|UNAUTHENTICATED|UNAVAILABLE|INVALID", "policy_id": str|null, "message": str}`.

**Public and customer routes** (customer routes need the `not_session` cookie)

| Method | Path | Request | Response | Codes |
|---|---|---|---|---|
| GET | `/api/health` | — | `{status, version, contract_version, git_sha, gold_version, policies_version, platform_revision, models: {graph, fast}, prompt_hash, classifier_version, today: {replay, live}}` | 200 |
| GET | `/api/demo/customers` | — | `[{customer_id, display_name, country, segment, scenario, language}]` (6 demo customers, spec 09) | 200 |
| GET | `/api/demo/scenarios` | `?country=MX\|CO\|AR&language=es\|pt` | `[{scenario_id, title, country, language, segment, customer_name, cases, tags}]` — one per demo customer gold serves, tagged with its spec 09 dev/sample case ids (never held-out); no `customer_id`, score or zone (1.6.0, live app) | 200 |
| POST | `/api/sessions` | `{display_name?, language: "es"\|"pt", country?, scenario?: <scenario_id>\|"auto", mode?}`; the original `{customer_id, mode}` still works (1.6.0) | `{session_id, mode, today, otp_demo, expires_at}` — the OTP is shown on screen (mock, ADR 0017); the server chooses the customer from the scenario and every session gets a fresh `demo-…` `run_id` (ADR 0026) | 201 / 400 / 404 / 422 |
| GET | `/api/sessions/{session_id}/recent-transactions` | `?limit=1..20` (default 10) | `[{transaction_id, date, amount, currency, merchant, last4}]` — the cookie session's own latest card transactions up to its `today`, no score (1.6.0, live app) | 200 / 401 / 404 |
| POST | `/api/sessions/{session_id}/verify` | `{otp}` | `{verified, expires_at}` + sets `not_session` cookie | 200 / 401 / 404 / 410 |
| * | `/api/agent/...` | LangGraph Server protocol subset: `POST threads`, `POST threads/{id}/runs/stream`, `GET threads/{id}/state` | proxied to Platform; `configurable.session_id` injected from the cookie; any client `session_id`/`customer_id` is dropped (AC-06); the stream carries SSE events `progress` (`ProgressItem`), `turn` (`CustomerTurn`) and `error` (the standard error shape), and `threads/{id}/state` returns the last `CustomerTurn`, never the raw thread state (D-013). A thread belongs to the session that created it: an unknown or foreign thread is 404. `[assumption]` (pending the lead) the two POST routes answer 401 `UNAUTHENTICATED` only for a missing or unknown cookie; a known session in any state is forwarded with `configurable.session_state` = `verified\|expired\|unverified` and the graph decides `reauthenticate` (spec 02 AC-07), whose turn carries no case, receipt or action claim, only the session line and the chips per spec 04 §4.5 (G-SES-01). `GET threads/{id}/state` is not forwarded: an expired session gets 401 `SESSION_EXPIRED` and an unverified one 401 `UNAUTHENTICATED`, with no turn | 200 / 401 / 404 |
| GET | `/api/notifications` | — | `[{notification_id, case_id, event, channel, masked_address, text, delivery_status, created_at}]` for the session's customer ("My notifications"); `delivery_status` = `queued\|sent\|delivered\|bounced\|failed` | 200 / 401 |
| GET | `/api/me/products` | — | `[ProductView]` (§6.6) — "My cards", read fresh on each call | 200 / 401 |
| GET | `/api/me/cases` | — | `[CustomerCaseSummary]` (§6.6) — the customer's cases, active first | 200 / 401 |
| PUT | `/api/me/preferences` | `{display_currency?, language?}` | the stored preferences (kept in the session) | 200 / 400 / 401 |
| GET | `/api/cases/{case_id}` | — | `CustomerCaseView` (§6.6) if the case belongs to the session's customer | 200 / 403 / 404 / 401 |
| POST | `/api/cases/{case_id}/info` | `{text}` | `{event_id}` → event `customer_info_added` | 201 / 403 / 404 / 401 |
| POST | `/api/cases/{case_id}/call-request` | `{preferred_time?}` | `{event_id, expected_contact_by}` → event `call_requested`; `expected_contact_by` is `YYYY-MM-DD` or `null`, from `contact.callback_within_business_days` and stored in the event (D-008, spec 03 AC-18) | 201 / 403 / 404 / 401 |
| POST | `/api/cases/{case_id}/reevaluation` | `{reason}` | `{event_id, case_id}` — a resolved case returns to `review`; a closed case gets a new case with `related_case_id` (spec 03) | 201 / 403 / 404 / 409 / 401 |
| POST | `/api/cases/{case_id}/channels/telegram` | — | `{deep_link, expires_at}` (one-time token, TTL 15 min) | 201 / 403 / 404 / 401 |
| POST | `/api/cases/{case_id}/channels/email` | `{email}` | `{confirmation_sent: true}` — confirmation link to that address | 202 / 400 / 403 / 404 / 401 |
| GET | `/api/channels/email/confirm` | `?token=` | redirect to `/case/{id}` with a confirmed banner | 302 / 410 DENY (unknown, used or expired token) |
| POST | `/api/telegram/webhook` | Telegram update; header `X-Telegram-Bot-Api-Secret-Token` | `{ok: true}` | 200 / 401 |
| POST | `/api/resend/webhook` | Resend e-mail event (`email.sent`, `email.delivered`, `email.bounced`, `email.failed`, …); headers `svix-id`, `svix-timestamp`, `svix-signature` verified with `RESEND_WEBHOOK_SECRET` | `{ok: true}` → row in `notification_deliveries` | 200 / 401 |

An expired session returns the standard `401` with `code: "SESSION_EXPIRED"` in the error body; a missing session returns
`401` with `code: "UNAUTHENTICATED"`. The UI reads `code` to show "verify again" instead of a login screen. Errors on customer routes always carry `policy_id: null` (D-013, `notifications.never_send`); the id is logged server-side. Validation errors answer `400 INVALID`.

`[assumption]` (D-013, default pending the lead) Customer routes emit only customer projections, so score, policy ids
and transcript never reach the browser (`notifications.never_send`): `CustomerTurn` (§6.4) and `CustomerCaseView`
(§6.6). `TurnResult` and `CaseView` stay inside the api, the agent, the eval hooks and the analyst console.

**Analyst routes** (Cognito JWT in `Authorization: Bearer`; `actor_id` = token `sub`)

| Method | Path | Request | Response | Codes |
|---|---|---|---|---|
| GET | `/api/console/cases` | `?status=&zone=&country=` | `[CaseSummary]` (§6.6), sorted by SLA then zone | 200 / 401 |
| GET | `/api/console/cases/{case_id}` | — | `{case: CaseView, handoff: handoff.schema.json, events: [CaseEvent]}` | 200 / 401 / 404 |
| POST | `/api/cases/{case_id}/action` | `AnalystActionIn` (`contracts/tools.py`) | `AnalystActionOut` | 200 / 401 / 403 / 409 |
| GET | `/api/console/settings` | — | `{supervised_mode, score_provider, policies_version}` | 200 / 401 |
| PUT | `/api/console/settings` | `{supervised_mode}` | same as GET; event `settings_changed` with actor | 200 / 401 |
| POST | `/api/console/demo/reset` | — | `{demo_transactions, sample_cases}` — regenerates the live-mode synthetic transactions and re-seeds the processed sample cases (spec 05) | 200 / 401 |

**Evaluation hooks** (only when `EVAL_MODE=true`; never in production) — see §6.8.

**Insight data for web pages:** static JSON files under `apps/web/public/data/` produced by scripts:
`evaluation_summary.json` (spec 10), `benchmark.json` (spec 15), `classifier.json` (spec 11), `pitch_numbers.json`,
`ops_kpis.json` (spec 14), `data_quality.json` (spec 12). Each file has `{generated_at, git_sha, source, data}`; the
shape of `data` is fixed in the producing spec.

### 6.3 MCP server (`apps/mcp`)
- **Endpoint:** `https://mcp.nickoftime.salazarvalverdeai.com/mcp`, streamable HTTP transport; header `X-API-Key`
  (value in SSM `/nickoftime/prod/MCP_API_KEY`). Locally `http://localhost:8100/mcp` (container port 8001, spec 06).
- **Tools** — exactly the 16 of `contracts/policies.yaml` `actors.customer.tools`; each has `<Name>In` / `<Name>Out`
  models in `contracts/tools.py` (v1.1; spec 03 fixes their behavior). Kind: R read · W write · N notification.

| Tool | Kind | Purpose | Writes | Verified with |
|---|---|---|---|---|
| `get_customer_profile` | R | First name, language, country, display currency, confirmed channels | — | — |
| `search_transaction` | R | Find the disputed charge (gold; plus `demo_transactions` in `live`) | — | — |
| `get_fraud_score` | R | The bank's score with its source and version | — | — |
| `compute_deadline` | R | Legal deadline for a new case, with `source_url`, `verified_on` and `deadline_source_label` in the session's language (1.5.0) | — | — |
| `open_case` | W | Open the case; no duplicate active case; closed case → new case with `related_case_id` | `cases`, `case_events` (`case_opened`) | `get_case` |
| `block_card` | W | Block the card | `product_overrides`, `case_events` (`card_blocked`) | `get_product_status` |
| `get_product_status` | R | One card: type, last 4, status, `read_at`; `action_id` + `verification_id` only when called with a write's `action_id` (D-025) | — | — |
| `list_my_cards` | R | The customer's cards with status; never a `V-` (plain reads); the listing's own `read_at`, set even with no cards (1.4.0) | — | — |
| `get_case` | R | Customer view of a case: status label, stored deadlines with source, `deadline_source_label` in the session's language (1.5.0) and `deadline_verified_on`, visible timeline, `taken_by_person`, `related_case_id`, `read_at` (replaces `get_case_status`) | — | — |
| `list_my_cases` | R | The customer's cases | — | — |
| `add_case_info` | W | Customer adds information to an active case | `case_events` (`customer_info_added`) | `get_case` |
| `request_call` | W | Customer asks a person to call; with no `case_id` it is reported only as `requested`, since no read verifies it (D-026) | `case_events` (`call_requested`); with no case, a `call_requests` row (task 03d) | `get_case` |
| `request_reevaluation` | W | Re-evaluate a resolved case (→ `review`) or open a related case for a closed one | `case_events` (`reevaluation_requested`) or `cases` | `get_case` |
| `convert_amount` | R | Amount in the display currency, with rate, source and date | — | — |
| `send_case_summary` | N | Send the receipt template to a confirmed channel | `notifications`, `case_events` (`notification_sent`) | `list_my_notifications` |
| `list_my_notifications` | R | Notifications with masked address and delivery status | — | — |

  The analysts' actions (approve credit, unblock, close, reopen) stay in the api behind Cognito and never appear in
  the MCP.
  `[assumption]` (D-014, pending the lead): the `open_case` and `get_case` results carry `deadline_verified_on`
  with the stored deadline, so a receipt re-sent later can fill `deadline.verified_on` (§6.7, ADR 0019).
  `contracts/tools.py` lists them in `CUSTOMER_TOOLS` (name → models) and `VERIFIED_WITH` (the column above). A W or N
  result says at most `state: "requested"` and carries no `V-` id; the verifying read mints `verification_id` with
  `read_at` (D-025 `[assumption]`, §6.5). The verifying reads take an optional `action_id` (the write they check)
  and return it with a `verification_id` only when its post-condition holds; a plain status read returns `read_at`
  only. `search_transaction` returns no `fraud_score` or `split`: the zone comes only
  from `get_fraud_score` (D-026 `[assumption]`). The fake server (`apps/mcp/mcp_server/fake.py`) answers each tool
  with fixtures built from these models. **Compatibility:** inputs forbid unknown fields (G-TOOL-01), while a
  consumer of an output ignores a field it does not know (the published output schema stays closed), so an additive
  minor version is backward compatible for consumers: the MCP server, deployed on merge, may run one minor version
  ahead of the agent revision on Platform, deployed by hand, and a new output field never fails an older agent.

- **Errors:** every tool returns `ToolError` (`DENY`, `NOT_FOUND`, `SESSION_EXPIRED`, `UNAVAILABLE`) instead of raising;
  a `DENY` is also written to `policy_denials` with its `policy_id`. A request for another customer's transaction,
  card or case answers the same `NOT_FOUND` as an unknown id, with `policy_id: null`, so it never reveals that the
  record exists; the refusal is still written to `policy_denials` with `POL-CROSS-CUSTOMER` and G-SES-02 (D-052,
  `scope.cross_customer_request: deny_and_log`). That write is best-effort: if it fails, the error is logged and the
  answer stays the same `NOT_FOUND`, never `UNAVAILABLE`, which would reveal the record.
- **Session:** each call loads `sessions` by `session_id`; expired or unverified → `SESSION_EXPIRED`. The
  `customer_id` never comes from the arguments.
- **Fault injection:** if the session row has `tool_faults` (set only by the eval seed, §6.8), the listed tools answer
  `UNAVAILABLE`.
- **Idempotency:** every W and N tool stores `idempotency_key` → result in `idempotency`; a repeated key returns the
  stored result without a second write. The stored key is `policies.yaml` `reliability.idempotency_key`,
  `[{run_id}:]c={customer_id}:{key}`: `{key}` is the call's `idempotency_key`, the customer comes from the session and
  the run prefix is present only with a `run_id` (§6.5, 1.4.0).
- **Mode:** each call reads `sessions.mode`; tools never read the system clock (AC-07, AC-08). Until `clock.today`
  lands (spec 02 T7), `search_transaction` answers `UNAVAILABLE` in `live` mode rather than an empty list (D-052);
  AC-08's `demo_transactions` rows stay P1.

### 6.4 Graph I/O (`apps/agent`, LangGraph Platform)
- **Graph id:** `dispute_intake` in `langgraph.json` (the real graph, spec 04; the T5 echo graph is `dispute_intake_echo`). **Input:** `{"messages": [{"role": "user", "content": str}],
  "language": "es"|"pt"|null, "action": {"type": "confirm|choose_option|verify_now|request_call|request_reevaluation|send_summary", "value": str}|null}`
  — `action` carries a button or chip press and skips the classifier (`confirm` takes `yes|no`, `choose_option` takes a
  transaction id or `none`). **Config** (injected by the api, never by the client):
  `configurable.session_id` (required), `configurable.session_state`, `configurable.mode`, `configurable.arm` and
  `configurable.case_id` (optional, for a returning customer); `configurable.llm_day_spent_usd` and
  `configurable.llm_day_cap_usd` (optional: the day's `llm_calls` spend and the G-OPS-01 daily cap, spec 05 AC-18).
- **Output state** (`TurnResult`, also the last item of a streamed run):

```json
{
  "reply": "string — customer-facing, ES or PT",
  "language": "es | pt",
  "decision": "block_and_open_case | confirm | ask | handoff | answer_status | connect_person | deny | reauthenticate | escalate_unconfirmed_action | null",
  "zone": "high | medium | human | null",
  "intent": "unrecognized_charge | wrongful_charge | status_inquiry | human_request | out_of_scope | null",
  "intent_confidence": 0.0,
  "options": [{"id": "TRX-…", "label": "USD 1,250.00 · 2026-05-31 · TIENDA X"}],
  "case_id": "K-… | null",
  "plan": ["Bloquear tu tarjeta ····4417", "Abrir tu caso y calcular tu fecha límite", "Enviarte el comprobante"],
  "progress": [{"step": "block_card", "label": "Bloqueando tu tarjeta…", "state": "verified", "at": "ISO-8601"}],
  "actions": [{"tool": "block_card", "action_id": "A-…", "state": "in_progress | requested | verified | not_confirmed", "verification_id": "V-… | null", "read_at": "ISO-8601 | null"}],
  "suggestions": [{"id": "view_case", "label": "Ver mi caso", "kind": "link", "href": "/case/K-…"},
                  {"id": "send_summary", "label": "Enviarme el comprobante", "kind": "action", "action": {"type": "send_summary"}},
                  {"id": "request_call", "label": "Que me llame una persona", "kind": "action", "action": {"type": "request_call"}}],
  "receipt": "customer_receipt | null",
  "handoff": "handoff.schema.json object | null",
  "guardrails_triggered": ["G-IN-01"],
  "denials": [{"policy_id": "…", "guardrail_id": "G-IN-01", "detail": "…"}],
  "usage": [{"provider": "bedrock", "model": "…", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "cost_usd": 0.0}],
  "mode": "replay | live",
  "trace": [{"node": "understand", "status": "ok | deny | error", "ms": 412, "detail": "intent=unrecognized_charge conf=0.93"}],
  "trace_id": "uuid (Platform run id)"
}
```
- `receipt` is present whenever a case was opened; `handoff` whenever the case goes to `review`. Both are built by
  `nick_of_time.receipt` from the same verified facts (ADR 0016).
- `progress` items are also streamed as custom events while the run is in progress (spec 04 AC-17);
  `answer_status` and `connect_person` come from spec 02 rules 3a–3b.
- `suggestions` holds 2 or 3 chips chosen by rules (spec 04 §4.5): `kind` is `text` (the web sends `label` as the next
  message), `action` (the web sends `action` as the next input) or `link` (`href` is an internal route set by the
  server: a `/` path of URL-safe characters, so never `//`, `/\`, a tab or a newline). The web shows them only under
  the last reply. The four action states are the only vocabulary for an action, in every surface; a `verified` action
  carries `verification_id` and `read_at`, and a `progress` item says `verified` only when `actions[]` holds a
  verified record of the same tool (`step` = `tool`). `options` holds at most `clarify.max_candidate_transactions`.
  `handoff` is validated against `handoff.schema.json` with formats checked: an action with `verified: true` needs a
  `V-` `verification_id`, and a deadline with a date needs an `https://` `source_url` and `verified_on` (no date, as
  for `POL-CLOCK-UNKNOWN`, needs neither).
- `CustomerTurn` = `TurnResult` without `handoff`, `zone`, `usage`, `trace` and `denials[].policy_id`
  (`TurnResult.for_customer()`); it is the only shape the browser receives (D-013 `[assumption]`, §6.2).
  `G-…` guardrail ids may appear in the chat; `notifications.never_send.policy_ids` means `POL-…` rule ids; receipts
  and notifications carry neither. `denials[].detail` comes only from a `messages.yaml` template, never from engine
  output.

### 6.5 Postgres schema (DDL in `packages/nick_of_time/store/schema.sql`, used through `nick_of_time.store`)
`apps/api/migrations` adopts `schema.sql` as its first migration (D-002); a test keeps the file in step with this
table. A column the table leaves untyped is `text` (timestamps `timestamptz`, counters `integer`) and a column is
`not null` unless marked `null` `[assumption]`. Append-only tables are marked **AO** (no `UPDATE`, `DELETE` or
`TRUNCATE`; enforced by a trigger in `schema.sql` and a test). The **latest** row of `product_overrides`,
`customer_channels` (per channel), `notification_deliveries` or `settings_events` is the one inserted last, the
highest `row_no` (the in-memory backend's insertion order), never the latest `created_at`, which a fixed or skewed
clock can repeat or step back `[assumption]`. `list_cases` breaks a `created_at` tie by `case_id` and
`list_notifications` by `notification_id`, both descending, and `list_denials` (oldest first) by `denial_id`, in both
backends `[assumption]`. "Sub not blank" means a character outside Python's `str.isspace()` set, spelled out in the
actor CHECKs so no server locale changes it; their `(?p)` keeps a newline out of the sub, as in the store's `ACTOR`.

| Table | Columns (type) | Notes |
|---|---|---|
| `sessions` | `session_id` text PK · `customer_id` text null · `otp_hash` text · `verified_at` timestamptz null · `expires_at` timestamptz · `language` text · `mode` text (`replay\|live`) · `display_currency` text null · `tool_faults` text[] · `run_id` text null · `arm` text null · `display_name` text null · `created_at` | TTL 15 min; `mode` fixed at creation; `run_id` set by the eval seed or, as `demo-…`, by every public session (ADR 0026, 1.6.0); `arm` by the eval seed or `DEFAULT_ARM`; `display_name` is the name a demo visitor typed (1.6.0) |
| `cases` **AO** | `case_id` text PK · `customer_id` · `transaction_id` · `product_id` · `country` · `product_type` · `zone` · `dispute_type` · `opened_on` date · `credit_deadline` date null · `ruling_deadline` date null · `deadline_source` text null · `deadline_source_url` text null · `deadline_verified_on` date null · `related_case_id` text null · `mode` text · `run_id` text null · `trace_id` · `created_at` | static facts only, insert-only (spec 03 AC-16; AO `[assumption]` D-023); `opened_on` is the business date of the notice (`clock.today(mode, country)`; the eval seed passes `initial_state.case.opened_on`) and `created_at` the audit time in every mode `[assumption]` (D-023); `deadline_verified_on` `[assumption]` (D-014), null only when both dates are null, like `deadline_source` (never empty) and `deadline_source_url` (always `https://` and a host, no whitespace); `mode`, `zone`, `product_type` and `dispute_type` take only the store model's values; `case_id` from `ids.new_id("case")` has 10^6 values, so the insert retries on a PK conflict (T9, §10) |
| `demo_transactions` | same columns as gold `transactions`, `transaction_id` PK · `synthetic` bool (always true) · `scenario` text · `generated_at` | `live` mode only; deleted and regenerated by "Reset demo"; never copied to gold, lakehouse or eval. `transaction_id` follows `ids.GOLD_PATTERN["transaction"]` and is drawn again if it clashes with gold; rows are told apart by `synthetic`, not by an id prefix (32 gold ids already start with `TRX-SYN` `[data]`) |
| `case_events` **AO** | `event_id` text PK · `case_id` FK · `seq` int · `type` text · `actor` text · `payload` jsonb · `customer_visible` bool · `trace_id` · `created_at` | unique (`case_id`, `seq`), `seq` ≥ 1; `actor` is `agent\|customer\|system\|analyst:<sub>` (sub not blank); `customer_visible` follows the ✓ list; `status_changed` needs `payload.to` (a status of `case_queue.transitions`); the five write types other than `notification_sent`, `action_verified` and `block_verified` need `payload.action_id`, every `payload.action_id` is an `A-` id and `action_verified` carries a `V-` `verification_id`; `analyst_action`, `assigned` and a `status_changed` to `resolved` or `closed` need an `analyst:` actor; `payload->>'action_id'` unique over the six write types (`case_opened`, `card_blocked`, `customer_info_added`, `call_requested`, `reevaluation_requested`, `notification_sent`), so one read never verifies two actions `[assumption]` (D-025) |
| `product_overrides` **AO** | `override_id` PK · `product_id` · `status` · `case_id` · `actor` · `run_id` text null · `created_at` · `row_no` bigint identity | `status` is `Active\|Blocked\|Closed\|Suspended` and `actor` as in `case_events`; current status = latest row **for the same `run_id`**, else gold; `override_id` is the `action_id` of the write `[assumption]` (D-025) |
| `notifications` **AO** | `notification_id` PK · `case_id` · `customer_id` · `event` · `channel` (`log\|telegram\|email`) · `masked_address` null · `text` · `trigger` (`auto\|on_request`) · `provider_message_id` null · `created_at` | |
| `notification_deliveries` **AO** | `delivery_id` PK · `notification_id` FK · `status` (`queued\|sent\|delivered\|bounced\|failed`) · `provider_event` jsonb null · `created_at` · `row_no` bigint identity | delivery status = latest row |
| `customer_channels` **AO** | `channel_id` PK · `customer_id` · `channel` · `address` (chat id or e-mail) · `event` (`linked\|confirmed\|revoked`) · `created_at` · `row_no` bigint identity | latest row per channel wins |
| `call_requests` **AO** | `event_id` text PK · `action_id` · `customer_id` · `session_id` · `preferred_time` text null · `expected_contact_by` date null · `run_id` text null · `trace_id` · `created_at` | a `request_call` with no case (D-026, task 03d): no case event and no verifying read, so it stays `requested`; `event_id` is the `E-` id the tool returns; `action_id` is an `A-` id used once; `expected_contact_by` is stored, never recomputed (D-008) |
| `link_tokens` | `token` PK · `case_id` · `channel` · `expires_at` · `used_at` null | one-time |
| `idempotency` **AO** | `key` PK · `action` · `result` jsonb · `run_id` text null · `created_at` · `args_hash` | the key is prefixed with `run_id` when present, then the scope `c=<customer_id>` (`-` for the api); `args_hash` is the sha256 of the call's canonical arguments and a key replayed with other arguments is refused `[assumption]` |
| `policy_denials` **AO** | `denial_id` PK · `trace_id` · `session_id` text null · `actor` (`agent\|customer\|analyst:<sub>`) · `policy_id` · `guardrail_id` · `detail` jsonb · `run_id` text null · `created_at` | `actor` is a closed list (no `system`; sub not blank); `session_id` null for an api or analyst denial; a rule-only denial cites `G-POL-01` (writers map a missing guardrail id to it) `[assumption]` (D-023) |
| `llm_calls` **AO** | `call_id` PK · `trace_id` · `provider` · `model` · `tokens_in` · `tokens_out` · `latency_ms` · `cost_usd` numeric · `run_id` text null · `created_at` | `run_id` from the session, so a run's tokens and cost sum alone `[assumption]` (D-023) |
| `settings_events` **AO** | `event_id` PK · `key` · `value` jsonb · `actor` · `created_at` · `row_no` bigint identity | `supervised_mode` = latest row |

**Case event types** (`case_events.type`, visible to the customer when marked ✓): `case_opened` ✓ · `card_blocked` ✓ ·
`block_verified` ✓ · `action_verified` (D-025) · `status_changed` ✓ · `handoff_emitted` · `assigned` ✓ (a person took
the case) · `analyst_action` · `customer_info_added` ✓ · `call_requested` ✓ · `reevaluation_requested` ✓ ·
`related_case_opened` ✓ · `notification_sent` ✓ · `receipt_issued` ✓ · `telegram_linked` ✓ · `email_confirmed` ✓.
Queue statuses (from `policies.yaml`): `new → verification | review → resolved → closed`. A case's status is the `to`
of its last `status_changed` event (payload `{from, to, on, reason?}`, `on` = business date, D-023), `new` before the
first one; `analyst_action` carries `{action, reason}` with actor `analyst:<sub>` (a blank sub is refused). Every
event's actor is `agent`, `customer`, `system` or `analyst:<sub>`, every payload is JSON, and a `payload.action_id`
on any event is an `A-` id. Payloads and stored text never hold NUL or a lone surrogate (Postgres cannot store them);
both backends refuse them with `StoreError`. The store accepts only `case_queue.transitions` (spec 02
`nick_of_time.policy.transition` once task 02c merges) and a status on every change. Analyst
actions follow D-034 `[assumption]` (task 01c, until spec 02 AC-10): `resolved` comes only from `resolve` and `closed`
only from `close_case`; `take` starts from `new`, `verification` or `review` and moves to `review` or `verification`;
`reopen_case` moves only `resolved → review`; the other actions keep the status; a closed case takes no analyst
action and never moves. A closed case also takes no customer write (`block_card`, `add_case_info`, `request_call`,
`request_reevaluation`): the store refuses them, and the tool opens a related case instead; `related_case_id` must
name a closed case of the same customer and run. Each of the six customer writes carries its own `action_id`, used
once, and no `V-` id: `case_opened {action_id}` (`open_case`, or `request_reevaluation` on a closed case),
`card_blocked {action_id, product_id}`, `customer_info_added`, `call_requested` and `reevaluation_requested`
`{action_id, …}`, and `notification_sent {notification_id, event, channel, action_id}` for `send_case_summary` (an
`auto` send has no `action_id`). A read returns a `V-` id only when it is called with a write's `action_id`: the
read of that write in §6.3 "Verified with" (`get_case`, `get_product_status` or `list_my_notifications`; the two
without a case id find the case with the store's `action_write`) mints it in `action_verified {action_id,
verification_id, read_at, read}` (`read` names that tool, so the auditor can check it), one per read; another read is
refused. A `card_blocked` action is verified only while its
override is the card's latest in the run and `Blocked`, and its first read also writes `block_verified {action_id,
product_id}`, once. A summary send is verified only while its latest `notification_deliveries` row is not `failed` or
`bounced` (D-035 `[assumption]`, pending the lead). When a post-condition does not hold, the store writes nothing
(`NotVerified`) and the read stays plain. A plain read, with no `action_id`, returns `read_at` only. The store's case and override records carry the latest `V-` id; a read returns a `V-` only when it is called with an action_id (§6.3).
The store's `verifications(case_id, action_id)` returns every `action_verified` of the
action by `read_at`, so the auditor accepts any `V-` id a turn showed whose `read_at` is at or after the request. A
call request with no case (D-026) lives in 03d's `call_requests`, stays `requested` and has no verifying read (D-025
`[assumption]`). The store alone writes `case_opened`, `status_changed`, `analyst_action`, `assigned`,
`related_case_opened` (with the new case), `card_blocked` (with its override), `action_verified` and `block_verified`
(from a read), `notification_sent` (with its notification), and `telegram_linked` (a Telegram `linked` row) and
`email_confirmed` (an e-mail `confirmed` row) with their `customer_channels` row, payload `{channel_id, channel}`
and never the address (task 01g).

### 6.6 View models (api)
- `CaseSummary`: `{case_id, customer_id, country, zone, queue_status, credit_deadline, ruling_deadline, sla_due_at,
  priority, tags, created_at}`.
- `CaseView`: `CaseSummary` + `{transaction: {transaction_id, amount, currency, date, merchant, synthetic},
  product_last4, status_label, taken_by_person, related_case_id, mode, receipt: customer_receipt|null,
  timeline: [{event_id, type, label, created_at}] (customer-visible only), deadline_countdown_days,
  deadline_source, deadline_source_url, deadline_verified_on (`[assumption]` D-014, §6.5; a deadline date always
  comes with its source, an `https://` URL and `deadline_verified_on`, ADR 0019),
  channels: {telegram: bool, email: bool}, notifications: [{notification_id, channel, masked_address,
  delivery_status, created_at}]}`.
- `CustomerCaseView`: `CaseView` without `customer_id`, `zone`, `priority`, `tags` and `sla_due_at`
  (`CaseView.for_customer()`); `GET /api/cases/{case_id}` returns it (D-013 `[assumption]`).
- `CustomerCaseSummary`: `{case_id, status_label, credit_deadline, ruling_deadline, product_last4, related_case_id,
  updated_at}`; the list shows only the date and links to `/case/{id}`, which carries the source, URL and
  `verified_on` (ADR 0019).
- `ProductView`: `{product_id, type, last4, status, verification_id, read_at}`.
- `[assumption]` `priority` is `normal|high` (raised by `case_queue.deadline_sla`); `transaction.amount` is a number,
  as in `contracts/tools.py` `Transaction`. Ids follow `nick_of_time.ids`; `last4` is 4 digits; timestamps carry
  their UTC offset. Python models: `nick_of_time.contracts`.

### 6.7 Customer receipt (`contracts/customer_receipt.schema.json`, new)
```json
{
  "receipt_id": "RC-…", "case_id": "K-…", "language": "es | pt", "issued_at": "ISO-8601",
  "verified_facts": [{"fact": "string", "source_id": "TRX-… | PRD-… | V-… | K-…"}],
  "mode": "replay | live", "product_last4": "4417",
  "amount": {"original": {"amount": "1250.00", "currency": "USD"}, "display": {"amount": "22500", "currency": "MXN", "rate": "18.0", "rate_source": "…", "as_of": "YYYY-MM-DD"} },
  "actions": [{"label": "Tarjeta bloqueada", "action_id": "A-…", "state": "verified", "verification_id": "V-…", "verified_at": "ISO-8601"}],
  "deadline": {"country": "MX", "product": "debit", "credit_deadline": "YYYY-MM-DD", "ruling_deadline": "YYYY-MM-DD", "deadline_source": "Banxico, Circular 3/2012, arts. 19 Bis 3 y 19 Bis 4 (modificada por la Circular 14/2018)", "source_url": "https://…", "verified_on": "YYYY-MM-DD"},
  "what_ai_did": "string (template)", "what_a_person_does": "string (template)",
  "next_steps": ["string"], "case_url": "https://nickoftime.salazarvalverdeai.com/case/K-…"
}
```
Required: `receipt_id, case_id, language, issued_at, verified_facts, actions, deadline, what_ai_did,
what_a_person_does`. Never contains score, policy ids or transcript (`notifications.never_send`). `amount.display` is
an approximation from `convert_amount` and is omitted when no verified rate exists (ADR 0019); `deadline` is null for a
country without a verified clock entry (`POL-CLOCK-UNKNOWN`), and its `deadline_source` is the source in the receipt's
language, `get_case`'s `deadline_source_label` (1.5.0), not the analyst's `source`. Optional fields may be null or absent, except
`next_steps`, an array that is empty by default. Structural rules, in the schema and the model alike:
- accepted ≠ verified: an action with `state: "verified"` carries a `V-` `verification_id` and `verified_at`;
- a non-null `deadline` has at least one non-null date, an `https://` `source_url` and `verified_on`;
- `source_id` is a gold transaction or product id or a `K-`/`V-` id, in the shapes below;
- `case_url` is `https://`, `deadline.country` is two upper-case letters, `deadline.product` is `debit|credit`, and
  every timestamp carries its UTC offset (RFC 3339; the model rejects naive datetimes).

The schema's `examples[0]` is the sample receipt `[simulated]` that stubs and the echo graph return
(`nick_of_time.contracts.sample_receipt()`): a MX debit notice on `DEMO_TODAY` 2026-06-01 about a USD charge on
2026-05-31 (gold México rows are USD `[data]`), credit by 2026-06-03 and source fields from spec 02 §4.3 row 1;
`amount.display` is null because no verified rate exists yet. `nick_of_time.contracts.CustomerReceipt` mirrors the
schema; a test feeds the same good and bad receipts to both.

**Identifiers** (`nick_of_time.ids`): case `K-` + 6 digits · action `A-` · verification `V-` · event `E-` ·
receipt `RC-` · notification `N-` · session `S-` + 16 url-safe chars. `[assumption]` `A-`, `V-`, `E-`, `RC-` and `N-`
take 12 upper-case hex characters; a case id has only 10^6 values, so the store retries on a primary-key conflict.
Transaction and product ids come from gold, or from `demo_transactions` in `live` mode, in the same shape: `TRX-` + 20 and `PRD-` + 12 upper-case letters or digits
(`ids.GOLD_PATTERN`; gold `transactions` and `products` `[data]`); customer ids are `CLI-` + 12 upper-case letters or digits
(`GOLD_PATTERN["customer"]`; all 150,000 gold customers match, 3,077 have no digit `[data]`).

### 6.8 Evaluation hooks (`EVAL_MODE=true` only)
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/eval/seed` | `{initial_state: eval_case.initial_state, run_id: str, arm: str}` | `{session_id, thread_id, run_id, arm, mode: "replay"}` — the mode is always `replay` (ADR 0020); always returns a `session_id`: `verified` (OTP done), `expired` (expires_at in the past) or `none` (row with no customer and no verification, so every tool answers `SESSION_EXPIRED` and the expected decision is `reauthenticate`). Applies `fixtures` as overlays and `tool_faults` |
| GET | `/api/eval/final-state/{session_id}` | — | `FinalState` below |

`[assumption]` (D-019, pending the lead) The harness sends the seeded `session_id` as the `not_session` cookie, the same way as a browser; there is no header alternative.

**Isolation between runs (pass^4).** Every row written while serving a seeded session carries its `run_id`
(`sessions`, `cases`, `case_events` through their case, `product_overrides`, `idempotency`, `notifications` through
their case, `policy_denials`, `llm_calls`; D-023 `[assumption]`), and every read of mutable state filters by the
session's `run_id` (product status = latest override for the same `run_id`, else gold). Rows are never reset or
deleted, so the append-only rule holds and each of the four runs starts from the same gold state. The harness uses
`run_id = <case_id>:<arm>:<k>` (k = 1…4).

**Public demo sessions (1.6.0, D-068, ADR 0026).** Every session the public `POST /api/sessions` opens gets its own
`run_id = demo-<UTC yyyymmddThhmmssZ>-<6 base32>` and follows the same isolation, so two visitors of one demo
customer never see each other's cases, blocks, notifications or idempotency keys. `customer_channels` is per customer,
not per run, so a demo run has no external channel: the Telegram and e-mail link routes refuse a demo-run case,
`get_customer_profile` lists no channel, `send_case_summary` answers `DENY`, and an analyst action on a demo-run case
writes only the in-app notification. The analyst console lists and acts on demo-run cases (`demo_runs=True`), never
on eval runs.

**Arms (system configurations).** One deployment serves every arm: `seed` stores `arm` in the session and the api
injects it as `configurable.arm`; the graph resolves it with `nick_of_time.config.resolve(arm)`.

| Arm | Understanding | Replies | LLM |
|---|---|---|---|
| `S0` | rules classifier (B0) | deterministic templates | none |
| `S1` | classifier chosen by spec 11 | templates + LLM for clarifying questions | Claude Haiku 4.5 |
| `S2` | same as S1 | same as S1 | Claude Sonnet 4.6 |
| benchmark arms (spec 15, B2) | as S1 | as S1 | the arm's model (e.g. `jev`) |

S0–S2 are named here and are the system comparison of ADR 0015; spec 15 can add arms without changing this contract.

`FinalState` (one per session, i.e. per run):
```json
{
  "run_id": "EV-0001:S1:3", "arm": "S1",
  "decision": "…", "zone": "…", "intent": "…",
  "transaction_id": "TRX-… | null", "product_id": "PRD-… | null", "candidate_transaction_ids": ["TRX-…"],
  "product_status": "Blocked | Active | …", "case_open": true, "case_id": "K-… | null", "queue_status": "…",
  "handoff_emitted": true, "receipt_issued": true, "receipt_has_deadline": true,
  "notifications": ["case_opened"], "guardrail_ids": ["G-IN-01"], "other_customer_data_exposed": false,
  "mode": "replay", "action_states": {"block_card": "verified"},
  "status_replies": [{"subject": "PRD-… | K-…", "stated_status": "Blocked", "read_status": "Blocked"}],
  "turns": [{"turn": 1, "latency_ms": 2140, "tokens_in": 1830, "tokens_out": 210, "cost_usd": 0.0031}],
  "totals": {"latency_ms": 2140, "tokens_in": 1830, "tokens_out": 210, "cost_usd": 0.0031},
  "run_meta": {"git_sha": "…", "platform_revision": "…", "policies_version": 2, "provider": "bedrock",
               "model_graph": "…", "model_fast": "…", "prompt_hash": "sha256:…", "classifier_version": "…"}
}
```
`transaction_id`/`product_id` are the ones acted on (block or case); per-turn latency feeds p50/p95, totals feed the
cost per case; `status_replies` compares each status the agent stated with a fresh read at the end of the turn and
feeds `coherence_rate` (spec 15). The harness drives turns through `/api/agent/...` with the seeded session and compares `FinalState`
against `expected`.

**Schema change (`eval/eval_case.schema.json`, minor):** add `"customer_returns"` to `type`; add
`expected.receipt: {"issued": bool, "has_deadline": bool}` and `initial_state.case_id` (for returning customers)
with its fixture `initial_state.case: {transaction_id, dispute_type, zone, queue_status, opened_on}` (each requires the
other); the seed computes the stored deadline with the clock at `opened_on`. `[assumption]` (default until spec 10
confirms) the seed maps a fixture `case_id` to a fresh id per run, because rows are never deleted and the four runs
must stay isolated by `run_id`.
`expected.decision` and `expected.intent` use the `TurnResult` vocabulary of §6.4, so `answer_status` and
`connect_person` are added and `status_inquiry` replaces `inquiry` (spec 11 Q4), plus `human_request`. The example
cases use charge dates inside the gold window, since eval sessions are always `replay` (`DEMO_TODAY` 2026-06-01,
ADR 0020), and gold-format placeholder ids (`CLI-`, `TRX-`, `PRD-`). EV-0001's charge falls within the 90 calendar days
before the notice (spec 02 §4.3, ADR 0023); an older-charge case is added once spec 02 T3 verifies that row.

### 6.9 Configuration names
`DEMO_TODAY` · `DATABASE_URL` · `GOLD_PATH` / `GOLD_S3_URI` · `MCP_URL` · `MCP_API_KEY` · `LANGGRAPH_API_URL` ·
`LANGSMITH_API_KEY` · `LLM_PROVIDER` (`bedrock|anthropic|fake`) · `BEDROCK_MODEL_GRAPH` · `BEDROCK_MODEL_FAST` ·
`COGNITO_USER_POOL_ID` · `COGNITO_CLIENT_ID` · `TELEGRAM_BOT_TOKEN` · `TELEGRAM_WEBHOOK_SECRET` · `RESEND_API_KEY` ·
`GIT_SHA` · `EVAL_MODE` · `DEFAULT_SESSION_MODE` (`live`) · `RESEND_WEBHOOK_SECRET`. `DEMO_TODAY` applies only to `replay`
sessions. Names only in `.env.example`; values in SSM (`/nickoftime/prod/*`) or the Platform deployment secrets.

## 7. Data model touched
Creates the Postgres schema of §6.5 and the receipt schema of §6.7; reads gold v1 (`gold/v1/` in S3, local
`data/gold/`) read-only; never reads `gold_eval`. `demo_transactions` lives only in Postgres and never flows into gold,
the lakehouse or evaluation (ADR 0020).

## 8. Assumptions and open questions (gate 1 — to close in this PR)
- **Q1 (all):** shared package name `nick_of_time` under `packages/` — OK? (Diego: OK)
- **Q2 (@gianzk):** `/chat` uses agent-chat-ui against the `/api/agent/...` proxy (LangGraph Server protocol), so the
  session is injected server-side — OK, or do you prefer a single `POST /api/chat/runs` SSE route?
- **Q3 (@gianzk):** Alembic for migrations under `apps/api/migrations` — OK?
- **Q4 (@vldiego):** ~~`FinalState` and the seed hook are enough?~~ **Answered in review:** added run isolation by
  `run_id`, `transaction_id`/`product_id` acted on, `run_meta` (models, prompt hash, versions), arms S0/S1/S2 selected
  through `seed`, per-turn latency and cost, and the `session: "none"` behavior (§6.8).
- **Q5 (all):** ~~`440` for an expired session?~~ **Decided (lead):** standard `401` with `code: SESSION_EXPIRED`
  in the body (§6.2).
- **Q6 (lead):** ~~are the 7 tools enough for the messages the agent must send?~~ **Decided (lead, 2026-10-04):** the
  16 tools of §6.3 (improvement #13), the four action states, delivery status for notifications, display currency and
  the two time modes (ADR 0020). The coherence rules become harness cases (spec 10).
- Assumption: analysts and customers use the same origin (`nickoftime.salazarvalverdeai.com`); no CORS.
- Assumption: Platform reaches the MCP over the internet with the API key; locally `langgraph dev` + local MCP.

## 9. Out of scope
Real logic of policies (spec 02), tools (03), graph (04), backend persistence (05) and UIs (07, 08, 13, 16) —
only their seams and stubs.

## 10. Plan, tasks and verification
Implementation goes in one `feat/01-*` branch per task (for example `feat/01-package-skeleton`, then
`feat/01-contract-models` stacked on it).
- [x] T1 — `packages/nick_of_time` skeleton: `contracts.py` (re-export + `TurnResult`, `CustomerReceipt`, `FinalState`,
      view models, customer projections), `ids.py` · covers AC-01 · `tests/test_spec01_contracts.py`
- [x] T2 — `contracts/customer_receipt.schema.json` + `eval_case.schema.json` minor change + example cases updated ·
      covers AC-01, AC-04 (receipt half; the echo graph is T5) · `tests/test_spec01_contracts.py`
- [x] T3 — api stub: every route of §6.2 and §6.8 returning fixtures validated by the models; `mode` on sessions ·
      covers AC-02, AC-06, AC-07
- [x] T4 — `contracts/tools.py` v1.1 and `policies.yaml` `actors.customer.tools` with the 16 tools; fake MCP server
      returning fixtures from those models · covers AC-03 · `tests/test_spec01_mcp_stub.py`. `synthetic` rows in
      `live` (AC-08) are P1 (D-001) and stay open.
- [x] T5 — echo graph `dispute_intake` (`apps/agent/agent/graph.py`) returning a `TurnResult` with a sample receipt;
      a minimal `langgraph.json` (graph path, `"python_version": "3.13"`, §6.1) · covers AC-04 ·
      `tests/test_spec01_graph_stub.py`. Task 04g owns the Platform configuration later.
- [x] T6 — `infra/compose.dev.yml` (api stub, mcp stub, postgres) and `.env.example` names of §6.9 · covers AC-02
- [x] T7 — remove the empty `apps/api/{audit,classifier,graph,policy,tools}` folders
- [ ] T8 — tests `tests/test_spec01_*.py` citing AC-02, AC-03, AC-04, AC-06, AC-07, AC-08
- [x] T9 — `nick_of_time.store`: `Store` interface and in-memory backend for cases, events, queue status and
      transitions, analyst actions, product blocks, verification reads (D-025) and notifications (D-002, D-003). Every
      read is scoped by `run_id`; the case reads, `action_write` and `record_verification` also by customer; the
      per-case calls expect a case loaded with `get_case`. The case insert retries with a fresh `ids.new_id("case")`
      on a `case_id` primary-key conflict and a test forces one collision · covers AC-01 ·
      `tests/test_spec01_store.py`. The Postgres backend `store/postgres.py` (task 01g) keeps the same rules: each
      write is one transaction under a per-case advisory lock (no UPDATE grant needed), so `record_verification`
      reads the post-condition (for a block, the product's latest override) and inserts `action_verified` and
      `block_verified` in one transaction; every store test runs on both backends, the Postgres half when
      `TEST_DATABASE_URL` is set (`-m postgres`), and `[postgres]`-only tests back the lock and the transaction
      (concurrent writers and first reads, the unique-index backstop). Owners of the other §6.5 accessors: `sessions`
      (read), `policy_denials` (insert), `customer_channels` and `idempotency` → task 01g's second PR
      (`feat/01-store-accessors`); `llm_calls` → task 01h (`add_llm_call` and
      `list_llm_calls(run_id, trace_id?)` on both backends, plus `llm_spend_since(since)`, the summed `cost_usd` of
      every run's rows created at or after `since`, which the api reads for the G-OPS-01 daily cap (spec 05 AC-18), `store/accounts.py`, `tests/test_spec01_store_llm_calls.py`:
      a store-made `LC-` id `[assumption]`, non-negative integer counts, a finite `cost_usd` in [0, 10^6] per call
      `[assumption]` with a scale Postgres `numeric` holds, kept as a decimal (`-0` stored as `0`), `run_id` required
      with no default so `None` (production) is passed on purpose (D-023), no update or delete, oldest first; the api
      writes one row per billed call from a run's usage, spec 04 AC-14, spec 18 AC-10; no column beyond the §6.5
      table; `cost_usd` is never null, so any arm that can write an `llm_calls` row must have a configured price
      `[assumption]`, pending lead decision D-058, with no schema change; the graph runs a turn whose arm has no price
      as S0 and only logs it at load, while CI fails when a default production arm has none, spec 04 T7);
      `demo_transactions` → task 03b; `link_tokens` and
      `settings_events` → spec 05 (api). The api checks `AnalystActionIn.idempotency_key` through the `idempotency`
      accessor before it calls `record_analyst_action`. Once task 02c merges, `record_analyst_action` takes the new
      status from `nick_of_time.policy.transition(current, action, actor)` (`Moved.status`), and the store's
      `check_transition` stays for agent and customer changes. Task 01g's second PR adds, on both backends
      (`store/accounts.py`, `tests/test_spec01_store_accounts.py`): `sessions` insert under a store-made `S-` id and
      read, with no update, so `mode` and `run_id` stay as created (AC-07; OTP verification and preferences are spec
      05's `[assumption]`), and `summary_sends`, the `on_request` sends of the session's customer and run since the
      session started, for spec 03 AC-21's per-session limit (D-041; a notification names no session, so another
      session of the same customer and run counts too `[assumption]`); `policy_denials` insert (a `PD-` id, a session's
      denial carries its `run_id`, a missing guardrail becomes `G-POL-01`) and read by run and session, oldest first
      (`created_at`, then `denial_id`); and `customer_channels` insert, with its case event, and the latest row per
      channel (the highest `row_no`), where only an e-mail is `confirmed`, on its `linked` address, and a channel takes
      a summary only while its latest row is a Telegram `linked` or an e-mail `confirmed` `[assumption]`. Bad input to these
      accessors is a `StoreError`, NUL and lone surrogates included. The `idempotency` accessor, in a separate small PR
      of the same task (`feat/01-store-idempotency`), is `once(key, action, customer_id, run_id, arguments, write)`: the first call
      runs `write()` and stores its JSON result, every later one returns it with `replayed` and writes nothing (spec 03
      AC-03, §6.3 Idempotency), under the key's advisory lock on Postgres so concurrent callers write once; the stored key is
      `[run_id:]c=<customer_id>:<key>` (`-` for the api's analyst actions, which check `AnalystActionIn.idempotency_key`
      with it), so one customer never replays another's result `[assumption]`; a key reused for another action or with other arguments and a
      result that is not a JSON object are a `StoreError`, and a refused write is not remembered and leaves none of its writes
- [x] T10 — `store/schema.sql`: the §6.5 tables as Postgres DDL with the append-only trigger and the unique
      action-id index, adopted verbatim by `apps/api/migrations` as its first migration (D-002); its actor CHECKs
      give no result that depends on the server locale (the stock `postgres:16` image included) · covers AC-01 ·
      `tests/test_spec01_store_schema.py`; its `postgres`-marked test runs when `TEST_DATABASE_URL` is set, and the
      CI job with a `postgres:16` service (`pytest -m postgres`, which also runs the store suite on Postgres) is a
      task-01g follow-up for the workflow owner (with grants of INSERT and SELECT only on the AO tables for the app
      role)
- [x] T11 — api stub follow-ups from the 01d round-2 review: `GET threads/{id}/state` 401 on an expired session (not
      forwarded), a data-free `reauthenticate` turn (session line, chips, no progress event), the seed answers the stored
      mode, exact key-set tests for the dict-shaped §6.2 rows, and tests for verify-expired 410, final-state on a
      non-eval session and the `none` seed's missing customer · covers AC-02, AC-07, AC-08 (seed half) ·
      `tests/test_spec01_api_stub.py`

**Closing checklist:** every AC has a passing test or check · status → Implemented · contract version recorded in
`/api/health` · lessons added to `CLAUDE.md`.

## 11. Sources
External sources checked on 2026-10-04.
- Telegram Bot API, `setWebhook` (`secret_token` → header `X-Telegram-Bot-Api-Secret-Token`):
  https://core.telegram.org/bots/api#setwebhook
- Resend, webhook signature headers `svix-id`, `svix-timestamp`, `svix-signature`:
  https://resend.com/docs/webhooks/verify-webhooks-requests · e-mail event types (`email.sent`, `email.delivered`,
  `email.bounced`, `email.failed`, …): https://resend.com/docs/webhooks/event-types
- langgraph-cli 0.4.32, `langgraph_cli/config.py`: `DEFAULT_PYTHON_VERSION = "3.11"` when `langgraph.json` has no
  `python_version`: https://pypi.org/project/langgraph-cli/0.4.32/
- jsonschema, format validation (`date-time` is checked only with `rfc3339-validator` installed):
  https://python-jsonschema.readthedocs.io/en/stable/validate/#validating-formats
- Internal: `contracts/gold_contract.md` R1 (gold window), `contracts/policies.yaml` (queue statuses, tools,
  `notifications.never_send`), `contracts/tools.py`, ADRs 0005, 0007, 0008, 0010, 0013, 0016, 0017, 0019, 0020,
  improvement drafts #12 (action states), #13 (tool catalog), #16 (two modes).
