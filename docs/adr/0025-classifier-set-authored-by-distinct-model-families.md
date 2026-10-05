# 0025. The classifier set is written by three model families, one per split, none of them Claude

- **Status:** Accepted — decided by the lead on 2026-10-05
- **Date:** 2026-10-05
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** specs 09 (§7.6, §8 Q3 and Q7), 11 (§8), 15 (§4.1, §8) · ADRs 0007, 0015, 0021 · `eval/PROTOCOL.md` §1.1

## Context
- Spec 11 AC-06 splits the classifier sentences **by author** (60/15/25), so that the test split measures how well a
  classifier generalizes to writers it never saw. Three splits need at least three disjoint authors.
- Spec 09 §8 proposed that each team member writes the seeds of one split (Q3) and that one LLM paraphrases all of
  them (Q7). On 2026-10-05 Diego cannot continue, the lead develops the classifier (so should not write the test
  split), and the set blocks spec 11 (learned arms) and spec 15 (B1 screen). About 880 sentences are needed.
- With one paraphrasing model for every split, the style of that model is shared by train and test, which weakens the
  author split; and spec 11 §8 already says results from a candidate of the same family as the generator are flagged.
- The likely benchmark winners are Claude models: Claude Haiku 4.5 is the B2 default until the benchmark runs (spec 11
  §4) and Sonnet 4.6 is the ceiling (spec 15 §8). A Claude generator would flag exactly the arms we expect to choose.
- The live structured-output smoke test (PR #71, 2026-10-04, finding F-013 in the lead's board) found that
  `google.gemma-3-12b-it`, `google.gemma-3-27b-it` and `meta.llama3-3-70b-instruct-v1:0` return no tool call, so
  they score as wrong predictions in B1 (D-022) and are not candidates we expect to choose. DeepSeek V3.2 passed the
  smoke test (`ok (tool)`).
- Model-generated text costs cents per split at the prices of `eval/bench/prices.yaml` (AWS Price List, us-east-2,
  read 2026-10-04) `[external]`.

## Decision
Each split has a **different generator model family**, and none of them is Claude:

| Split | Generator (Bedrock model id) | Family |
|---|---|---|
| Train | Llama 3.3 70B Instruct (`us.meta.llama3-3-70b-instruct-v1:0`) | Meta Llama |
| Validation | Gemma 3 27B (`google.gemma-3-27b-it`) | Google Gemma |
| Test | DeepSeek V3.2 (`deepseek.v3.2`) | DeepSeek |

1. Each generator writes its split's seed sentences and their paraphrases (about three per seed) from a fixed,
   versioned prompt (`eval/classifier/generate.py`, recorded by a prompt hash) with varied personas: formality, region
   (MX, CO and AR for ES; Brazilian-style PT for customers who keep their MX, CO or AR country, spec 09 Q5), typos,
   length. The code plans the slots and the card wording of every item; the model writes the text.
2. `author` = the generator model id. All sentences of one generator are in one split, so the author rule of
   `eval/PROTOCOL.md` §1.1 holds by construction. Each split records its generator: model id, prompt hash,
   temperature and seed (`eval/classifier/draft/generation.json`).
3. **Every line is reviewed by a person** for intent, amount, product and language drift, and is fixed or dropped (for
   example, a model turned "mi tarjeta" into "mi tarjeta de crédito", which changes the card the customer means).
   Train and validation are reviewed by the lead; **test is reviewed by someone who is not the classifier's
   developer** — the lead develops the classifier and Diego cannot continue, so in practice GianMarco (@gianzk).
   `eval/classifier/review.py promote` refuses a test split reviewed by the classifier developer.
4. Results of a candidate of the same family as the generator of the split being scored are flagged (spec 11 §8,
   `eval/PROTOCOL.md` §1.1). In the benchmark this concerns the Llama, Gemma and DeepSeek arms; the Llama and Gemma
   arms already fail the structured-output smoke test (F-013).
5. Model-generated sentences are `[simulated]`. This replaces spec 09 §8 Q3 (team authors) and Q7 (one paraphrase
   model).

Verified on 2026-10-05 with the team account (`nickoftime` profile), region `us-east-2`:
- `aws bedrock list-foundation-models`: `meta.llama3-3-70b-instruct-v1:0` (ON_DEMAND, INFERENCE_PROFILE),
  `google.gemma-3-27b-it` ("Gemma 3 27B PT", ON_DEMAND) and `deepseek.v3.2` (ON_DEMAND), all `ACTIVE`.
- `aws bedrock list-inference-profiles`: `us.meta.llama3-3-70b-instruct-v1:0` (`ACTIVE`, `SYSTEM_DEFINED`).
- The model cards list the same ids; the Llama 3.3 and Gemma 3 cards mark them Legacy, which does not matter for a
  one-off generation run whose output is frozen.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Three model families, one per split, no Claude (chosen) | Author split tests unseen writers; no favored candidate flagged; done in one run for cents; reproducible from a recorded prompt | Machine text is less diverse than real customers; every line needs human review; three candidate families get flagged |
| Team-written seeds + one LLM paraphraser (spec 09 Q3/Q7) | Human seeds; one flagged family | Needs three available writers, and Diego cannot continue; one paraphraser style crosses every split; the lead would write a split for the classifier they develop |
| One generator for all splits | Simplest; one flagged family | The "author" is the same model in every split, so the author split measures nothing |
| Claude as a generator | Strong ES/PT writing | Flags the arms we expect to choose (Haiku 4.5, Sonnet 4.6); the benchmark would favor or doubt its own winner |

## Consequences
- Easier: the set exists without waiting on people to write seeds; a split is regenerated from its prompt hash and seed.
- Harder: human review of about 1,070 draft lines, with the test reviewer not the classifier developer; the drafts
  are over-generated by about 20% per cell so that review drops still meet spec 11 AC-06.
- The benchmark report flags Llama, Gemma and DeepSeek results on a split their family wrote (spec 15).
- Model-generated text is `[simulated]` and less diverse than real customer messages; the classifier report says so,
  and the frozen splits do not claim to measure production traffic.
- No Claude model writes classifier sentences.
- Cost: cents per run `[external]` prices; recorded per split in `eval/classifier/draft/generation.json`.

## Confidence
Medium. Revisit if real (consented, anonymized) customer messages become available, if a generator family turns out to
be a candidate we would choose, or if review drops more than the 20% margin in a cell.

## Sources
- Spec 11 §8 (flagging of same-family candidates), spec 15 §8 (Haiku 4.5 incumbent, Sonnet 4.6 ceiling).
- F-013: live structured-output smoke, PR #71 comment of 2026-10-04 (gemma-3-12b, gemma-3-27b and llama-3-3-70b: no
  tool call; deepseek-v3-2: ok).
- Amazon Bedrock model cards, checked 2026-10-05:
  https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html ·
  https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-google-gemma-3-27b-pt.html ·
  https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-deepseek-deepseek-v3-2.html
- Supported models and inference profiles: https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html ·
  https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html (checked 2026-10-05).
- Prices: `eval/bench/prices.yaml` (AWS Price List offer files, us-east-2, read 2026-10-04).
