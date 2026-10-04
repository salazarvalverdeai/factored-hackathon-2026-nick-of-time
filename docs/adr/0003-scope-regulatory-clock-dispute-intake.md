# 0003. Scope: regulatory-clock card dispute intake (W3)

- **Status:** Accepted
- **Date:** 2026-09-28
- **Deciders:** team vote · **Owner:** @salazarvalverdeai
- **Related:** [`problem.md`](../../problem.md), [`docs/eda/`](../eda/)

## Context
The EDA mapped complaints to four workflows. Unrecognized and wrongful card charges (W3) are **36.4% of complaints**
`[data]`, have the worst first-contact resolution (43.6% vs 76.6% for the bank) `[data]`, NPS −85.3 `[data]`, and are
the only workflow with a legal deadline per country `[external]`.

## Decision
Build the intake of card disputes end to end: understand the customer (ES/PT), identify their own transaction, decide by
rules, act with verification (block the card, open the case), compute the country's regulatory deadline, give the
customer a verified receipt and the analyst a verified handoff. **We resolve the contact, not the complaint:** the bank
resolves the complaint within the deadline we compute and show.

Out on purpose: case investigation, chargebacks with the card network, automatic credit, voice, real WhatsApp,
multi-agent designs, Graph RAG, fine-tuning, our own fraud model.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| W3 dispute intake (chosen) | Largest pain, measurable, legal clock, verifiable actions | PT has 0% coverage in the data |
| W1 accounts and payments | High volume | No legal clock, no decision signal |
| W4 credit | High value per case | Long cycles, outcomes outside the data window |
| Generic agent for all workflows | Breadth | Nothing verifiable to show in 10 days |

## Consequences
A narrow problem where every claim is measurable and every action verifiable. Complaints' product foreign key is broken
in 100% of rows, so disputes start from `transactions`.

## Confidence
High; not reopened.
