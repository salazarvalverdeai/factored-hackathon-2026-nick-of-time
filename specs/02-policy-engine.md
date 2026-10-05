# Spec 02 — Policy engine + regulatory clock

- **Feature:** pure, deterministic code that turns `contracts/policies.yaml` into decisions — zone, decision, approval
  mode per action, allowed queue transitions and legal deadlines — with the rule ids that justify each one.
- **Status:** In progress (T1 done; gate 1 closed; Q7 closed by ADR 0020 on 2026-10-04; adds `clock.today(mode)`,
  display currency and the re-evaluation window)
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Technical Judgment (deterministic logic where AI is not appropriate)
- **Depends on:** `contracts/policies.yaml` · **Enables:** 03 (tools re-check permissions), 04 (decide node), 05 (queue
  transitions, supervised mode) · **ADRs:** 0005, 0006, 0019, 0020 (supersedes 0012)
- **Issue:** #4

> Full profile: money and compliance decisions. The engine never calls a network, a database or an LLM.

---

## 1. Introduction
"The LLM understands, the rules decide." This spec defines the *decide* step and the regulatory clock as a library in
`packages/nick_of_time/policy/` (layout from spec 01). The agent calls it to choose what to do; the MCP tools call it
again before writing (defense in depth); the api calls it for analyst transitions and supervised mode. Every result
carries the ids of the rules that produced it, so a regulator or an analyst can read *why*.

## 2. User stories
- As a **dispute analyst**, I want every automatic action to cite the rule that allowed it, so I can audit it in one click.
- As the **bank**, I want the legal deadline computed from the country's regulation with its source, so no case breaches it
  silently.
- As the **agent developer**, I want one function that returns the decision for a turn, so the graph never encodes
  business rules in prompts.

## 3. Acceptance criteria (EARS)
AC-01 to AC-06 come from issue #4 with the same numbers; AC-07 onward are added by this spec.

- **AC-01** — When the score is ≥ 50, 30–49 or < 30, the zone shall be `high`, `medium` or `human`. · [T]
- **AC-02** — If the score is null, its source is `llm`, or its source is not in `scoring.deciding_sources`, then the
  zone shall be `human` with its own policy id (`POL-SCORE-NULL` / `POL-SCORE-LLM` / `POL-SCORE-SOURCE`), and the
  decision shall still open a case. · [T]
- **AC-03** — When a MX debit dispute is opened for a charge made within the 48 hours before the notice, `credit_deadline`
  shall be the second business day after opening (opened 2026-06-01 → 2026-06-03) with its Banxico source; for an older
  MX debit charge it shall be a ruling deadline instead; an AR dispute shall get +10 business days and a CO dispute +15 business days,
  skipping weekends and the country's 2026 holidays; a PE dispute shall get +15 business days (SBS) and a CL dispute
  a refund deadline of +10 business days (+15 for cash advances and ATM withdrawals) and +7 more for the part above
  35 UF (Ley 20.009). · [T]
- **AC-04** — While `supervised_mode` is on, every action shall have approval mode `human_required`. · [T]
- **AC-05** — If no rule allows an action, then the engine shall deny it with `POL-DEFAULT-DENY`. · [T]
- **AC-06** — The amount tier shall change only the approval mode, never a deadline. · [T]
- **AC-07** — If the session is expired or unverified, then the decision shall be `reauthenticate` (G-SES-01) before any
  other rule is evaluated. · [T]
- **AC-08** — When intent confidence is below τ (0.80) or there is more than one candidate transaction, the decision shall
  be `ask`; after 2 clarification turns it shall be `handoff` with reason `clarification_exhausted`. · [T]
- **AC-09** — The approval mode of `provisional_credit` shall be `human_required` in every zone, tier and mode. · [T]
- **AC-10** — If an analyst transition is not listed in `case_queue.transitions`, or `close` is requested by a
  non-human actor, then the engine shall deny it with `POL-QUEUE-TRANSITION` / `POL-CLOSE-HUMAN`. · [T]
- **AC-11** — While a MX debit case is open, its priority shall rise on business day 1 and an alert shall be due before
  business day 2. · [T]
- **AC-12** — Every result shall include the ids of the rules that produced it and the `policies.yaml` version. · [T]
- **AC-13** — The same input shall always produce the same output; the test suite runs offline with no network,
  database or LLM. · [T]
- **AC-14** — If the customer's country has no verified entry in `regulatory_clock`, then the engine shall still open the
  case, return no legal deadline (never an invented one) and route it to a person with `POL-CLOCK-UNKNOWN`. · [T]
- **AC-15** — While `supervised_mode` is on, `open_case` shall still run automatically; supervised mode applies only to
  money actions (`block_card`, `unblock_card`, `provisional_credit`). · [T]
- **AC-16** — The clock shall take "today" only from `clock.today(mode, country)`: `DEMO_TODAY` in `replay`, the real
  date in the country's time zone in `live`; no function reads the system clock elsewhere. · [T]
- **AC-17** — When a conversion is requested, `fx.convert()` shall use only a reference rate that has `source_url`,
  `as_of` and `verified_on`; if none exists it shall return no converted amount, and the original amount is shown
  alone. Deadlines and zones never depend on a converted amount. · [T]
- **AC-18** — If a customer asks to re-evaluate a case resolved more than `reevaluation.window_days` ago in their
  country, then the engine shall deny it with `POL-REEVAL-WINDOW` and the agent offers a call instead. · [T]

## 4. Functional requirements
- **FR-01** Load and validate `policies.yaml` once (Pydantic model); an invalid file fails at startup, not at decision time.
- **FR-02** Evaluate rules in a fixed order (§4.1); the first terminal rule wins; every rule that fired is reported.
- **FR-03** Compute the zone from `get_fraud_score` output only — never from a number in the customer's text (G-IN-02).
- **FR-04** Combine approval modes as *the stricter wins*: `auto < manual_check < human_required`, across
  `approval.per_action`, the amount tier and `supervised_mode`.
- **FR-05** Compute deadlines per country and product with business-day calendars loaded from data files with their source.
- **FR-06** Validate analyst transitions against `case_queue.transitions`; compute SLA due times and the MX debit priority.
- **FR-07** Add stable rule ids to `policies.yaml` (`rules:` section), the PE and CL clock entries with their sources,
  the `POL-CLOCK-UNKNOWN` fallback, and bump `version` to 2.
- **FR-08** Supervised mode applies to money actions only; registering a case is never blocked (AC-15).
- **FR-09** Add to `policies.yaml`, per country: `time_zone`, `display_currency` and an `fx_reference` entry with its
  official source; and a `reevaluation` section with `window_days` per country (§4.4).

### 4.1 Evaluation order (first terminal rule wins)
| # | Rule id | Condition | Decision | Notes |
|---|---|---|---|---|
| 1 | `POL-SESSION` | session expired or unverified | `reauthenticate` | G-SES-01 |
| 2 | `POL-INJECTION` | input flagged by the injection detector (spec 11) | `deny` | G-IN-01, logged |
| 3 | `POL-CROSS-CUSTOMER` | request targets another customer's data | `deny` | G-SES-02, logged |
| 3a | `POL-HUMAN-REQUEST` | intent `human_request` | `connect_person` | `request_call` on the active case, or a general request; never refused (CFPB 2023) |
| 3b | `POL-STATUS` | intent `status_inquiry` | `answer_status` | read-only: the agent re-reads cards or cases (spec 04 AC-19); no case is opened |
| 4 | `POL-OUT-OF-SCOPE` | intent `out_of_scope`, or product is not a card | `deny` (polite abstention) | G-IN-04 |
| 5 | `POL-CLARIFY` | confidence < τ, or candidates > 1 (≤ 3), or candidates = 0 | `ask` (≤ 2 turns) | then rule 5b |
| 5b | `POL-CLARIFY-EXHAUSTED` | clarification turns > 2 | `handoff` (`clarification_exhausted`) | |
| 6 | `POL-SCORE-NULL` / `POL-SCORE-LLM` | score null, or source `llm` | zone `human` | case is still opened |
| 7 | `POL-ZONE-HIGH` | score ≥ 50 | `block_and_open_case` | block mode from §4.2 |
| 8 | `POL-ZONE-MEDIUM` | 30 ≤ score < 50 | `confirm`, then see §4.2 | customer confirmation required |
| 9 | `POL-ZONE-HUMAN` | score < 30 | `handoff` (`zone_human`) | case opened, no block |
| — | `POL-DEFAULT-DENY` | any action no rule allows | deny | `default: deny` |

`POL-TICKET-ALWAYS`: in every zone that reaches rules 6–9, `open_case` is allowed with mode `auto` (registering is not
a money decision).

### 4.2 Approval modes and what happens to the case
| Zone | `block_card` mode (policies) | Effective mode = stricter of mode, amount tier, supervised | Case status after the turn |
|---|---|---|---|
| high | `manual_check` | `manual_check` → block now, verify, case in `verification` · `human_required` → no block, handoff | `verification` or `review` |
| medium | `human_required` | after the customer confirms: open case + handoff proposing `approve_block` | `review` |
| human | not allowed | — | `review` |
| any | `provisional_credit`: `human_required` | always a person (AC-09) | — |

Amount tiers per country (`amount_gate.by_country`, local currency): `≤ low` → `auto`, `≤ high` → `manual_check`,
`> high` → `human_required`. MX transactions are in USD in the dataset and are converted at 18.0 MXN/USD
`[assumption]` before comparing. Each entry's `usd_rate` is a threshold-conversion parameter, never shown to a customer
(customer-facing amounts use §4.4): COP 4,000 and ARS 350 are the gold's implied rates `[data]`
(`queries/policy/implied_usd_rate.sql`); MXN 18.0 and BRL 5.5 stay `[assumption]` (the gold has no MXN or BRL amounts).

### 4.3 Regulatory clock (LATAM, data-driven)
The clock is a **table of verified country entries** in `policies.yaml`, not code. Each entry carries the regulator, the
legal basis, what the deadline is (refund / provisional credit or ruling / response), the number of days, business or
calendar, the official source URL and the date it was verified. **Adding a LATAM country is a PR with a source and a
test, no code change.** A country without a verified entry falls back to `POL-CLOCK-UNKNOWN` (AC-14).

| Country · product | `credit_deadline` | `ruling_deadline` | Legal basis | Official public source | Verified |
|---|---|---|---|---|---|
| MX · debit, charge within the **48 h** before the notice | opened + **2 business days** (provisional credit) | — | Banxico Circular 3/2012, as amended by Circular 14/2018 (in force since 2019-09-26) | [CONDUSEF](https://www.gob.mx/condusef/prensa/cargos-no-reconocidos-en-tarjeta-de-debito-se-restituiran-en-dos-dias-habiles-bancarios?idiom=es) · [DOF, Circular 14/2018](https://www.dof.gob.mx/nota_detalle.php?codigo=5539863&fecha=03%2F10%2F2018) | 2026-10-04 |
| MX · debit, older charge (claim within 90 days of the charge) | — | opened + **45 calendar days** `[external, to verify in T3]` | LTOSF art. 23 (clarifications) | [CONDUSEF](https://www.gob.mx/condusef/prensa/cargos-no-reconocidos-en-tarjeta-de-debito-se-restituiran-en-dos-dias-habiles-bancarios?idiom=es) | 2026-10-04 (90-day window) |
| MX · credit | — | opened + **45 calendar days** (180 if the charge was abroad) | LTOSF art. 23 | `[external, to verify in T3]` | — |
| AR · any card | opened + **10 business days** (reimbursement) | same date (resolution) | BCRA, Protección de los Usuarios de Servicios Financieros (texto ordenado) | [BCRA t-pusf](https://www.bcra.gob.ar/archivos/Pdfs/texord/t-pusf.pdf) | 2026-10-04 |
| CO · any card | — | opened + **15 business days** | SFC: petitions to supervised entities | [SFC FAQ](https://www.superfinanciera.gov.co/preguntas-frecuentes/3/3-derechos-de-peticion-ante-entidades-vigiladas/) | 2026-10-04 |
| BR · any card (PT demo only) | — | opened + **10 business days**, extendable once by an equal period | Resolução CMN 4.860/2020 (ouvidoria) | [BCB · Ouvidoria](https://www3.bcb.gov.br/sisorf_externo/manual/06-01-030-160.htm) | 2026-10-04 |
| PE · any card | — | opened + **15 business days** (extendable only when a third party must rule) | Resolución SBS N.° 04036-2022 | [El Peruano](https://busquedas.elperuano.pe/normaslegales/aprueban-el-reglamento-de-gestion-de-reclamos-y-requerimient-resolucion-sbs-no-04036-2022-2138687-1) | 2026-10-04 |
| CL · any card | opened + **10 business days** up to 35 UF (15 for cash advances and ATM withdrawals); +7 more days for the part above 35 UF | — | Ley 20.009 | [SERNAC](https://www.sernac.cl/portal/604/w3-propertyname-791.html) | 2026-10-04 |
| any other LATAM country | — | — | `POL-CLOCK-UNKNOWN`: case opened, routed to a person, no deadline invented |

- "Opened" = `clock.today(mode, country)`: `DEMO_TODAY = 2026-06-01` in `replay`, the real date in the country's time
  zone in `live` (ADR 0020). Example: a MX debit notice on Monday 2026-06-01 about a charge on 2026-05-31 →
  credit by Wednesday 2026-06-03.
- **Coverage note:** the dataset only has MX, CO and AR customers, so PE, CL and BR are exercised by unit tests and
  fixtures; the demo runs on MX, CO and AR (BR in Portuguese with a fixture). The README states it.
- **Every entry cites its official public source and the date it was verified** (ADR 0019); `policies.yaml` stores them as
  `source_url` and `verified_on` fields plus a comment, and a test fails if an entry lacks them. Rows marked
  `[external, to verify]` are re-checked in T3.
- Business days = Monday–Friday minus the country's bank holidays.
- Holiday lists live in `packages/nick_of_time/policy/holidays/{mx,ar,co,br,pe,cl}_2026.yaml`, each with the official source
  URL; they are `[external]` data, not code.
- Product mapping from gold: `Tarjeta Débito` → `debit`, `Tarjeta Crédito` → `credit`; any other product type is not a
  card (rule 4).
- MX debit SLA (`case_queue.deadline_sla.mx_debit`): priority `high` from business day 1; `alert_due_at` = start of
  business day 2.

### 4.4 Time zone, display currency and re-evaluation window
The customer sees the transaction's **original, exact amount** and, when it differs, an **approximate** amount in the
display currency (their country's currency, or USD if they ask), always with the rate's source and date. The reference
rate is each central bank's official series; the value and `as_of` are filled in T7 and re-verified per release
(ADR 0019). The amount tiers of §4.2 keep their own documented rates and are not affected.

| Country | `time_zone` (IANA) | `display_currency` | Official reference rate (`fx_reference.source_url`) |
|---|---|---|---|
| MX | `America/Mexico_City` | MXN | Banxico, FIX — [banxico.org.mx](https://www.banxico.org.mx/tipcamb/main.do?page=tip&idioma=sp) |
| CO | `America/Bogota` | COP | Banco de la República, TRM — [banrep.gov.co](https://www.banrep.gov.co/es/glosario/tasa-cambio-trm) |
| AR | `America/Argentina/Buenos_Aires` | ARS | BCRA, Com. "A" 3500 — [bcra.gob.ar](https://www.bcra.gob.ar/catalogo_de_datos/tipo-de-cambio-de-referencia-mayorista-y-promedio-mensual/) |
| PE | `America/Lima` | PEN | BCRP — [bcrp.gob.pe](https://www.bcrp.gob.pe/estadisticas/tipo-de-cambio.html) |
| CL | `America/Santiago` | CLP | Banco Central de Chile, dólar observado — [bcentral.cl](https://www.bcentral.cl/en/areas/statistics/exchange-statistics/types-of-changes-and-parities) |
| BR | `America/Sao_Paulo` | BRL | BCB, PTAX — [bcb.gov.br](https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes) |

**Re-evaluation window:** a resolved case can be sent back to review within `reevaluation.window_days` of its
resolution (proposal: 30 days for every country `[assumption]`, a product policy with no regulatory source); later, the
agent offers a call (AC-18). A closed case is never reopened by the customer: spec 03 opens a related case.

## 5. Non-functional requirements
- **Performance:** `decide()` < 5 ms p95 (pure Python, policies cached).
- **Security:** read-only access to `policies.yaml`; no environment variable can loosen a rule (only `supervised_mode`
  can make it stricter).
- **Observability:** the result is serializable; the graph writes it to the trace and `policy_denials` writes the denials.

## 6. API (Python, `nick_of_time.policy`)
```python
engine = PolicyEngine.load("contracts/policies.yaml")      # validates; exposes engine.version

decision: Decision = engine.decide(DecisionInput(
    session_state="verified|expired|unverified",
    intent="unrecognized_charge|wrongful_charge|status_inquiry|human_request|out_of_scope",
    intent_confidence=0.93, candidates=1, clarification_turns=0,
    injection_flagged=False, cross_customer=False,
    score=72.0, score_source="dataset",                     # from get_fraud_score
    amount=1250.0, currency="USD", country="MX", product_type="debit",
    customer_confirmed=None, supervised_mode=False,
))
# Decision: decision, zone, approval_modes {action: mode}, allowed_actions, handoff_reason,
#           queue_status_after, rule_ids [..], guardrail_ids [..], policies_version

engine.check(action="block_card", zone="high", amount=..., country=..., supervised_mode=False) -> Allow | Deny
today: date = clock.today(mode="replay", country="MX")     # 2026-06-01 in replay; the real local date in live
add_by: date = clock.add_business_days(country="MX", start=today, n=1)   # 2026-06-02 in replay (D-008)
# callback date for request_call; task 02b implements it in T3 with a unit test (2026-06-01 + 1 → 2026-06-02)
deadline: Deadline = clock.deadline(country="MX", product="debit", opened_on=today, abroad=False)
# Deadline: credit_deadline, ruling_deadline, deadline_source, calendar ("business"|"calendar"), holidays_skipped [..]
engine.transition(current="verification", action="resolve", actor="analyst:…") -> new status | Deny
engine.sla(case) -> {priority, sla_due_at, alert_due_at}
engine.reevaluation_allowed(country="MX", resolved_on=date(...), today=today) -> Allow | Deny("POL-REEVAL-WINDOW")
fx.convert(amount=1250.0, from_currency="USD", to_currency="MXN") -> {amount, rate, rate_source, as_of} | None
```

## 7. Data model touched
- `contracts/policies.yaml`: adds `rules:` (every id this spec names, each with its text and guardrail: those of §4.1,
  `POL-SCORE-SOURCE` for a score from a source that does not decide, `POL-AMOUNT-GATE`, `POL-AMOUNT-UNKNOWN` and
  `POL-SUPERVISED` for a stricter mode in §4.2, `POL-CLOCK-UNKNOWN`, `POL-QUEUE-TRANSITION`, `POL-CLOSE-HUMAN` and
  `POL-REEVAL-WINDOW`), `scoring.deciding_sources` (the sources whose score places a zone: `dataset`, `rules`,
  `model` and `synthetic`; never `llm`) with a `scoring.providers.synthetic` entry,
  `approval.money_actions` (AC-15), `usd_rate` per `amount_gate.by_country` entry (§4.2), the handoff reasons
  `zone_medium` and `supervised_mode` (also in `contracts/handoff.schema.json`), per-country `time_zone`,
  `display_currency` and `fx_reference`, the `reevaluation` section, and `version: 2`; validates
  `contact.callback_within_business_days` (D-008, task 02b). No threshold changes.
- `contracts/handoff.schema.json` also gains the optional `score_source` (the `GetFraudScoreOut.source` values) and
  `score_version` (D-033, default pending the lead), so `record_source_in_audit` reaches the analyst's card.
- The loader (FR-01) also refuses a file that breaks a firm rule: `default` other than `deny`, `open_case` not `auto`
  or `provisional_credit` not `human_required` in every zone, `block_card` not `human_required` in the medium and
  human zones or `human_required` in the high zone (the high zone blocks), `unblock_card` not `human_required` in every
  zone, `close` not `human_only`, zone bands with gaps, tiers that loosen as the amount grows, a rule citing an unknown
  guardrail, `llm` among the deciding sources, or a `scoring.provider` or deciding source without a `scoring.providers`
  entry (the audit needs its version). It types the `contact` section (D-008, added by #50), so the file loads with
  or without it. The loaded model is deeply frozen (read-only mappings, tuples), so no caller can loosen a rule at
  runtime; `model_dump()` and `model_dump_json()` still return plain dicts and lists, and without defaults they give
  back the file.
- **`synthetic` decides (D-027, default pending the lead):** a live-mode synthetic transaction (ADR 0020) carries the
  score generated with it, `get_fraud_score` returns it with `source: "synthetic"` (spec 03 §6), and it places a zone
  like the dataset score. It never reaches `replay`, the evaluation or a pitch number (ADR 0020 rule 2), and the receipt,
  the handoff card (`score_source`, D-033) and the console label it `[simulated]` (constitution #8). `tools.py` v1.1
  `GetFraudScoreOut.source` must list `"synthetic"` (#59). Any other source still goes to zone human with
  `POL-SCORE-SOURCE`.
- New data files: `packages/nick_of_time/policy/holidays/*_2026.yaml`.
- No database access.

## 8. Decisions (gate 1 closed by the lead, 2026-10-04)
- **Q1 — medium zone:** follow `policies.yaml`: after the customer confirms, the case is opened and an analyst approves
  the block (safer at 79.6% precision `[data]`); `three_zone_flow.svg` is updated in spec 13.
- **Q2 — CO:** 15 **business** days, labeled `[external, to verify]` until T3.
- **Q3 — MX credit:** 45 **calendar** days (180 if the charge was abroad).
- **Q4 — non-card products:** `deny` with a polite abstention (rule 4).
- **Q5 — supervised mode vs "the ticket is always opened":** supervised mode applies only to money actions (AC-15).
- **Q6 — LATAM coverage:** data-driven clock table; PE and CL added with verified sources; any other country falls
  back to `POL-CLOCK-UNKNOWN` (AC-14).
- **Rules 3a–3b (added 2026-10-04 with the five intents of spec 11):** a request for a person and a status question
  are answered after the security checks (rules 1–3) and before the dispute rules; every reply, including
  `reauthenticate` and `deny`, still offers a way to a person (spec 04 AC-20).
- **Q7 — demo date:** ~~move `DEMO_TODAY` to 2026-06-01?~~ **Decided (lead, 2026-10-04):** two time modes (ADR 0020,
  proposed). `replay` uses `DEMO_TODAY = 2026-06-01` (Monday), so charges of May 30–31 qualify for the MX 48 h rule;
  `live` uses the real date with labeled synthetic transactions. The clock receives "today" from the mode (AC-16).
- Assumption: MXN 18.0 per USD for the MX amount tiers (`[assumption]`, already in `policies.yaml`); it is never shown to
  a customer — customer-facing conversions use the official reference rate of §4.4.
- Assumption: holiday lists are verified against official sources while implementing; each file cites its URL.

## 9. Out of scope
Calibrating thresholds with data (Q-AMT, P2); the injection detector itself (spec 11); writing to Postgres (the
callers write).

## 10. Plan, tasks and verification
Implementation goes in `feat/02-policy-engine` once this spec and spec 01 (package layout) are approved.
- [x] T1 — Pydantic model of `policies.yaml` + loader with validation; add `rules:` and `version: 2` · FR-01, FR-07, AC-12
- [ ] T2 — `decide()` with the evaluation order of §4.1 and mode combination of §4.2 · AC-01, 02, 04, 05, 06, 07, 08, 09, 15
- [ ] T3 — `clock.deadline()` + holiday files with sources for MX, AR, CO, BR, PE, CL; re-verify every clock source · AC-03, AC-14
- [ ] T4 — `transition()` and `sla()` · AC-10, AC-11
- [ ] T5 — decision-table tests: zone × country × mode × tier, plus the boundaries 29/30/49/50 and null · AC-01…AC-13
- [ ] T6 — `docs`: policy ids listed in `/agent` content (spec 04 AC-08)
- [ ] T7 — `clock.today(mode, country)`, time zones, `fx_reference` values from the official series with `as_of`
      and `verified_on`, `fx.convert()`, `reevaluation_allowed()` · AC-16, AC-17, AC-18

**Closing checklist:** every AC has a passing test that cites it · status → Implemented · ADR if a question above
changes a decision · lessons added to `CLAUDE.md`.

## 11. Sources
External sources checked on 2026-10-04; the clock's legal sources are in the table of §4.3 and the reference-rate
sources in the table of §4.4.
- CFPB, *Chatbots in consumer finance* (6 June 2023), on not blocking access to a person (rule 3a):
  https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/
- IANA time zone database (zone names of §4.4): https://www.iana.org/time-zones
- Internal: `contracts/policies.yaml` (`amount_gate`, `approval`, `case_queue`, `regulatory_clock`),
  `contracts/gold_contract.md` R1 (gold ends 2026-05-31), ADR 0019 (official sources), ADR 0020 (two modes),
  `queries/pitch/p08_fraud_score_thresholds.csv` and ADR 0006 (79.6% precision at score ≥ 30 `[data]`).
- Values marked `[assumption]` (MXN and BRL tier rates, the 30-day re-evaluation window) have no external source.
