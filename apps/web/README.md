# apps/web — Nick of Time front end

Next.js 16 · React 19 · Tailwind 4 · shadcn-style components · Recharts. **This is not the Next.js you may know:** read
the guide you need in `node_modules/next/dist/docs/` before writing framework code (see `AGENTS.md`).

```bash
npm ci
npm run dev        # http://localhost:3000, mock data, no backend needed
npm run lint && npm test && npm run build     # what CI runs
```

## Page map
| Route | Spec | State |
|---|---|---|
| `/` | 16 | home: lockup, the problem in numbers (labeled, linked), how it works, "Evaluate in 3 minutes"; hero visual and OG image slots for the lead |
| `/chat` | 07 | demo customer + OTP, ES/PT chat with live tool steps and cards, streaming reply, verified receipt, trace, right detail panel; the mock plays the spec 01 §6.4.1 stream (`lib/mock/stream.ts`) |
| `/case/[id]` | 13 | working on mock data: timeline, countdown, call request, notifications, Telegram/e-mail |
| `/login`, `/console` | 08 | working on mock data: analyst login, KPI strip, inbox with SLA lights, Closed tab, handoff card, approve, audit, supervised mode |
| `/evaluation`, `/analytics`, `/data` | 12 | shells, content owned by Diego |
| `/agent` | 04 | architecture, graph nodes, policy ids, tools, guardrails and model inventory, generated from the repo (`npm run sync:agent`) |

## Add a page (5 steps)
1. `cp -r app/_template app/my-page` (the template is a private folder: it is linted and built but not routed).
2. Change the title, the description and the query. Keep the `PageShell`.
3. Read data with `useQuery((store) => …)` and handle all four states: loading, error, empty, content.
4. Act through `api` from `@/lib/api` (it returns promises and throws `ApiError`); show the error with `ErrorState`.
5. Add the route to `NAV` in `components/site-header.tsx` if it should appear in the header; run `npm run lint && npm test && npm run build`.

## Components (use these, do not re-invent them)
| Need | Use | File |
|---|---|---|
| Page frame | `PageShell` | `components/page-shell.tsx` |
| Card, table, button, tabs, input | `Card…`, `Table…`, `Button`, `Tabs…`, `Input`, `Textarea` | `components/ui/` |
| Risk zone | `ZoneBadge` — **high green, medium amber, human red**, always with its text label | `components/badges.tsx` |
| Case status | `StatusBadge` (`new · verification · review · resolved · closed`) | `components/badges.tsx` |
| Case history | `Timeline` (a case's status is its last event) | `components/timeline.tsx` |
| Chart | `BarChartCard` (Recharts); `source` is **required** and carries the figure label | `components/chart.tsx` |
| Animated figure (sparingly) | `NumberTicker` (Magic UI): renders the final value without JavaScript, animates once below the fold, never with reduced motion | `components/ui/number-ticker.tsx` |
| States | `LoadingState`, `EmptyState`, `ErrorState`, `DenyState` | `components/states.tsx` |
| Right detail panel ("Detail →") | `DetailPanel`, `DetailFields`, `DetailField`: generic modal sheet, Escape closes, focus returns | `components/detail-panel.tsx` |
| Chat building blocks | AI Elements (`conversation`, `suggestion`, `sources`, `task`), restyled to the brand | `components/ai-elements/` |

## Fetching data
Pages never import the mock store or call `fetch`. They read with `useQuery` (`lib/use-query.ts`) and `useSession`, and act
with `api` (`lib/api.ts`). Both modes answer the same `ApiClient` interface (`lib/client.ts`), so a page never knows which one it uses.

```tsx
const cases = useQuery((api) => api.listCases());      // { status: "loading" | "error" | "ok", … }; reloads after every action
const { analystSession, supervised } = useSession();   // who is signed in: the same in mock and live mode
await api.analystAction(id, "take");                    // throws ApiError { code, status }
```
- **Mock mode (default):** `lib/mock/` answers locally, persists in `localStorage` and enforces the backend rules: 15-minute
  customer sessions (`SESSION_EXPIRED`), analyst login, a status that is the last event, 409 for transitions outside the
  case queue, supervised mode, audit. `[simulated]` — none of it is dataset data.
- **Live mode:** `NEXT_PUBLIC_API_MODE=live` (read at build time) uses `lib/live.ts` over the spec 05 api. Customers verify with
  the on-screen code and the api sets an httpOnly cookie; analysts sign in with Amazon Cognito (`USER_PASSWORD_AUTH`) and the
  id token goes as `Authorization: Bearer` (kept in `sessionStorage`, this tab only). The chat is the api's agent proxy
  (thread + SSE stream with the step labels); a chip press sends its `action`, never text. A call that fails answers the
  api's error (`UNAVAILABLE`, `DENY`, `RATE_LIMITED`…): live mode never invents data.

  | Variable | Used for |
  |---|---|
  | `NEXT_PUBLIC_API_MODE` | `mock` (default) or `live`; inlined at build, so the production image takes it as a build arg (`deploy.yml` reads the repository variable of the same name) |
  | `NEXT_PUBLIC_COGNITO_CLIENT_ID`, `NEXT_PUBLIC_COGNITO_REGION` (default `us-east-2`) | the analysts' pool; the app client must allow `ALLOW_USER_PASSWORD_AUTH`, and the same pool must be the one the api verifies (`COGNITO_*`) |
  | `API_PROXY_URL` | `next dev` only: forwards `/api/*` to a local api (e.g. `http://localhost:8000`). In production Caddy routes `/api/*` |

  ```bash
  # a local api on :8000 (apps/api/README.md), then:
  NEXT_PUBLIC_API_MODE=live API_PROXY_URL=http://localhost:8000 NEXT_PUBLIC_COGNITO_CLIENT_ID=<app client id> npm run dev
  ```
  Known differences from the mock: the api has no customer logout route, so "Sign out" only forgets the session here (it expires
  by itself after 15 minutes); the console's audit panel lists this session's actions (the case timeline holds the server's
  record); e-mail is confirmed by a link, not at once; Telegram and e-mail answer `DENY` in a demo run (spec 05 AC-16).
- **Contract alignment (spec 01 §6.2, D-013):** customer pages get projections only. `api.getCase` returns `CustomerCaseView`
  (no score, zone, priority, handoff, policy ids, analyst names); the handoff card is `api.getConsoleCase`, analyst session only.
  The demo picker reads `api.listDemoCustomers()` (`GET /api/demo/customers`): no score. Priority is `normal | high`, dates are
  raw `YYYY-MM-DD`, `Receipt.issued_at` is UTC ISO-8601, `requestCall` returns `{event_id, expected_contact_by}`.
  In mock mode the bank-side fixtures (with the score) live inside the mock store only; live mode never has them.
- **Messages:** the agent's ES/PT texts are `lib/mock/messages.ts`, generated from `contracts/messages.yaml` with
  `npm run sync:messages`. `npm test` fails when the file drifts. Texts the contract does not have yet (refusal, clarify,
  cancel) are marked `LOCAL` in `lib/mock/agent.ts` until spec 04 adds them.

## Style rules
- **Brand:** follow [`docs/brand/BRAND.md`](../../docs/brand/BRAND.md). Violet `#7C3AED` is the primary, teal `#0F766E` means verified, amber `#D97706` marks deadlines and
  urgency (restrained), dark base `#080812` with `#111827` panels, Sora for text and JetBrains Mono for code. Logos and avatars are copies of the
  SVG/PNG sources in `docs/brand/` under `public/brand/`: never redraw the mark, no glow or shadows. Use the tokens (`bg-primary`, `text-brand-teal`, `border-brand-amber`).
- English for code, comments and UI; Spanish or Portuguese only for customer-facing text (agent replies, notifications).
- Tailwind classes and the theme tokens (`bg-background`, `text-muted-foreground`, `border`…); no hard-coded colors except the zone and status badges.
- Dark mode is the default and must stay readable; check both before asking for review.
- Mobile first: the customer chat works at 390 px, the console switches to tabs below 1024 px. No horizontal page scroll.
- Never show the fraud score, policy ids or the transcript to a customer. The analyst may see the score.
- Every figure on screen carries a label: `[data]` `[external]` `[assumption]` `[simulated]` `[projected]`.
- Accepted is not verified: show them as different states (`accepted` vs `verified ✓`).
- Color is never the only signal: badges always carry their text.

## Tests
`npm test` checks that `messages.ts` matches the contract and that `agent-reference.ts` matches its sources (`npm run sync:agent` regenerates it), then runs Node's built-in runner on `lib/**/*.test.ts`. Each test cites the acceptance criterion
it covers, for example `spec 13 AC-03`. A page built from the template must pass `npm run lint` and `npm run build`.

## Local check of `/evaluation` on fixtures
`EVALUATION_DATA_DIR` makes the page read its result files from another folder at build time, for a local screenshot
check with `app/evaluation/__fixtures__/` copied to a temp folder. It is unset in production; a path outside the
repository and the system temp directory is ignored and the page reads `public/data/`. Never put protocol results
there by hand: `public/data/` holds only exporter output.
