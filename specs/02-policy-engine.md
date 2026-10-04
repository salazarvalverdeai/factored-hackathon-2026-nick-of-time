# Spec 02 — Policy engine + regulatory clock

- **Feature:** pure, deterministic code that turns `contracts/policies.yaml` into decisions — zone, decision, approval
  mode per action, allowed queue transitions and legal deadlines — with the rule ids that justify each one.
- **Status:** Draft
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Technical Judgment (deterministic logic where AI is not appropriate)
- **Depends on:** `contracts/policies.yaml` · **Enables:** 03 (tools re-check permissions), 04 (decide node), 05 (queue
  transitions, supervised mode) · **ADRs:** 0005, 0006, 0012
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
- **AC-02** — If the score is null or its source is `llm`, then the zone shall be `human` with its own policy id
  (`POL-SCORE-NULL` / `POL-SCORE-LLM`), and the decision shall still open a case. · [T]
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

### 4.1 Evaluation order (first terminal rule wins)
| # | Rule id | Condition | Decision | Notes |
|---|---|---|---|---|
| 1 | `POL-SESSION` | session expired or unverified | `reauthenticate` | G-SES-01 |
| 2 | `POL-INJECTION` | input flagged by the injection detector (spec 11) | `deny` | G-IN-01, logged |
| 3 | `POL-CROSS-CUSTOMER` | request targets another customer's data | `deny` | G-SES-02, logged |
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
`[assumption]` before comparing.

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

- "Opened" = `DEMO_TODAY` in the demo (ADR 0012).
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
    intent="unrecognized_charge|wrongful_charge|inquiry|out_of_scope",
    intent_confidence=0.93, candidates=1, clarification_turns=0,
    injection_flagged=False, cross_customer=False,
    score=72.0, score_source="dataset",                     # from get_fraud_score
    amount=1250.0, currency="USD", country="MX", product_type="debit",
    customer_confirmed=None, supervised_mode=False,
))
# Decision: decision, zone, approval_modes {action: mode}, allowed_actions, handoff_reason,
#           queue_status_after, rule_ids [..], guardrail_ids [..], policies_version

engine.check(action="block_card", zone="high", amount=..., country=..., supervised_mode=False) -> Allow | Deny
deadline: Deadline = clock.deadline(country="MX", product="debit", opened_on=date(2026, 6, 3), abroad=False)
# Deadline: credit_deadline, ruling_deadline, deadline_source, calendar ("business"|"calendar"), holidays_skipped [..]
engine.transition(current="verification", action="resolve", actor="analyst:…") -> new status | Deny
engine.sla(case) -> {priority, sla_due_at, alert_due_at}
```

## 7. Data model touched
- `contracts/policies.yaml`: adds `rules:` (ids and descriptions of §4.1) and `version: 2`. No threshold changes.
- New data files: `packages/nick_of_time/policy/holidays/*_2026.yaml`.
- No database access.

## 8. Decisions (gate 1 closed by the lead, 2026-10-04; Q7 open)
- **Q1 — medium zone:** follow `policies.yaml`: after the customer confirms, the case is opened and an analyst approves
  the block (safer at 79.6% precision `[data]`); `three_zone_flow.svg` is updated in spec 13.
- **Q2 — CO:** 15 **business** days, labeled `[external, to verify]` until T3.
- **Q3 — MX credit:** 45 **calendar** days (180 if the charge was abroad).
- **Q4 — non-card products:** `deny` with a polite abstention (rule 4).
- **Q5 — supervised mode vs "the ticket is always opened":** supervised mode applies only to money actions (AC-15).
- **Q6 — LATAM coverage:** data-driven clock table; PE and CL added with verified sources; any other country falls
  back to `POL-CLOCK-UNKNOWN` (AC-14).
- **Q7 — demo date (open, lead):** the MX 2-business-day credit applies only to charges from the 48 h before the notice.
  Gold ends on 2026-05-31, so with `DEMO_TODAY=2026-06-03` no MX debit charge qualifies. Proposal: move `DEMO_TODAY` to
  **2026-06-01 (Monday)**, so charges of May 30–31 qualify and the credit deadline is 2026-06-03 (supersedes ADR 0012).
- Assumption: MXN 18.0 per USD for MX amounts (`[assumption]`, already in `policies.yaml`).
- Assumption: holiday lists are verified against official sources while implementing; each file cites its URL.

## 9. Out of scope
Calibrating thresholds with data (Q-AMT, P2); the injection detector itself (spec 11); writing to Postgres (the
callers write).

## 10. Plan, tasks and verification
Implementation goes in `feat/02-policy-engine` once this spec and spec 01 (package layout) are approved.
- [ ] T1 — Pydantic model of `policies.yaml` + loader with validation; add `rules:` and `version: 2` · FR-01, FR-07, AC-12
- [ ] T2 — `decide()` with the evaluation order of §4.1 and mode combination of §4.2 · AC-01, 02, 04, 05, 06, 07, 08, 09, 15
- [ ] T3 — `clock.deadline()` + holiday files with sources for MX, AR, CO, BR, PE, CL; re-verify every clock source · AC-03, AC-14
- [ ] T4 — `transition()` and `sla()` · AC-10, AC-11
- [ ] T5 — decision-table tests: zone × country × mode × tier, plus the boundaries 29/30/49/50 and null · AC-01…AC-13
- [ ] T6 — `docs`: policy ids listed in `/agent` content (spec 04 AC-08)

**Closing checklist:** every AC has a passing test that cites it · status → Implemented · ADR if a question above
changes a decision · lessons added to `CLAUDE.md`.
