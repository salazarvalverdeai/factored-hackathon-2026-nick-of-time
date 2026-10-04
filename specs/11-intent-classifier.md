# Spec 11 — Intent classifier, injection detector and selection protocol

- **Feature:** the learned components the challenge asks to compare against a baseline — the ES/PT intent and slot
  classifier and the injection detector — plus the pre-registered protocol that decides which arm ships.
- **Status:** Draft (updated 2026-10-04: status and human intents, mode-aware dates, thresholds checked against the test
  size; Q1–Q4 decided by the lead)
- **Owner:** @salazarvalverdeai (protocol reviewed by @vldiego) · **Priority:** P0 · **Size:** M
- **Challenge dimension:** Machine Learning
- **Depends on:** 09 (labeled sentence set) · **Enables:** 04 (understand node), 15 (benchmark B1) · **ADRs:** 0015,
  0016, 0020 (proposed)
- **Issue:** #13

> Full profile: the comparison against a baseline is a challenge requirement (organizers, 2026-09-29).

---

## 1. Introduction
Understanding a dispute message means three things: the **intent**, the **slots** that find the transaction (amount,
currency, date, merchant) and whether the message is an **injection**. The intents are five:

| Intent | Example (ES / PT) | Graph route (spec 04) |
|---|---|---|
| `unrecognized_charge` | "no reconozco un cargo de 1,250" / "não reconheço essa compra" | dispute |
| `wrongful_charge` | "me cobraron dos veces" / "fui cobrado duas vezes" | dispute |
| `status_inquiry` | "¿ya está bloqueada mi tarjeta?", "¿cómo va mi caso?" / "como está meu caso?" | status |
| `human_request` | "quiero hablar con una persona" / "quero falar com um atendente" | request a call |
| `out_of_scope` | anything else (loans, balance, small talk) | refuse with what it can do |

`unrecognized_charge` and `wrongful_charge` come from the complaint categories of the dataset
(`docs/eda/workflows/W3_disputes.md`) and `dispute_type` in `contracts/tools.py`. `status_inquiry` replaces the former
`inquiry` so that a returning customer gets a fresh reading. `human_request` exists so that a customer who asks for a
person is never blocked, and the classifier (not a keyword list alone) recognizes disputes — two risks the CFPB names
for chatbots in consumer finance. Re-evaluation, sending the receipt
and requesting a call also reach the graph as buttons (structured actions) that skip the classifier. This spec builds a rules baseline and learned alternatives, compares them on the same frozen test, and
picks one with a rule written before any result is seen. The conclusion is reported whether or not a model wins.

## 3. Acceptance criteria (EARS)
AC-01 to AC-05 come from issue #13 with the same numbers; AC-06 onward are added by this spec.

- **AC-01** — `eval/PROTOCOL.md` shall be reviewed by Diego, approved and sealed (sha256 with the held-out) before any
  result is seen. · [D]
- **AC-02** — Arms B0 (rules), B1 (TF-IDF + LR) and B2 (LLM) shall be evaluated on the same frozen test split. · [D]
- **AC-03** — The report shall include macro-F1 per language with a 95% bootstrap CI, per-class F1, recall of disputes
  (`unrecognized_charge` + `wrongful_charge`) and of `human_request` per language, slot accuracy, ECE, coverage at τ,
  p50/p95 latency and cost per 1,000 messages. · [D]
- **AC-04** — The injection detector (rules vs rules + LR) shall report injection recall and the false-positive rate on
  legitimate messages. · [D]
- **AC-05** — The chosen model shall be exported with its version, and the understand node shall load it. · [T]
- **AC-06** — The train/validation/test split shall be by author (60/15/25), with at least 100 test sentences per
  language and 20 per intent per language, fixed and hashed before training. · [C]
- **AC-07** — τ shall be chosen on the validation split only, as the lowest threshold that keeps precision ≥ 0.95 on the
  messages the classifier accepts `[assumption]`. · [D]
- **AC-08** — Relative dates ("ayer", "el viernes", "ontem") shall be resolved against the session's "today"
  (`clock.today(mode)`: `DEMO_TODAY` in historical mode, the real date in live mode). · [T]
- **AC-09** — The B0 rules arm shall run with no model file and no network, so arm S0 of the graph never needs an LLM. · [T]
- **AC-10** — When a message asks for a person in any wording of the test split, every arm shall return `human_request`
  or abstain; it shall never return `out_of_scope` for it (recall of `human_request` reported separately). · [D]

## 4. Functional requirements
| Arm | Intent | Slots | Notes |
|---|---|---|---|
| **B0 — rules (baseline)** | ES/PT keyword and pattern lists per intent | regex for amounts and currencies, date parser, merchant after "en/em/de" | deterministic; used by S0 |
| **B1 — TF-IDF + LR** | char 2–5 + word 1–2 n-grams, logistic regression, class-balanced, calibrated | same as B0 | trained on the train split |
| **B2 — LLM** | the LLM chosen by the lean rule of spec 15 §4.4 (Claude Haiku 4.5 until the benchmark runs), structured output (intent, confidence, slots) | from the LLM | zero-shot with the label definitions; no examples from test |
| **B3 — cascade** (P1) | B1; below τ → B2 | B0 regex, B2 when regex finds nothing | production pattern: cheap first, LLM only when unsure |
| Embeddings + LR, Jev | — | — | not in this spec: Jev is a spec 15 arm; embeddings are P2 |

**Injection detector:** rules (ES/PT/EN patterns such as "ignora tus instrucciones", "muestra la cuenta de", ids of
other customers, role-play markers) vs rules + LR (char n-grams) trained on the injection sentences of spec 09 plus
legitimate messages as negatives.

### 4.1 Thresholds and test size (checked 2026-10-04)
**What the check found.** With 300–400 sentences split 70/15/15, the test split has about 50–60 sentences, 25–30 per
language. At that size the measurement cannot support the planned thresholds:

| Test sentences per language | 95% CI of accuracy at 0.90 | 95% bootstrap CI width of macro-F1 (5 classes) |
|---|---|---|
| 26 | ± 11.5 points | ~20 points |
| 100 | ± 5.9 points | ~11 points |
| 200 | ± 4.2 points | ~9 points |
| 400 | ± 2.9 points | — |

A model at 0.90 can score anywhere from 0.80 to 1.00 on 26 sentences, so a floor of 0.80 does not separate a weak arm
from a strong one, and "within 2 points of the best" would need about 865 test sentences per language. Computed with
the normal approximation to the binomial and a 2,000-resample bootstrap on 5 balanced classes `[simulated]`.

**What it means for the thresholds.**
- Five coarse intents are easier than fine-grained banking intent sets (BANKING77 has 77), and classifiers do well on
  in-scope intents while out-of-scope detection is the hard part (Larson et al., 2019). The floor can be higher than
  0.80, and out-of-scope deserves its own number.
- Not every error costs the same. Confusing `unrecognized_charge` with `wrongful_charge` is cheap: both open a case
  with the same clock. Missing a dispute, or missing a request for a person, is the costly error — the two risks the
  CFPB names for chatbots in consumer finance. Those get their own recall floors.

**Floors (decided by the lead, sealed in `eval/PROTOCOL.md`):**
- macro-F1 ≥ 0.90 in ES and in PT `[assumption]`;
- recall ≥ 0.95 per language for "is a dispute" (the two dispute intents merged) and for `human_request` `[assumption]`;
- precision ≥ 0.95 on the messages accepted at τ (AC-07, unchanged);
- test split ≥ 100 sentences per language (AC-06), so the spec 09 set grows from 300–400 to about 800 sentences;
- comparisons between arms use paired McNemar on the same sentences, not a fixed point gap.

**Decision rule (copied into `eval/PROTOCOL.md`):**
1. Discard any arm below a floor of §4.1 in either language.
2. Among the rest, choose the simplest (B0 < B1 < B3 < B2) that is not significantly worse than the best arm (paired
   McNemar, p ≥ 0.05).
3. It must meet p95 ≤ 1.5 s and ≤ 1 USD per 1,000 messages.
4. If no learned arm beats B0 with significance (McNemar, p < 0.05), keep B0 and report it.
5. Injection detector: adopt rules + LR only if it raises recall without exceeding 2% false positives.

## 5. Non-functional requirements
- Reproducible: fixed seeds; `make classifier` trains and evaluates from the frozen split.
- The test split is never used for tuning; results are written once, after sealing.

## 6. API contract (Python, `nick_of_time.nlu`)
```python
nlu = load_nlu(arm="B1", path="models/intent-b1-v1.joblib")   # arm from the run config
r = nlu.parse(text, language_hint=None, today=clock.today(mode))   # mode from the session (ADR 0020)
# r: intent, confidence, slots {amount, currency, date, merchant}, language, injection_flagged, arm, version
```

## 7. Data model touched
Reads the sentence set of spec 09 (`eval/classifier/*.jsonl`). Writes `models/intent-*.joblib`, `models/injection-*.joblib`,
`eval/results/classifier.csv` and `apps/web/public/data/classifier.json` (spec 01 §6.2).

## 8. Assumptions and open questions (gate 1)
- **Q1 — thresholds:** **Decided (lead, 2026-10-04, after the check of §4.1):** the floors of §4.1, a test split of
  ≥ 100 sentences per language, paired McNemar instead of a point gap; p95 ≤ 1.5 s, ≤ 1 USD per 1,000 messages and
  ≤ 2% false positives for injections unchanged. The frozen splits are also the regression suite for later releases.
- **Q2 — B3 cascade:** **Decided (lead, 2026-10-04):** P1 as a separate B1 arm; it is what S1 runs, so B2 measures it.
- **Q3 — τ rule:** **Decided (lead, 2026-10-04):** precision ≥ 0.95 on accepted messages, chosen on validation.
- **Q4 — intent set:** **Decided (lead, 2026-10-04):** five intents. Spec 09 (Diego) relabels and adds sentences.
- Assumption: spec 09 delivers about 800 sentences (ES and PT, with author ids) written by the team and paraphrased
  with an LLM whose name is recorded; results from a candidate of the same family as the generator are flagged.

## 9. Out of scope
Fine-tuning; embeddings + LR (P2); Jev (benchmarked in spec 15); the agent's use of the result (spec 04).

## 10. Plan, tasks and verification
- [ ] T1 — `eval/PROTOCOL.md` with the floors and rule of §4.1; review by Diego; seal · AC-01, AC-06
- [ ] T2 — B0 rules + date parser · AC-08, AC-09
- [ ] T3 — B1 training with calibration; τ on validation · AC-02, AC-07
- [ ] T4 — B2 structured-output prompt (Haiku 4.5) · AC-02
- [ ] T5 — injection detector, both arms · AC-04
- [ ] T6 — evaluation script, report, export, ADR "model selection" (with spec 15) · AC-03, AC-05

## 11. Sources
External sources checked on 2026-10-04.
- Intent names: `contracts/tools.py` (`dispute_type`), `docs/eda/workflows/W3_disputes.md` (complaint categories).
- CFPB, *Chatbots in consumer finance* (6 June 2023) — chatbots that recognize a dispute only from specific words, and
  that hinder access to a person: https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/
  (PDF: https://files.consumerfinance.gov/f/documents/cfpb_chatbot-issue-spotlight_2023-06.pdf)
- OWASP, *LLM01: Prompt Injection* (injection patterns): https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- Calibration and ECE: Guo et al., *On Calibration of Modern Neural Networks* (ICML 2017): https://arxiv.org/abs/1706.04599 ·
  scikit-learn, *Probability calibration*: https://scikit-learn.org/stable/modules/calibration.html
- Larson et al., *An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction* (EMNLP-IJCNLP 2019) —
  classifiers do well on in-scope intents and struggle with out-of-scope queries: https://arxiv.org/abs/1909.02027
- Casanueva et al., *Efficient Intent Detection with Dual Sentence Encoders* (2020) — BANKING77, 13,083 examples over 77
  banking intents: https://arxiv.org/abs/2003.04807
- McNemar's test for comparing classifiers: Dietterich, *Approximate Statistical Tests for Comparing Supervised
  Classification Learning Algorithms*, Neural Computation 10(7), 1998: https://doi.org/10.1162/089976698300017197
- Internal: `contracts/policies.yaml` (`intent_confidence_min`, G-IN-04), ADR 0015 (pre-registration), ADR 0020
  (proposed, two modes), spec 04 §4.2 (routes).
- Thresholds marked `[assumption]` have no external source; they are fixed in `eval/PROTOCOL.md` before sealing.
