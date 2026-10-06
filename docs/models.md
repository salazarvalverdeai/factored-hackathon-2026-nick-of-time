# Models and decision engines

The inventory that ADR 0021 (§0) asks for: everything in Nick of Time that decides, scores or words something, with
its version, where it runs, the evidence behind it and how it is watched. Read from `main` at `a2fa15e` on 2026-10-06;
every row cites the file that holds the value. Figures carry their label (CLAUDE.md constitution #8).

Rule of the house: **the LLM understands, the rules decide, the tools act, verification confirms, a person closes.**
No model below decides a block, a zone, a deadline or a provisional credit.

## Decision engines (no learning, no LLM)

| Engine | Version | Where it runs | What it decides | Evidence | Owner |
|---|---|---|---|---|---|
| Policy engine (`nick_of_time.policy`) | `contracts/policies.yaml` `version: 2`, `default: deny` | `decide` node of the graph (`apps/agent/agent/intake.py`), every MCP write re-checks it (`apps/mcp/mcp_server/`) | zone, decision, approval mode, queue transitions, rule ids | spec 02, decision-table tests `tests/test_spec02_*.py` | lead |
| Regulatory clock (`nick_of_time.policy.clock`) | `regulatory_clock` table in `policies.yaml`, holiday files `packages/nick_of_time/policy/holidays/{mx,ar,co,br}_2026.yaml` | `compute_deadline`, `open_case` (MCP) | legal deadlines per country and product; PE and CL get `POL-CLOCK-UNKNOWN` | spec 02 AC-03, AC-14; ADR 0019, 0023 | lead |
| B0 rules NLU (`nick_of_time.nlu.rules`) | `ARM, VERSION = "B0", "b0-v1"` (`packages/nick_of_time/nlu/rules.py`) | `understand` node, every arm first (`load_nlu("B0")`, `intake.py`) | intent, slots, dates, language | spec 11; sealed test: macro-F1 ES 0.583 / PT 0.668 `[simulated]` (`apps/web/public/data/classifier.json`) | lead |
| Injection rules (`nick_of_time.nlu.injection`) | rules arm, no version constant | `understand` (G-IN-01) | flags an injection; the graph refuses | sealed test: recall 8/22, false positives 0/236 `[simulated]` (`classifier.json` `injection`) | lead |
| Tone rules (`nick_of_time.nlu.tone`) | keyword rules, no version constant (spec 04 AC-44, #235) | `understand` → `respond` | one acknowledgement label and line (`calm`, `urgent`, `frustrated`); never intent, decision or chips | `tests/test_spec04_tone.py` | lead |
| Grounding gate (`nick_of_time.receipt.build`) | exact match, ADR 0016 | `respond`, and every LLM-writer block | drops any reply line whose number, date or id is not in a tool result | spec 04 §4.3, `tests/test_spec04_respond.py`, `tests/test_spec04_writer.py` | lead |
| Outcome auditor A1–A7 (`nick_of_time.audit`) | `checks.py` (A3–A7), `rederive.py` (A1–A2) | evaluation harness (A5, A6: `eval/harness/compare.py`); console audit view (`GET /api/console/cases/{id}/audit`, `apps/api/app/console.py`) | findings only; never changes state | spec 18, `tests/test_spec18_*.py` | lead |

## Learned models and LLMs

| Role | Model and version | Where it is used | Chosen by | Evidence | Status |
|---|---|---|---|---|---|
| `understand` below τ (arm S1) | Claude Haiku 4.5, `us.anthropic.claude-haiku-4-5-20251001-v1:0` (`HAIKU` in `packages/nick_of_time/config/__init__.py`, env `BEDROCK_MODEL_FAST`) | demo sessions: `DEFAULT_ARM=S1` (`infra/deploy.sh`), only below `clarify.intent_confidence_min`, only in a verified session, never on a flagged message (spec 04 T7) | lead decision 2026-10-05 (deploy.sh comment), before the sealed benchmark | sealed test as B2: macro-F1 ES 0.932 / PT 0.915, `human_request` recall ES 20/23, PT 23/24, 1.84 USD per 1k messages `[simulated]` (`classifier.json`) | in production; see "Open for the lead" |
| `understand` per the sealed benchmark | **B0 rules** (no LLM) | — | ADR 0027 (lean rule, D-077): no arm meets the hard limits | `apps/web/public/data/benchmark.json` `model_map.understand` | Accepted 2026-10-06 |
| B1 TF-IDF + LR | `b1-v1` (`B1_VERSION`, `packages/nick_of_time/nlu/learned.py`), file `models/intent-b1-v1.joblib`, sha256 `8017f023…` | benchmark arm only; not loaded by the graph | spec 11 (not chosen) | sealed test: macro-F1 ES 0.916 / PT 0.914, `human_request` recall ES 20/23 `[simulated]` (`classifier.json`) | measured, not deployed |
| Chat writer (`word`, ADR 0030) | Claude Sonnet 4.6, `us.anthropic.claude-sonnet-4-6` (`SONNET`, env `BEDROCK_MODEL_GRAPH`; `ARM = "S2"` in `packages/nick_of_time/llm/writer.py`) | words the reply from template lines when the console setting `writer` is `llm` (default `template`, `apps/api/app/console.py`); every block passes the grounding gate | ADR 0030 (not benchmarked: spec 15 AC-12 is P1) | `tests/test_spec04_writer.py`; price 3.3 / 16.5 USD per 1M tokens in/out `[external]` (`eval/bench/prices.yaml`, checked 2026-10-04) | in production, switchable |
| Console case summary | Sonnet 4.6 through `writer.client_for` (S2) | `GET /api/console/cases/{id}/summary` words the template summary when `writer` is `llm` | spec 08 AC-17 | `tests/test_spec08_assisted_console.py` | in production |
| Judge, second opinion (spec 18) | Haiku 4.5 through `resolve("S1")` (`apps/api/app/console.py` `judge_client`) | `POST/GET /api/console/cases/{id}/second-opinion`, advisory, on demand; cap 0.01 USD per case and 10 s timeout `[assumption]` (`MAX_COST_USD`, `TIMEOUT_S` in `packages/nick_of_time/audit/judge.py`) | spec 18 §4.3, until a spec 15 `judge` task (P2) | `tests/test_spec18_judge.py`, `tests/test_spec18_console_second_opinion.py` | in production; opinions kept in api memory (no `second_opinions` table yet) |
| Demo persona (type D) | Haiku 4.5 through `resolve("S1")` (`apps/api/app/persona.py`) | drafts the demo visitor's first message; template fallback | spec 05 AC-20 | `tests/test_spec05_persona.py` | demo only |
| Voice speech-to-text | Voxtral Mini 3B, `mistral.voxtral-mini-3b-2507` (`VOXTRAL_MINI`, env `BEDROCK_MODEL_STT`) | `POST /api/voice/transcribe` (`apps/api/app/voice.py`); read-aloud is the browser's own TTS | ADR 0029, D-072 | `tests/test_spec05_voice.py`; price 0.04 / 0.04 USD per 1M tokens `[external]` (`prices.yaml`) | in production |
| Fraud score in the zones | **S-bank**: the bank's `fraud_score` from gold (`scoring.provider: dataset`, version `gold-v1`, `contracts/policies.yaml`) | zones in `decide`; live demo charges carry `synthetic-v0` | spec 17 rule 5: no learned arm passes | sealed test window (238,990 transactions, 211 frauds): PR-AUC 0.566 [0.500, 0.633] `[data]` (`apps/web/public/data/fraud_benchmark.json`) | in production |
| Fraud screen (spec 17) | nine scikit-learn arms and a stacked arm, versions in `eval/results/fraud_models_frozen.json` | not used: no arm passes; the stacked arm reproduces S-bank (PR-AUC 0.566), the others sit at 0.0008–0.0010 `[data]` | spec 17 §4.4 | `eval/results/fraud-test/fraud_benchmark.csv` | measured, not deployed |

Not available on the account at the sealed run: Sonnet 5.5 (`AccessDeniedException`) and Jev (no key), per
`benchmark.json`.

## Guards that apply to every LLM call
- **Fallback to rules.** An LLM error, timeout, schema failure, missing price (D-058) or cap stop runs the step as S0
  (spec 04 T7); the writer falls back to the template reply (ADR 0030).
- **Daily cap.** `DAILY_LLM_CAP_USD=10` on the api (`infra/deploy.sh`), summed from `llm_calls` (spec 05 AC-18).
- **Per conversation.** 0.02 USD for `understand` (D-064, spec 04 T7).
- **Prices.** Every LLM arm needs a row in `eval/bench/prices.yaml`; CI fails when a default production arm has none
  (`config.check_prices()`).
- **Provider.** `LLM_PROVIDER=bedrock` in production (`.env.example`, ADR 0009); CI uses `fake`.

## Monitoring
ADR 0021 lists what is watched per engine. On `main` today: the sealed evaluation results on `/evaluation`
(`apps/web/public/data/*.json`), the auditor's A5–A6 inside every harness run, the console audit view per case, and
`llm_calls` rows for cost. Online auditing with `audit_findings` (spec 18 AC-03–AC-05) and judge calibration (AC-14)
are not built.

## Open for the lead
- **`understand` in production versus ADR 0027.** The sealed benchmark keeps B0; demo sessions run S1 (B0, then Haiku
  4.5 below τ). Either keep S1 for the demo as a recorded exception or set `DEFAULT_ARM=S0`.
- **τ.** `contracts/policies.yaml` has `clarify.intent_confidence_min: 0.80`; spec 11 measured τ = 0.7364 on validation
  (`classifier.json` `tau`). The runtime uses 0.80.
- **Health payload.** `/api/health` reports `prompt_hash: null` and `classifier_version: null` (checked 2026-10-06), so
  the deployed `understand` prompt and NLU version are not visible from the public URL.
