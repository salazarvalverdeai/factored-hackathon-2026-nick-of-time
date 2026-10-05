"""Outcome auditor (spec 18, ADR 0021): deterministic checks that re-derive an agent run from its records.

Pure functions, no network, no LLM, no clock: the same records always give the same finding (AC-01). This module holds
checks A3–A7; `rederive` holds A1–A2, which re-run the policy engine and the clock on the recorded inputs.
"""
from nick_of_time.audit.checks import (ActionRead, Finding, LifecycleEvent, check_actions, check_coherence,
                                       check_grounding, check_lifecycle, check_privacy, reads_from_store)

from nick_of_time.audit.judge import AnalystDecision, SecondOpinion, opinion, record_decision
from nick_of_time.audit.rederive import check_deadline, check_decision

__all__ = ["ActionRead", "AnalystDecision", "Finding", "LifecycleEvent", "SecondOpinion", "check_actions",
           "check_coherence", "check_deadline", "check_decision", "check_grounding", "check_lifecycle",
           "check_privacy", "opinion", "reads_from_store", "record_decision"]
