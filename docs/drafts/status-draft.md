# Status (DRAFT for the lead's review)

**Cut:** 2026-10-05 · **Branch:** `main` at `4ca799a` · **Milestones:** `v0.2.0` tagged · `v0.3.0` reached (per the lead;
no tag in `origin` yet) · **Next:** `v0.4.0`, the three mandatory cases on the public URL, pending INT3. Supersedes the
2026-10-03 cut in `STATUS.md` once the lead moves it. Sizes only, no hours (working agreement).

## Milestones
Definitions are in `CONTRIBUTING.md` (milestone tags, freeze at `v0.4.0` on the public URL, D-004).

| Tag | Meaning | State | Commit | Evidence |
|---|---|---|---|---|
| `v0.1.0` | existing base | tagged | `f867942` (tag object; commit `0777d96`) | `git ls-remote --tags origin`, 2026-10-05 |
| `v0.2.0` | framework + integration contract with stubs | **tagged** | `dcca724` | [#77](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/77) is the tagged commit |
| `v0.3.0` | first case end to end | **reached**, tag not pushed | proposed target `4ca799a` (INT1, [#138](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/138)) | INT1 runs `dispute_intake` against the real MCP server locally (spec 04 section 10); the lead reports the milestone reached |
| `v0.4.0` | three mandatory cases on the public URL | **pending INT3** | none yet | INT3 is named by the lead; spec 04 section 10 defines INT1 only, so INT3's definition should be written down. Freeze applies after it |
| `v0.5.0` | evaluation + model selection | not started | | needs spec 10 T6-T7, spec 11 T6, spec 15 T6 |

## Live on the public URL
Verified with `curl https://nickoftime.salazarvalverdeai.com/api/health` on 2026-10-05:

| What | State | Evidence |
|---|---|---|
| `https://nickoftime.salazarvalverdeai.com` | Live, TLS through Caddy; api answers `status: ok`, `git_sha: 4ca799a...` (equals `origin/main` head), contract `1.4.0`, policies version 2 | `/api/health` |
| Models reported by the api | graph `us.anthropic.claude-sonnet-4-6`, fast `us.anthropic.claude-haiku-4-5-20251001-v1:0` (Bedrock, `us-east-2`) | `/api/health` |
| Time modes | replay `2026-06-01`, live `2026-10-05` | `/api/health`; ADR 0020 |
| `https://mcp.nickoftime.salazarvalverdeai.com` | Deployed from `apps/mcp` since [#122](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/122) and [#136](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/136) (CI-gated deploy); not re-probed here because it needs the API key | `infra/compose.yml`, `deploy.yml` |
| LangGraph Platform | Graph `dispute_intake` served by `apps/agent` ([#134](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/134), D-048); `platform_revision` is `null` in `/api/health`, so the deployed revision is **to be confirmed by the lead** | `langgraph.json`, `/api/health` |
| Web | Next.js app with the page shells; chat and console are on mock data until live wiring (spec 07 task 4, spec 08 task 5) | specs 07, 08 section 10 |
| Deploy gate | Deploy runs only after a green CI on `main` ([#136](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/136)) | `.github/workflows/deploy.yml` |

## Built since the 2026-10-03 cut
93 PRs merged on 2026-10-05 (UTC), after the 2026-10-04 ones; the 2026-10-05 list is in `CHANGELOG-draft.md`.
- **Data and contracts:** contract `1.4.0` (D-052, idempotency key, cards `read_at`) [#107](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/107); gold, `policies.yaml` v2.
- **Policy:** engine with rule ids [#63](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/63), clock rows MX, AR [#67](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/67) and CO, BR [#68](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/68), queue `transition` and `sla` [#86](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/86), D-029 call request [#80](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/80).
- **MCP:** gated FastMCP server and the 16 tools (spec 03 T1-T7 checked), image runs the real server [#122](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/122).
- **Agent:** all graph nodes (greet, understand, route, retrieve, decide, plan, act, verify, respond, plus clarify, refuse, connect, status, duplicate), S1/S2 with S0 fallback [#133](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/133), INT1 [#138](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/138).
- **API and store:** Postgres backend [#82](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/82), store-backed API with Cognito, analyst actions, channels and agent proxy [#111](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/111), demo customers from gold [#141](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/141).
- **Evaluation:** harness [#98](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/98), 20 dev and 80 held-out cases [#95](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/95), [#97](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/97), classifier drafts from three model families (ADR 0025) [#118](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/118), auditor checks A1-A7 and judge.
- **Web:** `/evaluation`, `/data`, `/analytics` pages [#102](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/102), [#103](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/103), [#72](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/72).
- **Infra and CI:** compose, OIDC and SSM deploy [#41](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/41), idempotent schema on every deploy [#129](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/129), Postgres suite in CI [#108](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/108), ruff and AC coverage gates [#57](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/57).

## In review (open PRs, 2026-10-05)
[#127](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/127) `make eval` ·
[#128](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/128) spec statuses ·
[#130](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/130) `/evaluation` benchmark sections ·
[#142](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/142) confirm an unnamed charge (D-067) ·
[#143](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/143), [#144](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/144) eval data kits ·
[#145](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/145), [#146](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/146) ops lakehouse ·
[#147](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/147) uptime monitor ·
[#148](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/148) demo rate limits and spend cap ·
[#149](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/149) contract 1.5.0 ·
[#150](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/150) Platform-outage turn ·
[#151](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/151), [#152](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/152) demo sessions by scenario ·
[#153](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/153) tool-output schema tolerance.

## Tests
Not re-run for this draft. The last result recorded in `STATUS.md` (12 Python tests passing, 2026-10-03) is stale; the
lead should paste the current `make test` and web results at the cut. CI jobs on `main`: pytest (with the Postgres
suite), web lint and build, gitleaks, ruff, AC coverage (`.github/workflows/ci.yml`).

## Not done yet
Specs 07 and 08 live wiring, spec 05 on Postgres on the public URL, evaluation runs on the sealed held-out set, model
selection ADR, fraud benchmark JSON, pitch and submission package (issues #19, #20). Per-spec blockers are in
`specs-readme-draft.md`. P2, not started: voice, ops lakehouse on Databricks, MLOps beyond the benchmark.

## Open items
- Confirm the Platform deployment revision and whether to push tag `v0.3.0` (proposed at `4ca799a`).
- Define INT3 in a spec or issue so `v0.4.0` has a written exit criterion.
- Confirm the submission time on Slack (2026-10-05), carried over from the 2026-10-03 cut.
