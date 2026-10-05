# 0024. A call request in the high zone defers the card block to the analyst

- **Status:** Accepted
- **Date:** 2026-10-04
- **Deciders:** Freddy (lead; D-029 and D-042 on 2026-10-04; the end of the hold, D-042, and D-043 on 2026-10-05) ·
  **Owner:** @salazarvalverdeai
- **Related:** specs 02 (rule 3a, AC-19), 03 (`block_card`), 04 (`decide`, `connect`), 11 (D-020) · ADRs 0005, 0006, 0014

## Context
- One firm business rule is "High zone blocks and verifies" (`CLAUDE.md`). `approval.per_action.block_card.high` is
  `manual_check`: the agent blocks, verifies and leaves the case in `verification` (`contracts/policies.yaml`).
- A customer may ask for a person and report a charge in the same message. D-020 made rule 3a
  (`POL-HUMAN-REQUEST`) non-terminal in that case: the call is registered and the dispute path still runs (spec 02 row
  3a, spec 11 §8).
- The engine first shipped with a default for this case (#64): the high zone still blocked, then the call was
  registered. That default was isolated in one constant for the lead to confirm or change (D-029).
- The high zone is a score ≥ 50. On the dataset, every transaction at that score was a fraud (precision 100%) and the
  band holds 48.8% of the frauds that have a score `[data]` (`queries/pitch/p08_fraud_score_thresholds.csv`,
  `contracts/policies.yaml` `zones.high`).
- Undoing a block takes a person: `unblock_card` is `human_required` in every zone (`contracts/policies.yaml`).
- A request for a person is never refused (CFPB, *Chatbots in consumer finance*, 2023-06-06, cited in spec 02 §11).

## Decision
The business rule in `CLAUDE.md` (merged in #83) now reads: "High zone blocks and verifies, unless the customer asked
for a person in that turn: the case opens, the call is registered and the analyst decides the block after the call
(D-029)". The case waits in `review` with the new handoff reason `person_requested`, and the block stays held until
the analyst approves the block, resolves or closes the case (D-042).

The details that matter:
- **Scope.** It applies only where rule 3a opens a case: one identified card transaction the customer did not reject,
  at intent confidence ≥ τ (D-031, decided 2026-10-04). Below τ only the call is registered and nothing is opened
  (spec 04 AC-02).
- **The other zones do not change.** In the medium and human zones the call path already opened the case without a
  block (`zone_medium`, `zone_human`). When the amount tier or supervised mode already needs a person, the case keeps
  `amount_over_case_gate` or `supervised_mode`.
- **Enforced twice.** `decide()` leaves `block_card` out of `allowed_actions`. `check()` takes a required strict bool
  `call_requested`. After the mode check, it denies a money action when the flag is true, citing `POL-HUMAN-REQUEST`.
- **How long the hold lasts (D-042).** The block stays held until the analyst decides it or ends the case, not only
  in the turn of the call request. The `block_card` tool reads `call_requested` from the store: it is true while the case has an open
  call: the case has a `call_requested` event or was opened with `handoff_reason` `person_requested` (this covers a
  failed verify of `request_call`, where spec 04's `connect` falls back to `active_or_general`), and no
  `approve_block`, `resolve` or `close_case` on that case followed (spec 03 §8). The hold is per case: a different
  charge opens a new case with no hold. Decided 2026-10-05: only those three analyst actions end the hold; `take`, `request_customer_info`,
  `mark_ambiguous` and every other analyst action keep it, because an analyst usually takes a case before the call
  and the block is the analyst's decision after the call. So a later plain-dispute turn about the same transaction
  cannot block either.
- **The later-turn block (D-043, decided 2026-10-05).** `decide()` stays without the store and `DecisionInput` gains
  no field (spec 02), so on that later turn it may still return `block_and_open_case`. While the hold is open, the
  `block_card` tool's `check()` re-check denies the block citing `POL-HUMAN-REQUEST`, and the agent reports it as not
  done (`accepted ≠ verified`).
- **Contracts.** `person_requested` is added to `handoff.schema.json`, `handoff.triggers` and the engine's
  `HandoffReason`. The `POL-HUMAN-REQUEST` and `POL-ZONE-HIGH` texts state the exception.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Defer the block to the analyst after the call (chosen) | The customer who asked for a person gets a person before any money action. No block the customer did not want needs an analyst to undo it. The handoff card names the reason. | The card stays active until the hold ends (see Consequences). A new contract value. |
| Block, then call (the #64 default) | Protection in that turn, as for any high-zone dispute | A money action on a customer who asked for a person. Undoing it needs an analyst. |
| Ask the customer whether to block in that turn | The customer chooses | An extra turn on a request for a person. The medium zone already asks, and the call request would be delayed. |
| Block only above an amount | Protects large charges | A new threshold with no source. The amount gate already raises the mode at a higher tier (`amount_gate`). |

## Consequences
- **Exposure window.** A high-zone card stays active from the call request until the hold ends (D-042). The callback the
  customer is promised is `contact.callback_within_business_days: 1` business day, an `[assumption]` with no external
  source (`contracts/policies.yaml` `contact`, D-008). The decision accepts that window for the cards the score marks
  as most likely fraud.
- **The hold outlives the turn (D-042).** The exposure window ends only when the analyst runs `approve_block`,
  `resolve` or `close_case` on the case; taking the case or asking the customer for information does not end it. A case
  in `review` with `person_requested` never moves to `verification` on its own: `case_queue` has no
  `review → verification` transition, and the block becomes the analyst's action.
- **Tool-side source of `call_requested`.** `BlockCardIn` gains no field: task 03c reads the open call from the store
  (spec 03 §8), so the flag comes from trusted state like the tool's other `check()` inputs, not from the agent.
- **Customer reply.** The `connect` reply does not say that the card stays active. Spec 04 decides whether it should.
- **Contract version.** The new enum value is an additive change: `CONTRACT_VERSION` and the spec 01 changelog take a
  minor bump (1.4.0). The analyst console shows `handoff_reason` as it is stored, so it needs a label for
  `person_requested`.
- Easier: the handoff card names why a high-zone case waits in `review`. `check()` and `allowed_actions` agree exactly,
  except while the medium zone waits for confirmation, and on a later turn while a D-042 hold is open (D-043), where
  the tool's `check()` denies the block that `decide()` allowed.

## Confidence
Medium. Revisit if high-zone call requests turn out to be frequent in the evaluation, if the callback promise grows
beyond one business day, or if analysts take long to act on `person_requested` cases.
