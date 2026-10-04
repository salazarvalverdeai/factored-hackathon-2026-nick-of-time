# Spec 11 — Intent classifier, injection detector and selection protocol

- **Feature:** the learned components the challenge asks to compare against a baseline — the ES/PT intent and slot
  classifier and the injection detector — plus the pre-registered protocol that decides which arm ships.
- **Status:** Draft
- **Owner:** @salazarvalverdeai (protocol reviewed by @vldiego) · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Machine Learning
- **Depends on:** 09 (labeled sentence set) · **Enables:** 04 (understand node), 15 (benchmark B1) · **ADRs:** 0015, 0016
- **Issue:** #13

> Full profile: the comparison against a baseline is a challenge requirement (organizers, 2026-09-29).

---

## 1. Introduction
Understanding a dispute message means three things: the **intent** (unrecognized charge, wrongful charge, inquiry,
out of scope), the **slots** that find the transaction (amount, currency, date, merchant) and whether the message is an
**injection**. This spec builds a rules baseline and learned alternatives, compares them on the same frozen test, and
picks one with a rule written before any result is seen. The conclusion is reported whether or not a model wins.

## 3. Acceptance criteria (EARS)
AC-01 to AC-05 come from issue #13 with the same numbers; AC-06 onward are added by this spec.

- **AC-01** — `eval/PROTOCOL.md` shall be reviewed by Diego, approved and sealed (sha256 with the held-out) before any
  result is seen. · [D]
- **AC-02** — Arms B0 (rules), B1 (TF-IDF + LR) and B2 (LLM) shall be evaluated on the same frozen test split. · [D]
- **AC-03** — The report shall include macro-F1 per language with a 95% bootstrap CI, per-class F1, slot accuracy, ECE,
  coverage at τ, p50/p95 latency and cost per 1,000 messages. · [D]
- **AC-04** — The injection detector (rules vs rules + LR) shall report injection recall and the false-positive rate on
  legitimate messages. · [D]
- **AC-05** — The chosen model shall be exported with its version, and the understand node shall load it. · [T]
- **AC-06** — The train/validation/test split shall be by author (70/15/15), fixed and hashed before training. · [C]
- **AC-07** — τ shall be chosen on the validation split only, as the lowest threshold that keeps precision ≥ 0.95 on the
  messages the classifier accepts `[assumption]`. · [D]
- **AC-08** — Relative dates ("ayer", "el viernes", "ontem") shall be resolved against `DEMO_TODAY`. · [T]
- **AC-09** — The B0 rules arm shall run with no model file and no network, so arm S0 of the graph never needs an LLM. · [T]

## 4. Functional requirements
| Arm | Intent | Slots | Notes |
|---|---|---|---|
| **B0 — rules (baseline)** | ES/PT keyword and pattern lists per intent | regex for amounts and currencies, date parser, merchant after "en/em/de" | deterministic; used by S0 |
| **B1 — TF-IDF + LR** | char 2–5 + word 1–2 n-grams, logistic regression, class-balanced, calibrated | same as B0 | trained on the train split |
| **B2 — LLM** | Claude Haiku 4.5, structured output (intent, confidence, slots) | from the LLM | zero-shot with the label definitions; no examples from test |
| **B3 — cascade** (P1) | B1; below τ → B2 | B0 regex, B2 when regex finds nothing | production pattern: cheap first, LLM only when unsure |
| Embeddings + LR, Jev | — | — | not in this spec: Jev is a spec 15 arm; embeddings are P2 |

**Injection detector:** rules (ES/PT/EN patterns such as "ignora tus instrucciones", "muestra la cuenta de", ids of
other customers, role-play markers) vs rules + LR (char n-grams) trained on the injection sentences of spec 09 plus
legitimate messages as negatives.

**Decision rule (copied into `eval/PROTOCOL.md`, `[assumption]` thresholds):**
1. Discard any arm with macro-F1 in PT < 0.80.
2. Among the rest, choose the simplest (B0 < B1 < B3 < B2) whose macro-F1 in ES and in PT is within 2 points of the best,
   or whose CI overlaps the best.
3. It must meet p95 ≤ 1.5 s and ≤ 1 USD per 1,000 messages.
4. If no learned arm beats B0 with significance (McNemar, p < 0.05), keep B0 and report it.
5. Injection detector: adopt rules + LR only if it raises recall without exceeding 2% false positives.

## 5. Non-functional requirements
- Reproducible: fixed seeds; `make classifier` trains and evaluates from the frozen split.
- The test split is never used for tuning; results are written once, after sealing.

## 6. API contract (Python, `nick_of_time.nlu`)
```python
nlu = load_nlu(arm="B1", path="models/intent-b1-v1.joblib")   # arm from the run config
r = nlu.parse(text, language_hint=None, today=DEMO_TODAY)
# r: intent, confidence, slots {amount, currency, date, merchant}, language, injection_flagged, arm, version
```

## 7. Data model touched
Reads the sentence set of spec 09 (`eval/classifier/*.jsonl`). Writes `models/intent-*.joblib`, `models/injection-*.joblib`,
`eval/results/classifier.csv` and `apps/web/public/data/classifier.json` (spec 01 §6.2).

## 8. Assumptions and open questions (gate 1)
- **Q1 — thresholds:** PT macro-F1 ≥ 0.80, "within 2 points", p95 ≤ 1.5 s, ≤ 1 USD per 1,000 messages, ≤ 2% false positives
  for injections. Approve or change before sealing.
- **Q2 — B3 cascade:** include it as a P0 arm or keep it P1? Proposal: P1.
- **Q3 — τ rule:** precision ≥ 0.95 on accepted messages, chosen on validation. OK?
- Assumption: spec 09 delivers 300–400 sentences with author ids; if fewer, the CIs widen and that is reported.

## 9. Out of scope
Fine-tuning; embeddings + LR (P2); Jev (benchmarked in spec 15); the agent's use of the result (spec 04).

## 10. Plan, tasks and verification
- [ ] T1 — `eval/PROTOCOL.md` with the rule above; review by Diego; seal · AC-01, AC-06
- [ ] T2 — B0 rules + date parser · AC-08, AC-09
- [ ] T3 — B1 training with calibration; τ on validation · AC-02, AC-07
- [ ] T4 — B2 structured-output prompt (Haiku 4.5) · AC-02
- [ ] T5 — injection detector, both arms · AC-04
- [ ] T6 — evaluation script, report, export, ADR "model selection" (with spec 15) · AC-03, AC-05
