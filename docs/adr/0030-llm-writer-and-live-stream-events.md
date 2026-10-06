# 0030. An LLM writer words chat replies, and the stream shows each tool call live

- **Status:** Accepted — decided by the lead on 2026-10-05
- **Date:** 2026-10-05
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** spec 01 (§6.4.1, AC-09 to AC-11, contract 1.8.0), spec 04 (§4.6, AC-37 to AC-41), spec 05, spec 07,
  spec 15 (`word` task) · ADRs 0009, 0016, 0027

## Context
- A walkthrough of the public URL on 2026-10-05 showed a working flow that reads like a menu bot:
  - every reply is a fixed template (spec 04 deferred LLM wording to the spec 15 `word` gate);
  - the stream carries only short progress labels;
  - chips are a fixed table.
- The jury compares the chat with current assistants (ChatGPT, Claude). What sets this system apart is invisible in
  the chat today: it understands free, aggressive or mixed language, acts through tools under rules, and verifies.
- The `word` benchmark of spec 15 has not run, so no measured result supports choosing a writer model.
- Grounding is already enforced line by line (`build.bad`, spec 04 §4.3, G-OUT-01). The receipt and the handoff card
  are built from tool results by `nick_of_time.receipt`, not by any LLM.
- The api must keep the LangSmith key server-side, take the customer from the session, and apply rate limits and the
  daily cap. This is the API passthrough pattern LangChain recommends for production.

## Decision
1. **A writer words the chat reply.** When `writer = llm`, `respond` has Sonnet 4.6 word the reply from the turn's
   facts and choose 2–3 chips from the row the rules allow. Haiku 4.5 keeps classifying.
2. **Every line is grounded before it is shown.**
   - A line with a digit is released only after it passes the grounding check.
   - A failing line, or any writer failure, falls back to its template.
   - The receipt, the handoff card and the notifications stay template- and tool-built.
3. **The stream shows each tool call.** The graph emits `tool` events (start, then result with cards built from tool
   results) and `text` chunks, named after the AG-UI event model. The api forwards them through the same projection
   that hides score, zone thresholds and policy ids (spec 01 §6.4.1).
4. **A server-side switch.** `writer` (`template | llm`) is a console setting, audited like supervised mode. With
   `template`, the chat behaves exactly as before this ADR.
5. **The browser keeps talking to the api, not to Platform.** Custom auth on the deployment is the documented
   alternative. It is deferred: it would move the session, limits, cap, cost log and handoff writes into the graph.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| A. LLM writer with line grounding, switchable (chosen) | Natural replies and live tool steps; facts stay tool-only; one-click fallback | Writer model not benchmarked; more cost per turn |
| B. Keep templates, restyle only the UI | No model risk; no cost | Still reads as a menu bot; misses what the system does |
| C. Wait for the spec 15 `word` benchmark | Measured choice | Not before the submission |
| D. Free agent loop for every tool, actions included | Most flexible | An LLM could reach a regulated action outside the rules' order; breaks the tested path |

## Consequences
- Chat replies stop being byte-for-byte reproducible when `writer = llm`. The evaluation is not affected, because the
  harness checks the final state and never the reply text.
- Cost per turn rises. The daily cap goes from 5 to 10 USD for the judging days.
- `/evaluation` states the limitation in one plain sentence: the writer was not benchmarked, and every line with a
  figure is checked against the tools before it is shown.
- Stage 2 (spec 04 AC-41), where the agent reads tools before asking again, is a P1 behind its own switch. The regulated
  path `decide → plan → act → verify` does not change.

## Confidence
Medium. Revisit when the spec 15 `word` benchmark runs, or if the grounding check drops more than a few lines per
hundred in production.
