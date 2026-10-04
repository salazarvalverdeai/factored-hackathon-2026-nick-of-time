# 0013. The customer receives proof: verified receipt, case page and notifications

- **Status:** Accepted
- **Date:** 2026-09-29
- **Deciders:** Freddy, after feedback from a Factored mentor · **Owner:** @gianzk
- **Related:** specs 04, 07, 13, ADR 0014

## Context
Feedback from a Factored mentor (2026-09-29): the vision solves a real problem; the hook is the customer's experience —
after talking to the agent they must feel their case is being worked on and not need to call a person. Everything that
proves it (verified block, deadline with its legal source, assigned analyst, audit) existed, but only the analyst saw it.

## Decision
- A **verified receipt** in `/chat`: card blocked at HH:MM, case id, legal deadline with its source, what the AI did and
  what a person will do. It uses the same verified-facts contract as the handoff card and passes exact-match grounding.
- A **case page** `/case/{id}`: timeline, deadline countdown, "request a call", and the customer can come back, see the
  history and add information (`customer_info_added`).
- **Notifications on every status** through the in-app log, **Telegram** (bot, opt-in deep link) and **email**
  (Resend, only to an address the user enters and confirms — never to dataset addresses).
- New metric: `receipt_rate`, the share of cases that end with a verified receipt and a date.

Pitch line: *"The analyst receives evidence, not a chat; the customer receives proof, not promises."*

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Receipt + case page + channels (chosen) | Turns verification into customer trust; measurable | More front-end work |
| Log-only notifications | Cheap | The customer sees nothing; the hook is lost |
| Real WhatsApp | Closest to real banking | Provider approval impossible in the time; tests only if time allows |

## Consequences
The harness requires a dated receipt in every case. If a channel fails, the notification stays in the log and the
receipt is unaffected.

## Confidence
High.
