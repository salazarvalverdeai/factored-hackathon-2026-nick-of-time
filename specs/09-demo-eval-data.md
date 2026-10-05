# Spec 09 — Demo and evaluation data

- **Feature:** real gold customers and transactions for the demo and the evaluation, with team-written ES/PT messages
  ("synthetic message over real state"): the demo index, the demo customers, the agent cases and the classifier set
  (written by three model families and reviewed line by line, ADR 0025).
- **Status:** Draft
- **Owner:** @vldiego · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Data Analytics, Machine Learning
- **Depends on:** gold v1 (`contracts/gold_contract.md`) · **Enables:** 04 (tests), 10, 11, 15, M02 (protocol seal) ·
  **ADRs:** 0007, 0015, 0020, 0021, 0025
- **Issue:** #11

> Minimal profile plus sections 7 and 8: there is no API, but the data model and the open questions decide the labels.

---

## 1. Introduction
The dataset has no customer text, so every evaluation item is real state from gold plus a message we write. This spec
fixes how candidates are chosen, how many items each set has, how the expected final state is derived, the file layout
that `eval/PROTOCOL.md` hashes, and the seal. Nothing here is scored: scoring belongs to specs 10, 11 and 15.

## 3. Acceptance criteria (EARS)
AC-01 to AC-06 come from issue #11 with the same numbers; AC-04 and AC-05 carry the lead's updates of 2026-10-04
(issue comments). AC-07 onward are added by this spec. Evidence: [T] test · [C] command · [U] screenshot · [D] file.

- **AC-01** — `eval/demo_index.csv` shall hold candidates per country × zone × split: cards only, the customer's own,
  inside the window of §7.2; the query is versioned in `queries/eval/demo_index.sql`. · [D]
- **AC-02** — There shall be 6 demo customers (2 per mandatory case) usable from `/chat`, in
  `eval/demo/customers.json`, with the shape of `GET /api/demo/customers` (spec 01 §6.2). · [D]
- **AC-03** — The agent set (20 dev + 80 held-out) shall validate against `eval_case.schema.json`, with the coverage of
  §7.4, `customer_returns` cases and the expected receipt per case. · [T] `tests/test_spec09_eval_data.py`
- **AC-04** — The classifier set (about 800 ES/PT sentences plus injection sentences) shall have the five intents of
  spec 11, slots and an author id per sentence, split by author 60/15/25 and frozen before training, with at least 100
  test sentences per language and 20 per intent per language. · [T] `tests/test_spec11_protocol.py` (already written)
- **AC-05** — The held-out shall be sealed with `eval/heldout.sha256` before any model is trained or evaluated on
  it. · [C] §7.7
- **AC-06** — A sample of 20 cases shall be labeled by a second person, with the agreement in `eval/README.md`. · [D]
- **AC-07** — If a case is in the `heldout` set, then its customer shall be in the held-out split of §7.1, and no
  customer or transaction shall appear in both sets. · [T]
- **AC-08** — The query, the scripts and the case files shall never read `data/gold_eval/` nor contain `is_fraud`. · [T]
- **AC-09** — The `expected` block of every agent case shall be produced by `eval/derive_expected.py` from the gold
  record and the policy engine (`nick_of_time.policy`, spec 02), not typed by hand; the messages are the only
  team-written fields. · [T]
- **AC-10** — Every classifier sentence shall record its source (`written` or `paraphrase`) and, for a paraphrase, the
  generator model; a paraphrase shall carry the author of its seed sentence. · [T]
- **AC-11** — `eval/demo/live_profiles.yaml` shall define, per zone, the profile of the synthetic recent transactions
  of live mode (ADR 0020), and `eval/demo/sample_cases.jsonl` the four processed sample cases with their scripted
  analyst steps; every item is labeled synthetic or scripted. · [D]

## 7. Data model touched
Reads `data/gold/transactions_enriched`, `products` and `customers` (read-only). Creates files under `eval/` and
`queries/eval/`. Never reads `data/gold_eval/` (constraint 7 of `CLAUDE.md`).

### 7.1 Customer split
`policies.yaml` gives the rule `hash(customer_id) mod 10` (train 0–6, dev 7, held-out 8–9) but no hash is implemented
and gold v1 has no `split` column. This spec fixes it as: the first 8 hex digits of `md5(customer_id)`, read as an
integer, mod 10. It is stable across engines and versions, unlike DuckDB's `hash()`. A test compares the SQL
expression with a Python reference. `Transaction.split` in `contracts/tools.py` must use the same function.

### 7.2 Candidates — `eval/demo_index.csv`
One row per candidate transaction: `product_type` in (`Tarjeta Débito`, `Tarjeta Crédito`), product owned by the
customer, `transaction_status = 'Approved'`, no `qc_*` flag raised, fixed seed.

**Window.** Issue #11 says May 2026. Counted on gold v1 with the split of §7.1 `[data]`, approved card transactions
with a score of 30 or more are too few for that:

| Window | Held-out, high (≥ 50) | Held-out, medium (30–49) | Dev, high | Dev, medium |
|---|---|---|---|---|
| May 2026 | 3 | 4 | 1 | 0 |
| 2026-03-03 to 2026-05-31 (proposed) | 7 | 10 | 5 | 1 |
| February–May 2026 | 10 | 12 | 5 | 2 |
| 12 months | 36 | 33 | 20 | 8 |

Only 0.067% of card transactions score 30 or more. This spec proposes **2026-03-03 to 2026-05-31**: the 90 days
before `DEMO_TODAY` (2026-06-01, ADR 0020), inside the claim period of LTOSF art. 23 and outside the training window
of the fraud model (June 2025–January 2026, spec 17). In that window the held-out has no high-zone candidate in
Colombia (5 in Mexico, 2 in Argentina). See Q1.

Columns: `customer_id`, `country` (`MX`|`CO`|`AR`, mapped from `customer_country`), `segment`, `split`, `product_id`,
`product_type` (`debit`|`credit`), `transaction_id`, `transaction_date`, `amount`, `currency`, `merchant_name`,
`fraud_score`, `zone`, `amount_tier` (`low`|`mid`|`above_high`, from `amount_gate.by_country`), `n_candidates_7d` (the
customer's card transactions within ±7 days, itself included and any status, to pick ambiguous cases).

**Sample.** The index holds `dev` and `heldout` customers only; train customers are used by no demo customer and no
case. Every high-zone and medium-zone candidate is kept. The human zone keeps 6 rows per country × split × product ×
score band (no score, below 30) × segment, ordered by `md5('demo-index-v1' || transaction_id)`: that string is the
fixed seed, so the same gold gives the same file. The rows per cell and the empty cells are in `eval/README.md`.

### 7.3 Demo — `eval/demo/`
- `customers.json`: six `dev` customers, two per mandatory case (normal, ambiguous, requires a human), with
  `customer_id`, `display_name`, `country`, `segment`, `scenario`, `language`. At least one PT customer and one MX debit
  customer (provisional credit by business day 2). `display_name` is invented and labeled so; no personal data from
  `gold.customers` is copied.
- `reference.json` (internal, never served): the mandatory case of each demo customer and the row of
  `demo_index.csv` behind it. `scenario` in `customers.json` stays neutral: it shows no score and no zone.
- `live_profiles.yaml`: for `high`, `medium` and `human`, the fields the live-mode generator needs (score range, amount
  range per country, merchant, hours before "now"). Synthetic, stored apart, never in gold, eval or pitch numbers.
- `sample_cases.jsonl`: MX high zone → credit approved → closed · CO human zone → information requested → resolved ·
  AR re-evaluation · PT injection refused, then a legitimate case. One is the case followed in the video.

### 7.4 Agent cases — `eval/cases/dev.jsonl` (20) and `eval/cases/heldout.jsonl` (80)
Coverage proposed to the lead (Q2). It is bounded by §7.2: with the proposed window the held-out has 7 high-zone and
10 medium-zone transactions, so the set uses them all instead of inventing scores.

| Type (schema) | Held-out | Dev | Expected decision |
|---|---|---|---|
| `normal` | 13 (5 high, 8 medium) | 4 (3 high, 1 medium) | `block_and_open_case` or `confirm` |
| `human` | 17 (13 score < 30 or null, 4 request for a person) | 4 | `handoff` or `connect_person` |
| `ambiguous` | 10 | 3 | `ask` |
| `customer_returns` | 8 (status and coherence: "¿ya está bloqueada?", "¿cómo va mi caso?") | 2 | `answer_status` |
| `injection` | 10 | 2 | `deny` |
| `unauthorized_access` | 6 | 1 | `deny` |
| `session_expired` | 4 | 1 | `reauthenticate` |
| `tool_failure` | 4 (2 `block_card` on high zone, 2 `open_case`) | 1 | `escalate_unconfirmed_action` |
| `missing_data` | 3 | 1 | `handoff` |
| `late_arrival` | 2 | 0 | `ask` |
| `out_of_scope` | 3 | 1 | `deny` |
| **Total** | **80** | **20** | |

Held-out language: 50 ES / 30 PT. Every country and every segment appears at least once per language. `cap` has no
case here (budget caps are tested in spec 04).

**Layout.** The team writes one line per case in `eval/cases/plan/<set>.jsonl`: `id`, `type`, `language`, `anchor`
(the row of `demo_index.csv` the case is about), `messages`, `intent` (the label of those messages; absent when the
case is refused before any intent matters), `notes`, `labeler` and, where the type needs them, `fixtures` (`none` or
`cluster`), `session`, `tool_faults` and `case`. `eval/derive_expected.py` turns each line into a case: the fixtures
are the anchor's row, or with `cluster` the customer's approved card transactions within 7 days either side of it
(read from gold), and `expected` comes from the policy engine (§7.5). Ids: `EV-0101` to `EV-0120` for dev and
`EV-0201` to `EV-0280` for the held-out (`EV-0001` to `EV-0005` are the examples of spec 01).

**Types that needed a definition.** `normal` in the medium zone has two shapes: one message ends in `confirm` with
nothing opened; two messages (the second confirms) end with the case opened and handed off. `human` holds scored
transactions below 30 and requests for a person, with or without a reported charge. `missing_data` is a transaction
with no fraud score and no merchant name: the case is opened and handed off, and the reply must not invent either.
`late_arrival` is a charge the customer reports before it is in their transactions: the case has no fixture, so there
is no candidate and the system asks; the amount in the message is the customer's own and is not in gold.

### 7.5 How `expected` is derived (AC-09)
`eval/derive_expected.py` calls the policy engine with the gold record and writes `decision`, `zone`, `intent`,
`final_state`, `queue_status`, `receipt`, `deadline_country`, `guardrail_ids` and `notifications`. The rows it must
reproduce (spec 02 §4.1 and §4.2):

| Record | `decision` | `product_status` | `case_open` | `queue_status` | `handoff_emitted` | `receipt.issued` |
|---|---|---|---|---|---|---|
| score ≥ 50, amount ≤ `high` tier | `block_and_open_case` | `Blocked` | true | `verification` | false | true |
| score ≥ 50, amount > `high` tier | `handoff` | `Active` | true | `review` | true | true |
| score 30–49, one message | `confirm` | `Active` | false | — | false | false |
| score 30–49, customer confirms in a second message | `handoff` | `Active` | true | `review` | true | true |
| score < 30 or null | `handoff` | `Active` | true | `review` | true | true |
| more than one candidate | `ask` | `Active` | false | — | false | false |
| status question on an existing case | `answer_status` | unchanged | unchanged | unchanged | false | false |
| request for a person | `connect_person` | `Active` | per D-020 | per D-020 | true | per D-020 |
| request for a person on a score ≥ 50 charge (D-029) | `connect_person` | `Active` | true | `review` | true | true |
| injection, another customer's data, out of scope | `deny` | `Active` | false | — | false | false |
| session expired or none | `reauthenticate` | `Active` | false | — | false | false |
| `block_card` fails twice | `escalate_unconfirmed_action` | `Active` | true | `review` | true | true |
| `open_case` fails twice | `escalate_unconfirmed_action` | `Active` | false | — | true | false |

The script runs `PolicyEngine.decide()` once per scripted message and keeps the last decision, so a case states the
outcome of its last turn. `tests/test_spec09_eval_data.py` checks every row above against the engine and every
committed case against the script. The cases are re-derived before the seal; any difference is fixed in the cases,
not in the engine. `[assumption]` Three things are not decided by the engine and follow this table: a failed
`block_card` or `open_case` gives `escalate_unconfirmed_action` (`reliability.on_failure`), and with no confirmed
case nothing is blocked and no receipt is issued; a request for a person counts as a
handoff even when no case is opened; `has_deadline` is true when the case is opened and the country has an entry in
`regulatory_clock`. `guardrail_ids` and `notifications` list only what the engine and the opened actions imply
(`case_opened`, `card_blocked`); the harness checks that they are present, not that they are the only ones.

### 7.6 Classifier set — `eval/classifier/train.jsonl`, `validation.jsonl`, `test.jsonl`
The layout `eval/PROTOCOL.md` hashes (Seal, b): top-level files whose names start with `train`, `validation` and
`test`. Each split is written by one generator model family, none of them Claude (ADR 0025): train Llama 3.3 70B
(`us.meta.llama3-3-70b-instruct-v1:0`), validation Gemma 3 27B (`google.gemma-3-27b-it`), test DeepSeek V3.2
(`deepseek.v3.2`), on Bedrock us-east-2. `python -m eval.classifier.generate` writes drafts to
`eval/classifier/draft/` (a subfolder, so not split files); a person reviews every line and
`python -m eval.classifier.review promote` writes the top-level split files (§7.7, `eval/README.md`).

One JSON object per line, in this order:

`id`, `text`, `language` (`es`|`pt`), `intent` (one of the five; null on injection rows), `label` (`injection` on
injection rows, absent otherwise), `also_dispute` (true when a `human_request` or `status_inquiry` sentence also
carries a dispute, D-020 d), `slots` (`amount` as a decimal string, `currency` as an ISO code, null for a bare "$" or
"pesos", spec 11 §8; `date` as YYYY-MM-DD resolved against `DEMO_TODAY`; `merchant`; null when absent), `card` (the
card wording the generator was asked to use, e.g. "mi tarjeta" or "cartão de crédito", or null), `author` (the
generator model id), `source` (`written` for a generator's seed, `paraphrase`), `generator` (the model id), `seed_id`
(the written sentence a paraphrase comes from; null on seeds), `origin` (the model id), `prompt_hash` (sha256 of the
versioned prompt), `persona` (formality, country, mood, typos, length, code switch), `review_status`.

- **Drafts** add `checks` (the generator's hints for the reviewer: a planned slot or card wording missing, an
  unplanned amount, date, merchant or card type, language or English drift, duplicates) and have
  `review_status: pending`.
- **Promoted rows** drop `checks` and carry `review_status` `kept` or `fixed`, `reviewer` (GitHub handle) and, on
  fixed rows only, `original` (the draft values the reviewer replaced). Dropped rows are not written.

Sizes, so the test of spec 11 passes with the shares inside 3 points:

| Split | Intent rows | Per language × intent | Injection rows | Total | Share |
|---|---|---|---|---|---|
| Train | 480 | 48 | 48 | 528 | 60% |
| Validation | 120 | 12 | 12 | 132 | 15% |
| Test | 200 | 20 | 20 | 220 | 25% |
| **Total** | **800** | | **80** | **880** | |

Review drops lines, so the drafts are over-generated by about 20% in every cell with the same shares: 58 / 15 / 24 per
language × intent and 58 / 15 / 24 injection rows (train / validation / test), 1,067 drafts in all. Each generator
writes a seed for about one row in four and three paraphrases per seed. Promotion checks the shares and the test
minimums on what review keeps, not on these targets.

All the sentences of one author are in one split, paraphrases included (AC-10); with one generator per split this
holds by construction. Model-generated sentences are `[simulated]`.

### 7.7 Seal
- `eval/heldout.sha256`: the bare sha256 of `eval/cases/heldout.jsonl`, one 64-hex token and nothing else
  (`shasum -a 256 eval/cases/heldout.jsonl | cut -d' ' -f1 > eval/heldout.sha256`, or
  `python -m eval.derive_expected seal` where `shasum` is missing). `.gitattributes` keeps `eval/cases/` and the hash
  file byte for byte, so a checkout with line-ending conversion gives the same hash.
- The hash in the repo is the hash of the current file. It becomes **binding at M02**, when it is copied into the
  seal block of `eval/PROTOCOL.md`; until then a review may still change a case, and the hash is written again.
- The classifier manifest hash is computed with the command of `eval/PROTOCOL.md` (Seal, b) and recorded there at M02;
  `python -m eval.classifier.review promote` prints the same hash after review and never writes it into the protocol.
- After the seal, `heldout.jsonl` and the three split files never change (ADR 0021); new data is a new sealed set.

## 8. Assumptions and open questions (gate 1 — to close in this PR)
- **Q1 (@salazarvalverdeai) — window.** AC-01 says May 2026, which leaves 3 high-zone and 4 medium-zone held-out
  transactions. Proposed: 2026-03-03 to 2026-05-31 (§7.2). This changes an issue criterion, so it needs your approval.
  The alternative is to raise scores through `fixtures` overlays, which makes the state synthetic.
- **Q2 (@salazarvalverdeai) — coverage.** Is §7.4 the "agreed coverage" of AC-03? It has 13 `normal` cases, not more,
  because real high and medium transactions are that scarce.
- **Q3 — authors.** **Decided by ADR 0025 (lead, 2026-10-05):** each split is written by a different generator model
  family, none of them Claude — train Llama 3.3 70B, validation Gemma 3 27B, test DeepSeek V3.2 — and `author` is the
  generator model id. Every line is reviewed by a person; train and validation by the lead, test by someone who is not
  the classifier's developer (in practice @gianzk).
- **Q4 (@salazarvalverdeai) — split function** of §7.1 (md5-based): OK for `Transaction.split`?
- **Q5 (@salazarvalverdeai) — PT cases.** The dataset has no BR customers. Default: PT cases use real MX, CO and AR
  customers with a Portuguese message and keep their real country; no case is labeled `BR`.
- **Q6 (all) — second labeler** for AC-06 (20 cases, about 20 minutes): who?
- **Q7 — paraphrase model.** **Decided by ADR 0025 (lead, 2026-10-05):** each split's generator writes its own seeds
  and paraphrases; results of a candidate of the same family as the generator of the split being scored are flagged
  (spec 11 §8), and the Llama and Gemma arms already fail the structured-output smoke test (F-013).
- Assumption: the agent-case messages are drafted with an AI assistant and reviewed line by line by their labeler;
  their `origin` stays `team-generated` and `eval/README.md` says so. The classifier sentences are written by the
  generator models of ADR 0025 (`origin` = the model id) and reviewed line by line before promotion. `[assumption]`
- Assumption: with 80 held-out cases the per-cell intervals are wide; results show n and do not over-claim (ADR 0007).
- Assumption: the counts of §7.2 hold for the split of §7.1; a different function (Q4) changes them slightly. `[data]`

## 9. Out of scope
The harness and its metrics (spec 10) · the classifier, its training and the protocol text (spec 11) · the live-mode
generator and the sample-case seeder (spec 05; this spec gives their inputs) · double labeling of the whole set · a
`split` column inside gold (contract v2) · calibrating `amount_gate` with data.

## 10. Plan, tasks and verification
Implementation goes in `feat/09-…` branches once this spec is approved.
- [x] T1 — `queries/eval/demo_index.sql` + `eval/demo_index.csv` (`python -m eval.demo_index`) · covers AC-01, AC-07, AC-08 · done when: the cells of
      §7.2 are filled or the empty ones are listed in `eval/README.md`
- [x] T2 — `eval/demo/customers.json`, `reference.json`, `live_profiles.yaml`, `sample_cases.jsonl` · covers AC-02, AC-11
- [x] T3 — `eval/derive_expected.py` + `eval/cases/plan/dev.jsonl` + `eval/cases/dev.jsonl` · covers AC-03, AC-09 · done when: 20 cases validate
- [x] T4 — `eval/cases/plan/heldout.jsonl` + `eval/cases/heldout.jsonl` + `eval/heldout.sha256` · covers AC-03, AC-05, AC-07 · done when: 80 cases
      validate with the counts of §7.4
- [ ] T5 — `eval/classifier/*.jsonl` from the generators of ADR 0025, reviewed line by line · covers AC-04, AC-10 ·
      done when: `tests/test_spec11_protocol.py` runs its split checks instead of skipping them, and passes (drafts,
      generator and review tools done, `tests/test_spec09_classifier_set.py`; review and promotion pending)
- [ ] T6 — second labeling of 20 cases + agreement in `eval/README.md` · covers AC-06
- [x] T7 — `tests/test_spec09_eval_data.py` citing AC-03, AC-05, AC-07, AC-08, AC-09 (done, offline, no gold needed); AC-10 comes with T5
- [ ] M02 — review and seal `eval/PROTOCOL.md`, tag `protocol-v1` (manual, after T4 and T5)

**Closing checklist:** every AC has a passing test or check that cites it · status → Implemented · lessons added to
`CLAUDE.md`.
