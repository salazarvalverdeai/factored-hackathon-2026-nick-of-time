# 0021. Continuous evaluation and outcome audit: a deterministic auditor, an advisory judge and sealed regression sets

- **Status:** Proposed
- **Date:** 2026-10-04
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai (auditor and judge) · @vldiego (monitoring and regression gate)
- **Related:** specs 10, 11, 15, 17, 18 · ADRs 0006, 0007, 0015, 0016, 0018, 0022 (proposed)

## Context
- The agent verifies its own actions (`verify` node), and the analyst decides escalated cases. Nothing independent
  re-checks what the agent told the customer.
- ADR 0018 closes the data loop (operation → medallion → `ops_kpis` and `feedback_cases`). It does not say how a release
  is gated, how quality is watched in production, or how new data enters evaluation without breaking comparability.
- Bank model-risk guidance asks for effective challenge by an independent party, outcomes analysis and ongoing
  monitoring. SR 26-2 (April 2026) leaves generative and agentic AI out of scope but asks banks to govern them with
  their own practices; NIST AI RMF asks that AI systems be monitored in production (MEASURE 2.4, MANAGE 4.1).
- The classifier's test split is small, so a measurement is only comparable over time if the split never changes
  (spec 11 §4.1).
- The system now has several models: the bank's score (a vendor model), our fraud model (spec 17), the intent
  classifier and the injection detector (spec 11), an LLM per task (spec 15) and the judge (spec 18). SR 26-2 calls a
  model inventory common industry practice.

## Decision
0. **Model inventory.** `docs/models.md` lists every model in use: purpose, owner, version, data window, metrics, gate
   and monitoring. The release gate and the monitoring below apply to every model in it, the bank's score included.
1. **Auditor = deterministic pipeline (second line).** `nick_of_time.audit` re-derives each run's decision, deadline,
   verified actions and facts from its records and stores findings in `audit_findings`. The same functions compute the
   harness's final-state checks (spec 18).
2. **Judge = advisory LLM for the analyst.** A second opinion on cases in review, every reason tied to evidence, labeled
   advisory; it never decides or changes state. Its model is a spec 15 task, and its agreement with analysts is measured.
3. **Sealed, versioned evaluation sets.** The v1 splits (spec 10 held-out, spec 11 test) are the regression suite of
   every release and never change. Production data (analyst decisions in `feedback_cases`) becomes a **new** sealed set
   (v2, v3…), reported side by side with v1, never merged into it.
4. **Release gate.** Every release runs the regression suite; any unsafe outcome or a floor below spec 11 §4.1 blocks it.
5. **Production monitoring.** Intent and language mix, share below τ, `receipt_rate`, `coherence_rate`, auditor
   findings per 100 runs, judge–analyst agreement, cost and p95 feed `ops_kpis`; ADR 0018's review triggers act on them.
6. **Champion / challenger.** The spec 15 benchmark is re-run when a new model appears or the cost passes the budget;
   a challenger replaces the champion only through the lean rule and the production gate. Real customer text goes only
   to models that passed that gate.
7. **Phasing.** P0: this ADR, the model inventory, spec 18's shared library used by the harness and the judge in the
   console, spec 17's benchmark of our fraud model against the bank's score. P1: the online auditor and its console
   panel. P2: the release gate for every model in the inventory as a nightly CI job, drift monitors, champion /
   challenger, the v2 set.

```
 1st line (operates)                  2nd line (independent)                         3rd line (assures)
 customer → agent → MCP tools → DB ─┬→ auditor per run → audit_findings → console flag   regression suite (sealed v1)
                                    ├→ judge (cases in review) → second opinion          on every release, for every
                                    │                                                    model in the inventory + human
                                    └→ ops medallion (ADR 0018) → KPIs → review triggers  sample review
 analyst decisions → feedback_cases → new sealed set v2 → reported beside v1
 new model or cost over budget → benchmark (spec 15) → champion / challenger → model-selection ADR
```

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Deterministic auditor + advisory judge (chosen) | Reproducible, cheap, explainable; the judge adds judgment where rules cannot | Two components to maintain |
| An LLM agent as auditor | Flexible, reads anything | Shares the agent's failure modes; not reproducible; costs tokens per run |
| Rely on the agent's own `verify` node | No extra work | Not independent: the same code checks itself |
| Human sample review only | Simple | Slow; misses most runs |

## Consequences
- Easier: a judge can see that the system checks itself independently; analysts get evidence-backed help; evaluation and
  monitoring share one definition of "correct".
- Harder: records must be complete enough to replay a run (inputs, tool results, policy version); the judge needs
  calibration before it is trusted beyond advice.
- Neutral: ADR 0018 stays; this ADR adds the gates and the auditor on top of it.

## Confidence
Medium-high for the auditor and the sealed sets; medium for the judge until AC-14 of spec 18 is measured.

## Sources
- SR 26-2, *Revised Guidance on Model Risk Management* (17 April 2026) — effective challenge, outcomes analysis,
  ongoing monitoring, model inventory: https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf
- NIST AI RMF 1.0 (NIST AI 100-1): https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- Zheng et al., *Judging LLM-as-a-Judge* (NeurIPS 2023): https://arxiv.org/abs/2306.05685
- Internal: ADR 0018, spec 11 §4.1, spec 15 §4.4–4.5, spec 17, spec 18. Checked on 2026-10-04.
