# Status

**Cut:** 2026-10-03 · **Branch:** `main` (+ `chore/00-adopt-framework` in review) · **Next milestone:** `v0.2.0` —
framework adopted and spec 01 (integration contract) approved with stubs.

## Deployed
| What | State | Verified |
|---|---|---|
| `https://nickoftime.salazarvalverdeai.com` | Caddy placeholder with TLS; `/api/health` → `{"status":"ok","service":"placeholder"}` | `curl`, 2026-10-03 |
| `https://mcp.nickoftime.salazarvalverdeai.com` | Placeholder with TLS | `curl`, 2026-10-03 |
| LangGraph Platform | No deployment yet (Plus tier available) | API, 2026-10-03 |
| Bedrock | Haiku 4.5 answers; Sonnet 4.6 activating after the use-case form | `converse`, 2026-10-03 |

## Built
- Data pipeline bronze → silver → gold with contracts, manifest and late-arrival fixture (`make setup` ≈ 60 s).
- Contracts: `policies.yaml`, `tools.py`, `handoff.schema.json`, `eval_case.schema.json`, `gold_contract.md`.
- Web scaffold: Next.js 16 + shadcn/ui with six page shells.
- Process: `CLAUDE.md`, `CONTRIBUTING.md`, spec and ADR templates, 18 ADRs, CI, CODEOWNERS (in review).

## Tests
| Suite | Result | Command |
|---|---|---|
| Python (offline) | 12 passed | `make test` |
| Web lint + build | passing | `cd apps/web && npm run lint && npm run build` |

## Not built yet
Agent graph, MCP server, policy engine in code, backend API and Postgres, analyst login, customer and analyst UIs,
notifications, evaluation sets and harness, model benchmark. See [`specs/README.md`](specs/README.md).

## Open items
- Diego to accept the repository invitation.
- Confirm the submission time on Slack (2026-10-05).
- Telegram bot and Resend account (lead), then their SSM parameters.
