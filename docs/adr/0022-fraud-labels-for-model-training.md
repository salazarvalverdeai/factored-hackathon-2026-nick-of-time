# 0022. Fraud labels may train our fraud model, by time window, and never reach the runtime

- **Status:** Proposed (draft — local review)
- **Date:** 2026-10-04
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** spec 17 · ADRs 0006, 0007, 0021 · constitution rule 7 in `CLAUDE.md`

## Context
- Constitution rule 7: "`is_fraud` lives only in `data/gold_eval/` and is read only by the evaluation harness." It
  protects the evaluation from leakage and keeps labels away from the agent.
- Spec 17 trains a fraud model to compare with the bank's score. Training needs labels.
- The team bucket already restricts `labels/v1/` to the lead and Diego, and denies the runtime roles (`docs/infrastructure.md` as updated in PR #24).
- The agent's evaluation cases (specs 09 and 10) use transactions from May 2026.

## Decision
1. The fraud-model training pipeline may read `gold_eval/transaction_labels` **only for the training window
   (2025-06 → 2026-01) and the validation window (2026-02 → 2026-03)**.
2. The test-window labels (2026-04 → 2026-05) are read **once**, by the evaluation step, after the model file is frozen
   and its hash recorded.
3. No transaction of the agent's evaluation cases is in the training window, so the agent's held-out stays clean.
4. The agent, the MCP server, the api, the web and every LLM **never** read labels; the model file holds no label and
   no transaction id.
5. The pipeline runs where the label access already is (the lead, or Diego for the harness), never in the deployed
   services.
6. Rule 7 of the constitution becomes: "`is_fraud` lives only in `data/gold_eval/`; it is read by the evaluation
   harness and, by time window, by the fraud-model training pipeline (ADR 0022)."

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Read labels by time window, test scored once (chosen) | Clean comparison with the bank's score; no leakage into the agent's evaluation | One more reader of the labels |
| No fraud model | Rule 7 untouched | No answer to "can we do better than the bank's score?" |
| Train on the bank's score as a pseudo-label | No label access | Learns the score's blind spots; cannot beat it where it is silent |

## Consequences
- Easier: a fair benchmark of our model against the bank's score, reported in `/evaluation`.
- Harder: the training code must enforce the windows, and a test checks it (spec 17 AC-05).
- Neutral: `CLAUDE.md` rule 7 is reworded when this ADR is accepted.

## Confidence
High.

## Sources
- `CLAUDE.md` (constitution rule 7); `contracts/gold_contract.md` R3, G1 (labels only in `gold_eval`);
  `docs/infrastructure.md` in PR #24 (label access in the team bucket, verified with the IAM policy simulator); spec 17 §4.1 (windows and counts); spec 09 issue #11 AC-01
  (agent cases from May 2026).
