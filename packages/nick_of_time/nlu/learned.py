"""Learned arms of spec 11 §4: B1 (TF-IDF + logistic regression, calibrated).

B1 returns the `NLUResult` of §6: the intent from the model; slots, language and the injection flag from B0;
`dispute_detected` is a predicted dispute OR the B0 dispute rules (§6). scikit-learn is imported only when B1 is built
or loaded, so B0 and S0 never need it (AC-09).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

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
