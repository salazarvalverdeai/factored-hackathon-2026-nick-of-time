# Spec 07 — Customer chat `/chat` with verified receipt and trace

- **Feature:** the customer-facing demo: chat in Spanish or Portuguese, a verified receipt and a visible trace.
- **Status:** In progress (works on mock data in PR #51; the live agent arrives with specs 04 and 05)
- **Owner:** @gianzk · **Priority:** P0 · **Size:** L
- **Challenge dimension:** AI Engineering
- **Depends on:** 16, then 04 and 05 · **Enables:** 13
- **ADRs:** [0013](../docs/adr/0013-customer-receives-proof-receipt-case-page-notifications.md), [0016](../docs/adr/0016-guardrails-injection-detector-and-exact-grounding.md), [0017](../docs/adr/0017-identity-mock-otp-customers-cognito-analysts.md)
- **Issue:** #9

> **Profile.** Minimal: sections 1, 3, 8, 9 and 10. The routes it calls belong to spec 01 §6.2.
> **Anti spec-drift.** If the chat changes later, update this spec in the same PR or mark it Superseded.

---

## 1. Introduction
The customer picks a demo customer, passes a one-time code shown on screen, and chats. When the agent blocks the card
and opens the case, the chat shows a receipt with only verified facts, and a trace panel shows each step and the
guardrails that fired. The customer app never receives the bank's score, the zone or policy ids (D-013).

## 3. Acceptance criteria (EARS)
AC-01 to AC-05 are copied from issue #9 with the same numbers. None is dropped or weakened.

- AC-01 — When the user picks a demo customer and passes the OTP, the system shall let them chat in Spanish and
  Portuguese. The picker shall read `GET /api/demo/customers` data, which carries no score or zone. · [U] · [T]
  `lib/api.test.ts` ("spec 07 AC-01: the customer chats in Spanish and in Portuguese", "… the demo picker data never
  carries the bank score or a zone")
- AC-02 — When the agent blocks and opens the case, the chat shall show the receipt widget: time, case id, deadline
  with its source, what the AI did and what a person will do, with the texts of `contracts/messages.yaml`. · [U] · [T]
  ("spec 07 AC-02: blocking and opening the case returns the receipt …")
- AC-03 — The trace panel shall show each graph step with its result and the guardrails that fired, and nothing the
  customer must not see (score, zone, policy ids). · [U] · [T] ("spec 07 AC-03: the trace lists each step …", "… what
  the customer chat shows never mentions the score or the zone")
- AC-04 — The UI shall distinguish "accepted" from "verified ✓" and show loading, error, DENY and expired-session
  states. · [U] · [T] ("spec 07 AC-04: accepted and verified are different …") An accepted action is labeled
  "requested", the word of spec 04 AC-18.
- AC-05 — The chat shall be usable at 390 px width, with no horizontal scroll. · [U]
- AC-06 — While the medium zone applies, the system shall state the plan and wait for the customer's confirmation
  before blocking (spec 04 AC-16); `customer_id` shall come only from the session. · [T] ("spec 07: the medium zone asks
  to confirm first …", "spec 07: customer_id comes only from the session")
- AC-07 — The picker label, the web's greeting and the agent's greeting shall name the same person: gold's first name,
  the one `get_customer_profile` returns (or the visitor's typed name in a demo session, §8). `GET /api/demo/customers`
  shall carry that name in `display_name`, and the web shall show its own greeting only until the agent greets, so a
  conversation shows exactly one greeting. · [T] `tests/test_spec07_names.py`, `lib/chat-view.test.ts` ("spec 07
  AC-07: …")
- AC-08 — After every live turn, the trace panel shall list the steps the web received: the progress labels streamed
  during the run, the understood request, the rules' decision, the plan, each action with its state (in progress,
  requested, verified, not confirmed) and its verification id, a verification summary, the case id and any denial.
  Each guardrail that fired shall show a plain-language name beside its id (`contracts/policies.yaml guardrails`); a
  policy id shall never be shown (AC-03). · [T] `lib/trace.test.ts`, `lib/live.test.ts` ("spec 07 AC-08: …")
- AC-09 — Agent replies shall keep their line breaks (capability bullets, numbered plan) and shall render as text,
  never as HTML. · [T] `lib/chat-view.test.ts` ("spec 07 AC-09: …")
- AC-10 — reserved for voice input (PR #178, spec 05 AC-21).
- AC-11 — While a turn runs, the chat shall show each `tool` event of spec 01 §6.4.1 as a checklist row in its state
  (running, done, failed) with the cards built from tool results (charge, verdict, deadline, case) and each action's
  state; a call with no result when the turn ends shall show as failed, and an action shall show as verified only with
  a `V-` id (constitution #4). · [T] `lib/chat-stream.test.ts` ("spec 07 AC-11: …")
- AC-12 — When `text` chunks arrive (writer `llm`), the chat shall render the reply as it is written, as safe markdown
  (no raw HTML, no half-written mark), and shall replace it with `turn.reply` when the turn ends. · [T] ("spec 07
  AC-12: …")
- AC-13 — The chips under the last reply shall be pills, at most three, and shall always include "talk to a person"
  (spec 04 AC-20, AC-39). · [T] ("spec 07 AC-13: …")
- AC-14 — A customer screen of the chat shall show no bracket label (`[simulated]`, `[data]`…) and no raw URL: a
  source is a named link; times and dates are in the session language (es-MX, pt-BR, 24 h) in the zone of the case's
  country, never from the system clock; beside a receipt, the reply shall not repeat its deadlines or sources, and the
  trace rows lead with a plain name, not a node key. · [T] ("spec 07 AC-14: …")
- AC-15 — A step, a card or "how I decided" shall open the shared right panel (`components/detail-panel.tsx`): a modal
  sheet that Escape closes, that keeps and then returns focus, that fits 390 px; motion stays off under
  `prefers-reduced-motion`. · [U]

## 8. Assumptions and open questions
- Assumption `[assumption]`: the scripted agent in `lib/mock/agent.ts` stands in for the LangGraph graph; refusal,
  clarify and cancel texts are local until spec 04 adds them to `contracts/messages.yaml`.
- Decided (lead, D-068, 2026-10-05; ADR 0026): the `/chat` start screen of demo mode, beside live mode. The web
  builds it on spec 05 AC-14 to AC-17 and never sends a `customer_id`:
  1. optional name field (≤ 40 characters: letters, with spaces, apostrophes, hyphens or ". " between words, no
     digits; a 422 `INVALID` shows the api's message);
  2. language ES or PT, required (the session language);
  3. country MX, CO or AR, optional (filters the scenarios);
  4. a scenario card from `GET /api/demo/scenarios?country&language` showing `title` and `customer_name` (gold's
     synthetic name), or "assign me one" (`scenario: "auto"`);
  5. `POST /api/sessions {display_name?, language, country?, scenario, mode?}`, then the OTP as today;
  6. after the OTP, the transactions of `GET /api/sessions/{id}/recent-transactions` as chips the visitor can pick,
     or free text. A chip sends a message naming the date, the amount with its currency and the merchant; when
     `merchant` is null it names only the date and amount; when the list holds more than one card it adds "card
     ending {last4}".
  7. demo type C (DEMOCD, only when the session's `mode` is `live`): a "register a test charge" form (amount in the
     country's currency, merchant) that posts `POST /api/sessions/{id}/synthetic-charge` (spec 05 AC-19); the answer
     and its chip carry the `[simulated]` label, and the chip list is re-read so the charge shows first. A 429 shows
     "one test charge per minute"; a 403 hides the form (a replay session).
  8. demo type D (DEMOCD): six character chips (aggressive, passive, terse, verbose, confused, code-switching ES/PT)
     that post `POST /api/demo/persona {character, transaction_id?}` (spec 05 AC-20; the chosen transaction chip, else
     the newest) and put the answer's `message` into the composer as an editable draft, never sent on its own. The
     draft is labeled "suggested" (`source: "llm"`, or "template" when the model was not used).
  The agent greets with the typed name, else the gold name, from `get_customer_profile`. Each session starts clean.
  Telegram and e-mail are off in a demo session (the link routes answer 403): the case page and the in-app log show
  every update.
- Open question: the receipt deadline line uses `status.credit_deadline` until the stub returns `source_url` and
  `verified_on` (ADR 0019); then it uses `receipt.credit_deadline`.

## 9. Out of scope
- Voice.
- The real agent and backend (specs 04, 05).

## 10. Plan, tasks and verification
- [x] Task 1 — OTP picker, chat, receipt widget, trace panel · covers AC-01 to AC-04 · done when: browser walk-through passes
- [x] Task 2 — mobile layout at 390 px · covers AC-05 · done when: no horizontal scroll
- [x] Task 3 — confirm-first flow and session-only identity · covers AC-06 · done when: the two tests pass
- [ ] Task 4 — call the live agent proxy (`/api/agent/...`, spec 05 M05) · covers AC-01 to AC-04 · done when: same flow on the public URL
- [ ] Task 5 — demo-mode start screen (D-068, the contract in §8) · covers AC-01 · done when: a visitor opens a demo
  session by scenario and picks a recent transaction on the public URL

- [x] Task 6 — production walkthrough fixes (2026-10-05): one greeting with the gold name, line breaks kept, trace
  filled on live turns with named guardrails · covers AC-07 to AC-09 · done when: the tests citing them pass
- [x] Task 7 — agentic chat, stage 1 (ADR 0030, plan of 2026-10-05): AI Elements (`conversation`, `suggestion`,
  `sources`, `task`, restyled to BRAND.md) with live tool steps, cards, streaming markdown, the receipt with its
  verified seal and named sources, chips as pills and the shared right panel; a mock stream in the exact §6.4.1 shapes
  (`lib/mock/stream.ts`) so it works with no backend · covers AC-11 to AC-15 · done when: the tests citing them pass

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
