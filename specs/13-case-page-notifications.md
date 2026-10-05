# Spec 13 — `/case/{id}` + Telegram + email notifications

- **Feature:** the customer receives proof, not promises, and does not need to call (ADR 0013).
- **Status:** In progress (page, linking and notification rules work on mock data in PR #51; real Telegram and Resend arrive with spec 05)
- **Owner:** @gianzk · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Technical Judgment
- **Depends on:** 05, 16; `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `RESEND_API_KEY` in SSM · **Enables:** E1
- **ADRs:** [0013](../docs/adr/0013-customer-receives-proof-receipt-case-page-notifications.md), [0017](../docs/adr/0017-identity-mock-otp-customers-cognito-analysts.md)
- **Issue:** #15

> **Profile.** Minimal: sections 1, 3, 8, 9 and 10. The routes it calls belong to spec 01 §6.2.
> **Anti spec-drift.** If the page or the channels change later, update this spec in the same PR or mark it Superseded.

---

## 1. Introduction
After the receipt, the customer follows the case on `/case/{id}`: timeline, a deadline countdown with its legal source,
a "request a call" button, and the channels (in-app log, Telegram, e-mail). Every status change is notified. The page
shows only the customer projection of the case: never the score, the zone, the priority, policy ids or the transcript.

## 3. Acceptance criteria (EARS)
AC-01 to AC-09 are copied from issue #15 with the same numbers. None is dropped or weakened.

- AC-01 — When a case's status changes, the customer shall get the notification in "My notifications" and, if linked,
  by Telegram and e-mail. · [U] · [T] `lib/api.test.ts` ("spec 13 AC-01 and AC-02: a status change notifies in-app and,
  once linked, by Telegram")
- AC-02 — When the customer taps "Get updates on Telegram", the system shall create a one-time token (TTL 15 min) and a
  deep link; on `/start <token>` it shall store the `chat_id` and record `telegram_linked`. · [T] (same test)
- AC-03 — If the Telegram webhook arrives without the correct secret header, or with an expired token, then it shall
  answer 401 and process nothing. · [T] ("spec 13 AC-03: a wrong secret or an expired token answers 401 …")
- AC-04 — E-mail shall be sent only to an address the user typed and confirmed, never to a dataset address. · [T]
  ("spec 13 AC-04: e-mail is sent only to an address the user typed and confirmed")
- AC-05 — `/case/{id}` shall show the timeline, a deadline countdown with its legal source and a "request a call"
  button, from the customer projection (no score, zone, priority, handoff, policy ids or analyst names). The call request
  shall return the event id and the expected contact date computed by the tool (D-008). · [U] · [T] ("spec 13 AC-05: the
  customer's case is a projection …", "… a call request returns the event id and the expected contact date …")
- AC-06 — When the customer adds information from `/case/{id}`, a `customer_info_added` event shall be visible to the
  analyst. · [T] ("spec 13 AC-06: information added from /case/{id} is an event the analyst can see")
- AC-07 — If a channel fails, then the notification shall stay in the log and the `/chat` receipt shall be unaffected.
  · [T] ("spec 13 AC-07: if a channel fails the notification stays in the log …")
- AC-08 — No customer message shall include the score, `policy_id`s or the transcript (`never_send`). · [T] ("spec 13
  AC-08: no customer notification carries the score, a policy id or the transcript")
- AC-09 — The flow diagrams shall be updated with the receipt, `/case/{id}`, the channels and the returning customer. ·
  [D] *Pending.*

A customer shall not read another customer's case · [T] ("spec 13: a customer cannot read another customer's case").

## 8. Assumptions and open questions
- Assumption `[assumption]`: the Telegram deep link uses a placeholder bot name and the webhook is simulated in the page
  until the real bot exists (spec 05).
- Open question: notifications become `GET /api/notifications` (session-wide, filtered by `case_id` on the client).
- `[assumption]` (EV1, pending the lead): the agent's own writes are told by the MCP read that verifies them
  (constitution #4). Once the first `get_case` that verifies an `open_case`, or the first `get_product_status` that
  verifies a `block_card`, has its answer, it writes the `case_opened` / `card_blocked` in-app `log` notification
  (`delivered`) once per case and event (`store.once`, key prefix `notify:`, which the gate refuses from a tool call);
  a failure is logged and never changes the read's answer. The text is the Spanish `policies.yaml` template filled with
  stored facts; `{deadline}` is the case page's earliest stored deadline, else "—". Portuguese text waits for D-073.
- Pending (follow-up for @gianzk): Telegram and e-mail delivery of `case_opened` / `card_blocked`. No component sends
  queued rows yet, so no external row is written for these two events (a queued row would show "Notificación enviada"
  for a message never sent). Any future sender shall skip rows older than N minutes `[assumption]`, so a backlog is
  never mass-sent.

## 9. Out of scope
- Real WhatsApp.
- The real Telegram bot, webhook and Resend sending (spec 05).

## 10. Plan, tasks and verification
- [x] Task 1 — `/case/{id}` with timeline, countdown, call request, add information · covers AC-05, AC-06 · done when: browser walk-through passes
- [x] Task 2 — notification rules and templates · covers AC-01, AC-07, AC-08 · done when: the tests pass
- [x] Task 3 — Telegram link and e-mail confirmation (mock) · covers AC-02, AC-03, AC-04 · done when: the tests pass
- [ ] Task 4 — real webhook, Telegram bot and Resend · covers AC-01 to AC-04 · done when: same flow on the public URL
- [x] Task 4b (EV1) — in-app `case_opened` / `card_blocked` notifications from the verifying reads · AC-01, AC-08 ·
      `apps/mcp/mcp_server/{notify,case_reads}.py`, `tests/test_spec13_case_notifications.py` on both backends
- [ ] Task 5 — update the flow diagrams · covers AC-09 · done when: the diagrams show receipt, case page and channels

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
