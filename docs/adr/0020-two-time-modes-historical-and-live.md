# 0020. Two time modes: historical (replay) for evaluation and processed cases, live for the demo

- **Status:** Accepted (supersedes [0012](0012-frozen-demo-date.md))
- **Date:** 2026-10-04
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** specs 01, 02, 03, 04, 05, 09, 10, 11, 15 · ADRs 0007, 0012, 0019

## Context
- The gold transactions end on 2026-05-31: R1 keeps `2025-06-01 ≤ transaction_date < 2026-06-01`
  ([`contracts/gold_contract.md`](../../contracts/gold_contract.md), R1). The demo is judged in October 2026.
- Mexico's 2-business-day provisional credit for debit cards applies only to charges made within the 48 hours before the
  notice ([CONDUSEF](https://www.gob.mx/condusef/prensa/cargos-no-reconocidos-en-tarjeta-de-debito-se-restituiran-en-dos-dias-habiles-bancarios?idiom=es),
  checked 2026-10-04). Older charges follow the slower path in spec 02 §4.3.
- ADR 0012 froze "today" at 2026-06-03. With that date, no MX debit charge in the gold falls within the 48 hours, so the
  headline rule is never shown. Using the real date instead makes every charge more than four months old.
- Evaluation needs a fixed "today" (reproducible, sealed held-out — ADR 0007). A judge trying the chat needs dates that
  look like today.

## Decision
The system runs in one of two **modes**, fixed when a session is created and never changed during it:

| | `replay` (historical) | `live` |
|---|---|---|
| Purpose | Evaluation, benchmark, and **processed sample cases** that show a case's full history | A judge reports a new charge today |
| "Today" | `DEMO_TODAY = 2026-06-01` (the day after the gold ends, a Monday) | The real date in the customer's country time zone |
| Transactions | Gold v1 as is | Gold v1 plus **synthetic recent transactions** for the demo customers, generated relative to today, stored apart in `demo_transactions` and flagged `synthetic` |
| Used by | Harness (spec 10), benchmark (spec 15), the sample-case seeder (spec 05) | `/chat` and the 5-minute tour |
| UI label | "Historical case · demo date 1 Jun 2026" | "Live · today" |

Rules:
1. The clock (spec 02) receives "today" from the mode — `clock.today(mode)`; no component reads the system clock directly.
2. Synthetic transactions never enter the gold, the lakehouse, the evaluation or any pitch number; "Reset demo"
   deletes and regenerates them.
3. Evaluation and benchmark runs refuse `live` mode.
4. Every synthetic item is labeled in the UI and the README.
5. A few historical cases are processed end to end (agent turn plus scripted analyst steps) so the console and
   `/case/{id}` show complete histories; one of them is the case followed in the video.

Example (MX debit): a notice on Monday 2026-06-01 about a charge on 2026-05-31 gets a provisional credit date of
Wednesday 2026-06-03 in replay; in live mode, a notice on Monday 2026-10-05 about yesterday's synthetic charge gets
Wednesday 2026-10-07. Both apply the spec 02 rule (opened + 2 business days).

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Two modes (chosen) | Reproducible evaluation and a demo that looks like today; the MX 48 h rule appears in both | Synthetic data to generate, label and keep out of metrics |
| Frozen date only (ADR 0012) | Simple, deterministic | June dates confuse a judge in October; on 2026-06-03 the MX 48 h rule never applies |
| Real date only | Natural for the judge | Every gold charge is months old; the 48 h rule never applies; evaluation is not reproducible |
| Shift the dataset's dates forward | One mode | Breaks gold contract R1 and the reproducibility of the pitch numbers |

## Consequences
- Easier: evaluation stays sealed and deterministic; the live demo shows today's dates and the strongest MX rule.
- Harder: the live mode needs a generator for recent transactions with a fraud score per zone (profiles chosen in
  spec 09) and a `mode` on every session, tool call and test.
- Neutral: ADR 0012 becomes Superseded; spec 02 resolves its Q7 by pointing here.

## Confidence
Medium-high. Revisit if the organizers provide transactions dated after 2026-05-31, or if the live mode's synthetic data
is mistaken for real data in a review.
