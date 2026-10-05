"""Learned arms of spec 11 §4: B1 (TF-IDF + logistic regression, calibrated) and B2 (LLM with forced tool use, D-011).

Both return the `NLUResult` of §6. B1 reads the intent from the model and takes slots, language and the injection flag
from B0; `dispute_detected` is a predicted dispute OR the B0 dispute rules (§6). B2 sends the prompt and schema the
graph's S1 step sends (`llm.steps`), so the benchmark measures what S1 runs (§8 Q2); language and the injection flag
come from B0. scikit-learn is imported only when B1 is built or loaded, so B0 and S0 never need it (AC-09).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from pydantic import ValidationError

from .. import llm
from .rules import parse_rules

DISPUTES = ("unrecognized_charge", "wrongful_charge")
SEED = 11
B1_VERSION = "b1-v1"


def train_b1(texts: list[str], intents: list[str], cal_texts: list[str], cal_intents: list[str]):
    """Char 2-5 + word 1-2 TF-IDF and a class-balanced logistic regression fit on train; sigmoid calibration fit on
    validation only, the protocol's one calibration split (eval/PROTOCOL.md §1.1). Deterministic (fixed seed)."""
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.frozen import FrozenEstimator
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline, make_union

    features = make_union(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
                          TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True))
    model = make_pipeline(features, LogisticRegression(class_weight="balanced", max_iter=2000, random_state=SEED))
    model.fit(texts, intents)
    return CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid").fit(cal_texts, cal_intents)


class B1NLU:
    arm = "B1"

    def __init__(self, model, version: str = B1_VERSION) -> None:
        self.model, self.version = model, version

    def parse(self, text: str, language_hint: Optional[str] = None, *, today: date):
        from . import NLUResult
        base = parse_rules(text, language_hint, today)
        proba = self.model.predict_proba([text])[0]
        best = int(proba.argmax())
        intent = str(self.model.classes_[best])
        return NLUResult.model_validate({
            **base, "intent": intent, "confidence": float(proba[best]),
            "dispute_detected": intent in DISPUTES or base["dispute_detected"],
            "other_language": base["other_language"] and intent == "out_of_scope", "arm": self.arm,
            "version": self.version})

    def save(self, path) -> None:
        import joblib
        joblib.dump({"model": self.model, "version": self.version}, path)

    @classmethod
    def load(cls, path) -> "B1NLU":
        import joblib
        blob = joblib.load(path)
        return cls(blob["model"], blob["version"])


class B2NLU:
    """The LLM arm. `last` keeps this call's billed result (also on `NoStructuredOutput`) for latency and cost, and
    is None when the provider gave no reply, so an error never bills the previous call again; a provider error or a
    reply with no valid tool input propagates, and the evaluation scores it as a wrong prediction (D-022). Slots
    outside the `Slots` contract are read as none [assumption]."""
    arm = "B2"

    def __init__(self, client: llm.LLMClient) -> None:
        self.client, self.version, self.last = client, client.model, None

    def parse(self, text: str, language_hint: Optional[str] = None, *, today: date):
        from ..llm.steps import INTENT_SCHEMA, MAX_TOKENS, UNDERSTAND
        from . import NLUResult, Slots
        self.last = None
        base = parse_rules(text, language_hint, today)
        user = json.dumps({"today": today.isoformat(), "message": text}, ensure_ascii=False)
        try:
            self.last = self.client.complete(UNDERSTAND, user, schema=INTENT_SCHEMA, tool_name="record_intent",
                                             max_tokens=MAX_TOKENS)
        except llm.NoStructuredOutput as exc:
            self.last = exc.result
            raise
        out = self.last.tool_input
        try:
            slots = Slots.model_validate(out["slots"]).model_dump()
        except ValidationError:
            slots = dict.fromkeys(("amount", "currency", "date", "merchant"))
        return NLUResult.model_validate({
            **base, "intent": out["intent"], "confidence": float(out["confidence"]), "slots": slots,
            "dispute_detected": out["dispute_detected"], "other_language": False, "arm": self.arm,
            "version": self.version})
