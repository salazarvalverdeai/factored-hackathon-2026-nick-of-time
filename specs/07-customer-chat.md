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
  states. · [U] · [T] ("spec 07 AC-04: accepted and verified are different …")
- AC-05 — The chat shall be usable at 390 px width, with no horizontal scroll. · [U]
- AC-06 — While the medium zone applies, the system shall state the plan and wait for the customer's confirmation
  before blocking (spec 04 AC-16); `customer_id` shall come only from the session. · [T] ("spec 07: the medium zone asks
  to confirm first …", "spec 07: customer_id comes only from the session")

## 8. Assumptions and open questions
- Assumption `[assumption]`: the scripted agent in `lib/mock/agent.ts` stands in for the LangGraph graph; refusal,
  clarify and cancel texts are local until spec 04 adds them to `contracts/messages.yaml`.
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

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
