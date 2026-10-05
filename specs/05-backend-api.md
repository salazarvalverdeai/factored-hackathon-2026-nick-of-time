# Spec 05 — Backend: API + Postgres + analyst login (Cognito) + customer session/OTP

- **Feature:** case state and audit are rows nobody can rewrite, and every action has a real actor.
- **Status:** In progress (api on the store, Cognito check, channels and agent proxy implemented and tested offline; running it on Postgres and the public URL is pending)
- **Owner:** @gianzk · **Priority:** P0 · **Size:** L
- **Challenge dimension:** Technical Judgment
- **Depends on:** 01 · **Enables:** 07, 08, 13, 14
- **ADRs:** [0010](../docs/adr/0010-postgres-for-case-state-and-audit.md), [0017](../docs/adr/0017-identity-mock-otp-customers-cognito-analysts.md), [0020](../docs/adr/0020-two-time-modes-historical-and-live.md), [0026](../docs/adr/0026-demo-sessions-isolated-by-run-id.md)
- **Issue:** #7

> **Profile.** Minimal: sections 1, 3, 8, 9 and 10. The routes and shapes belong to spec 01 §6.2; this spec makes them real.
> **Anti spec-drift.** If a route, a store accessor or the auth rule changes, update this spec in the same PR or mark it Superseded.

---

## 1. Introduction
`apps/api` replaces the fixtures of the spec 01 stub with the case store (`packages/nick_of_time/store`: Postgres in
production, `MemoryStore` in tests). The stub stays for the contract tests and runs when no store is given
(`create_app(store=...)` or `DATABASE_URL` selects the real one, `app/live.py`). The api reads and records; it decides
nothing about a dispute: transitions go through `policy.transition`, deadlines were stored by the tools, and a person
closes. `customer_id` and `mode` come only from the session row; the analyst's identity is the verified Cognito `sub`.

## 3. Acceptance criteria (EARS)
AC-01 to AC-08 are copied from issue #7 with the same numbers. AC-09 to AC-13 are added by the owner, AC-14 to AC-17 by the lead (D-068), AC-19 by the lead (DEMOCD, AC-18 is the abuse guard); AC-03 was amended by the lead (review of PR #111). None is dropped or weakened.

- AC-01 — When a customer session is requested and the OTP verified, the session shall last 15 minutes; once expired, every protected route shall answer `SESSION_EXPIRED`. · [T] `tests/test_spec05_api.py`
- AC-02 — A case's status shall be its last event in `case_events`; no row shall be updated or deleted. · [T]
- AC-03 — When the analyst runs a valid action, an event with actor and reason shall be recorded; when it changes the status (`take`, `resolve`, `reopen_case`), the customer notification shall go out. A status-keeping action (`approve_credit`, `approve_block`, `unblock_card`, `request_customer_info`, `mark_ambiguous`) records the event and does not notify (lead, D-034). · [T]
- AC-04 — If the transition does not exist in `case_queue`, then the API shall answer 409 and change nothing. · [T]
- AC-05 — The `/api` shall proxy runs to Platform injecting the `session_id` server-side; the LangSmith key shall never reach the browser. · [T]
- AC-06 — While `supervised_mode` is on, the `/api` shall require human approval and record the switch. · [T]
- AC-07 — If an analyst route receives a request without a valid Cognito JWT, then it shall answer 401; each action's `actor_id` shall come from the token. · [T]
- AC-08 — Team accounts and one "judge" account shall exist, documented in the README without the password (it goes only in the submission e-mail). · [D] `apps/api/README.md`
- AC-09 — A customer route shall read only the session's own customer: another customer's case answers 403 and writes a `policy_denials` row, and no customer view carries score, zone, priority, handoff or policy ids (D-013). · [T]
- AC-10 — An analyst action shall run once per `idempotency_key`; a replay returns the stored result and writes and notifies nothing, and a reason is required except for `take` and `approve_*`. · [T]
- AC-11 — The api shall serve the channels of spec 13: a signed Telegram link (TTL 15 min) and webhook (secret header, 401 otherwise), e-mail sent only to a typed and confirmed address, and a failing channel shall leave the in-app notification and the case unaffected. · [T]
- AC-12 — `POST /api/cases/{id}/reevaluation` shall move a resolved case back to `review` with `reevaluation_requested` (spec 03 AC-19), refuse an active case as `already_in_progress`, and open one related case for a closed case with deadlines derived by the clock from the new notice (never copied); repeating the request shall not open a second case. · [T]
- AC-13 — The api image shall ship an executable `/app/migrate.sh` (`alembic upgrade head`, baseline = `store/schema.sql`) for the deploy's migration hook (spec 06 FR-04). · [T] `tests/test_spec05_migrations.py` (offline `--sql`; the live run is Task 7)
- AC-14 — When a demo session is requested with a `display_name`, the api shall store it trimmed on the session row, refuse with 422 a name that is longer than 40 characters or is not a plain name (digits, URL, e-mail, control characters, an injection pattern), and `get_customer_profile` shall return it, else gold's first name. · [T] `tests/test_spec05_demo.py`
- AC-15 — `GET /api/demo/scenarios?country&language` shall list one scenario per demo customer gold serves (`scenario_id`, `title`, `country`, `language`, `segment`, `customer_name` = gold's synthetic first name, spec 09 dev/sample `cases` and `tags`), with no `customer_id`, score or zone; a held-out or test file or row shall never be read. · [T]
- AC-16 — When `POST /api/sessions` carries no `customer_id`, it shall require `language` (`es` or `pt`), choose the customer server-side from `scenario` (an id, or `auto`/none: random within `country`, preferring the language; 404 when nothing matches) and every public session, the original `{customer_id}` picker included, shall get a fresh `run_id = demo-<UTC yyyymmddThhmmssZ>-<6 base32>`, so two sessions of one customer never see each other's cases or blocks; a body with both `customer_id` and `scenario`/`country` is refused with 422. In a demo run no Telegram or e-mail channel is linked (403 `DENY`), shown or sent to (analyst actions write the in-app log only). · [T] (memory and `-m postgres`)
- AC-17 — `GET /api/sessions/{id}/recent-transactions?limit` (1–20, default 10) shall answer only for the verified session in the cookie (another id → 404) with its customer's latest card transactions (Approved or Pending) up to the session's `today`: `transaction_id`, `date`, `amount`, `currency`, `merchant` (null in some gold rows), the card's `last4`, and no score or label. · [T]
- AC-19 — When a verified live demo session posts `POST /api/sessions/{id}/synthetic-charge {amount, merchant}`, the api shall write one `demo_transactions` row for that session's run (dated today in the customer's country, in its currency, on its card, `synthetic`, the fixed synthetic score of D-027 and never one from the visitor) and answer it labeled `[simulated]`; a replay or production session shall get 403 `DENY`, another session id 404, a merchant that is not a plain store name or an amount above the cap 422, and a second charge within a minute or a fourth in the session 429. The charge shall be listed first by the session's recent transactions (`synthetic: true`) and found by that run's MCP tools only (spec 03 AC-14); it never reaches gold. · [T] `tests/test_spec05_synthetic_charge.py`

## 8. Assumptions and open questions
- Decided (lead): AC-03 is amended as above; notifications go out on status changes only, and the customer text carries a fixed outcome label from `messages.yaml` `status.label`, never the analyst's free-text reason.
- `[assumption]` `supervised_mode` (AC-06): the switch is a `settings_events` row with the analyst's actor, the current value is its latest row (default `approval.supervised_mode`), and every run's `configurable` carries it so the graph forces `human_required` on money actions (POL-SUPERVISED). The api itself approves nothing.
- `[assumption]` Store accessors added for this spec (Freddy's package, flagged for review): `revise_session` (OTP verification and preferences; `mode`, `customer_id`, `run_id`, `expires_at` never change), `record_setting`/`get_setting`/`setting_history` over the existing `settings_events` table, and `list_all_cases(run_id)` for the console only (approved by the lead; `list_cases` stays per customer). `revise_session` reads and updates in one transaction.
- `[assumption]` The graph writes its receipt and handoff card as the `receipt` of a `receipt_issued` and the `handoff` of a `handoff_emitted` event payload; the api shows what validates against the contract, else `receipt: null` / `handoff: {}`.
- `[assumption]` Gold lookups (transaction, products, demo customers) go through `app/catalog.py`. With `GOLD_PATH` set, `GoldCatalog` serves the spec 09 demo customers of `eval/demo/customers.json` (no score, no zone) and reads cards and card transactions from gold with DuckDB, read-only, refusing `gold_eval`; a demo customer gold does not hold (or holds under another country) cannot open a session. Without `GOLD_PATH`, `FixtureCatalog` serves the tests and the stub. A case whose transaction is not found answers `UNAVAILABLE`. · [T] `tests/test_spec05_catalog.py`
- `[assumption]` Telegram and e-mail confirmation tokens are signed and stateless (`LINK_SIGNING_KEY`); single use comes from `store.once` and from the channel row order. Notification templates are the Spanish ones of `policies.yaml`.
- `[assumption]` The Platform stream is normalized to `progress` items plus one final `turn` (the last `values`), and only the customer projection of the turn leaves the api.
- `[assumption]` `POL-REEVAL-WINDOW`: `policies.yaml` has no `reevaluation.window_days` yet, so a resolved case is reopened by status alone; the window check lands when the lead adds the value (spec 02 `reevaluation_allowed`).
- `/api/console/demo/reset` is not served by the live app until `demo_transactions` exist (spec 03 task 03b).
- Decided (lead, D-068, 2026-10-05; ADR 0026): public demo sessions, types A+B. The visitor's name, language, country and scenario open the session; the customer is chosen server-side (constitution #3) and the session runs under its own `demo-…` `run_id`, which the MCP server reads from the session row exactly as for eval runs (spec 01 §6.8). The analyst console lists and acts on production and demo-run cases (`demo_runs=True`), never eval runs. The original picker (`customer_id`) still works until the web moves to scenarios, and its sessions get a demo run too: every session the public URL opens is isolated (review of #152). `customer_channels` is per customer and a demo customer is shared, so a demo run has no external channel: the Telegram and e-mail link routes answer 403 `DENY` with a policy denial, the case view shows no channel, analyst actions write only the in-app notification, and the MCP server lists no channel and refuses `send_case_summary` (spec 01 §6.8).
- `[assumption]` Scenario ids are `SCN-<country>-<n>` in `customers.json` order; `language` filters the list strictly, while `auto` falls back to any language of the country. A name with digits is refused outright (a card number, a document or a phone), as is one NFKC would change (`²`, `Ⅻ`, full-width letters). In `live` mode the recent transactions are gold's up to the real date, after the run's synthetic charges (AC-19).
- `[assumption]` Demo type C (DEMOCD, AC-19): D-027 sets no rule for the synthetic score, so every visitor charge carries a fixed 72 (high zone: the block-and-verify path of the demo) [assumption]; the cap is the amount gate's high tier (≈ 5,000 USD in local currency) and the limits are one charge per minute and three per session, counted in process (the api runs one worker, as the abuse guard of AC-18 assumes). The charge goes on the customer's first active card and has no `transaction_country` (not abroad). The case page shows it like a gold charge, flagged `synthetic`.
- Open question: eval hooks (`/api/eval/*`) stay on the stub; the live app does not register them until spec 10 needs them on Postgres.

## 9. Out of scope
- Corporate SSO, DynamoDB.
- The Postgres run on the EC2 and the Cognito pool (spec 06); here Postgres is covered by the store's own tests when a server is available.

## 10. Plan, tasks and verification
- [x] Task 1 — sessions, OTP verify, 15-minute expiry · covers AC-01 · done when: the tests pass
- [x] Task 2 — case projections, customer routes, analyst actions through `policy.transition` · covers AC-02, AC-03, AC-04, AC-09, AC-10 · done when: the tests pass
- [x] Task 3 — Cognito JWT check and `actor_id` from the token · covers AC-07 · done when: the tests pass
- [x] Task 4 — agent proxy and supervised mode · covers AC-05, AC-06 · done when: the tests pass
- [x] Task 5 — Telegram, e-mail and webhooks · covers AC-11 · done when: the tests pass
- [x] Task 6 — accounts in the README · covers AC-08 · done when: the README lists them without the password
- [ ] Task 7 — run on Postgres and the public URL; Cognito pool values; gold catalog · covers AC-01 to AC-07 · done when: same flows on the public URL
- [x] Task 9 — demo type C (DEMOCD): the synthetic charge route, the run's charges in recent transactions and the case view, `demo_transactions.run_id` and `product_type` (migration 0003) · covers AC-19 · done when: the tests pass on memory and Postgres
- [x] Task 8 — demo sessions (D-068): name, scenarios, server-side customer, `demo-…` run_id, recent transactions; `sessions.display_name` (migration 0002) · covers AC-14 to AC-17 · done when: the tests pass on memory and Postgres

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
