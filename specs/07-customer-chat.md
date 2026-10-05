# Spec 07 — Customer chat `/chat` with verified receipt and trace

- **Feature:** the customer-facing demo: chat in Spanish or Portuguese, a verified receipt and a visible trace.
- **Status:** In progress (works on mock data in PR #51; the live agent arrives with specs 04 and 05)
- **Owner:** @gianzk · **Priority:** P0 · **Size:** L
- **Challenge dimension:** AI Engineering
- **Depends on:** 16, then 04 and 05 · **Enables:** 13
- **ADRs:** [0013](../docs/adr/0013-customer-receives-proof-receipt-case-page-notifications.md), [0016](../docs/adr/0016-guardrails-injection-detector-and-exact-grounding.md), [0017](../docs/adr/0017-identity-mock-otp-customers-cognito-analysts.md), [0029](../docs/adr/0029-voice-input-voxtral-stt-browser-tts.md)
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
- AC-10 — (lead, D-072) Where the browser can record audio, the chat shall offer push-to-talk: the clip goes to
  `POST /api/voice/transcribe` (spec 05 AC-21) and the returned `text` lands in the composer as an editable draft that
  the customer sends like typed text (never sent on its own); with the read-aloud toggle on, each agent reply shall be
  spoken with the browser's `speechSynthesis` in the session language. A 413, 415 or 503 shall show the api's calm
  message and keep typing available; with no microphone, no permission or no `speechSynthesis`, the chat works as
  today. · [U] · [T] (to add with the web work)

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
- Decided (lead, D-072, 2026-10-05; ADR 0029): voice for live mode, built by the web owner on spec 05 AC-21.
  1. **Mic button and push-to-talk:** hold (pointer or Space while focused) to record, release to send; a tap toggles
     for touch users. Recording stops at 30 s. `MediaRecorder` with `audio/webm;codecs=opus` (Chrome, Firefox,
     Safari 18.4+), else `audio/ogg;codecs=opus`, else 16 kHz mono WAV encoded in the page; the raw blob is the POST
     body with its `Content-Type`. Never store the clip (no IndexedDB, no upload elsewhere); release the stream after
     each clip so the browser's mic indicator turns off.
  2. **Silence:** Voxtral invents sentences for silence (spec 05 §8, live smoke). The api only gates silent 16-bit WAV,
     so for WebM/Opus and Ogg/Opus the client level gate is **required**: the page measures the level with an
     `AnalyserNode` and does not send a clip that never rose above the noise floor `[assumption]`; an empty `text`
     shows "No te escuchamos / Não ouvimos você".
  3. **Draft, not send:** every transcript, whatever the format (WebM/Opus included), fills the composer, focused, for
     the customer to correct and send; it is never sent on its own. The chat path then works as for typed text (the
     LLM understands, the rules decide).
  4. **Read aloud:** `speechSynthesis` with a voice of `es-MX` (else any `es-*`) or `pt-BR` (else any `pt-*`) by the
     session language, preferring voices with `localService === true`. A remote voice sends the reply text (amounts,
     merchant, card last 4, case id) to the browser vendor's servers, the same objection ADR 0029 raises against
     `SpeechRecognition`: when no local voice exists for the language, read-aloud stays off by default and the toggle
     notes "uses an online voice". It reads the reply text only, never chips, ids or the trace. A mute toggle in the
     chat header, off by default `[assumption]` and remembered in `localStorage`, cancels speech at once; a new reply
     or a new recording cancels the one being spoken.
  5. **Accessibility:** the mic is a real `<button>` with `aria-pressed` and an ES/PT label ("Mantén para hablar /
     Segure para falar"); recording state is announced through an `aria-live="polite"` region and shown by more than
     color (icon and text); keyboard push-to-talk works; read-aloud respects the mute toggle and is never the only
     channel (every reply stays on screen). Without mic permission the button explains how to enable it and typing
     stays the default.
- Open question: the receipt deadline line uses `status.credit_deadline` until the stub returns `source_url` and
  `verified_on` (ADR 0019); then it uses `receipt.credit_deadline`.

## 9. Out of scope
- Real-time speech-to-speech (Nova Sonic runs only in us-east-1; D-072) and voice in the analyst console.
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
- [ ] Task 7 — voice (D-072, the contract in §8): mic, push-to-talk, draft, read-aloud and mute · covers AC-10 · done
  when: a visitor speaks a claim in ES and in PT on the public URL and hears the reply

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
