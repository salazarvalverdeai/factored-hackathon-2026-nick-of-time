# Spec 18 — Outcome auditor and AI second opinion for the analyst

- **Feature:** an independent, deterministic **auditor** that re-derives every agent outcome from its records and flags
  any mismatch, plus an advisory **LLM judge** that gives the analyst a cited second opinion on escalated cases. The
  auditor's checks are the same in the evaluation harness and in production.
- **Status:** Draft (2026-10-04; gate 1 closed by the lead: the judge is in the submission)
- **Owner:** @salazarvalverdeai (library and judge) · @gianzk (api task and console panel) · @vldiego (harness and KPIs)
  · **Priority:** P0 library and judge, P1 online auditor · **Size:** M
- **Challenge dimension:** AI Engineering (verification and guardrails), Technical Judgment (where an LLM is and is not used)
- **Depends on:** 01 (records, `CaseView`), 02 (engine, clock), 03 (tool results), 04 (`TurnResult`, trace), 10
  (harness), 15 (judge model) · **Enables:** the console case view, `ops_kpis` (ADR 0018), `/evaluation`
- **ADRs:** 0007, 0016, 0018, 0021 · **Issue:** #29

---

## 1. Introduction
The agent acts, the auditor checks, the analyst decides. Two parts with different jobs:

- **Auditor (deterministic, no LLM).** After each run it recomputes what the agent claimed — the decision, the deadline,
  the verified actions, the facts in the receipt — from the recorded inputs, the tool results and `policies.yaml`, and
  compares. It is the second line: independent of the agent's own `verify` node and reproducible. It is a pipeline and
  not an agent, because an LLM auditing an LLM shares its failure modes and cannot be replayed.
- **Judge (LLM, advisory).** When a case reaches `review`, it reads the handoff card, the transcript and the evidence,
  and gives the analyst a second opinion on the agent's proposal, with every reason tied to an evidence id and a few
  questions to ask. It never decides, never changes state and never reaches the customer. Known LLM-judge biases
  (position, verbosity, self-enhancement) and analysts' over-reliance on automated advice are handled in §4.2.

## 2. User stories
- As an **analyst**, I want each escalated case to show which facts were re-checked independently and a cited second
  opinion, so I decide faster and catch what the agent missed.
- As the **bank**, I want every agent outcome re-derived by something other than the agent, so a wrong deadline, an
  unverified "blocked" or a leaked field is caught even if the agent's own checks failed.
- As the **team**, I want the same checks in the harness and in production, so evaluation numbers and production
  monitoring mean the same thing.

## 3. Acceptance criteria (EARS)
Each criterion carries its phase: **[P0]** in the submission · **[P1]** if time allows · **[P2]** nice to have.

**Auditor**
- **AC-01 [P0]** — The checks A1–A10 of §4.1 shall be pure functions in `nick_of_time.audit` that take a run's records
  and return findings; the same records shall always give the same findings. · [T]
- **AC-02 [P0]** — The harness (spec 10) shall compute its final-state checks with `nick_of_time.audit`, so offline
  evaluation and production audit share one implementation. · [T]
- **AC-03 [P1]** — When an agent run ends, the api shall run the auditor in the background; the customer's reply shall
  never wait for it. · [T]
- **AC-04 [P1]** — Every finding shall be stored append-only in `audit_findings` with `run_id`, `trace_id`, `case_id`,
  `check_id`, `severity`, `expected` and `observed`. · [T]
- **AC-05 [P1]** — If a finding is critical, then the case shall be flagged in the console, its priority raised, and the
  analyst shall acknowledge the finding before resolving the case. · [T]
- **AC-06 [P1]** — The console case view shall show the auditor result per check (passed, finding, not applicable) with
  an icon and a label, never only a color. · [U]

**Judge (second opinion for the analyst)**
- **AC-07 [P0]** — When a case enters `review`, the judge shall produce one second opinion: `agree`, `disagree` or
  `uncertain` with the agent's proposal, up to 5 reasons each citing an evidence id of the handoff card, and up to 3
  questions for the analyst. · [T]
- **AC-08 [P0]** — A reason or question that cites no valid evidence id, or states a number, date or id that is not in
  the evidence, shall be dropped (exact-match grounding, ADR 0016). · [T]
- **AC-09 [P0]** — The judge shall never change state, call a tool or reach the customer; the console shall label its
  output "AI second opinion — advisory" and show it after the auditor's facts. · [T]
- **AC-10 [P0]** — The analyst's decision shall be recorded on its own, together with whether it matched the judge. · [T]
- **AC-11 [P0]** — If the judge fails, times out or would exceed its budget (G-OPS-01), then the console shall show
  "No second opinion" and nothing else changes. · [T]
- **AC-12 [P2]** — The judge model shall be chosen by spec 15 as a third task, `judge`, with the lean rule, and from a
  different model family than the agent's models when one meets the bar. · [D]

**Monitoring and calibration**
- **AC-13 [P2]** — Findings per 100 runs (by check and severity) and the judge–analyst agreement rate shall feed
  `ops_kpis` (ADR 0018) and appear in `/evaluation`. · [D]
- **AC-14 [P2]** — Before the judge is trusted beyond advisory use, its agreement with analysts and with a labeled sample
  (Cohen's kappa) shall be reported. · [D]

## 4. Functional requirements

### 4.1 Auditor checks
| # | Check | Compares | Severity |
|---|---|---|---|
| A1 | Decision | `engine.decide()` on the recorded inputs = the recorded decision, same `policies_version` | critical |
| A2 | Deadline | `clock.deadline()` on the case's country, product and opening date = the stored deadlines | critical |
| A3 | Actions | every action shown as `verified` has a post-condition read after it, and the database agrees | critical |
| A4 | Grounding | every number, date, id and status in the reply, the receipt and the handoff appears in the tool results | critical |
| A5 | Coherence | every status told to the customer = the database read at the end of the turn | high |
| A6 | Privacy | no other customer's data; no score, policy ids or transcript in notifications; no card number or CVV | critical |
| A7 | Lifecycle | no duplicate active case; valid transitions only; no case closed without a person | critical |
| A8 | Chips | every action chip was allowed in that state (spec 04 AC-30) | medium |
| A9 | Notifications | each status change produced its notification on the confirmed channels, with a delivery status | medium |
| A10 | Cost and latency | within the budget and limits of G-OPS-01 | low |

Notes on A3–A7 (task 18a):
- **A3** follows D-025 `[assumption]`, pending the lead. Writes (`open_case`, `block_card`) return no V- id. The
  verifying read mints it in an append-only `action_verified {action_id, verification_id, read_at}` case event. Every
  verified claim (TurnResult `actions[]`, `receipt.actions[]` by `verified_at`, `handoff.actions[]` by `verified: true`)
  needs an `action_verified` event with the same `action_id` and `verification_id`, a `read_at` at or after the write's
  request, and a claimed time equal to that `read_at` (the handoff carries none). A V- id from anywhere else is not
  evidence.
- **A4** covers numbers, dates and ids; statuses belong to A5. Amounts are locale-aware: a last separator followed by
  1–2 digits is the decimal mark, and groups of 3 are thousands, also after a space or NBSP (`COP 3 500 000`). An ISO
  timestamp states only its date. The legal source (`deadline_source`, `source_url`, `verified_on`) is a
  `compute_deadline` fact and is checked. Skipped keys, none of them a tool fact: `receipt_id` and `issued_at` (minted
  with the receipt), `case_url` (a link the app builds), `trace_id` (runtime), `notifications_sent[].ts` (notifier),
  `intent_confidence` (classifier), `guardrails_triggered` (guardrail ids) and `verified_at` (checked by A3).
- **A6** applies the transcript rule to notification surfaces only (utterances of 20+ characters, word-bounded,
  case-blind). The score counts only within 40 characters of a score word (score, puntaje, puntuación, pontuação,
  riesgo, risco) and never as an amount. A card number must pass Luhn and is searched with ids and dates blanked out.
- **A7** also requires a person (`analyst:<sub>`, with a non-empty sub) for `resolved`, not only for `closed`. Active
  cases come from each case's last status; duplicates are keyed by customer and transaction.

### 4.2 Judge
- **Input:** the handoff card (`handoff.schema.json`), the transcript, the tool results with their ids, the decision with
  its rule ids, the bank's score and the auditor's results. Never the customer's other cases, never secrets.
- **Rubric (fixed):** (1) Does the transaction match the customer's account of it? (2) Is anything in the story
  inconsistent with the evidence, or a sign of social engineering? (3) Is the proposal consistent with the policy
  decision and the evidence? (4) Did the agent leave anything unverified? (5) What should the analyst ask?
- **Output:** structured — `verdict`, `reasons [{text, evidence_ids}]`, `questions [{text, evidence_ids}]`,
  `model`, `prompt_hash`, `created_at`, `dropped` (items removed by grounding). Details of the code `[assumption]`: the
  evidence a reason may cite is the handoff's `evidence` plus the `verified_facts` source ids (D-036); the facts it may
  state come from the handoff and the tool results, minus A4's skipped keys, never the transcript; an item with a
  spelled-out number, a month name or an id-shaped token that is not exactly an evidence id is dropped; a verdict with
  no grounded reason becomes `uncertain`; more than 5 reasons or 3 questions is invalid output and gives no opinion.
- **Bias controls:** a fixed rubric and structured output instead of free comparison (position and verbosity effects);
  a model family different from the agent's (self-enhancement); temperature 0; every reason must cite evidence
  (AC-08).
- **Over-reliance controls:** labeled advisory and shown after the auditor's facts (AC-09); the analyst's decision and
  its match with the judge are recorded (AC-10) and measured (AC-14).

### 4.3 Scope for the submission
| Phase | What | Acceptance criteria |
|---|---|---|
| **P0 — in the submission** | This spec and ADR 0021 with the diagram and the model inventory; `nick_of_time.audit` with A1–A7 used by the harness; **the judge's second opinion in the console** | AC-01, AC-02, AC-07 – AC-11 |
| **P1 — if time allows** | Online auditor as an api background task, `audit_findings`, auditor panel and critical flag in the console | AC-03 – AC-06 |
| **P2 — nice to have** | Judge chosen by the benchmark, monitoring KPIs, calibration against analysts; the continuous-evaluation pipeline of ADR 0021 (release gate for every model in the inventory) | AC-12 – AC-14 |

Until spec 15 picks the `judge` model (AC-12), the judge runs on Claude Haiku 4.5 `[assumption]`. The agent's proposal
comes from the policy engine, not from an LLM, so the judge does not grade its own output.

## 5. Non-functional requirements
- Auditor: no network and no LLM; p95 under 2 s per run `[assumption]`.
- Judge: at most one call per case in review; cost under 0.01 USD per case `[assumption]`, estimated before the call
  and the call is skipped when over budget or when the client has no prices; input capped at about 12k tokens; timeout
  10 s because G-OPS-01's 800 ms would always expire on a model call (D-037) `[assumption]`; the customer never sees it.

## 6. API contract (additions to spec 01, minor version)
```python
findings: list[Finding] = audit.run(records)            # records: TurnResult, trace, tool results, case events
opinion: SecondOpinion | None = judge.opinion(handoff, transcript, evidence, client=llm, audit=findings)   # None = "No second opinion"
decision: AnalystDecision = judge.record_decision(case_id, analyst, action, proposal_action=..., second_opinion=opinion)
```
- **Input mapping (for the `records_for_run(run_id)` adapter of T2, reused by T3).** `FinalState` does not change.
  - A3: the claims are the TurnResult `actions` (`ActionRecord`), `receipt.actions` and `handoff.actions`. The evidence
    is one `ActionRead` per `action_verified` event (D-025), with `action_id`, `verification_id` and `read_at` from its
    payload; `requested_at` is the `created_at` of the write event (`case_opened` or `card_blocked`) with the same
    `action_id`.
  - A5: `FinalState.status_replies` (told vs a fresh read, the K- id included).
  - A6: surfaces from the reply, the receipt and `notifications.text`; `other_customer_data_exposed` from `FinalState`.
  - A7: `case_opened` → `LifecycleEvent(type="status", status="new")`; `status_changed` → `status` = payload `to`; the
    analyst's credit `analyst_action` (`approve_credit`) → `type="provisional_credit"`; `actor` as stored (`agent`,
    `system`, `customer` or `analyst:<sub>`). The `(case_id, customer_id, transaction_id)` keys come from `cases`.
- `GET /api/console/cases/{case_id}` adds `audit: [{check_id, status, severity, expected, observed}]` and
  `second_opinion: {...} | null`.
- `POST /api/console/cases/{case_id}/audit/{finding_id}/ack` → event `audit_acknowledged` with the analyst as actor.

## 7. Data model touched
- New append-only tables `audit_findings` and `second_opinions`.
- New case event types, not visible to the customer: `audit_finding`, `audit_acknowledged`, `second_opinion_issued`.
- `analyst_action` payload adds `matched_second_opinion` (bool or null).

## 8. Decisions (gate 1, lead, 2026-10-04)
- **Q1 — scope:** P0 = documentation, the shared library used by the harness **and the judge**; P1 = online auditor and
  its console panel; P2 = monitoring, calibration and the continuous-evaluation pipeline.
- **Q2 — a critical finding** flags the case, raises its priority and asks the analyst to acknowledge it before
  resolving; it never changes the case or messages the customer on its own.
- **Q3 — judge inputs** include the bank's score, our fraud model's score when present (spec 17) and the rule ids, as
  the analyst sees them.
- **Q4 — the analyst sees the judge right away**, labeled advisory, after the auditor's facts; agreement is measured.
- **Q5 — owners:** lead (library and judge), GianMarco (api task and console panel), Diego (harness and KPIs).

## 9. Out of scope
The judge deciding, closing or messaging; judging customer-facing replies in real time; correction notices to customers;
tools for the third line (internal audit).

## 10. Plan, tasks and verification
- [ ] T1 [P0] — `nick_of_time.audit` with A1–A7 as pure functions + tests on recorded fixtures · AC-01
      (A3–A7 done, task 18a: `tests/test_spec18_audit_a3_a7.py`, A3 on D-025's `action_verified`; A1–A2 remain,
      task 18b)
      Note: AC-01 names A1–A10, but P0 is A1–A7 (§4.3, T1); A8–A10 are outside P0, pending the lead.
- [ ] T2 [P0] — harness uses the library for its final-state checks (with @vldiego) · AC-02
- [ ] T3 [P1] — api background task, `audit_findings`, critical flag and acknowledgment · AC-03, AC-04, AC-05
- [x] T4 [P0] — judge: prompt with the fixed rubric, structured output, grounding of reasons, fallback · AC-07, AC-08,
      AC-10, AC-11 (`nick_of_time/audit/judge.py`, `tests/test_spec18_judge.py`; the fallback is `None`, the timeout and
      the per-case cost cap are `[assumption]` defaults, see §4.2 and §5; the `AnalystDecision` record leaves persistence
      to the store owner, see T5)
- [ ] T5 [P0] — second-opinion panel in the console (with @gianzk) · AC-09; the api also calls `judge.record_decision`
      and stores `matched_second_opinion` in the `analyst_action` payload and the opinion in `second_opinions` · AC-10
- [ ] T5b [P1] — auditor panel and critical flag in the console (with @gianzk) · AC-06
- [ ] T6 [P2] — `judge` as a spec 15 task; KPIs in `ops_kpis`; calibration report · AC-12, AC-13, AC-14

## 11. Sources
External sources checked on 2026-10-04.
- Federal Reserve, FDIC and OCC, *SR 26-2 — Revised Guidance on Model Risk Management* (17 April 2026; supersedes SR
  11-7 and SR 21-8): "effective challenge" by objective, independent experts; outcomes analysis; ongoing monitoring. Its
  footnote 3 leaves generative and agentic AI out of scope and asks banks to govern them with their own practices:
  https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf
- NIST, *AI Risk Management Framework 1.0* (NIST AI 100-1) — MEASURE 2.4 (monitored in production), MANAGE 4.1
  (post-deployment monitoring, appeal and override, incident response): https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* (NeurIPS 2023 Datasets and Benchmarks) —
  position, verbosity and self-enhancement biases; over 80% agreement with human preferences for strong judges:
  https://arxiv.org/abs/2306.05685
- Parasuraman and Manzey, *Complacency and Bias in Human Use of Automation: An Attentional Integration*, Human Factors
  52(3), 2010 — over-reliance on automated advice: https://doi.org/10.1177/0018720810376055
- IIA, *The IIA's Three Lines Model* (2020) — first line operates, second line monitors, third line assures:
  https://www.theiia.org/en/content/position-papers/2020/the-iias-three-lines-model-an-update-of-the-three-lines-of-defense/
- Internal: ADR 0016 (exact-match grounding), ADR 0018 (lifecycle and review triggers), ADR 0007 (final-state
  evaluation), spec 04 (AC-19, AC-30), spec 10 (`FinalState`), spec 15 (lean rule), `contracts/policies.yaml`
  (G-OPS-01, G-OPS-02, `notifications.never_send`), `contracts/handoff.schema.json`.
- Values marked `[assumption]` have no external source.
