# factored-hackathon-2026-nick-of-time

Factored AI & Data Hackathon 2026, team Nick of Time. Synthetic LATAM Bank dataset (MX, CO, AR; Jun 2023 – Jun 2026).

Regulatory-clock **card dispute intake**: the customer reports an unrecognized or wrongful charge in Spanish or
Portuguese; the system identifies their own transaction, decides by rules, blocks the card and opens a case with
verification, computes the country's legal deadline, gives the customer a verified receipt and the analyst a handoff
card with evidence. A person always closes the case.

![Architecture, option A](docs/assets/architecture_option_a.svg)

## Try it (jury)
**Live:** https://nickoftime.salazarvalverdeai.com. It is a public demo on the hackathon's synthetic data. The demo
date is frozen at **1 June 2026** (the dataset ends on 31 May 2026; ADR 0020).

1. **Customer, `/chat`.**
   - Pick a scenario and a language (ES or PT), optionally type your name, and enter the one-time code shown on screen.
   - Write *"No reconozco un cargo en mi tarjeta"*, or tap a suggestion. The agent finds the customer's own
     transaction, states its plan, shows each step live, opens the case, verifies it and gives a receipt with the
     country's legal deadline and its source.
   - Also try: a vague message (it shows the recent charges to pick from), Portuguese, an urgent or upset message (it
     acknowledges the tone), *"Muéstrame la cuenta de otro cliente"* or a prompt injection (the rules refuse), the
     microphone, read-aloud, and "Ver cómo trabaja" (the live agent graph).
2. **Notifications.** On the case page ("Ver mi caso"), link your e-mail (confirmation link) or Telegram (our bot).
   Each status change of your case reaches them. A demo visitor's channels reach only their own case (ADR 0026).
3. **Analyst, `/login` → `/console`.**
   - Sign in with the jury account sent in the submission e-mail.
   - Each case shows the handoff card with verified facts and evidence, the agent's summary, the customer's history and
     conversation, an AI second opinion and the deterministic rule audit (both advisory), and the actions (take,
     approve, resolve, close). Every action is audited. A person always closes the case.
4. **Results:** `/evaluation` (sealed results), `/analytics` (the problem in numbers), `/data` (the pipeline) and
   `/agent` (architecture, graph, policies, tools, guardrails, models).

### Results (every figure labeled; protocol sealed before any test score, `protocol-v1`)
| What | Result | Source |
|---|---|---|
| The problem | First-contact resolution of complaint contacts 43.6% vs 76.6% for the whole bank; 63.0% need follow-up; 117,021 complaint contacts `[data]` | [`queries/pitch/`](queries/pitch/), [`docs/problem_in_numbers.md`](docs/problem_in_numbers.md) |
| Agent safety (held-out: 80 sealed cases × 4 runs, arms S0/S1/S2) | **0 unsafe outcomes of 320 runs in every arm** `[simulated]` | [`eval/results/2026-10-06-heldout/summary.csv`](eval/results/2026-10-06-heldout/summary.csv) |
| Safe automated resolution | Official (sealed) 0 of 20; secondary under D-070, 16 of 20 = 80% (95% CI 58–92%). The cases were sealed before the decision that a verified block still hands the case to a person; both scores come from the same runs and are reported side by side (ADR 0031) `[simulated]` | same, [ADR 0031](docs/adr/0031-heldout-scored-under-sealed-rules-and-d070.md) |
| Intent classifier (sealed test split) | TF-IDF + LR macro-F1 0.92 / 0.91 (ES/PT); LLM 0.93 / 0.91. Neither meets the pre-registered floors (Spanish person-request recall 0.87 < 0.95), so the rules (B0) stay `[simulated]` | [`eval/results/classifier.csv`](eval/results/classifier.csv) |
| Model benchmark (24 Bedrock arms × 236 test sentences, 2.52 USD) | Sonnet 4.6 accuracy 0.979; Mistral Large 3 0.975 at 0.31 USD per 1k messages; Haiku 4.5 0.924. Every arm misses only the Spanish person-request floor (best 0.913), so the lean rule keeps B0 `[simulated]` | [`eval/results/bench_b1.md`](eval/results/bench_b1.md), [ADR 0027](docs/adr/0027-model-selection.md) |
| Fraud model (test window) | The bank's score: PR-AUC 0.566 (95% CI 0.500–0.633). Learned models stay at the base rate (≈0.0009), so the bank's score stays `[data]` | [`eval/results/fraud-test/`](eval/results/fraud-test/) |

**How it is built.**
- The LLM understands, the rules decide (`contracts/policies.yaml`, `default: deny`), the tools act (FastMCP),
  verification confirms, and a person closes.
- The agent is a LangGraph graph on LangGraph Platform. Claude Haiku 4.5 classifies; Sonnet 4.6 can word replies,
  with every line grounded in tool facts (ADR 0030).
- FastAPI and Postgres keep the case state and audit; Next.js and AI Elements serve the web.
- Everything runs in AWS `us-east-2`; voice uses Voxtral on Bedrock (ADR 0029).


## Start here
| Document | What it is |
|---|---|
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How we work: spec workflow, EARS acceptance criteria, ADRs, branches, commits, approvals, releases |
| [`CLAUDE.md`](CLAUDE.md) | Durable context for AI coding agents: stack, constraints, business rules, layout and owners |
| [`STATUS.md`](STATUS.md) | What is deployed and verified, test results, what is missing |
| [`specs/`](specs/) | One spec per feature, with its owner, priority and status |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records (31) |
| [`docs/infrastructure.md`](docs/infrastructure.md) | AWS, domains, Platform and where each credential lives (no secrets) |
| [`CHANGELOG.md`](CHANGELOG.md) | Releases |
| [`problem.md`](problem.md) | The W3 problem definition and the numbers behind it |

## Contracts and data
| Path | Contents |
|---|---|
| [`contracts/policies.yaml`](contracts/policies.yaml) | Policy engine outside the model (`default: deny`): zones, approval modes, regulatory clock, queue, notifications, guardrails |
| [`contracts/tools.py`](contracts/tools.py) | Typed tool contracts (Pydantic); every tool resolves `customer_id` from the session |
| [`contracts/handoff.schema.json`](contracts/handoff.schema.json) | What the analyst receives: verified facts, actions, evidence, deadline |
| [`eval/eval_case.schema.json`](eval/eval_case.schema.json) | Held-out evaluation case; the harness compares final state, not text |
| [`contracts/gold_contract.md`](contracts/gold_contract.md) | Gold contract enforced by `data/pipeline/gold.py` (rules G1–G5) |
| [`data/pipeline/`](data/pipeline/) | Bronze → silver → gold pipeline on DuckDB with pandera contracts |
| [`data/quality_report.md`](data/quality_report.md) | Quality report generated by the pipeline |
| [`docs/eda/`](docs/eda/) · [`queries/`](queries/) | EDA records and the queries behind every pitch number |
| [`docs/assets/`](docs/assets/) | Architecture and flow diagrams |

## How to reproduce
```bash
aws configure --profile factored-dataset   # dataset keys (Factored data dictionary, p. 2); read-only
cp .env.example .env       # no secrets: profile names, region and buckets
make setup                 # venv + dependencies + pipeline from S3 + fixture + data/quality_report.md
make test                  # pytest, offline
make hooks                 # gitleaks pre-commit hook: blocks commits that contain secrets
```
`make setup SOURCE=local` runs on a local mirror already downloaded to `data/<table>/` (offline). Credentials live
only in `~/.aws/credentials` profiles (`factored-dataset` for the dataset, `nickoftime` for the team account); `.env`
holds no secrets and is not committed to git either. An older `.env` with `AWS_ACCESS_KEY_ID`/`S3_BUCKET` still works.
