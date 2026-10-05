# Spec 02 — Policy engine + regulatory clock

- **Feature:** pure, deterministic code that turns `contracts/policies.yaml` into decisions — zone, decision, approval
  mode per action, allowed queue transitions and legal deadlines — with the rule ids that justify each one.
- **Status:** In progress (T1, T2, T4 and T5 done; gate 1 closed; Q7 closed by ADR 0020 on 2026-10-04; adds
  `clock.today(mode)`, display currency and the re-evaluation window)
- **Owner:** @salazarvalverdeai · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Technical Judgment (deterministic logic where AI is not appropriate)
- **Depends on:** `contracts/policies.yaml` · **Enables:** 03 (tools re-check permissions), 04 (decide node), 05 (queue
  transitions, supervised mode) · **ADRs:** 0005, 0006, 0019, 0020 (supersedes 0012), 0023 (amends 0019 and
  0020), 0024
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
- **AC-03** — When a MX debit or credit dispute is opened for a charge made within the 90 calendar days before the
  notice, `credit_deadline` shall be the second business day after opening (opened 2026-06-01 → 2026-06-03) and
  `ruling_deadline` opening + 45 calendar days (+180 if the charge was abroad), with its Banxico source (Circular 3/2012
  art. 19 Bis 3 fr. II for debit, Circular 34/2010 numeral 3.4 b) for credit; ADR 0023); for an older MX
  charge it shall be the LTOSF art. 23 ruling deadline only; an AR dispute shall get a ruling deadline of +10 business
  days and no credit deadline (BCRA t-pusf 3.1.6; ADR 0023) and a CO dispute +15 business days, skipping
  weekends and the country's 2026 holidays; a PE dispute shall get +15 business days (SBS) and a CL dispute a refund
  deadline of +10 business days (+15 for cash advances and ATM withdrawals) and +7 more for the part above 35 UF
  (Ley 20.009). · [T]
- **AC-04** — While `supervised_mode` is on, every money action (AC-15) shall have approval mode `human_required`. · [T]
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
- **AC-19** — When a call request reports a charge on one identified card transaction the customer did not reject, at
  intent confidence ≥ τ, the decision shall be `connect_person` with `open_case` only, no block in any zone and the
  call on the opened case; in the high zone the case shall wait in `review` with `person_requested`, unless the amount
  tier or supervised mode already needs a person (that reason instead); and after the mode check, `check()` with
  `call_requested` true shall deny every money action citing `POL-HUMAN-REQUEST`, also on a later turn whose decision
  would block, since the tool passes the flag until the analyst runs `approve_block`, `resolve` or `close_case`
  (D-042, D-043, ADR 0024). · [T]

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
| 3 | `POL-CROSS-CUSTOMER` | request targets another customer's data | `deny` | G-SES-02, logged. `[assumption]` (EV-0116, spec 10 T6 dev run): when rule 2 also fires, the deny cites both (`POL-INJECTION`, `POL-CROSS-CUSTOMER`; G-IN-01 and G-SES-02), so the deny records G-SES-02 when rules 2 and 3 both fire (D-074, pending the lead) |
| 3a | `POL-HUMAN-REQUEST` | intent `human_request` | `connect_person` | `request_call` on the active case, or a general request; never refused (CFPB 2023). If the message also reports a charge (`dispute_detected`), 3a is not terminal (D-020): the call goes on the case opened for the one card transaction, and that case follows rules 6–9 like a confirmed dispute, except that nothing is blocked in that turn (D-029, ADR 0024, AC-19): the analyst decides the block after the call, and the block stays held until the analyst approves the block, resolves or closes the case (D-042). `check()` enforces it on the tool side: after the mode check, with `call_requested=True` it denies a money action citing `POL-HUMAN-REQUEST`. τ gates this case-opening branch (D-031, decided 2026-10-04): below τ only the call is registered (`active_or_general`), and nothing is opened or blocked (spec 04 AC-02). High zone: `connect_person`, `open_case` only, case in `review` with `person_requested`; when the block needs a person anyway (amount tier, supervised mode), that reason instead. Medium and human zones: `connect_person`, `open_case` only (never a block, no confirmation asked), case in `review` with `zone_medium` / `zone_human`. With no single card transaction, or one the customer rejected (`customer_confirmed` false), only the call (`active_or_general`) |
| 3b | `POL-STATUS` | intent `status_inquiry` | `answer_status` | read-only: the agent re-reads cards or cases (spec 04 AC-19); no case is opened. With `dispute_detected` and `active_case` false (the customer has no active case), 3b is not terminal: the turn goes on like a dispute (rules 4–9), citing `POL-STATUS` first (D-020). With an active case, or `active_case` not known (null), the status is answered |
| 4 | `POL-OUT-OF-SCOPE` | intent `out_of_scope` with confidence ≥ τ and no reported charge (below τ, rule 5 asks; D-024), or the one identified transaction's product is not a card | `deny` (polite abstention) | G-IN-04. Never for `human_request`. With `dispute_detected` the intent branch is off and rule 5 asks: a message that reports a charge never gets an abstention for its label alone (D-032, the D-020 default pending the lead); the product branch still applies. `product_type` also takes the gold labels `Tarjeta Débito` / `Tarjeta Crédito`; one candidate without a product type is an input error |
| 5 | `POL-CLARIFY` | confidence < τ, or candidates > 1 (≤ 3), or candidates = 0, or intent `out_of_scope` with a reported charge (D-032) | `ask` (≤ 2 turns) | then rule 5b |
| 5b | `POL-CLARIFY-EXHAUSTED` | clarification turns already sent ≥ `clarify.max_clarification_turns` (2) | `handoff` (`clarification_exhausted`) + a general call request (`RequestCallIn.case_id = null`) so a person gets it (D-024) | |
| 6 | `POL-SCORE-NULL` / `POL-SCORE-LLM` / `POL-SCORE-SOURCE` | score null, source `llm`, or a source not in `scoring.deciding_sources` (`dataset`, `rules`, `model`, `synthetic`) | zone `human` | case is still opened. A `synthetic` score (live mode) decides and is labeled `[simulated]` (§7, D-027) |
| 7 | `POL-ZONE-HIGH` | score ≥ 50 | `block_and_open_case` | block mode from §4.2 |
| 8 | `POL-ZONE-MEDIUM` | 30 ≤ score < 50 | `confirm`, then see §4.2; "not that charge" → rule 5 / 5b `[assumption]` | customer confirmation required |
| 9 | `POL-ZONE-HUMAN` | score < 30 | `handoff` (`zone_human`) | case opened, no block |
| — | `POL-DEFAULT-DENY` | any action no rule allows | deny | `default: deny` |

`POL-TICKET-ALWAYS`: in every zone that reaches rules 6–9, `open_case` is allowed with mode `auto` (registering is not
a money decision). `screen()` runs rules 1–4 only (spec 04 `route`, before the transaction is retrieved); it returns
nothing for a dispute and for a call request or status question that goes on to the dispute path (rules 3a and 3b with a
charge), which `decide()` completes; on that path every result cites `POL-HUMAN-REQUEST` or `POL-STATUS` first. τ gates
rules 4 (intent branch) and 5; rules 3a and 3b match the intent label at any confidence. `clarification_turns` counts
the clarification questions already sent to the customer. `[assumption]` (7) A `clarification_exhausted` handoff opens
no case (there is no single transaction) and registers a general call instead. (8) Rule 1 passes only when
`session_state` is exactly `verified`. `injection_flagged`, `cross_customer`, `supervised_mode` and `dispute_detected`
have no default: a caller that omits one gets an error (fail closed). They and `customer_confirmed` / `active_case` are
strict bools: `0`, `1`, `"off"` or `"true"` are input errors, as in `check()`.

### 4.2 Approval modes and what happens to the case
| Zone | `block_card` mode (policies) | Effective mode = stricter of mode, amount tier, supervised | Case status after the turn |
|---|---|---|---|
| high | `manual_check` | `manual_check` → block now, verify, case in `verification`, unless the customer asked for a person in that turn: no block, `review` with `person_requested`, and the analyst decides the block after the call (D-029) · `human_required` → no block, handoff | `verification` or `review` |
| medium | `human_required` | after the customer confirms: open case + handoff proposing `approve_block` | `review` |
| human | not allowed | — | `review` |
| any | `provisional_credit`: `human_required` | always a person (AC-09) | — |

Amount tiers per country (`amount_gate.by_country`, local currency): `≤ low` → `auto`, `≤ high` → `manual_check`,
`> high` → `human_required`. MX transactions are in USD in the dataset and are converted at 18.0 MXN/USD
`[assumption]` before comparing. Each entry's `usd_rate` is a threshold-conversion parameter, never shown to a customer
(customer-facing amounts use §4.4): COP 4,000 and ARS 350 are the gold's implied rates `[data]`
(`queries/policy/implied_usd_rate.sql`); MXN 18.0 and BRL 5.5 stay `[assumption]` (the gold has no MXN or BRL amounts).
When the tier or supervised mode makes a money action stricter than `approval.per_action`, the result cites
`POL-AMOUNT-GATE` or `POL-SUPERVISED`. `[assumption]` When no tier applies (a country without an entry such as PE or CL,
an amount missing, negative or not finite, or a currency other than the entry's or USD) the mode is `human_required` and
the result cites `POL-AMOUNT-UNKNOWN`. A result carries a `handoff_reason` exactly when it is a `handoff` or it leaves a
case in `review` (D-024, and the rule 3a cases of D-020, so every handoff card in the analyst queue has a reason):
`zone_human`, `zone_medium`, `amount_over_case_gate` (over the gate or no tier), `supervised_mode`,
`person_requested` (a high-zone call request, D-029) or `clarification_exhausted` (a handoff with no case). `check()`
answers for automated callers and requires `supervised_mode` and `call_requested` (the customer asked for a person and
the hold has not ended, D-042) as bools (`None` or a missing flag raises `TypeError`, never "off"). The mode check
comes first: `human_required` is a `Deny` citing the rule that raised the mode, else `POL-DEFAULT-DENY`. Then, after
the mode check, `check()` denies a money action when `call_requested` is true, citing `POL-HUMAN-REQUEST` (D-029, ADR
0024). The hold lasts until the analyst runs `approve_block`, `resolve` or `close_case` (D-042): `decide()` reads no
store (D-043), so the `block_card` tool passes `call_requested` true while the case has an open call (spec 03 §8), and
a later turn whose decision would block is denied there.

### 4.3 Regulatory clock (LATAM, data-driven)
The clock is a **table of verified country entries** in `policies.yaml`, not code. Each entry carries the regulator, the
legal basis, what the deadline is (refund / provisional credit or ruling / response), the number of days, business or
calendar, the official source URL and the date it was verified. **Adding a LATAM country is a PR with a source and a
test, no code change.** A country without a verified entry falls back to `POL-CLOCK-UNKNOWN` (AC-14).

| Country · product | `credit_deadline` | `ruling_deadline` | Legal basis | Official public source | Verified |
|---|---|---|---|---|---|
| MX · debit, charge within the **90 calendar days** before the notice | opened + **2 business days** (provisional credit) | opened + **45 calendar days** (ruling; 180 if the charge was abroad) | Banxico Circular 3/2012, arts. 19 Bis 3 fr. II and 19 Bis 4, as amended by Circular 14/2018 (in force since 2019-09-26) | [Banxico, compiled text](https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-3-2012/%7B4E0281A4-7AD8-1462-BC79-7F2925F3171D%7D.pdf) · [DOF, Circular 14/2018](https://dof.gob.mx/nota_detalle.php?codigo=5539863&fecha=03/10/2018) | 2026-10-04 |
| MX · debit, older charge | — | opened + **45 calendar days** `[assumption]`: art. 23 says "días" without defining them (180 if the charge was abroad) | LTOSF art. 23 fr. II (clarifications) | [Orden Jurídico Nacional, LTOSF](https://www.ordenjuridico.gob.mx/Documentos/Federal/pdf/wo46.pdf) | 2026-10-04 |
| MX · credit, charge within the **90 calendar days** before the notice | opened + **2 business days** (provisional credit) | opened + **45 calendar days** `[assumption]`: numeral 3.6 says "días" without defining them (ruling; 180 if the charge was abroad) | Banxico Circular 34/2010, numerals 3.4 b) and 3.6, as amended by Circular 13/2018 | [Banxico, compiled text](https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-34-2010/%7B0C55B906-6DB4-6B88-FED0-67987E9FB3CC%7D.pdf) | 2026-10-04 |
| MX · credit, older charge | — | opened + **45 calendar days** `[assumption]`: art. 23 says "días" without defining them (180 if the charge was abroad) | LTOSF art. 23 fr. II | [Orden Jurídico Nacional, LTOSF](https://www.ordenjuridico.gob.mx/Documentos/Federal/pdf/wo46.pdf) | 2026-10-04 |
| AR · any card | — (item 2.3.5.1's 10-day reimbursement lists charges the bank itself generates, not a third party's unrecognized charge) | opened + **10 business days** (resolution, item 3.1.6) | BCRA, Protección de los Usuarios de Servicios Financieros (texto ordenado al 2026-05-06) | [BCRA t-pusf](https://www.bcra.gob.ar/archivos/Pdfs/texord/t-pusf.pdf) | 2026-10-04 |
| CO · any card | — | opened + **15 business days**, extendable once up to double (Ley 1755 de 2015, art. 14, parágrafo); business days per Ley 4 de 1913, art. 62, counted Monday–Friday `[assumption]` | SFC: petitions to supervised entities (Ley 1755 de 2015, art. 14) | [SFC FAQ](https://www.superfinanciera.gov.co/preguntas-frecuentes/3/3-derechos-de-peticion-ante-entidades-vigiladas/) · [Ley 4 de 1913](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=8426) | 2026-10-04 |
| BR · any card (PT demo only) | — | opened + **10 business days**, extendable once by an equal period `[to verify]`: whether the SAC term of Decreto 11.034/2022, art. 13 (7 calendar days, first level) reaches banks | Resolução CMN 4.860/2020, art. 6, § 2 (ouvidoria, second level) | [BCB, Resolução CMN 4.860](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolu%C3%A7%C3%A3o%20CMN&numero=4860) | 2026-10-04 |
| PE · any card | — | opened + **15 business days** (extendable only when a third party must rule) | Resolución SBS N.° 04036-2022 | [El Peruano](https://busquedas.elperuano.pe/normaslegales/aprueban-el-reglamento-de-gestion-de-reclamos-y-requerimient-resolucion-sbs-no-04036-2022-2138687-1) | 2026-10-04 |
| CL · any card | opened + **10 business days** up to 35 UF (15 for cash advances and ATM withdrawals); +7 more days for the part above 35 UF | — | Ley 20.009 | [SERNAC](https://www.sernac.cl/portal/604/w3-propertyname-791.html) | 2026-10-04 |
| any other LATAM country | — | — | `POL-CLOCK-UNKNOWN`: case opened, routed to a person, no deadline invented |

- "Opened" = `clock.today(mode, country)`: `DEMO_TODAY = 2026-06-01` in `replay`, the real date in the country's time
  zone in `live` (ADR 0020). Example: a MX debit notice on Monday 2026-06-01 about a charge on 2026-05-31 →
  credit by Wednesday 2026-06-03.
- **MX and AR rows (ADR 0023; the article quotes are there):** the 48 h window of Circular 3/2012 art. 19
  Bis 3 fr. I and Circular 34/2010 numeral 3.4 a) applies only to a theft or loss notice, so it is not modeled; a
  claim of unrecognized charges (fr. II, numeral 3.4 b)) qualifies when filed within 90 calendar days of the charge
  ("Días" are calendar days, Circular 3/2012 art. 2), on debit and credit alike. Day 90 qualifies, the 45 days of
  Circular 34/2010 and LTOSF count as calendar days `[assumption]` — each the reading with the earlier deadline. The
  clock computes the credit date for both dispute types; the receipt shows it only for an unrecognized or duplicate
  charge, and for other wrongful charges it drives only the AC-11 SLA (D-030, decided by the lead on 2026-10-04; ADR
  0019 point 3). The 48 h figure came from a
  [CONDUSEF press release of 2018-10-03](https://www.gob.mx/condusef/prensa/cargos-no-reconocidos-en-tarjeta-de-debito-se-restituiran-en-dos-dias-habiles-bancarios?idiom=es)
  (checked 2026-10-04) that summarizes fr. I only. AR promises only the resolution date (t-pusf 3.1.6); when an
  analyst finds the charge is one the bank itself generated (the list in item 2.3.5.1), the reimbursement is due by
  that same date, and the receipt never promises it.
- **Coverage note:** the dataset only has MX, CO and AR customers, so PE, CL and BR are exercised by unit tests and
  fixtures; the demo runs on MX, CO and AR (BR in Portuguese with a fixture). The README states it.
- **Every entry cites its official public source and the date it was verified** (ADR 0019); `policies.yaml` stores them as
  `source_url` and `verified_on` fields plus a comment, and a test fails if an entry lacks them. Rows marked
  `[external, to verify]` are re-checked in T3. Each entry also has a `source_label` with the customer's `es` and `pt`
  name of the same source and `source_url` (task DLANG; `clock.source_label()`): the customer never reads the
  analyst's English `source`, and the agent never translates it (constitution #5).
- Business days = Monday–Friday minus the country's bank holidays. A day whose bank closure is not certain (e.g. AR
  "días no laborables", BR Good Friday) counts as a business day `[assumption]`, so a deadline can only
  come earlier, never later, except CO's Monday–Friday count (CO row). A count that reaches a year with no holiday file returns no deadline at all, not even a calendar-day term of the same
  entry (`POL-CLOCK-UNKNOWN`; no date is invented). In live mode from mid-December this holds until the next
  year's calendars are added. Holiday files are validated when `policies.yaml` loads (FR-01).
- Holiday lists live in `packages/nick_of_time/policy/holidays/{mx,ar,co,br,pe,cl}_2026.yaml`, each with the official source
  URL; they are `[external]` data, not code.
- The charge's age is counted between local dates in the country's time zone; day 90 still qualifies `[assumption]`.
  `charged_at` is a timezone-aware datetime (spec 01: timestamps are UTC) or a date; a naive datetime is rejected.
  A date one day after the notice date counts as the same day, since a UTC date can lead the local date
  `[assumption]`; a UTC charge date likewise shifts the 90-day boundary by one day, so a charge on local day 91 may
  be counted as day 90 and qualify, which gives an earlier deadline, never a later one. The clock raises if a charge-age row (MX) gets no charge date.
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

### 4.5 Analyst queue (FR-06, AC-10, AC-11)
`queue.transition()` and `queue.sla()` live in `policy/queue.py` as functions over the loaded policies, like the clock,
so the queue adds no method to `PolicyEngine`. Analyst actions (`AnalystActionIn.action`) follow D-034:

| Action | Starts from | Status after |
|---|---|---|
| `take` | `new`, `verification`, `review` | `review` `[assumption]`: the only D-034 target allowed from all three |
| `resolve` | `verification`, `review` (`case_queue.transitions`) | `resolved` |
| `close_case` | `resolved` | `closed` |
| `reopen_case` | `resolved` | `review` |
| `approve_credit`, `approve_block`, `unblock_card`, `request_customer_info`, `mark_ambiguous` | any but `closed` | unchanged |

The agent's write tools (spec 03 `open_case`, `block_card`) move a case through `store.change_status`, which checks the
same `case_queue.transitions` table, not through `queue.transition()`, which is for analyst actions only `[assumption]`
pending D-063.

A closed case takes no analyst action; any other move is `POL-QUEUE-TRANSITION`, an unknown action
`POL-DEFAULT-DENY`. Every analyst action needs a person (`analyst:<sub>`, sub not blank): `close_case` by anyone else
is `POL-CLOSE-HUMAN`, any other action `POL-DEFAULT-DENY` `[assumption]`. The loader types `case_queue` and refuses a
queue where something leaves `closed`, a status other than `resolved` reaches `closed`, a status is missing, an
`sla_hours` value is not positive, or a `deadline_sla` alert is not after its priority rise.

`sla()` gives `sla_due_at` = the time the case entered its status + `sla_hours` (none for `new`, `resolved` and
`closed`). For an open (not resolved or closed) case in a `deadline_sla` scope (MX debit), priority is `high` from
business day 1 after `opened_on` and `alert_due_at` is local midnight at the start of business day 2 (§4.3). `[assumption]`
It applies to every open MX debit case, as AC-11 reads, with or without a credit deadline; a count past the last
holiday file gives priority `high`, no alert time and `POL-CLOCK-UNKNOWN`. "Today" is an argument (AC-16).

## 5. Non-functional requirements
- **Performance:** `decide()` < 5 ms p95 (pure Python, policies cached).
- **Security:** read-only access to `policies.yaml`; no environment variable can loosen a rule (only `supervised_mode`
  can make it stricter).
- **Observability:** the result is serializable; the graph writes it to the trace and `policy_denials` writes the denials.

## 6. API (Python, `nick_of_time.policy`)
```python
engine = PolicyEngine.load("contracts/policies.yaml")      # validates; exposes engine.version

decision: PolicyDecision = engine.decide(DecisionInput(
    session_state="verified|expired|unverified",
    intent="unrecognized_charge|wrongful_charge|status_inquiry|human_request|out_of_scope",
    intent_confidence=0.93, candidates=1, clarification_turns=0,
    injection_flagged=False, cross_customer=False, dispute_detected=False,   # required, like supervised_mode
    score=72.0, score_source="dataset",                     # from get_fraud_score
    amount=1250.0, currency="USD", country="MX", product_type="debit",
    customer_confirmed=None, supervised_mode=False,
    active_case=None,                                       # rule 3b: False = no active case; None = not read yet
))
# customer_confirmed refers to the currently selected transaction: None = not asked, False = "not that charge".
#   Spec 04 resets it to None whenever selected_transaction changes, so a stale rejection never reaches a new charge.
# PolicyDecision: decision (contracts.Decision), zone, approval_modes {action: mode}, allowed_actions, handoff_reason,
#           request_call, queue_status_after, rule_ids [..], guardrail_ids [..], policies_version
# request_call: where to register the call request (RequestCallIn), or None for no call:
#   "active_or_general" - rule 3a: on the customer's active case if there is one, else a general request
#   "opened_case"       - rule 3a with a charge: on the case open_case returned this turn, which is the existing case
#                         when open_case reports duplicate_of (spec 03 AC-15)
#   "general"           - rule 5b: a general request (RequestCallIn.case_id = null); no case was opened
engine.screen(input) -> PolicyDecision | None              # rules 1–4 only; None = a dispute, go on (spec 04 route)
engine.amount_tier(amount=1250.0, currency="USD", country="MX") -> "auto" | "manual_check" | "human_required"
engine.check(action="block_card", zone="high", supervised_mode=False, call_requested=False,
             amount=..., currency=..., country=...) -> Allow | Deny   # call_requested: an open call (D-029, D-042)
today: date = clock.today(mode="replay", country="MX")     # 2026-06-01 in replay; the real local date in live
add_by: date = clock.add_business_days(country="MX", start=today, n=1)   # 2026-06-02 in replay (D-008)
# callback date for request_call; task 02b implements it in T3 with a unit test (2026-06-01 + 1 → 2026-06-02)
deadline: Deadline = clock.deadline(country="MX", product="debit", opened_on=today, abroad=False)
# Deadline: credit_deadline, ruling_deadline, deadline_source, source_url, verified_on, calendar {credit|ruling:
#   "business"|"calendar"}, holidays_skipped [..], extendable_once, rule_ids, policies_version; charged_at= (aware datetime
#   or date) is required for a charge-age row (MX). Computed once at opening and stored (spec 03 AC-16).
queue.transition(current="verification", action="resolve", actor="analyst:…") -> Moved | Deny   # §4.5
# Moved: action, previous, status (the next status_changed `to`; = previous when the action keeps it), rule_ids,
#   policies_version. The api appends the event; the status stays the last event (append-only).
queue.sla(QueueCase(status, status_since, country, product_type, opened_on), today=today)
#   -> Sla: priority "normal"|"high", sla_due_at, alert_due_at, rule_ids (case_queue keys), policies_version
engine.reevaluation_allowed(country="MX", resolved_on=date(...), today=today) -> Allow | Deny("POL-REEVAL-WINDOW")
fx.convert(amount=1250.0, from_currency="USD", to_currency="MXN") -> {amount, rate, rate_source, as_of} | None
```

## 7. Data model touched
- `contracts/policies.yaml`: adds `rules:` (every id this spec names, each with its text and guardrail: those of §4.1,
  `POL-SCORE-SOURCE` for a score from a source that does not decide, `POL-AMOUNT-GATE`, `POL-AMOUNT-UNKNOWN` and
  `POL-SUPERVISED` for a stricter mode in §4.2, `POL-CLOCK-UNKNOWN`, `POL-QUEUE-TRANSITION`, `POL-CLOSE-HUMAN` and
  `POL-REEVAL-WINDOW`; spec 03 adds `POL-ZONE-MISMATCH`, G-IN-02, for its `open_case` zone check, D-060),
  `scoring.deciding_sources` (the sources whose score places a zone: `dataset`, `rules`,
  `model` and `synthetic`; never `llm`) with a `scoring.providers.synthetic` entry,
  `approval.money_actions` (AC-15), `usd_rate` per `amount_gate.by_country` entry (§4.2), the handoff reasons
  `zone_medium` and `supervised_mode` (also in `contracts/handoff.schema.json`), per-country `time_zone`,
  `display_currency` and `fx_reference`, the `reevaluation` section, and `version: 2`; validates
  `contact.callback_within_business_days` (D-008, task 02b). No threshold changes.
- `contracts/handoff.schema.json` and `handoff.triggers` gain the reason `person_requested` (D-029), mirrored by
  `HandoffReason` in the engine.
- `version` stays 2 through D-029 because no version-2 decision has been recorded or deployed yet. Once decisions are
  recorded (spec 18 A1 re-runs `decide()` at the same `policies_version`), any change in behavior bumps `version`.
- `contracts/handoff.schema.json` also gains the optional `score_source` (the `GetFraudScoreOut.source` values) and
  `score_version` (D-033, default pending the lead), so `record_source_in_audit` reaches the analyst's card.
- The loader (FR-01) also refuses a file that breaks a firm rule: `default` other than `deny`, `open_case` not `auto`
  or `provisional_credit` not `human_required` in every zone, `block_card` other than `manual_check` in the high zone
  and `human_required` in the medium and human zones (§4.2), `unblock_card` not `human_required` in every zone,
  `close` not `human_only`, zone bands with gaps, tiers that loosen as the amount grows, a rule citing an unknown
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
- **Q3 — MX credit:** 45 **calendar** days (180 if the charge was abroad). For a claim within 90 calendar days of the
  charge, Circular 34/2010 numeral 3.4 b) also sets a provisional credit by business day 2 (ADR 0023).
- **Q4 — non-card products:** `deny` with a polite abstention (rule 4).
- **Q5 — supervised mode vs "the ticket is always opened":** supervised mode applies only to money actions (AC-15).
- **Q6 — LATAM coverage:** data-driven clock table; PE and CL added with verified sources; any other country falls
  back to `POL-CLOCK-UNKNOWN` (AC-14).
- **Rules 3a–3b (added 2026-10-04 with the five intents of spec 11):** a request for a person and a status question
  are answered after the security checks (rules 1–3) and before the dispute rules; every reply, including
  `reauthenticate` and `deny`, still offers a way to a person (spec 04 AC-20).
- **Q7 — demo date:** ~~move `DEMO_TODAY` to 2026-06-01?~~ **Decided (lead, 2026-10-04):** two time modes (ADR 0020).
  `replay` uses `DEMO_TODAY = 2026-06-01` (Monday, the first day after the gold window), so every MX
  charge dated 2026-03-03 to 2026-05-31 (≤ 90 calendar days before) gets the business-day-2 credit, debit and credit
  alike (ADR 0023, which replaces the earlier 48 h rationale); `live` uses the real date with labeled
  synthetic transactions (in October every gold charge is more than 90 days old, so only these show the
  business-day-2 credit). The clock receives "today" from the mode (AC-16).
- **D-029 — a call request in the high zone (decided by the lead, 2026-10-04; ADR 0024, AC-19):** a call request
  that reports a high-zone charge does not block the card. The agent opens the case and registers the call; the case
  waits in `review` with `person_requested`, and the analyst decides the block after the call. Medium and human zones
  do not change. `check(call_requested=True)` withholds the block on the tool side too. `POL-HUMAN-REQUEST` and
  `POL-ZONE-HIGH` state the exception.
- **D-042 — how long the D-029 hold lasts (decided by the lead, 2026-10-04; end condition 2026-10-05; ADR 0024,
  AC-19):** until the analyst runs `approve_block`, `resolve` or `close_case` on the case, not only in the turn of the
  call request; `take`, `request_customer_info`, `mark_ambiguous` and any other analyst action keep it.
  `call_requested` is read from the store while a call is open on the case (spec 03 §8, task 03c), so a later
  plain-dispute turn about the same transaction cannot block either.
- **D-043 — the later-turn block (decided by the lead, 2026-10-05; ADR 0024, AC-19):** `decide()` stays without the
  store and `DecisionInput` gains no field. While the hold is open, a later turn whose decision proposes `block_card`
  is denied by the tool's `check()` re-check citing `POL-HUMAN-REQUEST`, and the agent reports it as not done.
- Assumption: MXN 18.0 per USD for the MX amount tiers (`[assumption]`, already in `policies.yaml`); it is never shown to
  a customer — customer-facing conversions use the official reference rate of §4.4.
- Assumption: holiday lists are verified against official sources while implementing; each file cites its URL.
- **T3 finding (2026-10-04; ADR 0023; default applied by D-028):** the official text of art. 19 Bis 3 (Banxico
  compiled text through Circular 11/2026) ties the 48 h window to a **theft or loss** notice (fr. I); a claim of
  unrecognized charges is credited by business day 2 when filed within **90 calendar days** of the charge (fr. II;
  "Días" are calendar days, art. 2), and art. 19 Bis 4 sets the ruling at 45 days. CONDUSEF's 2018 press release
  summarizes it as "48 horas previas". Circular 34/2010 numerals 3.4 b) and 3.6 set the same rule for credit cards.
  The clock follows the official texts; an hours window (`when_charged_within: {hours: 48}`) is supported and tested.

## 9. Out of scope
Calibrating thresholds with data (Q-AMT, P2); the CO e-commerce payment reversal of Ley 1480 de 2011,
art. 51 (P1, `[external, to verify]`); the injection detector itself (spec 11); writing to Postgres (the
callers write).

## 10. Plan, tasks and verification
Implementation goes in `feat/02-policy-engine` once this spec and spec 01 (package layout) are approved.
- [x] T1 — Pydantic model of `policies.yaml` + loader with validation; add `rules:` and `version: 2` · FR-01, FR-07, AC-12
- [x] T2 — `decide()` with the evaluation order of §4.1 and mode combination of §4.2 · AC-01, 02, 04, 05, 06, 07, 08, 09, 15, 19
- [ ] T3 — `clock.deadline()` + holiday files with sources for MX, AR, CO, BR, PE, CL; re-verify every clock source · AC-03, AC-14
      (MX, AR, CO and BR done with `add_business_days` (D-008); PE and CL pending: until then they get `POL-CLOCK-UNKNOWN`)
- [x] T4 — `transition()` and `sla()` (`policy/queue.py`, §4.5) · AC-10, AC-11
- [x] T5 — decision-table tests (`tests/test_spec02_table.py`): zone × country × mode × tier, plus the boundaries 29/30/49/50 and null · AC-01…AC-13
- [ ] T6 — `docs`: policy ids listed in `/agent` content (spec 04 AC-08)
- [ ] T7 — `clock.today(mode, country)`, time zones, `fx_reference` values from the official series with `as_of`
      and `verified_on`, `fx.convert()`, `reevaluation_allowed()` · AC-16, AC-17, AC-18 (`today` and time zones done;
      fx and re-evaluation pending)

**Closing checklist:** every AC has a passing test that cites it · status → Implemented · ADR if a question above
changes a decision · lessons added to `CLAUDE.md`.

## 11. Sources
External sources checked on 2026-10-04; the clock's legal sources are in the table of §4.3 (with the MX and AR
article quotes in ADR 0023) and the reference-rate sources in the table of §4.4.
- CFPB, *Chatbots in consumer finance* (6 June 2023), on not blocking access to a person (rule 3a):
  https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/
- IANA time zone database (zone names of §4.4): https://www.iana.org/time-zones
- Internal: `contracts/policies.yaml` (`amount_gate`, `approval`, `case_queue`, `regulatory_clock`),
  `contracts/gold_contract.md` R1 (gold ends 2026-05-31), ADR 0019 (official sources), ADR 0020 (two modes),
  `queries/pitch/p08_fraud_score_thresholds.csv` and ADR 0006 (79.6% precision at score ≥ 30 `[data]`).
- Values marked `[assumption]` (MXN and BRL tier rates, the 30-day re-evaluation window) have no external source.
