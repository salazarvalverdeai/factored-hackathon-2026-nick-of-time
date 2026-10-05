"""Judge of spec 18 section 4.2: an advisory second opinion for the analyst on a case in review (AC-07, AC-08, AC-10, AC-11).

It reads the handoff card, the transcript, the tool results and the auditor's findings, asks one LLM call with a fixed
rubric for structured output, and keeps only the reasons and questions that are grounded (ADR 0016). It never changes
state, calls a tool or reaches the customer. On any failure it returns None ("No second opinion"), never an exception.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, Field

from nick_of_time.audit.checks import _ID, Finding, _scalars, _tokens
from nick_of_time.llm import LLMClient

Verdict = Literal["agree", "disagree", "uncertain"]
MAX_REASONS, MAX_QUESTIONS = 5, 3
MAX_COST_USD = 0.01        # [assumption] spec 18 section 5: under 0.01 USD per case
TIMEOUT_S = 10.0           # [assumption] G-OPS-01's 800 ms is the agent's; the judge runs off the customer's path
MAX_INPUT_TOKENS = 12_000  # [assumption] pre-call budget guard, estimated as characters // 4 (as the fake provider does)
MAX_OUTPUT_TOKENS = 700
_NEVER_SEEN = frozenset({"is_fraud", "fraud_label", "label", "labels", "eval_label"})  # constitution #7

RUBRIC = """You are a second reader for a bank analyst reviewing a card-dispute case. You advise; you never decide.
Answer the fixed rubric, in this order:
1. Does the transaction match the customer's account of it?
2. Is anything in the story inconsistent with the evidence, or a sign of social engineering?
3. Is the agent's proposal consistent with the policy decision and the evidence?
4. Did the agent leave anything unverified?
5. What should the analyst ask?
Return verdict (agree | disagree | uncertain) on the agent's proposal, up to 5 reasons and up to 3 questions. Every reason
and question must list the evidence ids (TRX-, PRD-, CLI-, A-, V-, RC-, K- ...) it rests on, taken only from the evidence
list given. State no number, date or id that does not appear in the evidence. If the evidence is not enough, say uncertain."""
PROMPT_HASH = hashlib.sha256(RUBRIC.encode()).hexdigest()[:16]

_ITEM = {"type": "object", "required": ["text", "evidence_ids"], "additionalProperties": False,
         "properties": {"text": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}}}
OUTPUT_SCHEMA = {"type": "object", "required": ["verdict", "reasons", "questions"], "properties": {
    "verdict": {"enum": ["agree", "disagree", "uncertain"]},
    "reasons": {"type": "array", "items": _ITEM, "maxItems": MAX_REASONS},
    "questions": {"type": "array", "items": _ITEM, "maxItems": MAX_QUESTIONS}}}


class Cited(BaseModel):
    text: str
    evidence_ids: list[str] = Field(min_length=1)


class SecondOpinion(BaseModel):
    """The judge's structured output, after grounding. Advisory: the console labels it "AI second opinion - advisory"."""
    verdict: Verdict
    reasons: list[Cited] = Field(max_length=MAX_REASONS)
    questions: list[Cited] = Field(max_length=MAX_QUESTIONS)
    model: str
    prompt_hash: str
    created_at: dt.datetime
    dropped: int = 0   # reasons and questions removed by grounding, for the calibration metrics (AC-13)


class AnalystDecision(BaseModel):
    """The analyst's decision, recorded on its own with its match to the judge (AC-10).

    [assumption] shape only; persistence belongs to the store owner (spec 18 section 7: `analyst_action` payload
    adds `matched_second_opinion`, a bool or null, and `second_opinions` is an append-only table)."""
    case_id: str
    analyst: str
    action: str                              # an analyst action, same enum as copilot_proposal.action
    proposal_action: Optional[str] = None    # what the agent proposed
    judge_verdict: Optional[Verdict] = None  # None when there was no second opinion
    matched_second_opinion: Optional[bool] = None
    decided_at: dt.datetime


def _clean(node: Any) -> Any:
    """A copy without the labels the judge must never see (constitution #7)."""
    if isinstance(node, dict):
        return {k: _clean(v) for k, v in node.items() if k not in _NEVER_SEEN}
    if isinstance(node, (list, tuple)):
        return [_clean(v) for v in node]
    return node


def _grounded(item: dict, valid_ids: set[str], facts: set[str]) -> Optional[Cited]:
    """Keep an item only if every id it cites is evidence and every number, date or id in its text is in the evidence."""
    ids = [i for i in item.get("evidence_ids", []) if isinstance(i, str)]
    text = str(item.get("text", "")).strip()
    if not text or not ids or not set(ids) <= valid_ids or not _tokens(text) <= facts:
        return None
    return Cited(text=text, evidence_ids=ids)


def opinion(handoff: dict, transcript: Iterable[str], evidence: Iterable[Any], *, client: LLMClient,
            audit: Iterable[Finding] = (), now: Optional[dt.datetime] = None, max_cost_usd: float = MAX_COST_USD,
            timeout_s: float = TIMEOUT_S) -> Optional[SecondOpinion]:
    """One second opinion for a case in review, or None ("No second opinion") on failure, timeout or budget (AC-11)."""
    try:
        handoff, evidence = _clean(handoff), _clean(list(evidence))
        # the evidence the reasons may cite: ids in the handoff card and in the tool results (AC-07, AC-08)
        corpus = [*_scalars(handoff), *_scalars(evidence)]
        valid_ids = {i for s in corpus for i in _ID.findall(s)} | {str(e) for e in handoff.get("evidence", [])}
        facts = _tokens(" ".join(corpus))   # the transcript is the customer's words, not evidence of a fact
        user = json.dumps({"handoff": handoff, "transcript": list(transcript), "tool_results": evidence,
                           "evidence_ids": sorted(valid_ids), "auditor": [f.model_dump(mode="json") for f in audit]},
                          default=str, ensure_ascii=False)
        if (len(RUBRIC) + len(user)) // 4 > MAX_INPUT_TOKENS:
            return None
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            res = pool.submit(client.complete, RUBRIC, user, schema=OUTPUT_SCHEMA, tool_name="second_opinion",
                              max_tokens=MAX_OUTPUT_TOKENS).result(timeout=timeout_s)
        finally:
            pool.shutdown(wait=False)
        if res.cost_usd is not None and res.cost_usd > max_cost_usd:
            return None
        out = res.tool_input or {}
        raw_r, raw_q = out["reasons"][:MAX_REASONS], out["questions"][:MAX_QUESTIONS]
        reasons = [g for r in raw_r if (g := _grounded(r, valid_ids, facts))]
        questions = [g for q in raw_q if (g := _grounded(q, valid_ids, facts))]
        verdict = out["verdict"] if reasons else "uncertain"   # [assumption] a verdict nobody can check is "uncertain"
        return SecondOpinion(verdict=verdict, reasons=reasons, questions=questions, model=res.model,
                             prompt_hash=PROMPT_HASH, created_at=now or dt.datetime.now(dt.timezone.utc),
                             dropped=len(raw_r) + len(raw_q) - len(reasons) - len(questions))
    except Exception:   # noqa: BLE001 - AC-11: the caller never sees an exception from the judge (incl. timeout)
        return None


def record_decision(case_id: str, analyst: str, action: str, *, proposal_action: Optional[str],
                    second_opinion: Optional[SecondOpinion], now: Optional[dt.datetime] = None) -> AnalystDecision:
    """Whether the analyst's action matched the judge (AC-10). `agree` matches when the analyst took the agent's proposal,
    `disagree` when they did not; `uncertain` or no opinion is None (nothing to match)."""
    verdict = second_opinion.verdict if second_opinion else None
    took = action == proposal_action
    matched = {"agree": took, "disagree": not took}.get(verdict) if verdict else None
    return AnalystDecision(case_id=case_id, analyst=analyst, action=action, proposal_action=proposal_action,
                           judge_verdict=verdict, matched_second_opinion=matched,
                           decided_at=now or dt.datetime.now(dt.timezone.utc))
