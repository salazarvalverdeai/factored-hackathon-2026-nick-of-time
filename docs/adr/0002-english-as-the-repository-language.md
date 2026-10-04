# 0002. English as the repository language

- **Status:** Accepted
- **Date:** 2026-09-28
- **Deciders:** Freddy, GianMarco, Diego, David · **Owner:** @salazarvalverdeai

## Context
The team works in Spanish, the bank's customers write in Spanish and Portuguese, and the judges and the wider
engineering audience read English.

## Decision
In the context of a public repository judged by an international panel, we write everything recorded in the repo in
English — code, identifiers, contracts, docs, specs, ADRs, commits, pull requests, issues and the UI the judges see —
and keep Spanish and Portuguese only for customer-facing text (agent replies, notification templates, evaluation
messages). Dataset values stay as they are. Personal drafts in other languages stay out of git.

## Consequences
One vocabulary across code and docs (`/console`, `POST /api/cases/{id}/action`, queue `new → verification → review →
resolved → closed`, zones `high/medium/human`). Customer-facing templates in `contracts/policies.yaml` remain in
Spanish/Portuguese on purpose.

## Confidence
High.
