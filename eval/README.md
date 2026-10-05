# eval/

Evaluation data and tools (owner: @vldiego). The dataset has no customer text, so every item here is **real state
from gold plus a message the team writes** (spec 09). Nothing in this folder reads `data/gold_eval/`, except the
harness of spec 10 when it scores.

| File | What it is | Spec |
|---|---|---|
| `demo_index.csv` | candidate transactions for the demo and the agent cases | 09 §7.2 |
| `demo_index.py` | runs `queries/eval/demo_index.sql` and writes the CSV; holds the customer split function | 09 §7.1 |
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
