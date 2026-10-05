# Spec 16 — Web foundation + front-end standard

- **Feature:** one standard for adding pages to the web app, and a mock API client so pages work before the backend exists.
- **Status:** Implemented (shells, components, mock client and README in PR #51; live mode on the spec 05 api in Task 5)
- **Owner:** @gianzk · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Technical Judgment
- **Depends on:** 01 (types follow the spec 01 §6.2 contract) · **Enables:** 07, 08, 12, 13, E1, `/agent`
- **ADRs:** [0013](../docs/adr/0013-customer-receives-proof-receipt-case-page-notifications.md), [0017](../docs/adr/0017-identity-mock-otp-customers-cognito-analysts.md)
- **Issue:** #18

> **Profile.** Minimal: sections 1, 3, 8, 9 and 10. There is no API of its own.
> **Anti spec-drift.** If the standard in `apps/web/README.md` changes, update this spec in the same PR or mark it Superseded.

---

## 1. Introduction
Diego and Freddy add page content without waiting for the backend. The foundation gives every page the same shell,
shared components (zone and status badges, timeline, chart, loading/empty/error/DENY states), the brand kit
(`docs/brand/BRAND.md`) and one data door, `lib/api.ts`. In mock mode it answers from `lib/mock/`, which enforces the
rules the backend must enforce; in live mode it talks to the spec 05 api through the same interface (`lib/client.ts`).

## 3. Acceptance criteria (EARS)
AC-01 to AC-05 are copied from issue #18 with the same numbers. None is dropped or weakened.

- AC-01 — The system shall provide shells for every page in the map (`/`, `/chat`, `/case/[id]`, `/login`, `/console`,
  `/evaluation`, `/analytics`, `/data`, `/agent`) with layout, navigation and dark mode. · [U]
- AC-02 — The system shall provide shared components: card, table, chart (Recharts, source label required), zone badge
  (high green, medium amber, human red, always with its text), status badge, timeline, and loading, empty, error and
  DENY states. · [U]
- AC-03 — The system shall provide an API client with a mock mode that follows the spec 01 contract, so pages work
  without the backend; in live mode it shall answer from the spec 05 api through the same interface and, when the api
  fails, shall answer the api's error instead of inventing data. · [T] `apps/web/lib/api.test.ts` ("spec 16 AC-03: …";
  "spec 07: agent texts are the ones in contracts/messages.yaml …" keeps the mock texts equal to the contract) and
  `apps/web/lib/live.test.ts` ("spec 16 AC-03: …" and the spec 05 / 04 / 13 criteria the live client carries: sessions,
  agent turns, case pages, notifications, Cognito sign-in, analyst actions, supervised mode)
- AC-04 — `apps/web/README.md` shall replace the Next.js boilerplate with the standard: how to add a page, which
  components to use, how to fetch data, style rules (including the brand kit) and an example page. · [D]
- AC-05 — A new page built from the template (`app/_template`) shall pass lint and build in CI. · [C] `npm run lint &&
  npm test && npm run build` in the `web` job of `.github/workflows/ci.yml`

## 8. Assumptions and open questions
- Assumption `[assumption]`: until spec 05 ships, the mock store is the only data source; `lib/types.ts` follows the
  merged spec 01 projections (customer pages never receive score, zone, priority or policy ids).
- Decided (Task 5): the open question resolved differently from the first guess. Live mode needed async reads, so `useQuery`
  now takes any `api` call (`useQuery((api) => api.listCases())`) and the pages changed with it; `lib/client.ts` is the
  interface both clients implement, and `lib/live.ts` the live one. The console lists summaries and reads the selected case
  with its handoff card (`GET /api/console/cases/{id}`), as the api serves them.
- `[assumption]` Analysts sign in from the browser with Cognito `USER_PASSWORD_AUTH` and the id token is kept in `sessionStorage`
  (this tab only, expires with the token, no refresh). The pool's app client must allow that flow; a user created by an admin
  with a temporary password must set a new one first (the page does not answer `NEW_PASSWORD_REQUIRED`).
- `[assumption]` The api has no customer logout route (spec 05), so "Sign out" in live mode only forgets the session in the browser.
- `[assumption]` The console's audit panel in live mode lists the actions of this browser session; the server's record is the case
  timeline (`case_events`). A global audit list needs an api route that does not exist yet.

## 9. Out of scope
- Page content owned by others (`/evaluation`, `/analytics`, `/data`, `/agent`).
- The real backend (spec 05).

## 10. Plan, tasks and verification
- [x] Task 1 — shells, header with the brand logo, dark mode · covers AC-01 · done when: pages open on `npm run dev`
- [x] Task 2 — shared components and the private `_template` page · covers AC-02, AC-05 · done when: lint and build pass
- [x] Task 3 — `lib/api.ts` with `lib/mock/` and tests · covers AC-03 · done when: `npm test` passes
- [x] Task 4 — `apps/web/README.md` standard · covers AC-04 · done when: the 5-step "add a page" works from the template
- [x] Task 5 — wire live mode on the spec 05 API · covers AC-03 · done when: the same pages run with `NEXT_PUBLIC_API_MODE=live` (checked by hand against a local api: chat, case page, call request, analyst sign-in, take; the public URL run belongs to spec 05 Task 7)

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
