# Architecture (DRAFT for the lead's review)

Status: **draft**, refreshed 2026-10-05 against `origin/main` at `5636caa`. Nothing here replaces a current document; the
lead decides what moves to `docs/`. Every claim names the file it comes from. Where a figure appears it carries a label
from CLAUDE.md rule 8 (`[data]` `[external]` `[assumption]` `[simulated]` `[projected]`). Legend used in every diagram:
**solid = current** (in `main`), **dashed = future (P2) or not yet verified on the public URL**.

## 1. Services and where they run

Sources: `infra/compose.yml`, `infra/caddy/Caddyfile`, `.github/workflows/deploy.yml`, `docs/infrastructure.md`,
`langgraph.json`, `apps/api/README.md`, ADRs 0008, 0009, 0010, 0011, 0017.

```mermaid
flowchart LR
  user([Customer or analyst<br/>browser]):::ext
  tg([Telegram]):::ext
  mail([Resend e-mail]):::ext

  subgraph ec2["EC2 nickoftime-app, us-east-2 · Docker Compose"]
    caddy["Caddy 2<br/>TLS, two hosts, only 80/443 published"]
    web["web<br/>Next.js 16 + shadcn/ui :3000"]
    api["api<br/>FastAPI :8000<br/>abuse guard, daily LLM cap,<br/>GoldCatalog, demo sessions"]
    mcp["mcp<br/>FastMCP server :8001<br/>16 customer tools"]
    pg[("Postgres 17<br/>cases, append-only events, audit")]
    gold[/"gold Parquet v1<br/>read-only mount"/]
  end

  platform["LangGraph Platform (LangSmith)<br/>graph dispute_intake"]
  bedrock["Amazon Bedrock us-east-2<br/>Sonnet 4.6 · Haiku 4.5"]
  anth["Anthropic API<br/>fallback"]
  uptime["GitHub Actions uptime.yml<br/>every 15 minutes"]
  stt["Bedrock Mistral Voxtral us-east-2<br/>speech to text (in progress)"]
  cognito["Cognito pool<br/>nickoftime-analysts"]
  s3[("S3 nickoftime-gold<br/>gold/v1 · backups · labels/v1 protected")]
  ssm["SSM Parameter Store<br/>/nickoftime/prod/*"]

  user -->|"nickoftime... host"| caddy
  user -->|"mcp... host, API key"| caddy
  caddy -->|"/api/*"| api
  caddy -->|"everything else"| web
  caddy -->|"mcp host"| mcp
  web -.->|"same origin /api"| api
  api --> pg
  api --> gold
  api -->|"thread + run proxy"| platform
  api --> cognito
  api --> tg
  api --> mail
  platform -->|"MCP over HTTPS, key"| caddy
  platform --> bedrock
  platform -.-> anth
  uptime -->|"health checks"| caddy
  uptime -.->|"alert on healthy to failing"| tg
  api -.->|"POST /api/voice/transcribe"| stt
  mcp --> pg
  mcp --> gold
  s3 -.->|"deploy syncs gold to host"| gold
  ssm -.->|"deploy.sh reads secrets"| ec2

  classDef ext fill:#eee,stroke:#888,color:#222
```

Notes, each from its source:
- Only Caddy publishes ports; `web`, `api`, `mcp` and `postgres` are internal (`infra/compose.yml`, header comment).
- Caddy serves `nickoftime.salazarvalverdeai.com` (`/api/*` to `api:8000`, rest to `web:3000`, same origin so no CORS)
  and `mcp.nickoftime.salazarvalverdeai.com` (to `mcp:8001`) (`infra/caddy/Caddyfile`).
- `api` and `mcp` mount gold read-only at `/gold/v1` and share the Postgres `DATABASE_URL` (`infra/compose.yml`,
  spec 06 FR-09).
- The graph is `dispute_intake` in `apps/agent/agent/intake.py`, registered for Platform in `langgraph.json`; the api
  proxies threads and runs and keeps the Platform key server-side (`apps/api/README.md`, `apps/api/app/platform.py`).
  Platform reaches the MCP server at its public host, with an API key (ADR 0008; `docs/infrastructure.md`).
- Models: Bedrock `us-east-2`, `us.anthropic.claude-sonnet-4-6` for the graph and `...haiku-4-5...` for the fast path,
  as reported by `GET /api/health` on the public URL on 2026-10-05; Anthropic API is the fallback (ADR 0009).
- Analysts sign in with Cognito (admin-created users only); customers use a mock session and OTP (ADR 0017,
  `docs/infrastructure.md`).
- Gold lives in S3 `gold/v1/`; labels (`is_fraud`) sit apart in `labels/v1/` behind a deny-by-default policy and are not
  readable by the EC2 role, Platform or the deploy role (`docs/infrastructure.md`, CLAUDE.md rule 7).
- Verification state: `GET /api/health` on the public URL answered `git_sha` `4ca799a...`, contract `1.4.0`, policies
  version 2 (a point-in-time reading earlier on 2026-10-05; `main` is now contract `1.7.0`, `packages/nick_of_time/__init__.py`), `platform_revision: null` (2026-10-05). The Platform link is drawn solid because the api code and graph are
  in `main`; the null revision means the lead should confirm the deployed revision before this goes in a final doc.

## 2. Deploy path

Sources: `.github/workflows/deploy.yml` (header and jobs), `.github/workflows/ci.yml`, `infra/deploy.sh`,
`docs/infrastructure.md`, ADR 0011, PR #136.

```mermaid
flowchart LR
  dev["Merge to main"] --> ci["CI workflow<br/>pytest incl. Postgres suite, ruff, AC coverage,<br/>web lint + build, gitleaks"]
  ci -->|"workflow_run completed,<br/>conclusion = success, event = push"| build
  ci -.->|"red CI: nothing deploys"| stop(["stop"])
  subgraph gha["Deploy workflow"]
    build["build matrix: web, api, mcp<br/>tag = CI-tested SHA"] --> ghcr[("GHCR images")]
    ghcr --> oidc["assume role nickoftime-gha-deploy<br/>GitHub OIDC, no AWS keys"]
    oidc --> ssm["SSM Run Command on nickoftime-app"]
  end
  ssm --> script["infra/deploy.sh SHA<br/>pull first, apply schema, up, reload Caddy"]
  script --> health{"/api/health reports<br/>the deployed SHA?"}
  health -->|yes| live(["live"])
  health -->|no| rollback["restore last good version,<br/>workflow fails"]
  manual["workflow_dispatch<br/>lead's explicit override"] -.-> build
```

- Deploy starts only from a completed CI run of a push to `main` with conclusion `success` (`deploy.yml`, `if:` on the
  build job; PR #136). `workflow_dispatch` is the lead's explicit override.
- One concurrency group, never cancelled half-way (`deploy.yml`, `concurrency`).
- `schema.sql` is idempotent and applied on every deploy (PR #129); gold is synced to the host (PR #119).

## 3. Business flow of a dispute

Sources: `apps/agent/agent/intake.py` (graph wiring, lines 778-800), specs 01, 02, 03, 04, 05, 08, 13, `CLAUDE.md`
(constitution and business rules), `contracts/policies.yaml` via spec 02.

Principle (CLAUDE.md rule 1): the LLM understands, the rules decide, the tools act, verification confirms, a person
closes.

```mermaid
flowchart TD
  c([Customer in /chat<br/>mock session + OTP]) -->|"message in ES/PT"| api["api: session cookie<br/>customer_id from session only"]
  api --> thr["LangGraph Platform thread + run"]

  subgraph graph["Graph dispute_intake (apps/agent/agent/intake.py)"]
    identity --> greet --> understand --> route
    route -->|"injection / out of scope"| refuse
    route -->|"asks for a person"| connect
    route -->|"status question"| status
    route -->|"dispute"| retrieve
    retrieve -->|"read failed"| respond
    retrieve --> decide
    decide -->|"missing data"| clarify
    decide -->|"deny"| refuse
    decide -->|"duplicate case"| duplicate
    decide -->|"human zone"| connect
    decide -->|"allow or confirm"| plan
    plan -->|"confirm first"| respond
    plan --> act --> verify
    verify -->|"session expired"| respond
    verify -->|"high zone, call requested"| connect
    verify --> respond
    refuse --> respond
    connect --> respond
    clarify --> respond
    status --> respond
    duplicate --> respond
  end

  thr --> identity
  understand -.->|"S1/S2 LLM, S0 rules fallback"| llm["Bedrock"]
  retrieve -->|"tools"| mcp["MCP server: search, profile,<br/>fraud score, convert, deadline"]
  decide -->|"policy engine<br/>contracts/policies.yaml, default deny"| pol["decision + rule id"]
  act -->|"open_case, block_card<br/>idempotent"| mcp
  verify -->|"get_product_status<br/>post-condition"| mcp
  mcp --> store[("Postgres store<br/>append-only case_events")]
  respond --> receipt["Verified receipt (customer)<br/>handoff card (analyst)<br/>only tool-returned facts"]
  receipt --> notify["Notifications: in-app log,<br/>Telegram, e-mail"]
  receipt --> c
  store --> console["Analyst console /console<br/>queue, handoff, auditor, judge opinion"]
  console --> person(["Analyst decides:<br/>provisional credit, resolve, close"])
  person -->|"status change"| store
  store --> notify
```

How each stage maps to the repo:

| Stage | What happens | Source |
|---|---|---|
| Session | Customer picks a demo customer and verifies a mock OTP; `customer_id` comes only from the session | ADR 0017; `apps/api/app/main.py` (`/api/sessions`, `/verify`); CLAUDE.md rule 3 |
| greet / understand / route | Greeting with capabilities; intent and injection detection (S0 rules, S1/S2 LLM with budget and rules fallback); branch | spec 04; PRs #88, #133 |
| retrieve | Read-only tools find the customer's own transactions, profile, fraud score (optional input), currency conversion | spec 03; PRs #106, #120 |
| decide | The policy engine returns a decision and rule id by zone, country, mode and tier; the LLM never reads `policies.yaml` | spec 02; ADR 0005; PR #63 |
| plan / act | State the plan, then `open_case` and `block_card` with idempotency keys. High zone blocks unless the customer asked for a person (the analyst decides after the call, D-029) | specs 02 and 03; ADR 0024; PRs #80, #123 |
| verify | Re-read the product status; an action is reported only after its post-condition holds (`accepted` is not `verified`) | CLAUDE.md rule 4; spec 04; PR #109 |
| respond | Reply, receipt, handoff card, grounding check (exact match to tool results), 2-3 suggestion chips | CLAUDE.md rule 5; ADR 0016; PR #109 |
| Regulatory clock | `compute_deadline` returns the country's legal deadline with `source_url` from the data table in `policies.yaml`; unknown country returns `POL-CLOCK-UNKNOWN` | spec 02 section 4.3; ADR 0019; PRs #67, #120 |
| Case queue | `new -> verification or review -> resolved -> closed`, status is the last appended event | spec 02 (`transition`, `sla`); spec 05 AC-02; PR #86 |
| Analyst console | Inbox, handoff card, timeline, actions through `policy.transition`, auditor findings, judge second opinion (advisory) | specs 05, 08, 18; ADR 0021 |
| Person closes | No case is closed without a person; provisional credit is always a human decision | CLAUDE.md rule 6 |
| Notifications | Every status change reaches in-app log, Telegram and e-mail; never score, policy ids or transcript | spec 13; CLAUDE.md |

## 3b. Demo sessions and public hardening (current in `main`)

Sources: spec 05 AC-14 to AC-19 and tasks 8-10, ADR 0026, `apps/api/app/guard.py`, `apps/api/app/catalog.py`,
`packages/nick_of_time/llm/steps.py`, `apps/api/app/live.py`, spec 04 AC-17, `.github/workflows/uptime.yml`.

```mermaid
flowchart TD
  v([Public visitor]) --> guard["Abuse guard (guard.py)<br/>per-IP and global hourly limits on sessions and turns,<br/>429 with a bilingual message"]
  guard --> sess["POST /api/sessions<br/>name, language, scenario<br/>server picks the customer"]
  sess --> cat["GoldCatalog<br/>read-only gold + demo customers of spec 09"]
  sess --> run["run_id demo-...<br/>isolated like an eval run (ADR 0026),<br/>no Telegram or e-mail channel"]
  run --> turn["Agent turn via Platform proxy"]
  turn -->|"Platform down"| calm["Calm retry turn in ES/PT"]
  turn --> llm{"Daily LLM cap reached?<br/>llm_spend_since, DAILY_LLM_CAP_USD"}
  llm -->|yes| s0["S0 rules fallback"]
  llm -->|no| s12["S1/S2 understand"]
  turn --> prog["Progress stream:<br/>one customer label per step"]
  sess --> typec["Demo type C: synthetic-charge<br/>row in demo_transactions for this run"]
  typec --> turn
```

- Limits: 10 sessions and 60 agent requests per IP per rolling hour, 300 and 1500 globally `[assumption]`, in process
  memory, one uvicorn worker on one EC2 (`guard.py`, spec 05 AC-18).
- The daily LLM cap defaults to 5.0 USD `[assumption]` and degrades `understand` to the S0 rules arm
  (`llm/steps.py`: `DAY_CAP_USD`, `DAILY_LLM_CAP_USD`).
- A Platform outage answers a calm retry turn instead of an error (PR #150, `tests/test_spec05_platform_down.py`).
- Tool inputs stay strict while tool outputs ignore unknown fields (PR #153); the legal deadline source is named in the
  customer's language (contract 1.5.0, PR #149). Contract is `1.7.0` in `main`.
- Demo type C lets a live visitor register a simulated charge `[simulated]` for its own run (PR #160, spec 05 AC-19);
  type D, a generated persona that drafts the first message, is open PR #161.
- The uptime workflow checks the public endpoints every 15 minutes and alerts on Telegram only on a healthy to failing
  change, plus one recovery message (`uptime.yml`, PR #147).

## 3c. Local stacks for tests and evaluation (current)

```mermaid
flowchart LR
  subgraph int1["INT1: tests/local_mcp.py, test_spec04_int_local.py"]
    g1["real graph dispute_intake"] --> m1["real MCP server"] --> st1[("in-memory store")]
  end
  subgraph evl["make eval-local (spec 10 T6)"]
    api2["store-backed api<br/>with eval hooks :8000"] --> plat2["langgraph dev :2024<br/>real graph"]
    plat2 --> mcp2["real MCP server :8001"]
    api2 --> st2[("one in-memory store")]
    mcp2 --> st2
    h["make eval: harness<br/>dev set, S0 and S1"] --> api2
  end
  rob["Robustness suite (eval/robustness):<br/>simulated customer characters +<br/>constitution checker, in CI offline"] --> g1
```

- INT1 runs the graph against the real MCP server offline (PR #138); `make eval-local` starts the store-backed api, the
  real MCP server and the real graph over one in-memory store, with `EVAL_PROVIDER=fake` to stay off Bedrock
  (`Makefile`, PR #164). The robustness suite is outside the sealed evaluation (`tests/test_robustness_suite.py`,
  PR #157).

## 3d. Voice

| Part | State | Source |
|---|---|---|
| Speech to text: Bedrock Mistral Voxtral in `us-east-2` behind `POST /api/voice/transcribe` | **Current, in progress**: being built in a separate PR (branch `feat/05-voice-stt`), not in `main` | lead's brief, 2026-10-05 |
| Text to speech: browser `speechSynthesis` in the web app (GianMarco) | **Current, in progress** | lead's brief |
| Real-time speech to speech (Nova Sonic) | **Out**: available only in `us-east-1`, we run in `us-east-2` (decision D-072) | lead's brief |

Voice must keep the constitution: the transcript goes through the same graph, so the LLM understands, rules decide and
`customer_id` still comes only from the session.

## 4. Data and evaluation plane

Sources: ADR 0004, 0007, 0018, 0022, `contracts/gold_contract.md`, specs 09, 10, 12, 14, 15, 17, 18, CLAUDE.md rule 7.

```mermaid
flowchart LR
  raw[("bank dataset<br/>bronze")] --> silver["silver<br/>DuckDB + Polars + pandera"] --> gold[("gold Parquet v1<br/>read-only at runtime")]
  gold --> runtime["api + mcp<br/>runtime reads"]
  labels[("labels/v1 is_fraud<br/>protected prefix")] --> harness["Evaluation harness<br/>final state, pass^4,<br/>sealed held-out set"]
  labels --> fraud["Fraud model training<br/>by time window (ADR 0022)"]
  harness --> results["eval/results<br/>/evaluation page"]
  fraud --> results
  store[("Postgres case events")] --> auditor["Deterministic auditor A1-A7<br/>+ LLM judge advisory"]
  auditor --> console["Analyst console"]
  store -.->|"spec 14, in memory today"| ops["Ops lakehouse bronze/silver/gold<br/>ops_kpis.json"]
  runtime -.->|"never reads"| labels
```

The dashed edge labeled "never reads" marks that the runtime does not read labels (CLAUDE.md rule 7).

## 5. Current vs future

**Current** = merged in `main` at `5636caa`. **In progress** = open PR or branch. **Future** = documented only, nothing
built (see `roadmap-p2.md`).

| Area | Current (in `main`) | In progress | Future | Source |
|---|---|---|---|---|
| Web | Page shells, `/evaluation` with benchmark sections, `/data`, `/analytics`, screenshots (PR #163) | Live mode on the spec 05 api (open PR #168) | | `apps/web/app/`; specs 07, 08, 12, 16 |
| API | Store-backed FastAPI, Cognito check, channels, agent proxy, GoldCatalog, demo sessions with `demo-` run ids, abuse guard, daily LLM cap, calm Platform-down turn | Demo type D (open PR #161); `POST /api/voice/transcribe` | Run on Postgres on the public URL (spec 05 task 7) | spec 05 section 10 |
| MCP | 16 tools, gated server, tolerant outputs, contract `1.7.0` | | | spec 03; `packages/nick_of_time/__init__.py` |
| Agent | All nodes, S1/S2 with S0 fallback, progress stream, confirm-first for an unnamed charge | | INT3 on the public URL (gates `v0.4.0`) | spec 04; PRs #133, #156, #142 |
| Policy | Rules engine, MX/AR/CO/BR clock rows, queue, D-029 | | PE and CL clock rows (spec 02 T3) | spec 02 |
| Evaluation | Harness, 20 dev and 80 held-out cases, `make eval-local`, robustness suite | Rule-decided test split (open PR #166), status replies in FinalState (open PR #167) | Held-out run on S0/S1/S2 after sealing the protocol | specs 09, 10 |
| Ops lakehouse | Bronze, silver, gold `ops_kpis` on the in-memory store, `make ops`, `ops_kpis.json` (PRs #145, #146) | | Run on Postgres (spec 14 T5); Databricks Delta (T7) | spec 14; `roadmap-p2.md` |
| Monitoring | Uptime workflow with Telegram alert (PR #147) | | Metrics, dashboards, alerting on quality | `roadmap-p2.md` |
| Voice | | Speech to text (Voxtral), browser text to speech (see 3d) | Real-time speech to speech is out (D-072) | lead's brief |
| MLOps | Fraud screen, model benchmark arms, budget guard, gate evidence | | Registry, continuous evaluation, retrain loop | `roadmap-p2.md` |

## 6. Figures used here

| Figure | Value | Label | Source |
|---|---|---|---|
| FCR of dispute contacts, this problem | 43.6% vs 76.6% for the bank | `[data]` | CLAUDE.md "What it is"; `docs/problem_in_numbers.md` |
| Fraud-score zones | high >= 50, medium 30-49, human < 30 or null | `[assumption]` (policy parameters) | CLAUDE.md business rules; `contracts/policies.yaml` |
| Deadlines | MX debit credit by business day 2 for charges within 48 h; AR 10 business days; CO 15 business days | `[external]` | spec 02 section 4.3; ADRs 0019, 0023 (each row has `source_url` and `verified_on` in `policies.yaml`) |
| Replay date | 2026-06-01 | `[assumption]` (fixed demo date) | ADR 0012, ADR 0020 |
| Instance and budget | t3.medium, 100 USD/month budget | `[assumption]` (project configuration) | `docs/infrastructure.md` |
| Customers and transactions in demo | synthetic bank data | `[simulated]` | CLAUDE.md "What it is" |

Open points for the lead: confirm the Platform deployment revision (health shows `null`); decide whether the future
rows for MLOps stay in the final diagram or only in the pitch.
