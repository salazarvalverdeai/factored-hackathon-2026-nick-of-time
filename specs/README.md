# Specs

One spec per feature, written by its owner from [`_template.md`](_template.md) and approved through a `spec/NN-slug`
pull request (merge = Approved). The workflow is in [`CONTRIBUTING.md`](../CONTRIBUTING.md#2-spec-workflow-step-by-step).
Each feature also has a GitHub issue with its acceptance criteria; the issue links the spec and never copies it.

States: **Draft → Approved → In progress → Implemented → Superseded**. Sizes: **S** < 1 h · **M** 1–2 h · **L** 2–4 h.

## Index

| # | Feature | Owner | P | Size | Depends on | Status |
|---|---|---|---|---|---|---|
| 01 | Integration contract + stubs (folders, REST API, MCP contract, graph I/O, Postgres schema, customer receipt, eval hooks) | @salazarvalverdeai · approved by all three | P0 | M | — | Not started |
| 02 | Policy engine + regulatory clock | @salazarvalverdeai | P0 | M | contracts | Not started |
| 03 | MCP server with the 7 customer tools | @salazarvalverdeai | P0 | M | 01, 02 | Not started |
| 04 | Agent graph on LangGraph Platform (guardrails, receipt, handoff, returning customer) | @salazarvalverdeai | P0 | L | 02, 03 | Not started |
| 05 | Backend: API + Postgres + analyst login (Cognito) + customer session/OTP | @gianzk | P0 | L | 01 | Not started |
| 06 | Deploy + CI (Compose on EC2, GHCR, OIDC, SSM) | @gianzk | P0 | M | — | Not started |
| 07 | Customer chat `/chat` with verified receipt and trace | @gianzk | P0 | L | 16, 04, 05 | Not started |
| 08 | Analyst login + console `/login`, `/console` | @gianzk | P0 | L | 16, 05 | Not started |
| 09 | Demo and evaluation data (demo index, agent cases, classifier set) | @vldiego | P0 | M | gold | Not started |
| 10 | Evaluation harness (final state, pass^4, challenge metrics) | @vldiego | P0 | M | 01, 09 | Not started |
| 11 | Intent classifier + injection detector + selection protocol | @salazarvalverdeai | P0 | M | 09 | Not started |
| 12 | Insight pages content: `/evaluation` (P0), `/analytics`, `/data` | @vldiego | P0/P1 | M | 16, 10, 15 | Not started |
| 13 | `/case/{id}` + Telegram + email notifications | @gianzk | P0 | M | 05 | Not started |
| 14 | Operational lakehouse (bronze → silver → gold of case events; Databricks desirable) | @vldiego | P1 | M–L | 05 | Not started |
| 15 | Model benchmark (Haiku 4.5 vs Sonnet 4.6 vs Jev vs TF-IDF + LR vs rules; cost vs quality) | @salazarvalverdeai | P0 | M | 09, 11 | Not started |
| 16 | Web foundation + front-end standard (page shells, shared components, mock API client) | @gianzk | P0 | M | 01 | Not started |

Deliverables without a spec (tracked as issues with a checklist): **E1** pitch (slides, 3-minute video, landing
page) · **E2** submission package (README, secrets audit, `v1.0.0`, e-mail).

The existing data pipeline (`data/pipeline/`) predates this process and is not re-specified; its contract is
[`contracts/gold_contract.md`](../contracts/gold_contract.md).
