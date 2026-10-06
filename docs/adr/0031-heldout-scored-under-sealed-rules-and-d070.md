# 0031. Held-out scored under the sealed rules and, secondarily, under D-070

- **Status:** Accepted — decided by the lead on 2026-10-06 (D-083, in chat)
- **Date:** 2026-10-06
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** spec 10 (AC-15, §4.1, §7.1, §7.2, §8), spec 09 (§7.5), spec 04 (AC-34) · ADRs 0007, 0015, 0021

## Context
- The agent held-out (80 cases, `eval/cases/heldout.jsonl`) was derived and sealed under tag `protocol-v1` on
  2026-10-05 (ADR 0007, ADR 0021). Its file and hash never change.
- D-070 (lead, 2026-10-05) came after the seal. It is an approved rule: a person closes every case, so the analyst
  handoff card is emitted whenever a case opens, a verified high-zone block included (spec 04 AC-34, spec 09 §7.5).
- The held-out keeps the pre-D-070 rule (`eval/derive_expected.py`, `expected_for(..., sealed=True)`), where a verified
  high-zone block expects `handoff_emitted: false`. The agent now emits the handoff on those runs.
- Scored only as sealed, every verified-block run fails on `handoff_emitted`. Safe automated resolution would read
  about 0 `[assumption]`: its denominator is the runs whose expected decision is `block_and_open_case`, and all of them
  are verified blocks. The figure would reflect the order of two decisions, not how the agent behaves.
- Nobody has run or seen held-out results. The run-once command (spec 10 T7) has not been started.

## Decision
The held-out reports two scores, computed in code from the same runs:
1. **Official: sealed rules.** The pre-registered score, with the expectations exactly as sealed. It stays the
   official figure, and it is what the arm's `overall` and the existing `summary.csv` rows hold.
2. **Secondary: D-070 handoff rule.** Only `final_state.handoff_emitted` is re-derived under D-070: an opened case is
   a handoff (`eval.derive_expected.d070_expected`). Every other expectation stays sealed. For any case,
   `d070_expected(expected_for(case, intent, sealed=True))` equals `expected_for(case, intent, sealed=False)`, which a
   test checks on every row of spec 09 §7.5. The rule is applied to the sealed `expected` blocks, so the policy engine
   is not re-run on the held-out and no other policy change made after the seal can enter the secondary score.

The secondary score covers safe automated resolution, unsafe outcomes, pass^k, handoff agreement, and missed and
unnecessary escalations, each with its numerator, denominator and 95% Wilson interval, labeled `[simulated]`. It is
written next to the official score in `meta.json`, `summary.csv` (`<metric>_d070` rows) and `evaluation_summary.json`
(`scoring` and `scores_d070`), with the labels "official: sealed rules (protocol-v1)" and "secondary: D-070 handoff
rule, ADR 0031". Dev runs are scored once, as before.

This decision is recorded before the held-out run, while no held-out result exists.

## Why the sealed set and the protocol do not change
- `eval/cases/heldout.jsonl`, `eval/heldout.sha256`, `eval/PROTOCOL.md` and tag `protocol-v1` are not touched. The seal
  guard and the run-once claim are unchanged, and the held-out still runs once.
- The official score is the pre-registered one, computed as before. The secondary score is an added view of the same
  runs. It is never used to choose a model: the held-out only confirms the map chosen on dev (PROTOCOL §0.2, §2.1).
- Every reported figure says which score it belongs to, so a reader never takes the secondary figure for the
  pre-registered one.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Official sealed score plus a labeled D-070 secondary score (chosen) | The pre-registered figure stays intact; the reader also sees the agent judged by the rule it runs under | Two numbers to explain |
| Sealed score only | Simplest; nothing added after the seal | Safe automated resolution reads about 0 `[assumption]` because of rule order, not agent behavior |
| Re-derive and re-seal the held-out under D-070 | One score | Changes a sealed set after the seal (ADR 0021); needs a new protocol version and a new seal |
| Re-run `expected_for(sealed=False)` on the held-out cases | Uses the derivation function directly | Any policy change made after the seal would also move the expectations, not only the handoff field |

## Consequences
- The pitch and `/evaluation` can show the official figure and, beside it, the D-070 figure, each with its label.
- The web page can ignore `scores_d070` until it chooses to show it: the arms' shape is unchanged.
- A later rule change after the seal would need its own ADR. This decision covers D-070 and the `handoff_emitted`
  field only.

## Confidence
High. To revisit if a new protocol version re-seals the held-out under D-070. The secondary score would then be
dropped.
