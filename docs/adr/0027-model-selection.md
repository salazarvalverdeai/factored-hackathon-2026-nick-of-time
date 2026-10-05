# 0027. Model selection per LLM task (understand, word, judge)

- **Status:** Proposed. This is a draft. Every number below comes from a **development run on validation, not the
  pre-registered test result**. The lead fills the decision from `make bench` after the seal (M02).
- **Date:** 2026-10-05
- **Deciders:** Freddy (lead) · **Owner:** @salazarvalverdeai · **Reviewer:** none yet (Diego could not continue,
  as the seal block of `eval/PROTOCOL.md` records)
- **Related:** specs 04, 11, 15 (§4.2, §4.4, §4.5, AC-07) · ADRs 0009, 0015, 0021, 0025, 0028 · `eval/PROTOCOL.md` §1.1, §2

## Context
- The agent uses an LLM for only two tasks: `understand`, below τ, and `word`. The analyst console adds a third task,
  `judge`. Each task gets the cheapest model that is good enough, or no LLM at all (spec 15 §4.2).
- The rule is pre-registered in `eval/PROTOCOL.md` §2.3 (spec 15 §4.4): hard limits first; then no arm significantly
  worse than the best (paired McNemar, p ≥ 0.05); then the cheapest arm (a tie goes to the lower p95); then the
  production gate (§4.5). If no LLM arm beats B0 with significance, B0 stays.
- The B1 screen is decided once, on the frozen **test** split, after the seal (PROTOCOL §0.2). Validation may be used
  only to fix prompts (§2.1). The protocol was sealed on 2026-10-05; tag `protocol-v1` points to `7b18f72`.
- `make bench` is the only command that writes `eval/results/bench_*`, `benchmark.json` and
  `docs/assets/benchmark_cost_quality.svg`. Before the first model call it runs the shared seal guard
  (`eval/harness/seal_guard.py`):
  - `check_seal` with the classifier split manifest. It checks that the tag is on the sealing commit, that the
    protocol is unchanged, that the protocol sha256 and the split manifest recompute to the sealed values, and that no
    sealed input has an uncommitted change.
  - `claim_run("bench")`, which writes `eval/results/bench/bench.start.json` and refuses a second run.

  The command also refuses while any official output already exists. `benchmark.json` embeds the guard as `protocol`.
- The classifier test split was decided by the fixed rules `rules-v1` (ADR 0028). Every B1 test result therefore
  carries `test_review: rules-v1` and the PROTOCOL §1.1 label "test split decided by fixed rules, without independent
  human review", in `benchmark.json`, `bench_b1.md` and `bench_b1.csv`.

## Decision (draft)
The model map is the output of `make bench` on the sealed test split under PROTOCOL §2.3. This ADR records, for each
task, three rows (best measured, cheapest that meets the bar, chosen) and the resulting map (spec 15 AC-07). Until the
sealed run exists, the rows below come from the development run and decide nothing.

| Task | Best measured | Cheapest that meets the bar | Chosen |
|---|---|---|---|
| `understand` | `sonnet-4-6` | none | `b0_rules` (no LLM): no arm meets the hard limits `[assumption]`, see "How the code reads §2.3" |
| `word` | not run (AC-12 is P1) | — | `templates` |
| `judge` | not run (joins in P2) | — | `haiku-4-5` (spec 15 §8, Q4) |

### How the code reads §2.3 where it is silent `[assumption]`
Lead decision D-077 is pending. `eval/bench/report.py` implements the recommended reading, set in one constant,
`SELECTION_READING`, so it can be changed if the lead picks the other reading. Each output (`benchmark.json`
`model_map.understand.reading`, `bench_b1.md`) names the reading it used.
- **Best arm of rule 2.** By default (`among_passing`), the best arm is the best among the arms that pass rule 1.
  This follows spec 11 §4: "among the rest". The alternative (`all_measured`) compares with the best of every
  measured arm, so an arm that fails a hard limit could still set the bar.
- **Every arm fails rule 1, or no arm that meets the bar passes the gate.** §2.3 does not cover this. B0 rules stays,
  because it is the no-LLM option of PROTOCOL §0.3, and `chosen_by` says so with `[assumption]`.
- **No arm was measured.** No arm is chosen (`chosen: "none"`), and the command exits with code 3. It does not name
  an unmeasured B0.
- **Rule 5.** The code applies it as the protocol words it: B0 stays when **no** LLM arm beats it with significance.
  It is not applied to the chosen arm alone.
- **"Best".** The best arm is the one with the highest intent accuracy, the quantity that McNemar compares.

## Development run on validation, not the pre-registered test result
Run of 2026-10-05: `make bench-dev` on Bedrock `us-east-2`, replay mode with `DEMO_TODAY` 2026-06-01. It used the 150
reviewed validation sentences, injection rows apart (D-022), and 24 arms. All metrics are `[simulated]` because the
sentences are generated (Gemma 3 27B, ADR 0025), so the two Gemma arms carry `same_family_as_generator`. Spend was
2.48 USD `[projected]` from `eval/bench/prices.yaml` and 1.34 USD `[data]` actual, smoke calls included. The raw output
is in the git-ignored folder `eval/.runs/bench/2026-10-05-validation-bedrock/`.

| Arm | Accuracy [95% Wilson] | Macro-F1 es / pt | Dispute recall es / pt | Person recall es / pt | Slot acc. | p50 / p95 ms | USD per 1k msgs | McNemar p vs best | Pareto |
|---|---|---|---|---|---|---|---|---|---|
| `sonnet-4-6` | 0.907 [0.849, 0.944] | 0.905 / 0.909 | 0.90 / 1.00 | 0.73 / 0.80 | 0.989 | 1256 / 1370 | 5.44 | best | yes |
| `nova-2-lite` | 0.893 [0.834, 0.933] | 0.893 / 0.894 | 0.93 / 0.97 | 0.67 / 0.73 | 0.811 | 868 / 1528 | 0.663 | 0.77 | yes |
| `haiku-4-5` | 0.840 [0.773, 0.890] | 0.836 / 0.840 | 0.93 / 0.93 | 0.53 / 0.67 | 0.870 | 1163 / 1431 | 1.86 | 0.006 | no |
| `nova-lite` | 0.807 [0.736, 0.862] | 0.827 / 0.785 | 0.87 / 0.93 | 0.73 / 0.73 | 0.757 | 802 / 1228 | 0.063 | < 0.001 | yes |
| `nova-pro` | 0.787 [0.714, 0.845] | 0.801 / 0.774 | 0.87 / 0.97 | 0.67 / 0.47 | 0.865 | 883 / 1385 | 0.846 | < 0.001 | no |
| `b0_rules` | 0.607 [0.527, 0.681] | 0.609 / 0.580 | 0.40 / 0.57 | 1.00 / 0.60 | 0.789 | 0.18 / 0.38 | 0 | < 0.001 | yes |

- **Hard limits (rule 1):** no arm passes. The floor that binds every LLM arm is `human_request` recall of at least
  0.95 per language; the best result is 0.73 / 0.80 (Sonnet 4.6). Nova 2 Lite also has a p95 above 1.5 s.
- **No structured output (AC-11, D-011): 15 of the 20 reachable LLM arms.** Twelve leave out the null slot keys that
  the `understand` schema requires (`'date' is a required property`): Nova Micro, gpt-oss 20B and 120B, Ministral 3 8B
  and 14B, Mistral Large 3, Llama 4 Scout and Maverick, Qwen3 32B and 235B, Nemotron Nano 3 and DeepSeek V3.2. Three
  return no tool call at all: Gemma 3 12B and 27B, and Llama 3.3 70B. This confirms F-013. These arms are recorded and
  reported, not removed.
- **Unavailable (AC-06):** Sonnet 5.5 (`AccessDeniedException`, spec 15 §8), Jev (`TYPESAFE_API_KEY` was not loaded)
  and B1 TF-IDF + LR (waiting for spec 11 T3, task 11b).
- **Production gate (AC-10):** `es_pt_quality` is written by the run, as a pass when the arm meets the macro-F1 floor
  in both languages. Bedrock availability now cites the Bedrock SLA, checked on 2026-10-05. On this run only Sonnet 4.6
  passes the production gate.

## Open questions for the lead (after the seal, before `make bench`)
The protocol was sealed on 2026-10-05 (tag `protocol-v1` → `7b18f72`). The sealed manifest covers the split files, so
no label may change. Only the prompt or the schema may still change, validated on validation (PROTOCOL §2.1). Nothing
may change once the test run has started.
- **Q1: slot keys.** Should the `understand` schema (spec 04, `nick_of_time.llm.steps.INTENT_SCHEMA`) stop requiring
  the null slot keys? That would let 12 more arms reach B1.
  - The schema is not a hashed input, and §2.1 allows prompt and schema fixes on validation.
  - B1 has to measure the request that production sends, so the change belongs to spec 04 and lands in both places.
  - After the change, re-run `make bench-dev` on validation, record the new `prompt_hash` here, and only then run
    `make bench`.
- **Q2: person requests.** Every LLM arm misses `human_request` far more often than the floor allows.
  - **Do not act on this by relabeling.** `validation.jsonl` and `test.jsonl` are in the sealed manifest, so any label
    edit breaks the seal, and `make bench` would refuse.
  - Only the prompt wording may change, validated on validation before the test run.
- **Q3: no arm meets the hard limits.** Handled by the reading above `[assumption]`; D-077 is pending.
- **Q4: Jev.** The local `.env` stops parsing at an unquoted value on line 40, so the Jev key was never loaded.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Lean rule per task on the sealed test split (chosen) | pre-registered, cheapest model that is good enough, no-LLM can win | the B1 test split is used once; there is no re-tuning after it |
| Keep the incumbent (Haiku 4.5) without a benchmark | no work | not evidence-based; on this dev run it is dominated by Nova 2 Lite and Sonnet 4.6 |
| Choose on the validation numbers above | available now | breaks PROTOCOL §0.2: validation is used to fix prompts, not to choose |

## Consequences
- The map is loaded by `nick_of_time.config.resolve(arm)` as arm S1 once it is accepted.
- If Q1 or Q2 changes the prompt or the schema, the development run must be repeated on validation before
  `make bench`. The split labels never change after the seal.

## Confidence
Low until the sealed run exists. The development numbers are 150 sentences from one generator family. The sealed test
run decides.
