# Closed stack and full-stack setup — W3 Nick of Time

> **Historical (2026-09-28).** Kept for context. Current decisions live in [`docs/adr/`](adr/README.md), the work
> plan in [`specs/`](../specs/README.md) and GitHub issues, and how we work in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

> Monday Sep 28, 2026. Decisions so we don't discuss them again. Label `[opinion]` where it is my own judgment.

---

## 1. Stack decisions (and why)

| Question | Decision | Why |
|---|---|---|
| Amplify + EC2 with GHCR? | **Yes, with a nuance:** backend on **EC2** with `docker compose` and images on **GHCR**; frontend on **Amplify** only if the team wants two deploys. **Recommendation `[opinion]`: deployment monolith on EC2** (Caddy + API + web in one `compose`) with Amplify as optional | App Runner does not read GHCR (only ECR), so EC2 is the natural fit with GHCR. The risk of splitting is HTTPS: Amplify serves on `https://`, and if the backend on EC2 is on `http://` the browser blocks the calls (mixed content). With Caddy on EC2 and a domain (yours or a free subdomain like DuckDNS) TLS is automatic and the front end can live on the same Caddy |
| LangGraph with Bedrock? | **Yes, now, not later.** It is the orchestrator | You already know it; its `StateGraph` is literally the state machine Understand → Identity → Retrieve → Decide → Act → Verify → Escalate; `get_graph().draw_mermaid()` draws the agent's real graph for the UI and the slides (that is the honest "wow": it is the code, not a drawing); per-session checkpoints; `ChatBedrock` from `langchain-aws` connects without leaving the account. A single graph, no multi-agent |
| Observability? | **LangSmith for development + our audit log as the source of truth** | LangSmith turns on with two environment variables and shows every node, tool and tokens. But it is SaaS outside AWS: the demo texts (synthetic) travel there; this is declared. The evidence graph and point 6 of the challenge come from **our** audit table (DynamoDB or SQLite), not from LangSmith. If Slack forbids external SaaS, LangSmith is turned off and what remains is our own log + OpenTelemetry to CloudWatch |
| Where do the tools live? | **In the same container as the backend**, as Python functions decorated with `@tool` that read DuckDB and write DynamoDB | Lambda adds one more deploy, cold starts and credentials; it earns no points. On the path-to-operations slide we say: "in production each tool would be a bank service behind a gateway" |
| Astro or Next? | **Next.js (App Router) + Tailwind + shadcn/ui + next-themes.** Decided | Astro does not run Next; it runs React islands. Plain Next is simpler for an app with two stateful views and streaming |
| Where does the graph run? | **Option A primary: LangGraph Platform** (deploy from `langgraph.json`, Studio, persistence, `interrupt()` for the human) with the tools as an **MCP server on the EC2** (FastMCP behind Caddy, API key or mTLS, IP allowlist). **Option B (everything on EC2)** stays documented as a migration: the graph imports nothing platform-specific and the tools are the same functions; switching A → B means replacing the MCP adapter with a direct import. For lack of time B is not executed; it is explained in the README and on the path-to-operations slide | The team knows the platform; less infrastructure to maintain in 8 days. Conditions: ask on Slack today whether the synthetic text may leave AWS and declare it in the README; `langgraph dev` locally for debugging; the harness runs against the deploy URL. If Slack forbids it, B becomes primary without touching the graph |
| How is the `fraud_score` obtained? | **As a tool with a swappable provider**: `get_fraud_score(transaction_id)` → `{score, source, version}`. Providers: `dataset` (reads the gold column for the demo's preset transactions; the starting one), `rules` (simple heuristic: amount vs usual, channel, hour, country), `model` (plan B trained against `is_fraud`), `llm` (only to illustrate; never decides a block). The active provider is set in `policies.yaml` and the source is recorded in the audit log and on the handoff card ("score 72 · source: dataset v1") | It mirrors reality: the bank's fraud engine is a service the system consumes. If Slack says the score does not exist in real time, the provider switches to `model` without touching the graph or the policies |
| State logic in the web app? | **No.** Every case transition goes through `POST /api/cases/{id}/action`, validated against `policies.yaml` and written to the audit log | Permissions outside the client; every transition with a trace. The web app only holds interface state |
| Databricks for the pipeline? | **Allowed under three conditions**, otherwise local DuckDB | (1) a workspace without a cost block that reads the `us-east-2` S3 bucket today; (2) gold materialized as Parquet in our bucket, which the API reads with DuckDB; (3) notebooks exported to `.py` in the repo + a local fallback script so the judges can reproduce without Databricks |
| Front + back monolith? | **Yes in deployment, no in code.** Two folders (`apps/web`, `apps/api`), three containers (caddy, api, web) in one `compose` on the same EC2 | They evaluate "backend, frontend and deploy" and "reproducible setup", not service separation. One `docker compose up` that brings everything up is more defensible than five services |
| AgentCore or Bedrock Agents? | **Not for building.** Mentioned in the path to production | Bedrock Agents defines the orchestration in the console: hard to evaluate with pass^4 and to show "policy outside the model". AgentCore Policy (Cedar) is exactly our policy engine, but it is in preview and adds a learning curve; our `policies.yaml` + evaluator does the same and we control it. The path slide: "the YAML evaluator would be replaced by AgentCore Policy and the tools would go to the Gateway" |
| Analytics dashboard? | **Yes, as a page of the app**, not as a separate product | The kickoff says it is not mandatory, but there is a Data Analytics criterion. A page with Recharts that reads precomputed CSVs from the gold layer costs half a day and shows the problem and the results |
| Model on Bedrock? | Whichever they have enabled in `us-east-2`; a good one for understanding and writing, a cheap one for fallback zero-shot classification | Request enablement today: it takes hours |

---

## 2. What the platform is (app pages)

| Route | For whom | What it shows | Owner |
|---|---|---|---|
| `/` | everyone | Landing page: what it is, architecture (SVG), links to the views, deploy status | Full stack |
| `/chat` | customer | ES/PT chat with language toggle, side panel with the case trace live | Full stack |
| `/console` | analyst | Inbox of escalated cases; detail with handoff card, evidence graph, trace, buttons approve credit / request info / close | Full stack |
| `/data` | judges | Pipeline (bronze → silver → gold), quality report with counts, snapshot manifest, updates fixture | Data 1 (content), Full stack (page) |
| `/evaluation` | judges | Held-out results table by scenario × language × segment with n, pass^4, latency, cost; error analysis | Freddy (content), Full stack (page) |
| `/analytics` | judges | Dashboard: problem in numbers, score zones, deadlines by country, business case with labels | Data 2 (content), Full stack (page) |
| `/agent` | judges | The real LangGraph graph (`draw_mermaid`), rendered `policies.yaml`, tool contracts | Freddy (content), Full stack (page) |

It is not a chat: it is seven pages on one backend. The chat and the console are the ones demonstrated in the video; the other four are the ones the judges open afterwards.

---

## 3. Repo structure

```
factored-hackathon-2026-nick-of-time/
├── README.md                 # one-command setup, architecture, what is real and what is mock
├── problem.md
├── docker-compose.yml        # caddy + api + web
├── Caddyfile                 # automatic TLS, /api/* → api:8000, /* → web:3000
├── .github/workflows/
│   ├── ci.yml                # tests + schema validation + build
│   └── deploy.yml            # build → push GHCR → ssh EC2 → compose pull && up
├── apps/
│   ├── api/                  # FastAPI + LangGraph + tools + policies (Python package nick_of_time)
│   │   ├── graph/            # StateGraph nodes
│   │   ├── tools/            # search_transaction, block_card, open_case, get_*_status
│   │   ├── policy/           # policies.yaml evaluator + regulatory clock
│   │   ├── audit/            # audit log (DynamoDB / SQLite) → evidence graph
│   │   └── classifier/       # rules, embeddings+LR, jev (optional)
│   └── web/                  # Next.js + shadcn (7 pages)
├── contracts/                # policies.yaml, tools.py, handoff.schema.json
├── data/
│   ├── pipeline/             # bronze→silver→gold, checks, manifest, fixture
│   └── gold/                 # versioned parquet (or .gitignore + download from S3)
├── eval/                     # eval_case.schema.json, .jsonl cases, harness, results
├── docs/eda/                 # case files, queries, output CSVs
└── infra/                    # EC2 user-data, minimal IAM, example environment variables
```

---

## 4. Auto-deploy (the most important "hello world")

`deploy.yml` on every push to `main`:
1. `docker build` of `apps/api` and `apps/web` → push to `ghcr.io/<org>/nickoftime-api:sha` and `-web:sha`.
2. `ssh` to the EC2 (key in GitHub Secrets) → `docker compose pull && docker compose up -d`.
3. Smoke test: `curl https://<domain>/api/health` and `/` return 200; if not, the job fails and alerts.

EC2: `t3.medium` (DuckDB with 5M transactions fits in memory if the gold layer is filtered Parquet; if not, `t3.large`), IAM role with read access to the dataset's S3, `bedrock:InvokeModel`, DynamoDB and CloudWatch Logs. Ports 80/443 open, 22 only from the team's IP.

---

## 5. Full-stack tasks with acceptance criteria (today and tomorrow)

Strict order: each hello world is built, deployed and seen on the public URL before moving on to the next.

| # | Task | Acceptance criterion (met or not) | Estimate |
|---|---|---|---|
| 1 | Repo `factored-hackathon-2026-nick-of-time` with the structure from section 3, `.gitignore` (`.env`, `data/gold`, `node_modules`), `README` with placeholders | The repo exists, is public, and `git log -p \| grep -i -E "AKIA\|secret"` returns nothing | 30 min |
| 2 | EC2 + domain + Caddy | `https://<domain>/` responds with valid TLS (padlock) and `https://<domain>/api/health` returns `{"status":"ok","version":"<sha>"}` | 1.5 h |
| 3 | `apps/api` FastAPI hello world in a container | `/api/health` comes from the `ghcr.io/.../nickoftime-api` image, not from the host | 45 min |
| 4 | `apps/web` Next.js + shadcn + next-themes hello world | The landing page loads in dark by default, the toggle switches to light, and it looks good on a phone (DevTools 390px) | 1 h |
| 5 | Complete `deploy.yml` | A push to `main` that changes the landing page text shows on the URL in under 10 min without touching the EC2 | 1 h |
| 6 | Bedrock hello world from the container | `POST /api/llm/ping` returns a sentence generated by the model using the IAM role (no keys in the container) | 45 min |
| 7 | LangGraph hello world | A `StateGraph` with nodes `understand → decide → respond` runs on `/api/chat`, and `/api/agent/graph` returns the Mermaid from `get_graph()` that the `/agent` page renders | 1.5 h |
| 8 | DuckDB + S3 hello world | `/api/tools/ping` reads a Parquet from the bucket (or from the local gold) and returns `count(*)` of `transactions` | 45 min |
| 9 | DynamoDB (or SQLite in dev) hello world | `/api/audit/ping` writes and reads a row `{trace_id, step, tool, result, ts}`; `docker compose` brings up the same code with SQLite if there is no AWS | 45 min |
| 10 | LangSmith + audit log | A call to `/api/chat` shows up as a trace in LangSmith **and** as rows in the audit table with the same `trace_id` | 30 min |
| 11 | Mock identity | `POST /api/session` with `customer_id` → simulated OTP (always `000000` in the demo) → session with TTL 15 min; `/api/tools/*` without a session returns `401` and with an expired session `SESSION_EXPIRED` | 1 h |
| 12 | Tools per `contracts/tools.py` over the gold layer | `search_transaction` with the session of C-48213 never returns another customer's transactions (test); `block_card` twice with the same `idempotency_key` does not duplicate; `get_product_status` reflects the block | 3 h |
| 13 | Real `/chat` page | Sends a message, receives a streaming response, the side panel lists the graph steps with timings | 3 h |
| 14 | `/console` page | Lists cases with `zone = human`; opens one and renders `handoff.schema.json`; the "approve credit" button changes the case status and is recorded in the audit log | 4 h |
| 15 | `/data`, `/evaluation`, `/analytics`, `/agent` pages | Each one renders the content its owner delivers from files in `data/gold`, `eval/results` and `docs/` (JSON/CSV), with no business code in the front end | 1 day (Friday) |

Tasks 1–5 today. 6–10 tomorrow, Tuesday morning. 11–12 Tuesday afternoon. 13 Wednesday (along with the end-to-end case). 14 Thursday. 15 Friday.

---

## 6. Initial front-end conditions (so we don't redo it)

- Dark by default (`next-themes`, `class` strategy), toggle in the header, color tokens in `globals.css`.
- Responsive: full-screen chat on mobile; three-column console (inbox · case · evidence) that turns into tabs at < 1024px.
- Fixed semantic colors: high zone `emerald`, medium `amber`, human `rose`; DENY in red with `policy_id`.
- IDs in monospace; "accepted" and "verified ✓" are different states and look different.
- ES/PT toggle that changes the language of the UI and of the case; UI texts in one JSON per language.
- Mandatory states in every view: loading, error, empty, DENY, expired session.
- Visual references: Intercom inbox (console), Linear (density and dark), Langfuse trace viewer (trace panel).

---

## 7. Tasks for the other three with acceptance criteria

### Freddy (agent, policies, ML, harness)
| # | Task | Acceptance criterion | When |
|---|---|---|---|
| F1 | `policies.yaml` evaluator (`apps/api/policy`) | `evaluate(score, amount, country, product, session)` returns `zone`, `allowed_actions`, `deadlines` with dates in business days and `policy_ids`; tests: 5 zones/thresholds × 4 countries pass; `score=None` → human | Mon–Tue |
| F2 | Regulatory clock | For an MX debit or credit claim filed within 90 calendar days of the charge it returns `credit_deadline = +2 business days` and `ruling_deadline = +45 days` (ADR 0023); AR `+10 business days`; CO `+15`; BR `+10 business days`; holidays as a list in YAML (fixture, labeled) | Tue |
| F3 | LangGraph graph v0 | `StateGraph` with typed state (`session`, `language`, `intent`, `slots`, `candidates`, `zone`, `actions`, `verifications`, `handoff`); nodes understand → identity → retrieve → decide → act → verify → escalate/respond; `langgraph dev` opens it in Studio; EV-0001 reaches `Blocked` + case + deadline | Tue–Wed |
| F4 | Jev test | 40 ES + 40 PT labeled sentences; Jev vs rules: if it does not beat rules on PT or access fails, it is closed with a note in `docs/decisions.md` | Wed |
| F5 | Intent classifier | Keyword rules; embeddings + calibrated logistic regression (split by template, τ on validation); macro-F1 table by language, ECE and coverage at 95% accuracy; the `understand` node uses the best one and abstains below τ | Thu |
| F6 | Harness | Runs `eval/*.jsonl`, compares final state against `expected`, pass^4, latency p50/p95, tokens and cost per case, by language × type × segment with n; output in `eval/results/*.csv`, which `/evaluation` reads | Fri–Sat |
| F7 | Zone calibration | Precision/recall curve of `fraud_score` against `is_fraud` on a temporal + per-customer held-out with CI; features + score vs score alone; honest conclusion in `docs/ml.md` | Sat |
| F8 | Daily integration | From Wednesday on, one end-to-end case per day on the public URL; scope lock on Thursday if it does not run | Daily |

### Data A (pipeline, quality, repo presentation)
| # | Task | Acceptance criterion | When |
|---|---|---|---|
| A1 | Decide Databricks or DuckDB | Today: a notebook or script reads `transactions` from the `us-east-2` S3 bucket; otherwise, local DuckDB, no discussion | Mon |
| A2 | Bronze → silver with contracts | Schema contracts (pandera or Pydantic) for customers, products, transactions, complaints, surveys; checks with counts: duplicates, nulls, FK to another customer's product, future dates, transaction before account opening, `México`/`Mexico`; `data/quality_report.md` generated, not written by hand | Tue |
| A3 | Gold Parquet + manifest | `data/gold/*.parquet` (or on S3) with `manifest.json`: version, date, rows per table, hash; the API reads it with DuckDB; `make setup` reproduces it from scratch in < 15 min | Tue–Wed |
| A4 | Updates fixture | Folder `data/fixtures/late_arrival/` with late partitions and a schema change, labeled; the pipeline processes it and the report shows what changed; `missing_data` and `late_arrival` cases in `eval/` | Thu |
| A5 | `docs/eda` organized | W1–W4 case files, `findings.md`, `data_quality.md`, `queries/` with their output CSV; an index that says which file backs each pitch number | Wed |
| A6 | `/data` page (content) | JSON/MD that the front end renders: pipeline diagram, table of checks with counts, manifest, fixture | Fri |
| A7 | README and reproducibility | `git clone` + `.env.example` + `docker compose up` brings everything up with SQLite and local gold; "what is real, what is mock, what is synthetic" section; review of secrets in the history | Sun |

### Data B (analytics, business, evaluation set)
| # | Task | Acceptance criterion | When |
|---|---|---|---|
| B1 | Frozen pitch queries | `queries/` with SQL and output CSV for: 36.4% (rules CMP-01/02/03 with confidence), FCR and follow-up by reason, AHT, NPS/CSAT, 16 days, 120 frauds/month, precision/recall by score threshold; every number in the deck points to a file | Mon–Tue |
| B2 | Deadlines and business case | `docs/business.md`: table of deadlines by country with link; savings formula with labeled assumptions; time and quality outcomes with baseline; measured / simulated / projected separation | Tue |
| B3 | ES/PT evaluation set | 200–300 cases in `eval/cases.jsonl` valid against `eval_case.schema.json`; minimum coverage per cell language × type (normal, ambiguous, human, injection, session_expired, unauthorized, tool_failure, missing_data) × country; Freddy defines the count matrix on Monday | Tue–Thu |
| B4 | Double labeling | A second person labels 40 random cases; agreement reported (% and kappa); disagreements resolved and documented | Thu |
| B5 | View specification | One page per view (chat, console) with fields, states and actions, so the full stack builds without guessing | Tue |
| B6 | `/analytics` dashboard | Power BI published to the web and embedded, or CSV + Recharts; reads only `queries/*.csv`; shows problem, zones, deadlines, business case with labels | Thu–Fri |
| B7 | Results table | With the harness output: by scenario × language × segment with n; text for the results slide and for the README | Sat |
