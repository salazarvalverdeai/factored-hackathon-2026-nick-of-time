# 0028. The classifier test split is decided by fixed rules when no independent person can review it

- **Status:** Accepted — decided by the lead on 2026-10-05
- **Date:** 2026-10-05
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** spec 09 (§7.6, T5, M02), spec 11 (§7.1, §8) · ADRs 0015, 0021, amends [0025](0025-classifier-set-authored-by-distinct-model-families.md) ·
  `eval/PROTOCOL.md` §1.1

## Context
- ADR 0025 asks a person who is not the classifier's developer to review every line of the test split. The developer
  is the lead; Diego cannot continue and GianMarco had not reviewed it on 2026-10-05, the day of the submission.
- The protocol must be sealed before any test score exists (ADR 0015), and specs 11, 15 and 17 wait for the seal.
- The drafts already carry deterministic review hints (`checks`, no model): missing planned slots, unplanned dates,
  amounts or merchants, duplicates, language leaks and drift, injection rows with no injection cue.
- Letting the developer review test, or letting an LLM decide it, would bias the split the decision is scored on.

## Decision
When no person other than the classifier's developer can review the test split before the seal, the test split is
decided by fixed rules, `eval.classifier.review.rule_decision`, signed `rules-v1`:
1. **Drop** a row with any of the hints `duplicate`, `same_as_seed`, `near_duplicate`, `language_leak`,
   `language_drift`, `injection_without_marker`, `unplanned_amount`, `unplanned_date`, `unplanned_merchant`,
   `unplanned_card_type`: the text would contradict its gold slots, card, language or label.
2. **Fix** a row whose planned slot or card wording is missing from the text (it becomes null), whose amount digits
   or merchant do not appear in the text (null), or whose `also_dispute` contradicts the text (`dispute_missing` →
   false, `unplanned_dispute` → true).
3. **Keep** every other row.

`python -m eval.classifier.review auto-review` writes the decisions into `draft/review_test.csv`; `promote` accepts
`rules-v1` only for the test split and only with `--allow-rule-review`. The classifier developer still may not review
test. Train and validation stay reviewed by a person.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Fixed rules, signed `rules-v1` (chosen) | No reviewer bias; deterministic and reproducible; the seal is not blocked | No human judgment of intent drift that the hints do not catch; some good rows are dropped |
| The developer reviews test | Human judgment | The developer would shape the split the classifier is scored on, which the author split exists to avoid |
| An LLM decides test | Fast; catches intent drift | Biases the split toward that model's family, and the benchmark covers almost every family (ADR 0025) |
| Wait for GianMarco | Keeps ADR 0025 as written | Blocks the seal and specs 11, 15 and 17 on submission day |

## Consequences
- Every result on the test split is labeled "test split decided by fixed rules, without independent human review":
  `classifier.json` carries `test_review: "rules-v1"` (spec 11 §7.1) and the protocol states it before the seal.
- Intent drift that no hint catches stays in test; the per-class F1 and the McNemar comparisons may be noisier.
- If an independent person reviews test later, that is a new split and a new seal (ADR 0021), not an edit.

## Confidence
Medium. Revisit if an independent reviewer becomes available before any test score exists, or if the rules drop so
many rows that a cell falls under the minimums of spec 11 AC-06 (`promote` refuses then).
