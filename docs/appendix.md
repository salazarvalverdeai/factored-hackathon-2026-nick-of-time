# Appendices: stack, contracts, numbers, open items

> **Historical (2026-09-28).** Kept for context. Current decisions live in [`docs/adr/`](adr/README.md), the work
> plan in [`specs/`](../specs/README.md) and GitHub issues, and how we work in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Stack and settled decisions (Monday 28)

| Question | Decision | Why |
| --- | --- | --- |
| Where the graph runs | LangGraph Platform (option A): deploy from `langgraph.json`, Studio, persistence, `interrupt()` | The team knows it; the dataset's data and keys are public, with no restriction on external services; declared in the README |
| Customer tools | MCP server (FastMCP) on the EC2 behind Caddy, API key or mTLS and allowlist; permissions by session `customer_id` inside each tool | A bank service behind a gateway |
| Analyst tools | API endpoints (`POST /api/cases/{id}/action`), run by the human from the console; the copilot only proposes | Separation of actors; every click is an audited event |
| Approval mode | Configurable per action in `policies.yaml`: `auto`, `human_required`, `manual_check`; global "supervised mode" switch in the console, audited | Safe automation and human control that can be switched on |
| Migration to B (all on EC2) | Documented, not executed for lack of time; switching A → B means replacing the MCP adapter with a direct import | Path to operation |
| LLM | Amazon Bedrock in `us-east-2`, via IAM role | Cost per token measurable per case |
| `fraud_score` | Tool `get_fraud_score(transaction_id)` with a swappable provider: `dataset` (the bank's), `rules`, `model`, `llm` (illustration only, forces the human zone); source and version in the audit | We consume the score from the bank's fraud engine; we don't build one |
| Backend | FastAPI in a container on EC2, GHCR, `docker compose` (Caddy + api + web), GitHub Actions with auto-deploy | App Runner doesn't read GHCR; Caddy handles HTTPS |
| Frontend | Next.js + Tailwind + shadcn/ui + next-themes; `/chat` starts from `agent-chat-ui` | Dark mode and ready-made components |
| Voice | Optional if time allows: ElevenLabs in `/chat` | Outside the minimum |
| Data | Bronze → silver → gold with pandera; gold Parquet with manifest; DuckDB in the container; pinned versions | 15 numbers reproduced; stable sha |
| State and audit | DynamoDB (SQLite in dev): `case_events` append-only, `llm_calls`, `policy_denials`; case status = last event | Each row is a node of the evidence graph |
| Observability | LangSmith in development + our own audit log as the source of truth | The challenge asks for records, not chain-of-thought |
| CI | Minimal `ci.yml`: tests, eval schema validation, build | Without CI the badges go red without anyone noticing |
| Out | AgentCore, Bedrock Agents, Lambda per tool, Neptune, Graph RAG, multi-agent, self-hosted LangGraph Server, our own fraud model | They don't score points |

## Contracts (in `contracts/` and `eval/`)

| Contract | What it fixes | What is non-negotiable |
| --- | --- | --- |
| `policies.yaml` | Deny by default; identity (TTL 15 min, OTP to write); scope per session; score provider; zones high ≥ 50, medium 30–49, human < 30 or null; amount threshold (1,000 and 5,000 USD, to be calibrated); approval mode per action and global switch; ticket always; provisional credit never `auto`; handoff triggers; clock per country with source; retries 2, timeout 800 ms; idempotency; actors and their tools | The LLM never reads or edits this file; the zone is computed only on `get_fraud_score()` |
| `tools.py` (customer) | `search_transaction`, `get_fraud_score`, `compute_deadline`, `block_card`, `open_case`, `get_product_status`, `get_case_status`; every tool receives `session_id` | `block_card` → `get_product_status == Blocked` before informing |
| Analyst API | `list_cases`, `get_case`, `approve_credit`, `approve_block`, `unblock_card`, `request_customer_info`, `mark_ambiguous`, `close_case`, `reopen_case`, `supervised_mode` | Only the human runs them; each one is an event with actor and reason |
| `handoff.schema.json` | Request, verified facts, actions with result and `verified`, evidence, open questions, copilot proposal, deadline with source, `trace_id` | Never the raw transcript |
| `eval_case.schema.json` | Id, language, type, team-generated origin, initial state, messages, expected (decision, zone, final state) | Final state, not text |
| `gold_contract.md` | Base tables (12 months: 2025-06-01 to 2026-05-31), derived tables, fixtures, `gold_eval/` and `gold_analytics/`; rules G1–G5 before publishing | `is_fraud` never in the tools' tables; gold read-only |

## Verified pitch numbers
The 15 numbers are reproduced with `python -m queries.run`; see `docs/eda/README.md` (number → query → CSV table) and `04_diego.md` (explanation in words). Three change wording: median duration instead of AHT; recall 48.8% on frauds with a score (38.7% of the total); 679 only as an average of 36.4%.

## Monday afternoon changes
- `policies.yaml`: `case_queue`, `notifications`, `guardrails` (15 with ID), `data_splits`; `block_card` in the high zone → `manual_check`; `close: human_only`.
- `tools.py`: `compute_deadline`, `notify_customer`, `AnalystActionIn/Out`, `Transaction.split`.
- `eval_case.schema.json`: `set`, `guardrail_ids`, `queue_status`, `notifications`. `handoff.schema.json`: `queue_status`, `notifications_sent`, `guardrails_triggered`.
- Repo `factored-hackathon-2026-nick-of-time`: `docs/README.md`, `docs/team/*.md`, `docs/appendix.md`, `docs/stack.md`, `docs/concepts.md`, `docs/differentiators.md`, `docs/assets/*.svg`, `contracts/`, `eval/`.

## Open items
- [ ] GitHub accounts for all four; push of the public repo (David) as soon as Freddy shares the final name.
- [ ] Confirm the deadline in Slack: Monday, October 5, 5:00 pm.
- [ ] Bedrock models enabled in `us-east-2`.
- [ ] LangGraph Platform plan and region verified.
- [ ] Databricks reads the S3 bucket or is dropped.
- [ ] Count matrix for the evaluation set (Freddy).
- [ ] `docs/decisions.md` with these decisions, dated.
- [ ] Amount thresholds calibrated with the snapshot.
- [ ] Approval mode defaults per action and per zone in `policies.yaml`.
- [ ] Pin versions in `requirements.txt` (DuckDB included).
- [ ] Decide the injection classifier (rules + LR recommended, or Llama Guard) and output grounding (exact comparison recommended, or LLM judge).
