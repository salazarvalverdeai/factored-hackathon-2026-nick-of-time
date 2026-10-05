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
AC-01 to AC-06 are copied from issue #10 with the same numbers. None is dropped or weakened.

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

## 8. Assumptions and open questions
- Assumption `[assumption]`: mock accounts `freddy`, `gianmarco`, `diego`, `judge` with any non-empty password stand in for
  Cognito (ADR 0017).
- Open question: the approval payload becomes `POST /api/cases/{id}/action` with `AnalystActionIn` when the live API is wired.

## 9. Out of scope
- Evidence graph visualisation (P2).
- The real login and backend (spec 05).

## 10. Plan, tasks and verification
- [x] Task 1 — `/login` and the session guard · covers AC-01 · done when: redirect and wrong-user checks pass
- [x] Task 2 — inbox, handoff card, timeline, actions, audit panel · covers AC-02 to AC-04 · done when: browser walk-through passes
- [x] Task 3 — supervised mode · covers AC-05 · done when: the test passes
- [x] Task 4 — responsive tabs · covers AC-06 · done when: tabs below 1024 px, grid from 1024 px
- [ ] Task 5 — Cognito login and `POST /api/cases/{id}/action` · covers AC-01, AC-04, AC-05 · done when: same flow on the public URL

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
