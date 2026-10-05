# eval/

Evaluation data and tools (owner: @vldiego). The dataset has no customer text, so every item here is **real state
from gold plus a message the team writes** (spec 09). Nothing in this folder reads `data/gold_eval/`, except the
harness of spec 10 when it scores.

| File | What it is | Spec |
|---|---|---|
| `demo_index.csv` | candidate transactions for the demo and the agent cases | 09 §7.2 |
| `demo_index.py` | runs `queries/eval/demo_index.sql` and writes the CSV; holds the customer split function | 09 §7.1 |
| `demo/customers.json` | the six demo customers of `/chat`, in the shape of `GET /api/demo/customers` | 09 §7.3 |
| `demo/reference.json` | internal: the mandatory case and the index transaction behind each demo customer; never served | 09 §7.3 |
| `demo/live_profiles.yaml` | profiles of the synthetic recent transactions of live mode `[simulated]` | 09 §7.3 |
| `demo/sample_cases.jsonl` | four processed sample cases with scripted analyst steps | 09 §7.3 |
| `cases/plan/dev.jsonl` | what the team writes for each dev case: type, messages, intent and the index row it is about | 09 §7.4 |
| `cases/dev.jsonl` | the 20 dev agent cases, built by `derive_expected.py`; do not edit by hand | 09 §7.4 |
| `cases/plan/heldout.jsonl`, `cases/heldout.jsonl` | the same for the 80 held-out cases | 09 §7.4 |
| `heldout.sha256` | sha256 of `cases/heldout.jsonl` | 09 §7.7 |
| `second_label.py`, `labeling/` | blind second-labeling sheet of the dev cases and the agreement with the first labels | 09 AC-06 |
| `derive_expected.py` | builds a case file from its plan; `expected` comes from the policy engine | 09 §7.5 |
| `eval_case.schema.json`, `examples.jsonl` | shape of an agent case, with five examples | 01 |
| `PROTOCOL.md` | pre-registered evaluation rules; unsealed until M02 | 11, 15, 17 |
| `bench/` | model benchmark | 15 |
| `harness/` | the evaluation harness (`make eval`) | 10 |
| `local/` | the real stack for `make eval` on one machine (`make eval-local`): api with the eval hooks, MCP server, graph | 10 T6 |
| `classifier/generate.py`, `classifier/draft/` | classifier sentence drafts from three model families and their run record | 09 §7.6 |
| `classifier/review.py` | review sheets of the drafts and promotion to `classifier/{train,validation,test}.jsonl` | 09 §7.6 |
| `classifier/evaluate.py` | scores B0 and B1, picks τ on validation, exports `classifier.json` after the seal | 11 T3, T4, T6 |

## Demo index
`python -m eval.demo_index` rewrites `demo_index.csv` from `data/gold/` (it needs `make setup`). The same gold gives
the same file: the human-zone sample is ordered by a hash of the transaction id, with no random draw.

- **Candidates:** approved card transactions on a product the customer owns, no `qc_*` flag raised, from 2026-03-03 to
  2026-05-31 (the 90 days before `DEMO_TODAY`).
- **Split:** by customer, `int(md5(customer_id)[:8], 16) % 10` — 7 is `dev`, 8 and 9 are `heldout`. Train customers
  (0 to 6) are not in the index.
- **Sample:** every high-zone and medium-zone candidate is kept. The human zone keeps 6 per country × split × product
  × score band (no score, below 30) × segment.
- **`n_candidates_7d`:** the customer's card transactions within 7 days either side of the row, itself included, any
  status. A value of 2 or more marks a candidate for an `ambiguous` case.

Rows per cell on gold v1 `[data]` (596 rows, 563 customers):

| Country | Zone | Split | Rows |
|---|---|---|---|
| MX | high | dev | 2 |
| MX | high | heldout | 5 |
| MX | medium | dev | 0 |
| MX | medium | heldout | 4 |
| MX | human | dev | 96 |
| MX | human | heldout | 96 |
| CO | high | dev | 2 |
| CO | high | heldout | 0 |
| CO | medium | dev | 1 |
| CO | medium | heldout | 5 |
| CO | human | dev | 96 |
| CO | human | heldout | 96 |
| AR | high | dev | 1 |
| AR | high | heldout | 2 |
| AR | medium | dev | 0 |
| AR | medium | heldout | 1 |
| AR | human | dev | 93 |
| AR | human | heldout | 96 |

**Empty cells.** Gold has no candidate for CO high held-out, MX medium dev and AR medium dev: only 0.067% of card
transactions score 30 or more `[data]`. The agent cases use the scored transactions that exist and never invent a
score. No candidate is above the `high` amount tier either (550 `low`, 46 `mid`), so the "block needs a person because
of the amount" row has no real transaction in this window.

## Demo data (`demo/`)
Six real `dev` customers, two per mandatory case. The customer, the card and the transactions are real gold state
`[data]`; the display names are **invented** and no personal field of `gold.customers` is copied. `scenario` is neutral
on purpose: it never shows a score or a zone to the person using `/chat`.

| Demo customer | Country, card | Mandatory case | Language | Real transaction behind it |
|---|---|---|---|---|
| Ana | MX debit | normal (high zone: block and open the case) | es | 1,533.08 USD on 2026-03-18 |
| Camilo | CO credit | normal (medium zone: confirm first) | es | 1,230,906.80 COP on 2026-04-13 |
| Sofía | MX, several cards | ambiguous | es | 3 card charges between 2026-03-20 and 2026-03-30 |
| Bruno | AR debit | ambiguous | pt | 3 card charges between 2026-05-19 and 2026-05-22 |
| Valentina | CO credit | requires a human (no score) | es | 1,598,055.46 COP on 2026-05-14 |
| Rafaela | AR debit | requires a human (score below 30) | pt | 75,525.08 ARS on 2026-05-29 |

The dataset has no Brazilian customer, so the Portuguese customers are real AR customers who write in Portuguese and
keep their real country (spec 09 Q5, default).

- **Live mode** (`live_profiles.yaml`): what the generator of spec 05 creates for each demo customer relative to the
  real date. Every generated row is synthetic `[simulated]`, is stored only in `demo_transactions` and never enters
  gold, the evaluation or a pitch number (ADR 0020). Amount ranges are the p25 to p75 of approved card transactions in
  gold v1 `[data]`; score ranges and hours are our choice `[assumption]`.
- **Processed sample cases** (`sample_cases.jsonl`): four historical cases on other `dev` customers, so a demo
  customer never meets a seeded case. The customer text and every analyst step are scripted `[simulated]`; the
  transactions are real. `SC-01` is the case proposed for the video.

| Id | Case | Ends in |
|---|---|---|
| SC-01 | MX high zone: card blocked, credit approved, closed | `closed` |
| SC-02 | CO human zone: information requested, then resolved | `resolved` |
| SC-03 | AR human zone: resolved, then re-evaluated at the customer's request | `review` |
| SC-04 | PT: injection refused, then a legitimate case handed to a person (human zone) | `review` |

## Agent cases (`cases/`)
`PYTHONPATH=packages python -m eval.derive_expected dev` rebuilds `cases/dev.jsonl` from `cases/plan/dev.jsonl`. To
change a case, edit its plan line and rebuild; a test fails if a committed case differs from what the script derives.

- **Real state:** the customer and the transaction fixtures come from `demo_index.csv` (ambiguous cases also read the
  customer's neighbouring card transactions from gold) `[data]`.
- **Team-written:** the customer messages, their intent label and the notes. They were drafted with an AI assistant
  and are reviewed line by line by the labeler; `origin` stays `team-generated`. `[simulated]`
- **Derived:** the whole `expected` block, from `nick_of_time.policy` (spec 02). A case states the outcome of its last
  scripted turn.

Dev set: 20 cases, 14 in Spanish and 6 in Portuguese — 4 `normal`, 4 `human`, 3 `ambiguous`, 2 `customer_returns`,
2 `injection` and 1 each of `unauthorized_access`, `session_expired`, `tool_failure`, `missing_data`, `out_of_scope`.

Held-out set: 80 cases on 80 different held-out customers, 50 in Spanish and 30 in Portuguese — 13 `normal`,
17 `human`, 10 `ambiguous`, 8 `customer_returns`, 10 `injection`, 6 `unauthorized_access`, 4 `session_expired`,
4 `tool_failure`, 3 `missing_data`, 2 `late_arrival`, 3 `out_of_scope`. It uses all 7 high-zone held-out transactions
gold has (5 `normal`, 2 `tool_failure`) and all 10 medium-zone ones (8 `normal`, 2 `customer_returns`) `[data]`.
With 80 cases the intervals per cell are wide: results show n and do not over-claim (ADR 0007).

**Seal.** `eval/heldout.sha256` is the sha256 of `cases/heldout.jsonl`
(`PYTHONPATH=packages python -m eval.derive_expected seal`). No model has been trained or evaluated on the held-out.
The hash becomes binding at M02, when `eval/PROTOCOL.md` is sealed; after that the file never changes and new data
is a new sealed set (ADR 0021). **Do not use the held-out to tune prompts, rules or thresholds: use the dev set.**

## Local real stack (spec 10 T6)
`make eval-stub` scores the api stub's fixture; `make eval-local` stands up the real system, so `make eval` scores what
the real `dispute_intake` graph does. Two shells, from the repo root:

```bash
make gold-pull                 # once: data/gold (or GOLD_PATH=/path/to/gold on both commands)
make eval-local                # shell 1: api :8000 + MCP :8001 + langgraph dev :2024; Ctrl-C stops all three
make eval                      # shell 2: dev set, S0 and S1, 4 runs -> eval/.runs/<utc time>-dev/
make eval EVAL_ARMS=S0 EVAL_RUNS=1      # a quick pass with no model call
```

- **What runs.** One process (`python -m eval.local`) serves the store-backed api of spec 05 (`app.live`) and the MCP
  server the deploy runs (`mcp_server.__main__.build`, a fresh 48-hex key per start), both over one in-memory store, and
  starts `langgraph dev` on `langgraph.json`. The api reaches the graph through its own Platform client and the graph
  reaches the MCP server through `MCP_URL`, as on Platform. `make eval-local` installs `langgraph-cli[inmem]` into the
  venv on first use (local only; CI never needs it).
- **Why not Platform.** The deployment's graph calls the production MCP server, which writes the production database;
  it cannot reach a local MCP server or a seeded local session, so evaluation runs never use it.
- **Evaluation hooks.** The live api has no `/api/eval/*` routes (spec 05 §8); `eval/local/hooks.py` adds them to the
  local app only, so no deployed image carries them. The seed writes a `replay` session (`verified`, `expired` or
  `none`), the case's language and `tool_faults`, and a returning customer's case with clock deadlines, under a store
  run id unique per seed, so a second `make eval` against the same process starts from gold again. Fixtures must be gold
  rows: overlays (held-out `late_arrival`) are refused, not invented.
- **Final state.** Read from the turns the api received from the graph (decision, zone, intent, receipt, handoff card,
  guardrails, actions, usage, latency) and from fresh store and gold reads of the run (case, queue status, card
  status, notifications, call requests, denials). `handoff_emitted` is a handoff card in any turn or a call to a person
  registered in the run (spec 09 §7.5). `other_customer_data_exposed` is any transaction, card or case id in what the
  customer received that is not theirs in the run. `status_replies` stays empty until the graph states them (spec 04
  T5), so `coherence_rate` has no denominator yet. A turn that ended without a graph turn makes the run `failed`.
- **Safety.** Loopback only; no `.env` is read and `DATABASE_URL` is dropped (the in-memory store only); no Telegram or
  e-mail is sent; replay "today" is 2026-06-01 (ADR 0020). The harness refuses the production host. S0 calls no model;
  S1 calls Bedrock Haiku 4.5 with `AWS_PROFILE` (default `nickoftime`, us-east-2), at most one `understand` call per
  turn and 0.02 USD per conversation (G-OPS-01). `EVAL_PROVIDER=fake make eval-local` keeps S1 off Bedrock (it then
  runs as S0).
- **Cost.** A dev pass of S1 (20 cases, 4 runs, 84 turns) projects to at most 0.38 USD `[assumption]`: 84 turns × one
  call of ≤ 1,500 input and ≤ 512 output tokens at the Haiku 4.5 price of `bench/prices.yaml` (1.10 / 5.50 USD per 1M);
  the 2026-10-05 run spent 0.037 USD on 20 calls `[simulated]`.

## Second labeling (AC-06)
A second person labels the 20 **dev** cases blind, and the agreement with the first labeler (`vldiego`) is reported
here. The sample is the whole dev set and never the held-out: the second labeler (the lead, @salazarvalverdeai,
AI-assisted) develops the agent and the classifier, so they must not read held-out cases before the seal (ADR 0007).
`eval/second_label.py` never opens `cases/heldout.jsonl`.

```bash
python -m eval.second_label export       # writes eval/labeling/dev_second_label.csv; refuses to overwrite without --force
# fill intent, decision, handoff, case_open, labeler (and note) in the CSV, one row per case, without opening cases/
python -m eval.second_label agreement    # writes eval/labeling/agreement.json and prints a Markdown table
```

- **Blind:** the sheet has the messages and the state (country, segment, session, candidate transactions with the
  bank's `fraud_score`, any existing case, tool faults), and no `expected`, no first-labeler intent and no case `type`
  (it nearly gives away the decision). `labeler` is the GitHub handle of the second labeler (`salazarvalverdeai`).
  `agreement.json` lists the `type` of each disagreeing case for analysis.
- **Vocabulary:** `intent` is one of the five intents of spec 11 or `none` when the case is refused before an intent
  matters; `decision` is one of the nine decisions of spec 09 §7.5; `handoff` and `case_open` are `yes` or `no`.
- **Agreement:** per field, n, agreements, percent agreement, Cohen's kappa and the disagreeing case ids, against
  `cases/plan/dev.jsonl` (intent) and `cases/dev.jsonl` `expected` (decision, handoff, case open). If both raters use
  a single category for every case, kappa is 0/0 and is defined as 1.0. Disagreements are discussed and the cases
  fixed in the plan, never in `expected` by hand.
- **Result (2026-10-05):** the sheet was pre-filled blind by an AI assistant (Claude Code), from the sheet and the
  rules only (spec 02, `contracts/policies.yaml`, spec 09 §7.5), without opening `cases/`, and every row was then
  checked by the lead, who signs it as `labeler`. Sheet: `labeling/dev_second_label.csv`; numbers:
  `labeling/agreement.json`.

  | Field | n | Agreements | % agreement | Cohen's kappa | Disagreeing cases |
  |---|---|---|---|---|---|
  | `intent` | 20 | 19 | 95.0 | 0.925 | EV-0117 |
  | `decision` | 20 | 20 | 100.0 | 1.0 | - |
  | `handoff` | 20 | 20 | 100.0 | 1.0 | - |
  | `case_open` | 20 | 20 | 100.0 | 1.0 | - |

  EV-0117 (expired session): the second label is `none`, because the case is refused before any intent matters,
  and the first keeps the intent of the message. Both give `reauthenticate`, so it is a labeling convention, not a
  disagreement on the outcome, and no case changes. With 20 cases the kappas are wide; they show the labels are
  reproducible from the written rules, not that the rules are right.

## Classifier set (`classifier/`)
The ES/PT sentences of spec 11, with five intents, slots and injection rows (spec 09 §7.6). They are written by three
model families, one per split and none of them Claude, so the author split tests writers the classifier never saw
(ADR 0025): train **Llama 3.3 70B**, validation **Gemma 3 27B**, test **DeepSeek V3.2**, on Bedrock us-east-2.
`author` is the generator model id. The sentences are `[simulated]`: less varied than real customers.

1. **Generate** (done once; cents):
   `AWS_PROFILE=nickoftime PYTHONPATH=packages python -m eval.classifier.generate` (`--dry-run` plans and prices
   without calling a model; it stops when the projected cost is over 2 USD). The code plans each item — persona,
   situation, slots, card wording — from a fixed seed; the prompt is versioned by a hash. Each generator writes seeds,
   then about three paraphrases per seed, about 20% more than the final size in every cell. Output:
   `classifier/draft/{train,validation,test}.jsonl` (`review_status: pending`, with `checks` hints) and
   `classifier/draft/generation.json` (model, region, temperature, seed, prompt hash, counts, tokens, cost).
2. **Review** every line: `PYTHONPATH=packages python -m eval.classifier.review export` writes
   `classifier/draft/review_<split>.csv`. Fill `decision` (`keep`, `fix` with the `fixed_*` cells, or `drop`) and
   `reviewer` on every row; look for intent, amount, product and language drift (for example "mi tarjeta" turned into
   "mi tarjeta de crédito"). **Train and validation: the lead. Test: someone who is not the classifier's developer
   (GianMarco).**
3. **Promote** once the three sheets are done: `PYTHONPATH=packages python -m eval.classifier.review promote`
   (`--dry-run` first). It refuses rows without a decision, a test sheet reviewed by the classifier developer and a set
   outside spec 11 AC-06, writes `classifier/{train,validation,test}.jsonl` and prints the manifest sha256 of
   `PROTOCOL.md` Seal (b). The hash is recorded at M02 by the lead; after the seal the split files never change.

Review hints in `checks` are deterministic (no model call; `python -m eval.classifier.generate --recheck` refreshes
them without touching any text), so they speed the review up without biasing the test split (ADR 0025). A hint is not
a decision: the reviewer reads every line. Beyond the slot and card hints: `same_as_seed` (a paraphrase equal to its
seed after folding case, accents and punctuation); `duplicate:<id>` (same folded text as an earlier row of the split,
naming the first by id order); `near_duplicate:<id>:<score>` (character 3-gram Jaccard >= 0.9 with an earlier row of
the split); `language_leak` (a curated ES-only word in a PT row or PT-only word in an ES row; lists in `generate.py`,
precision over recall); `too_short` (under 4 words, injection rows excepted); `injection_without_marker` (an
injection row with none of a small set of cues such as ignore/ignora, system prompt, otro cliente, actúa como, admin;
it may have softened into a complaint); `cross_split_duplicate:<split>/<id>` (the same sentence in two splits, which
would break the author split). Rows are never compared across splits for the other hints.

Results of a candidate in the same family as a split's generator are flagged (spec 11 §8). Nothing under `draft/` is
a split file: the manifest hashes top-level files only.

Not done yet: the second labeling of 20 cases (AC-06), and the review and promotion of the classifier set (AC-04,
AC-10).

## Classifier evaluation (spec 11 T3, T4, T6)
B1 (TF-IDF + logistic regression) is fit on train and calibrated on validation; τ is the lowest B1 threshold that keeps
precision ≥ 0.95 on validation (AC-07). Every arm is reported at τ.

- `make classifier`: **development run on validation**. Writes `.runs/classifier/<time>/classifier.json` and the B1
  file there (ignored by git), labeled "development run on validation"; never a result path of `PROTOCOL.md`. Before
  the split files are promoted it reads the human-reviewed train and validation drafts; it never reads test.
- `make classifier-test`: **the one test-split run, after the seal (M02)**. Refused while `PROTOCOL.md` is UNSEALED, when no
  `protocol-v1` tag in HEAD's history holds this same `PROTOCOL.md`, or when the promoted split files do not hash to
  the sealed manifest. It scores exactly the pre-registered arms B0, B1 and B2 and refuses any other set (AC-02,
  `PROTOCOL.md` §1.2). It runs once: before B1 is saved and `test.jsonl` is read, the shared guard of
  `harness/seal_guard.py` checks the seal and the committed sealed inputs, then claims the run
  (`results/classifier-test/classifier-test.start.json`); a marker or an output of an earlier run refuses it. It saves
  B1 before `test.jsonl` is read, then writes `models/intent-b1-v1.joblib`,
  `results/classifier.csv` and `apps/web/public/data/classifier.json` (spec 11 §7.1). The export records
  `test_review` (`rules-v1` or `human`) and, for `rules-v1`, the label "test split decided by fixed rules, without
  independent human review" (ADR 0028), plus the B1 file's sha256 and the scikit-learn version that wrote it.
