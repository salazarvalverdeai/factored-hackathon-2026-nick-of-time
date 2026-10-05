# Spec 16 — Web foundation + front-end standard

- **Feature:** one standard for adding pages to the web app, and a mock API client so pages work before the backend exists.
- **Status:** In progress (shells, components, mock client and README delivered in PR #51; AC-05 is checked by CI)
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
rules the backend must enforce; in live mode it answers `LIVE_API_NOT_READY` until spec 05.

## 3. Acceptance criteria (EARS)
AC-01 to AC-05 are copied from issue #18 with the same numbers. None is dropped or weakened.

- AC-01 — The system shall provide shells for every page in the map (`/`, `/chat`, `/case/[id]`, `/login`, `/console`,
  `/evaluation`, `/analytics`, `/data`, `/agent`) with layout, navigation and dark mode. · [U]
- AC-02 — The system shall provide shared components: card, table, chart (Recharts, source label required), zone badge
  (high green, medium amber, human red, always with its text), status badge, timeline, and loading, empty, error and
  DENY states. · [U]
- AC-03 — The system shall provide an API client with a mock mode that follows the spec 01 contract, so pages work
  without the backend; in live mode, while the backend is not wired, it shall answer `LIVE_API_NOT_READY` instead of
  inventing data. · [T] `apps/web/lib/api.test.ts` ("spec 16 AC-03: …", three tests; "spec 07: agent texts are the ones
  in contracts/messages.yaml …" keeps the mock texts equal to the contract)
- AC-04 — `apps/web/README.md` shall replace the Next.js boilerplate with the standard: how to add a page, which
  components to use, how to fetch data, style rules (including the brand kit) and an example page. · [D]
- AC-05 — A new page built from the template (`app/_template`) shall pass lint and build in CI. · [C] `npm run lint &&
  npm test && npm run build` in the `web` job of `.github/workflows/ci.yml`

## 8. Assumptions and open questions
- Assumption `[assumption]`: until spec 05 ships, the mock store is the only data source; `lib/types.ts` follows the
  merged spec 01 projections (customer pages never receive score, zone, priority or policy ids).
- Open question: when `NEXT_PUBLIC_API_MODE=live` is wired, only `lib/api.ts` and `lib/use-query.ts` should change.

## 9. Out of scope
- Page content owned by others (`/evaluation`, `/analytics`, `/data`, `/agent`).
- The real backend (spec 05).

## 10. Plan, tasks and verification
- [x] Task 1 — shells, header with the brand logo, dark mode · covers AC-01 · done when: pages open on `npm run dev`
- [x] Task 2 — shared components and the private `_template` page · covers AC-02, AC-05 · done when: lint and build pass
- [x] Task 3 — `lib/api.ts` with `lib/mock/` and tests · covers AC-03 · done when: `npm test` passes
- [x] Task 4 — `apps/web/README.md` standard · covers AC-04 · done when: the 5-step "add a page" works from the template
- [ ] Task 5 — wire live mode on the spec 05 API (stub #56) · covers AC-03 · done when: the same pages run with `NEXT_PUBLIC_API_MODE=live`

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
