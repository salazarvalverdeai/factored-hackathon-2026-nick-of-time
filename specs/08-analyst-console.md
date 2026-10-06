# Spec 08 — Analyst login + console `/login`, `/console`

- **Feature:** the analyst receives evidence, not a chat, and every click is audited.
- **Status:** In progress (works on mock data in PR #51; Cognito and the live API arrive with spec 05)
- **Owner:** @gianzk · **Priority:** P0 · **Size:** L
- **Challenge dimension:** Technical Judgment
- **Depends on:** 16, then 05 · **Enables:** 13
- **ADRs:** [0010](../docs/adr/0010-postgres-for-case-state-and-audit.md), [0017](../docs/adr/0017-identity-mock-otp-customers-cognito-analysts.md)
- **Issue:** #10

> **Profile.** Minimal: sections 1, 3, 8, 9 and 10. The routes it calls belong to spec 01 §6.2.
> **Anti spec-drift.** If the console changes later, update this spec in the same PR or mark it Superseded.

---

## 1. Introduction
An analyst signs in, sees the inbox by status with zone, deadline and priority, opens a case to read the handoff card
and the timeline, and decides: approve the provisional credit or close the case. A person always decides (constitution
#6). Supervised mode asks for a second confirmation, and every action and every mode change is audited with the user.

## 3. Acceptance criteria (EARS)
AC-01 to AC-06 are copied from issue #10 with the same numbers. None is dropped or weakened. AC-07 to AC-09 are added
by the console KPI work (PR `feat/web-console-kpis`).

- AC-01 — If there is no analyst session, then `/console` shall redirect to `/login`. The handoff card is analyst-only:
  a customer session shall not read it. · [U] · [T] `lib/api.test.ts` ("spec 08 AC-01: the handoff card is analyst-only …")
- AC-02 — The inbox shall list cases by status with zone (color and text), deadline and priority (`normal | high`). · [U]
- AC-03 — When the analyst opens a case, the system shall show the handoff card per `handoff.schema.json` and the case
  events timeline. · [U] · [T] ("spec 08 AC-03: an opened case carries a handoff card shaped like handoff.schema.json")
- AC-04 — When the analyst approves the credit, the status shall change, the action shall be audited with their user and
  it shall show on the customer's `/case/{id}`. · [U] · [T] ("spec 08 AC-04: approving the credit changes the status …")
- AC-05 — The supervised-mode switch shall exist and every change shall be audited; while it is on, an approval needs a
  second human confirmation. · [U] · [T] ("spec 05 AC-06: supervised mode needs human confirmation …")
- AC-06 — Below 1024 px the console shall switch to tabs; from 1024 px it shall show three columns. · [U]
- AC-07 — The console shall show a KPI strip above the inbox with three figures, each with its definition in a tooltip
  (hover and keyboard focus) and its figure label (`[simulated]` on demo cases): **open cases** (status `new`,
  `verification` or `review`); **deadlines at risk** (open cases whose nearest legal deadline is 2 calendar days away
  or less, or past, on the api's business clock; cases with no legal deadline are never counted); **time to
  verification** (median time from the case opening to its first verified action, `block_verified` or
  `action_verified`, or the mock's `verification_started`; cases without one are left out). Nothing shall read the system clock to compute them.
  · [T] `lib/console-metrics.test.ts` ("spec 08 AC-07: …") · [U]
- AC-08 — Each open case in the inbox shall carry an SLA light from the days left to its nearest legal deadline (credit
  or ruling) as the api counts them (`deadline_countdown_days`; the mock counts from its frozen demo date): green
  "On track" at 3 days or more, amber "Due soon" at 1–2 days, red "Due today" or "Past due"; each with an icon and
  text, never color alone. If the case has no legal deadline (POL-CLOCK-UNKNOWN), then the light shall show a neutral
  "No legal deadline · a person decides" state and no date or count shall be invented. · [T] ("spec 08 AC-08: …") · [U]
- AC-09 — The inbox shall have a Closed tab listing the resolved and closed cases, the most recently finished first,
  with their outcome, who resolved them, the time to close (opening → closing; "waiting for a person to close it" while
  resolved) and whether the nearest legal deadline was **met** (resolved on or before it on the case's business clock),
  **missed**, or did not exist (**no legal deadline**). A case's status is its last event. · [T] ("spec 08 AC-09: …") · [U]

AC-10 to AC-15 are added by the assisted case view (PR `feat/08-assisted-console-web`); the routes they read are the
analyst-only `GET /api/console/cases/{id}/context`, `/summary`, `/audit`, `/conversation` and `GET|POST …/second-opinion`.
- AC-10 — When the analyst opens a case, the case view shall start with the agent's summary (its lines and who wrote
  them, model or template) and the nearest legal deadline with its countdown and its source as a named link; if the
  case has no legal deadline, then it shall say a person decides and show no date. · [T] `lib/console-assist.test.ts` · [U]
- AC-11 — The case view shall show the customer's history as cards: previous cases, transactions within ±30 days with
  the disputed one marked by a word as well as a color, cards, calls and notifications; "Detail" shall open the shared
  detail panel (`components/detail-panel.tsx`, spec 07) with the whole list. A transaction with no merchant or no
  known card shall read "Unknown merchant" or "—", never "null". · [T] · [U]
- AC-12 — The case view shall show the deterministic auditor A1–A7 as a checklist titled "The outcome re-derives from
  the rules" (an icon and a word per check, spec 18 AC-06), then, only when the analyst asks for it, the judge's opinion
  labeled "AI second opinion — advisory" with every reason tied to its evidence ids; without one it shall say "No second
  opinion" and the api's reason (`X-No-Opinion-Reason`) in one calm line (spec 18 AC-09, AC-11). A check the api marks
  `not_applicable` (`passed: null`) shall read "n/a", never a failure. · [T] · [U]
- AC-13 — The copilot proposal shall read in plain words (`explanation`, else the rationale); its button shall run an
  existing analyst action only after a confirm step, supervised mode keeps its second confirmation, and a proposal no
  console action carries out shall say so. · [T] · [U]
- AC-14 — The case header shall show a status stepper (new → verification or review → resolved → closed, each step's
  state in words) and the SLA light of AC-08; every enum shall read as a human label, dates as es-MX on a 24 h clock,
  with no bracket tags, no horizontal scroll at 390 px, both themes and full keyboard use. · [T] · [U]
- AC-15 — The case view shall offer a "Conversation" tab next to the handoff card, which stays the first and default
  tab: a read-only transcript of the customer–agent conversation by chat session (`GET /api/console/cases/{id}/conversation`,
  analyst only), drawn like the chat (the chat's safe markdown, the AI Elements conversation log), with nothing to send.
  When the route answers 503, the tab shall say "Conversation not available right now", not an error. · [T] · [U]
AC-16 to AC-22 are the api side of the assisted case view (PR `feat/08-assisted-console-api`; AC-10 to AC-15 are its
web side, PR `feat/08-assisted-console-web`); the shapes are in §6.
- AC-16 — When the analyst asks for a case's context (`GET /api/console/cases/{id}/context`), the api shall return, from
  the store and gold only (never the customer-scoped MCP server), the customer's other cases with their status and
  outcome, the customer's card transactions from 30 days before the disputed charge to 30 days after it (never past the
  case's business today) with the disputed one flagged, the cards with their status in the case's run, the call requests
  and the notifications; every list shall keep to the case's own `run_id` (ADR 0026). · [T]
  `tests/test_spec08_assisted_console.py`
- AC-17 — When the analyst asks for a case's summary (`GET /api/console/cases/{id}/summary`), the api shall return
  template lines (what the customer reported, what the agent did with **verified** actions only, what is left to decide,
  the legal deadline) built from the handoff card and the store, and the nearest legal deadline with its days left and
  source, or `null` with no invented date (POL-CLOCK-UNKNOWN). While the console `writer` setting is `llm`, the lines
  shall be worded through the spec 04 §4.6 line gate (a line with a number, date or id that is not a fact falls back to
  its template lines); no client, no price, the daily cap (`DAILY_LLM_CAP_USD`), a timeout or any error shall give the
  template. The result shall be cached per case, handoff version and setting, and each billed call written to
  `llm_calls`. · [T] `tests/test_spec08_assisted_console.py`
- AC-18 — When the analyst asks for a second opinion (`POST /api/console/cases/{id}/second-opinion`), the api shall run
  the spec 18 judge on the case's latest handoff card, the verified reads, the charge and the auditor's checks, and
  return it labeled "model opinion (advisory)"; `GET` shall return the latest one, or 404 while there is none. It shall
  make at most one judge call per case and handoff version, skip the call when the day's spend plus the judge's
  per-case cap passes `DAILY_LLM_CAP_USD`, write each billed call to `llm_calls`, and write no case event, status or
  notification (spec 18 AC-09). A failure, a timeout, the budget or a case with no card shall answer 204 with the reason
  in `X-No-Opinion-Reason` ("No second opinion", spec 18 AC-11). · [T] `tests/test_spec08_assisted_console.py`,
  `tests/test_spec18_console_second_opinion.py`
- AC-19 — When the analyst asks for a case's audit (`GET /api/console/cases/{id}/audit`), the api shall return the
  deterministic auditor's checklist A1–A7 (spec 18 §4.1), each passed, a finding or not applicable with its reason, the
  re-derived outcome (zone from the card's score, deadlines from the clock) and whether everything matches; it shall
  change nothing. · [T] `tests/test_spec08_assisted_console.py`
- AC-20 — When a case's handoff card carries a `copilot_proposal`, `GET /api/console/cases/{id}` shall return it with an
  `explanation`, one Spanish sentence "Sugerencia: …, porque …" chosen by fixed rules from the proposal and the card (no
  LLM); nothing else of the card shall change, and the stored card (the `handoff_emitted` payload) never changes. · [T]
  `tests/test_spec08_assisted_console.py`
- AC-21 — Every route of AC-16 to AC-19 and AC-22 shall require the analyst's Cognito token (401 without it or with a
  bad one); a case of an evaluation run, or one that does not exist, shall answer 404. · [T]
  `tests/test_spec08_assisted_console.py`
- AC-22 — When the analyst asks for a case's conversation (`GET /api/console/cases/{id}/conversation`), the api shall
  return, read-only, the chat threads that named the case, each with its session's start and only the
  customer-visible messages in order (the customer's own texts and the agent's replies as the customer saw them),
  never internal state, scores, zones, rule or policy ids, tool results or the handoff card. A thread is marked with a
  case only when a turn of the session's own customer, in the session's run, names that case; a thread whose session
  is another customer's or another run's shall be left out (ADR 0026). The transcript shall never be written to a
  notification. Without a Platform that can search threads, the route shall answer 503 `UNAVAILABLE`. · [T]
  `tests/test_spec08_console_conversation.py`

## 6. API contract (assisted console, AC-16 to AC-22)
All routes take `Authorization: Bearer <Cognito id token>` and the case id in the path; they read and never write a
case. Dates are ISO `YYYY-MM-DD`, times ISO 8601 with offset.
```text
GET  /api/console/cases/{id}/context
  {case_id, previous_cases: [{case_id, opened_at, status, outcome: approve_credit|approve_block|close_without_action|null}],
   transactions: [{transaction_id, date, amount, currency, merchant|null, last4|null, disputed: bool, synthetic: bool}],
   cards: [{product_id, last4, product: debit|credit, status}],
   calls: [{requested_at, status: "requested", case_id|null, expected_contact_by|null}],
   notifications: [{at, channel: log|telegram|email, event, status: queued|sent|delivered|bounced|failed, case_id}]}
GET  /api/console/cases/{id}/summary
  {case_id, lines: [str], writer: "llm"|"template",
   deadline: {kind: credit|ruling, date, days_left, source_label, source_url} | null}
POST /api/console/cases/{id}/second-opinion      200 the opinion | 204 "No second opinion", X-No-Opinion-Reason:
                                                  no_handoff|budget|timeout|error|unavailable
GET  /api/console/cases/{id}/second-opinion      200 the latest opinion | 404 none yet
  opinion: {case_id, verdict: agree|disagree|uncertain, reasons: [{text, evidence_ids: [str]}],
            questions: [{text, evidence_ids}], model, label: "model opinion (advisory)", created_at}
GET  /api/console/cases/{id}/audit
  {case_id, checks: [{id: A1..A7, name, status: passed|finding|not_applicable, passed: bool|null,
                      severity|null, detail, expected, observed}],
   rederived_outcome: str (one line, e.g. "zone high · credit by 2026-06-03 · ruling by … · source …"),
   rederived: {zone|null, credit_deadline|null, ruling_deadline|null, deadline_source|null}, matches: bool}
GET  /api/console/cases/{id}/conversation
  {case_id, threads: [{thread_id, session_started_at,
                       messages: [{role: "customer"|"agent", text, at}]}]}      (threads by session start, oldest first)
GET  /api/console/cases/{id}         (existing, same ConsoleCaseOut) handoff.copilot_proposal adds
  explanation: "Sugerencia: …, porque …"
```

## 8. Assumptions and open questions
- Assumption `[assumption]`: mock accounts `freddy`, `gianmarco`, `diego`, `judge` with any non-empty password stand in for
  Cognito (ADR 0017).
- Assumption `[assumption]` (AC-07, AC-08): "at risk" is 2 calendar days or less because the api's clock and the legal
  dates are dates, not times; 2 days is the MX debit credit window (2 business days, Banxico 3/2012), the shortest
  clock in `contracts/policies.yaml`. Changing it is one constant (`AT_RISK_DAYS` in `apps/web/lib/console-metrics.ts`).
- Assumption `[assumption]` (AC-09): the resolution's business date is its local date in the country's time zone for
  `live` cases, and the api's frozen today (deadline − days left) for `replay` cases and the mock (ADR 0020, ADR 0012).
  The legal date measured is the nearest one, the same date the api's countdown counts to.
- Known limit (AC-07, AC-09): the api's case list carries no events and no countdown, so the console reads each case's
  detail (`GET /api/console/cases/{id}`, six at a time). The api's events carry no payload, so a live credit approval
  shows as "Resolved by a person" with the analyst who resolved it; the mock names "Credit approved". Adding either to
  the list is a spec 01 change and is out of this PR.
- Assumption `[assumption]` (AC-16): the context window is ±30 days around the disputed charge, capped at the case's
  business today and at 200 rows, with the transaction statuses `search_transaction` can find (Approved, Pending);
  `outcome` is the case's first decisive analyst action read as the judge reads it (spec 18 §4.2), null while open.
  A call request with no case (D-026) has no case id; none is verified, so its status is always `requested`.
- Assumption `[assumption]` (AC-17): the summary lines are analyst-facing Spanish; the LLM wording reuses the spec 04
  writer's `Gate` (same line grounding) with an analyst prompt and the `S2` client; a failed wording is not cached, so
  the next read retries. `days_left` is computed on every read, never cached, and is not in the lines (it is not a
  tool fact, so the gate would drop it).
- Assumption `[assumption]` (AC-20): the `explanation` is a fixed-rule sentence like the card's own `rationale`, added
  only to the response (handoff.schema.json leaves `copilot_proposal` open); the stored card stays as the graph wrote
  it (spec 05 AC-21, constitution #5).
- Known limit (AC-18, AC-19): no `second_opinions` table exists in `schema.sql` (spec 18 §7), so the latest opinion
  per case lives in api process memory and is lost on a restart; `llm_calls` has no task column, so the judge's rows
  carry a `judge-` trace id and the summary's `console-summary-` (as `persona-` and `voice-`). The judge gets no
  transcript (the api does not hold one). The analyst decision's `matched_second_opinion` (spec 18 AC-10) is not
  written yet: it needs the `analyst_action` payload to change in the store. A4 and A5 need the agent trace's tool
  results and replies, so the console shows them as not applicable; A1 compares the zone only, since the decision's
  recorded inputs live in the trace.
- Assumption `[assumption]` (AC-22): the store holds no case → session → thread link and the store schema is not
  changed here, so the link lives in Platform's thread metadata: the api adds `case:<case_id>: true` (`PATCH
  /threads/{id}`) when a turn from Platform names a case of the session's customer in its run (stream and reconcile
  paths), and the console finds the threads with `POST /threads/search` and reads `POST /threads/{id}/history`. The
  store then checks each thread's session (customer and run). The graph resets `messages` every turn, so the
  transcript is rebuilt from the checkpoints: a customer text when a run's input first holds it, the agent's `reply`
  at the checkpoint that ends a turn (no next node, a new `trace_id`). A chip press shows only the agent's reply.
  Threads from before this change carry no mark and are not found.
- Assumption `[assumption]` (AC-10 to AC-13, AC-15): until the api lane's routes are on `main`, mock mode answers them from
  `apps/web/lib/mock/console.ts`, derived from the mock case (simulated); live mode calls the routes with the analyst's
  id token and never invents data. A `GET …/second-opinion` 404 and a `POST` 204 or `null` read as no opinion.
- Open question: the approval payload becomes `POST /api/cases/{id}/action` with `AnalystActionIn` when the live API is wired.

## 9. Out of scope
- Evidence graph visualisation (P2).
- The real login and backend (spec 05).

## 10. Plan, tasks and verification
- [x] Task 1 — `/login` and the session guard · covers AC-01 · done when: redirect and wrong-user checks pass
- [x] Task 2 — inbox, handoff card, timeline, actions, audit panel · covers AC-02 to AC-04 · done when: browser walk-through passes
- [x] Task 3 — supervised mode · covers AC-05 · done when: the test passes
- [x] Task 4 — responsive tabs · covers AC-06 · done when: tabs below 1024 px, grid from 1024 px
- [x] Task 6 — KPI strip, SLA light and Closed tab · covers AC-07 to AC-09 · done when: `lib/console-metrics.test.ts`
  passes and the console shows them at 1440 px and 390 px
- [ ] Task 7 — assisted case view: summary, customer history, auditor, second opinion, proposal, stepper, conversation tab · covers
  AC-10 to AC-15 · done when: `lib/console-assist.test.ts` passes on the mock and the view works against the live routes
- [ ] Task 5 — Cognito login and `POST /api/cases/{id}/action` · covers AC-01, AC-04, AC-05 · done when: same flow on the public URL
- [x] Task 8 — assisted console api: context, summary, second opinion, audit, the proposal's explanation and the
  case's conversation (`apps/api/app/console.py`, thread marks in `app/live.py` and `app/platform.py`) · covers AC-16
  to AC-22 · done when: `tests/test_spec08_assisted_console.py` and `tests/test_spec08_console_conversation.py` pass

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
