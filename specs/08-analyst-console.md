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
- [ ] Task 5 — Cognito login and `POST /api/cases/{id}/action` · covers AC-01, AC-04, AC-05 · done when: same flow on the public URL

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
