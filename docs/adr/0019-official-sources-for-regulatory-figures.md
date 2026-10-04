# 0019. Every regulatory or external figure cites an official public source and a verification date

- **Status:** Accepted
- **Date:** 2026-10-04
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** spec 02 (regulatory clock), [`contracts/policies.yaml`](../../contracts/policies.yaml), ADR 0005

## Context
The system tells customers dates such as "your credit is due by Wednesday 3 June (Banxico)". A wrong deadline is a
compliance failure, not a cosmetic bug. On 2026-10-04 a review against official sources found that Mexico's 2-business-day
debit credit applies only to charges made within the 48 hours before the notice — a condition our contract had missed.
Deadlines change by regulation, and secondary sources (blogs, law-firm summaries) disagree with each other.

## Decision
Any regulatory deadline, legal threshold, exchange rate or other external figure used by the product or quoted in docs:
1. comes from an **official public source** (regulator, official gazette, consumer agency) — never from memory or a
   secondary summary;
2. is stored with **`source_url`** and **`verified_on`** fields (and a short comment) next to the value in
   `contracts/policies.yaml` or the data file that holds it;
3. is labeled `[external]` in docs; if not yet checked against the official text it stays `[external, to verify]`
   and cannot be shown to a customer as a commitment;
4. is enforced by a test: a `regulatory_clock` entry without `source_url` and `verified_on` fails CI;
5. is re-verified when the regulation changes or before each release that relies on it.

A country without a verified entry gets no deadline: the case is opened and routed to a person (`POL-CLOCK-UNKNOWN`).

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Source + verification date per figure, tested (chosen) | Auditable; errors are traceable and fixable | Research time per country |
| Sources in a separate document | Less clutter in the YAML | Drifts from the values it justifies |
| Trust the team's notes | Fast | Already produced one wrong rule (MX 48 h) |

## Consequences
Customer-facing deadlines are defensible in front of a regulator and a judge; adding a LATAM country is a reviewed PR
with its source. Each country costs a short research step.

## Confidence
High.
