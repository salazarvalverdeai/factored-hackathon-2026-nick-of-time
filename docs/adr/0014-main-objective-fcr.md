# 0014. Main objective: first-contact resolution of dispute contacts

- **Status:** Accepted
- **Date:** 2026-09-29
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** specs 10, 15, ADR 0013

In the context of dispute contacts with 43.6% first-contact resolution versus 76.6% for the bank `[data]`, facing
several possible goals (follow-ups, handling time, NPS, resolution time), we decided that the product's main objective
is to **raise FCR of dispute contacts**, measured in the harness by the **complete-intake rate**, the **precision and
recall of blocks** against `is_fraud`, and **`receipt_rate`**, with follow-ups and human time as secondary effects of
the same lever, to achieve one number everyone optimizes, accepting that NPS and resolution time are long-term outcomes
we do not measure in a week, instead of reporting a basket of metrics with no priority.
