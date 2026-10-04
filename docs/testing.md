# Testing

How Nick of Time is tested, where each kind of test runs, and how it produces the evidence that acceptance criteria
require ([T] test · [C] command · [U] screenshot or video · [D] file — see [CONTRIBUTING.md](../CONTRIBUTING.md)).

## 1. Levels
| Level | What | Tool | Runs |
|---|---|---|---|
| Unit | policies, clock, tools, store, receipt builder | pytest | CI, every PR |
| Integration | graph with the `fake` LLM and the fake MCP; API with TestClient + Postgres service | pytest | CI, every PR |
| Contract | MCP tools vs `contracts/tools.py`; API vs its OpenAPI; handoff, receipt and eval cases vs their JSON Schemas | pytest (+ Schemathesis, P1) | CI, every PR |
| **End-to-end (web)** | user journeys in the browser against the mock API | **Playwright** | CI, PRs touching `apps/web/` |
| Accessibility | WCAG A/AA rules on the main pages | `@axe-core/playwright` | CI, with E2E |
| Evaluation | final-state harness, pass^4, real LLM; its checks come from the auditor library `nick_of_time.audit` (spec 18) | `eval/` (spec 10) | manual / before releases |
| Smoke (post-deploy) | public URL alive, health SHA, pages render | Playwright + `curl` | after every deploy |

## 2. Playwright setup (spec 16 sets it up; every UI spec adds its scenarios)
- **Location:** `apps/web/e2e/`, config `apps/web/playwright.config.ts`.
- **Projects:** `desktop-chromium` (1280×800) and `mobile` (390×844, touch) — every P0 journey runs in both.
- **Server under test:** in CI, Playwright's `webServer` starts the Next.js app in **mock mode**
  (`NEXT_PUBLIC_API_MODE=mock`), which serves the spec 01 fixtures. No backend, LLM or AWS in CI: tests are deterministic.
- **Auth:** CI uses `AUTH_MODE=mock` with a pre-built `storageState` for the analyst. Real Cognito login is covered only by
  the post-deploy smoke, using the judge account from a GitHub secret the lead loads.
- **Selectors:** roles and accessible names first (`getByRole('button', { name: … })`); `data-testid` only for
  structural anchors, in kebab-case: `receipt-card`, `trace-step`, `zone-badge`, `case-timeline`, `deadline-countdown`,
  `inbox-row`, `handoff-card`, `supervised-toggle`, `suggestion-chips`, `progress-step`, `action-state`, `mode-badge`,
  `second-opinion`, `audit-panel`.
- **Naming and traceability:** one file per spec, `e2e/specNN-<topic>.spec.ts`; every test title starts with the
  criterion it proves: `test('AC-02 shows the verified receipt after a block', …)`.
- **Evidence:** CI uploads the HTML report, traces and screenshots as artifacts. A screenshot attached to a passing
  test counts as [U] evidence for that criterion.
- **Stability rules:** no fixed sleeps (use web-first assertions); fixtures are static; `retries: 1` in CI with
  `trace: 'on-first-retry'`; a flaky test is fixed or quarantined within the day, never ignored.
- **Budget:** the E2E job stays under 4 minutes.

## 3. Scenarios per spec
| Spec | Scenario (criterion) | Projects |
|---|---|---|
| 16 web foundation | every page in the map renders its shell, nav and dark mode; loading, empty, error and DENY states render from the mock (AC-01, AC-02); a page built from the template passes (AC-05) | both |
| 07 `/chat` | pick a demo customer → OTP → chat in ES and PT (AC-01); a high-zone case shows the receipt with time, case id, deadline and source (AC-02); the trace lists each step (AC-03); "accepted" vs "verified ✓", DENY and expired-session states (AC-04); usable at 390 px (AC-05); three starter chips on the first turn and 2–3 chips under the last reply only, with a person always reachable; an action chip sends its action (spec 04 AC-29–AC-32); the plan, the progress steps and the four action states render from the fixture (spec 04 AC-16–AC-18); the mode badge shows Live or Historical (ADR 0020) | both |
| 08 `/login` + `/console` | no session → redirect to `/login` (AC-01); inbox sorted with zone colors (AC-02); open a case → handoff card + timeline (AC-03); approve credit → status changes and shows on `/case/{id}` (AC-04); supervised-mode toggle audited (AC-05); tabs below 1024 px (AC-06); the second opinion is labeled advisory, shown after the facts, and "No second opinion" renders when it is missing (spec 18 AC-09, AC-11); P1: the audit panel shows each check with icon and label and a critical finding needs acknowledgment (spec 18 AC-05, AC-06) | both |
| 13 `/case/{id}` | timeline, deadline countdown with source, "request a call" (AC-05); add information → event visible (AC-06); "Get updates on Telegram" shows a deep link; e-mail opt-in asks for confirmation (AC-02, AC-04); each notification shows its masked address and delivery status; "ask for a re-evaluation" appears only on a resolved case (spec 01 §6.2) | both |
| 12 insight pages | `/evaluation`, `/analytics` and `/data` render charts from the JSON fixtures with their labels (`[data]`, `[simulated]`) | desktop |
| E1 landing | `/` shows the problem in numbers and "try the demo" leads to `/chat` | both |
| Accessibility | no `serious` or `critical` axe violations on `/`, `/chat`, `/case/{id}`, `/console` | desktop |

Over time (ADR 0021, nice to have): the sealed evaluation sets become a nightly regression gate for every model and
decision engine in the inventory.

## 4. Post-deploy smoke (spec 06)
After each deploy, a short Playwright run against `https://nickoftime.salazarvalverdeai.com`: `/api/health` returns
the deployed SHA; `/`, `/chat`, `/evaluation` render; the analyst login page loads. It is **read-only** — it never
creates cases outside the demo sandbox — and a failure marks the deploy as failed.

## 5. Before recording the video
Reset the demo data (spec 05), run the full E2E suite against the public URL with the judge account, and keep the
Playwright report of that run as the release evidence for `v0.4.0`.
