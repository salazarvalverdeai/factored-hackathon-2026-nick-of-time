# Spec 05 — Backend: API + Postgres + analyst login (Cognito) + customer session/OTP

- **Feature:** case state and audit are rows nobody can rewrite, and every action has a real actor.
- **Status:** In progress (api on the store, Cognito check, channels and agent proxy implemented and tested offline; running it on Postgres and the public URL is pending)
- **Owner:** @gianzk · **Priority:** P0 · **Size:** L
- **Challenge dimension:** Technical Judgment
- **Depends on:** 01 · **Enables:** 07, 08, 13, 14
- **ADRs:** [0010](../docs/adr/0010-postgres-for-case-state-and-audit.md), [0017](../docs/adr/0017-identity-mock-otp-customers-cognito-analysts.md), [0020](../docs/adr/0020-two-time-modes-historical-and-live.md)
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
AC-01 to AC-08 are copied from issue #7 with the same numbers. AC-09 to AC-11 are added by the owner. None is dropped or weakened.

- AC-01 — When a customer session is requested and the OTP verified, the session shall last 15 minutes; once expired, every protected route shall answer `SESSION_EXPIRED`. · [T] `tests/test_spec05_api.py`
- AC-02 — A case's status shall be its last event in `case_events`; no row shall be updated or deleted. · [T]
- AC-03 — When the analyst runs a valid action, the status shall change, an event with actor and reason shall be recorded, and the notification shall go out. · [T]
- AC-04 — If the transition does not exist in `case_queue`, then the API shall answer 409 and change nothing. · [T]
- AC-05 — The `/api` shall proxy runs to Platform injecting the `session_id` server-side; the LangSmith key shall never reach the browser. · [T]
- AC-06 — While `supervised_mode` is on, the `/api` shall require human approval and record the switch. · [T]
- AC-07 — If an analyst route receives a request without a valid Cognito JWT, then it shall answer 401; each action's `actor_id` shall come from the token. · [T]
- AC-08 — Team accounts and one "judge" account shall exist, documented in the README without the password (it goes only in the submission e-mail). · [D] `apps/api/README.md`
- AC-09 — A customer route shall read only the session's own customer: another customer's case answers 403 and writes a `policy_denials` row, and no customer view carries score, zone, priority, handoff or policy ids (D-013). · [T]
- AC-10 — An analyst action shall run once per `idempotency_key`; a replay returns the stored result and writes and notifies nothing, and a reason is required except for `take` and `approve_*`. · [T]
- AC-11 — The api shall serve the channels of spec 13: a signed Telegram link (TTL 15 min) and webhook (secret header, 401 otherwise), e-mail sent only to a typed and confirmed address, and a failing channel shall leave the in-app notification and the case unaffected. · [T]

## 8. Assumptions and open questions
- `[assumption]` AC-03 and `approve_credit`: D-034 keeps the status on `approve_*`, `unblock_card`, `request_customer_info` and `mark_ambiguous`. Those actions record the event with actor and reason and return `new_status == previous_status`; only a status change (`take`, `resolve`, `reopen_case`) notifies, because `policies.yaml` `notifications.events` has templates only for `in_review` and `resolved`. A notification for the money approvals needs a template there (lead).
- `[assumption]` `supervised_mode` (AC-06): the switch is a `settings_events` row with the analyst's actor, the current value is its latest row (default `approval.supervised_mode`), and every run's `configurable` carries it so the graph forces `human_required` on money actions (POL-SUPERVISED). The api itself approves nothing.
- `[assumption]` Store accessors added for this spec (Freddy's package, flagged for review): `revise_session` (OTP verification and preferences; `mode`, `customer_id`, `run_id`, `expires_at` never change), `record_setting`/`get_setting`/`setting_history` over the existing `settings_events` table, and `list_cases(customer_id=None)` for the console, as `get_case` already reads it.
- `[assumption]` The graph writes its receipt and handoff card as the `receipt` of a `receipt_issued` and the `handoff` of a `handoff_emitted` event payload; the api shows what validates against the contract, else `receipt: null` / `handoff: {}`.
- `[assumption]` Gold lookups (transaction, products, demo customers) go through `app/catalog.py`; only the fixture catalog exists until the data pipeline publishes a reader. A case whose transaction is not found answers `UNAVAILABLE`.
- `[assumption]` Telegram and e-mail confirmation tokens are signed and stateless (`LINK_SIGNING_KEY`); single use comes from `store.once` and from the channel row order. Notification templates are the Spanish ones of `policies.yaml`.
- `[assumption]` The Platform stream is normalized to `progress` items plus one final `turn` (the last `values`), and only the customer projection of the turn leaves the api.
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

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
