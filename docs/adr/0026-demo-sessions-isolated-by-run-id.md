# 0026. Public demo sessions: a scenario picks the customer server-side and each session runs under its own run_id

- **Status:** Accepted (lead decision D-068, 2026-10-05)
- **Date:** 2026-10-05
- **Deciders:** Freddy (lead; D-068, demo mode types A+B) · **Owner:** @salazarvalverdeai
- **Related:** specs 01 (§6.5 `sessions`, §6.8 isolation), 05 (AC-14 to AC-17), 07, 09 · ADRs 0004, 0017, 0020

## Context
- The public `/chat` lets any visitor try the agent on the six spec 09 demo customers (`eval/demo/customers.json`).
  Many visitors use the same six customers at the same time, and the store is append-only: nothing may be reset or
  deleted (constitution #2, spec 01 §6.5).
- Evaluation runs already solve the same problem: every row written while serving a seeded session carries the
  session's `run_id`, and every read of mutable state filters by it (spec 01 §6.8, D-023). The MCP server reads the
  session row on every call, so it scopes cases, blocks and idempotency keys by that `run_id` without other changes.
- `customer_id` comes only from the session, never from the customer's text (constitution #3). The greeting name
  must be a tool fact (spec 04 AC-15), and the picker showed `customers.json` names that gold does not hold.

## Decision
A demo session is opened with a scenario, not a customer: `POST /api/sessions {display_name?, language, country?,
scenario?}`. The api maps the scenario (or `auto`) to one of the demo customers gold serves and stores, on the session
row, a fresh `run_id = demo-<UTC yyyymmddThhmmssZ>-<6 base32>` and the visitor's typed `display_name`.

The details that matter:
- **Scenarios** come from `customers.json` tagged with the spec 09 dev and sample cases of the same customer. A file or
  folder named `heldout` or `test` is refused before it is opened, and a row of another set is dropped.
- **Name.** `display_name` is optional, trimmed, at most 40 characters, letters with spaces, apostrophes, hyphens and
  dots only (no digits, URL, e-mail, control character or injection pattern; 422 otherwise). `get_customer_profile`
  returns it when present, else gold's first name, so the greeting stays a tool fact.
- **Isolation.** The demo `run_id` follows the eval path unchanged: two demo sessions of one customer never see each
  other's cases, blocks, notifications or idempotency keys. No row is deleted.
- **No external channel in a demo run.** `customer_channels` is per customer, not per run, and a demo customer is
  shared by every visitor, so a Telegram chat or inbox bound by one visitor would receive another visitor's summaries.
  In a `demo-` run the Telegram and e-mail link routes refuse the case, `get_customer_profile` lists no channel,
  `send_case_summary` answers `DENY` (logged by the gate as a policy denial), and analyst actions write only the
  in-app notification. Production sessions keep their channels.
- **Analysts.** The console lists and acts on production cases and on demo-run cases (`demo_runs=True` in
  `get_case`/`list_all_cases`), never on eval runs.
- The original picker (`customer_id`) still works until the web moves to scenarios, and its sessions get a fresh
  `demo-` run too: every session the public URL opens is isolated.

**Update 2026-10-05 (DEMOCD, demo type C).** A live demo visitor may register one synthetic charge at a time
(`POST /api/sessions/{id}/synthetic-charge`, spec 05 AC-19). The `demo_transactions` row carries the session's `run_id`
and is read only by that run, so the same isolation holds: another visitor of the same customer, a replay session or a
production session never sees it (spec 03 AC-14). Its score is a fixed `[assumption]` value labeled `synthetic`
(D-027), never the visitor's; it never reaches gold, the lakehouse, the evaluation or a pitch number (ADR 0020).
Demo type D, a generated persona (`POST /api/demo/persona`, spec 05 AC-20), only drafts the visitor's first message in
a chosen character's voice: S1 writes it from the session's own charge with the name passed as data, its cost is an
`llm_calls` row of the run, and the visitor edits and sends it like any message, so no tool, receipt or rule reads it.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| A fresh `run_id` per demo session (chosen) | Reuses the eval isolation already enforced by the MCP gate and the store; append-only intact | The console needs a demo-run filter; `sessions` gains one column; channels are off in demo runs |
| Channels scoped per run (with the chosen run) | Telegram and e-mail would work in the demo | A schema change or a join through case events on every channel read; not for the deadline |
| Reset the demo customers between visitors | One shared state | Deletes or rewrites audit rows (breaks #2); visitors collide mid-demo |
| One synthetic customer per visitor | Full isolation | Not a gold customer, so the MCP finds no transactions (D-052) |

## Consequences
- Each visitor starts clean and the analyst still sees every demo case. Eval runs stay out of the console.
- The demo shows notifications in the in-app log and the case page only; Telegram and e-mail are shown with a
  production session.
- `sessions.display_name` is a new nullable column (`schema.sql`, migration 0002).
- A demo case is tied to a short-lived session: once it expires, the visitor sees it only through the case page link.

## Confidence
High for isolation (the same mechanism the eval harness relies on). Revisit if demo traffic needs the store pruned.
