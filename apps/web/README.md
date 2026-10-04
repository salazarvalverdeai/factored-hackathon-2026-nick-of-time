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
| `/` | 16 | home with links |
| `/chat` | 07 | working on mock data: demo customer + OTP, ES/PT chat, verified receipt, trace |
| `/case/[id]` | 13 | working on mock data: timeline, countdown, call request, notifications, Telegram/e-mail |
| `/login`, `/console` | 08 | working on mock data: analyst login, inbox, handoff card, approve, audit, supervised mode |
| `/evaluation`, `/analytics`, `/data` | 12 | shells, content owned by Diego |
| `/agent` | 04 | shell |

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
| States | `LoadingState`, `EmptyState`, `ErrorState`, `DenyState` | `components/states.tsx` |

## Fetching data
Pages never import the mock store. They read with `useQuery` (`lib/use-query.ts`) and act with `api` (`lib/api.ts`).

```tsx
const cases = useQuery((store) => store.listCases());   // { status: "loading" | "error" | "ok", … }
await api.approveCredit(id);                            // throws ApiError { code, status }
```
- **Mock mode (default):** `lib/mock/` answers locally, persists in `localStorage` and enforces the backend rules: 15-minute
  customer sessions (`SESSION_EXPIRED`), analyst login, a status that is the last event, 409 for transitions outside the
  case queue, supervised mode, audit. `[simulated]` — none of it is dataset data.
- **Live mode:** `NEXT_PUBLIC_API_MODE=live` answers `LIVE_API_NOT_READY` until spec 05 ships the backend. Only
  `lib/api.ts` and `lib/use-query.ts` change then; the pages do not.
- Spec 01 (integration contract) is not merged yet. When it lands, regenerate `lib/types.ts` from its stubs.

## Style rules
- English for code, comments and UI; Spanish or Portuguese only for customer-facing text (agent replies, notifications).
- Tailwind classes and the theme tokens (`bg-background`, `text-muted-foreground`, `border`…); no hard-coded colors except the zone and status badges.
- Dark mode is the default and must stay readable; check both before asking for review.
- Mobile first: the customer chat works at 390 px, the console switches to tabs below 1024 px. No horizontal page scroll.
- Never show the fraud score, policy ids or the transcript to a customer. The analyst may see the score.
- Every figure on screen carries a label: `[data]` `[external]` `[assumption]` `[simulated]` `[projected]`.
- Accepted is not verified: show them as different states (`accepted` vs `verified ✓`).
- Color is never the only signal: badges always carry their text.

## Tests
`npm test` runs Node's built-in runner on `lib/**/*.test.ts` (no extra packages). Each test cites the acceptance criterion
it covers, for example `spec 13 AC-03`. A page built from the template must pass `npm run lint` and `npm run build`.
