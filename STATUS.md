# Status

**Cut:** 2026-10-06 · **Based on:** `main` at `a2fa15e` (#242) · **Submission:** Monday 2026-10-05 (Factored AI & Data
Hackathon 2026, W3). Spec states are in [`specs/README.md`](specs/README.md); decisions in [`docs/adr/`](docs/adr/);
the model and decision-engine inventory in [`docs/models.md`](docs/models.md).

## Deployed
| What | State | Verified |
|---|---|---|
| `https://nickoftime.salazarvalverdeai.com` | web + api live; `/api/health` → `status: ok`, `git_sha` `076a479` (#230), contract 1.8.0, gold `v1`, policies 2, graph model Sonnet 4.6, fast model Haiku 4.5, `platform_revision: null` | `curl`, 2026-10-06 |
| `https://mcp.nickoftime.salazarvalverdeai.com` | real MCP server: 16 tools, 16 handlers, store `postgres`, no absent module | `curl /health`, 2026-10-06 |
| Deploy | GitHub Actions → OIDC → SSM after CI passes on `main`: 33 successful runs `[data]`; #236, #240, #241 and #242 are merged but not yet on the public URL (health still shows `076a479`) | `gh run list --workflow deploy.yml`, 2026-10-06 |
| LangGraph Platform | `dispute_intake` serves `/chat`; a new Platform revision is created by hand | `/chat` in production, 2026-10-06 |
| Bedrock `us-east-2` | Sonnet 4.6, Haiku 4.5 and Voxtral Mini answer in production; Sonnet 5.5 not enabled on the account | `benchmark.json`, 2026-10-06 |

## Live on `main`
- **Customer chat `/chat`** (spec 07): AI Elements layout with inline tool steps, paced reveal and the receipt hero
  (#219), the live `dispute_intake` graph beside the chat (#230), the charge card on the confirm step (#238), demo start
  screen and voice input recorded as WAV and transcribed by Voxtral (#205, #178, #237).
- **Agent** (spec 04, Implemented with P1 deferred): rules decide, S1 understands below τ, the switchable LLM writer
  with line grounding and live tool events (ADR 0030, #202), latest charges as cards (#207), customer tone by rules
  (#235).
- **Analyst console** (spec 08): assisted case view with context, summary, auditor checks, the advisory second opinion
  and the conversation (#209, #210); KPI strip, SLA light and Closed tab (#186).
- **Case page and notifications** (spec 13): a demo visitor links their own e-mail or Telegram and gets their case's
  updates (#241, ADR 0026 amended).
- **Interface in ES · PT · EN** with a header language selector (spec 16 AC-06, #216).
- **Evaluation, sealed once under `protocol-v1`** (spec 10, 11, 15, 17; all `[simulated]` except the fraud window, which
  is `[data]`):
  - held-out, 80 cases × 4 runs, scored under the sealed rules and under D-070 (ADR 0031):
    `apps/web/public/data/evaluation_summary.json`, `eval/results/2026-10-06-heldout/`;
  - classifier: no arm meets the floors, B0 kept (`apps/web/public/data/classifier.json`);
  - model benchmark: Sonnet 4.6 best at 0.979, Mistral Large 3 0.975 at 0.31 USD per 1,000 messages; every arm misses
    the Spanish `human_request` floor (21/23 at best), so `understand` keeps B0 (ADR 0027, Accepted;
    `apps/web/public/data/benchmark.json`);
  - fraud: no learned arm passes; the bank's score stays (PR-AUC 0.566 [0.500, 0.633] on 211 frauds,
    `apps/web/public/data/fraud_benchmark.json`).
- **Insight pages** `/evaluation`, `/analytics`, `/data` (spec 12, Implemented).

## Tests
| Suite | Result | Command |
|---|---|---|
| Python (offline) | 5,697 passed, 348 skipped, 2 xfailed (local, `a2fa15e` + this refresh, 2026-10-06) | `.venv/bin/pytest -q` |
| AC coverage gate | no Implemented spec misses a citing test; specs 01, 07, 08 and 13 still warn | `python scripts/ci/ac_coverage.py` |
| Web lint + build + unit | CI job `web` | `cd apps/web && npm run lint && npm run build` |

## Open
- **#231** — agent path for the case and a "How it works" drawing in the console (spec 08 AC-23, AC-24): open PR, P1.
- **Spec 01** — AC-08, AC-10 and AC-11 are tested in other specs' files, which the coverage gate does not read; the
  lead picks the fix (spec 01 §10 open items).
- **Spec 02** — PE and CL clock entries, `fx.convert()` and `reevaluation_allowed()` in the engine (P1).
- **Spec 04** — the "Agregar información" chip (`add_case_info`) and re-evaluation (P1); `platform_revision` not
  reported by `/api/health`.
- **Spec 06** — rollback drill and first S3 backup not evidenced.
- **Spec 07, 08, 13** — 26, 13 and 6 [T] criteria without a citing Python or Playwright test (their owner's call);
  spec 08: the console "Tono del cliente" line; spec 07: tasks 5 and 7 need a check on the public URL.
- **Spec 18** — no `second_opinions` table (D-057): the latest opinion lives in api memory; `matched_second_opinion` is
  not stored with the analyst's action.
- **Models** — demo sessions run S1 while ADR 0027 keeps B0 for `understand`; runtime τ is 0.80 while spec 11 measured
  0.7364 (`docs/models.md`, "Open for the lead").
