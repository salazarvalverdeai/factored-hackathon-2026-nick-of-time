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
| `derive_expected.py` | builds a case file from its plan; `expected` comes from the policy engine | 09 §7.5 |
| `eval_case.schema.json`, `examples.jsonl` | shape of an agent case, with five examples | 01 |
| `PROTOCOL.md` | pre-registered evaluation rules; unsealed until M02 | 11, 15, 17 |
| `bench/` | model benchmark | 15 |

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
| SC-04 | PT: injection refused, then a legitimate high-zone case | `verification` |

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
The held-out set (80 cases), its seal and the second labeling of 20 cases (AC-06) are not done yet.
