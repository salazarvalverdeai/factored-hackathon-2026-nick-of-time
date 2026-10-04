"""Policy engine (spec 02 §4.1, §4.2, §6): decide() for a turn, check() for one action before a write. Pure: no network,
database, LLM or clock. Every result cites the rule ids that produced it and the policies.yaml version (AC-12)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Optional, Union, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nick_of_time.contracts import Decision, GetFraudScoreOut, Intent, ProductType, QueueStatus, Zone
from nick_of_time.policy.model import MODES, POLICIES_PATH, ApprovalMode, Policies, load_policies

CARDS = get_args(ProductType)                             # gold Tarjeta Débito / Tarjeta Crédito, mapped by the caller
ScoreSource = GetFraudScoreOut.model_fields["source"].annotation
ZONE_RULE: dict[str, str] = {"high": "POL-ZONE-HIGH", "medium": "POL-ZONE-MEDIUM", "human": "POL-ZONE-HUMAN"}
EMITTED = {*ZONE_RULE.values(), "POL-SESSION", "POL-INJECTION", "POL-CROSS-CUSTOMER", "POL-HUMAN-REQUEST", "POL-STATUS",
           "POL-OUT-OF-SCOPE", "POL-CLARIFY", "POL-CLARIFY-EXHAUSTED", "POL-SCORE-NULL", "POL-SCORE-LLM",
           "POL-TICKET-ALWAYS", "POL-AMOUNT-GATE", "POL-SUPERVISED", "POL-DEFAULT-DENY"}
REASONS = {"zone_human", "amount_over_case_gate", "clarification_exhausted"}


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionInput(_Frozen):
    """One understood turn. No customer_id: it lives only in the session (constitution #3). The score and its source
    come only from get_fraud_score, never from the customer's text (FR-03)."""
    session_state: str                                    # only "verified" passes rule 1
    intent: Intent
    intent_confidence: float = Field(ge=0, le=1)
    candidates: int = Field(0, ge=0)
    clarification_turns: int = Field(0, ge=0)             # clarification questions already asked
    injection_flagged: bool = False
    cross_customer: bool = False
    score: Optional[float] = Field(None, ge=0, le=100)
    score_source: Optional[ScoreSource] = None
    amount: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = None
    country: Optional[str] = None
    product_type: Optional[str] = None                    # "debit" | "credit"; anything else is not a card
    customer_confirmed: Optional[bool] = None             # medium zone; None = not asked yet
    supervised_mode: bool = False

    @model_validator(mode="after")
    def _score_comes_with_its_source(self) -> DecisionInput:
        if self.score is not None and self.score_source is None:
            raise ValueError("a score needs the source get_fraud_score returned with it (FR-03)")
        return self


class PolicyDecision(_Frozen):
    decision: Decision
    zone: Optional[Zone] = None
    approval_modes: dict[str, ApprovalMode] = {}          # effective mode per action, once a zone is known
    allowed_actions: list[str] = []                       # what the agent may run this turn; anything else is denied
    handoff_reason: Optional[str] = None
    queue_status_after: Optional[QueueStatus] = None
    rule_ids: list[str] = Field(min_length=1)
    guardrail_ids: list[str] = []
    policies_version: int


class _Verdict(_Frozen):
    action: str
    rule_ids: list[str]
    policies_version: int


class Allow(_Verdict):
    mode: ApprovalMode


class Deny(_Verdict):
    policy_id: str
    guardrail_id: Optional[str]


class PolicyEngine:
    def __init__(self, policies: Policies):
        missing = (EMITTED - set(policies.rules)) | (REASONS - set(policies.handoff.triggers))
        if missing:
            raise ValueError(f"policies.yaml lacks rule ids or handoff triggers the engine emits: {sorted(missing)}")
        self.policies, self.version = policies, policies.version

    @classmethod
    def load(cls, path: Union[str, Path] = POLICIES_PATH) -> PolicyEngine:
        return cls(load_policies(Path(path)))

    # ---------- approval modes (§4.2, FR-04) ----------
    def amount_tier(self, amount: Optional[float], currency: Optional[str], country: Optional[str]) -> ApprovalMode:
        """The tier in the country's currency; USD converts at the gate's usd_rate. [assumption] No gate for the
        country, no amount or another currency → human_required: no rule allows less."""
        gate, tiers = self.policies.amount_gate.by_country.get(country or ""), self.policies.amount_gate.tiers
        if gate is None or amount is None or currency not in (gate.currency, "USD"):
            return "human_required"
        local = Decimal(str(amount)) * (Decimal(str(gate.usd_rate)) if currency == "USD" else 1)
        if local <= Decimal(str(gate.low)):
            return tiers.up_to_low
        return tiers.up_to_high if local <= Decimal(str(gate.high)) else tiers.above_high

    def _mode(self, action: str, zone: str, amount, currency, country, supervised: bool) -> tuple[ApprovalMode, list]:
        """Stricter of per_action, the amount tier and supervised mode, on money actions only (AC-15); also returns
        the ids of the rules that made it stricter than per_action. The file's switch can only add strictness."""
        approval = self.policies.approval
        base = approval.per_action[action][zone]
        if action not in approval.money_actions:
            return base, []
        supervised = supervised or approval.supervised_mode
        raisers = [(rule, mode) for rule, mode in (("POL-AMOUNT-GATE", self.amount_tier(amount, currency, country)),
                                                   ("POL-SUPERVISED", "human_required" if supervised else "auto"))
                   if MODES.index(mode) > MODES.index(base)]
        return max([base, *(m for _, m in raisers)], key=MODES.index), [rule for rule, _ in raisers]

    def check(self, action: str, zone: str, *, amount: Optional[float] = None, currency: Optional[str] = None,
              country: Optional[str] = None, supervised_mode: bool = False) -> Union[Allow, Deny]:
        """May an automated caller (agent or customer tool) run `action` now? human_required is denied here: only a
        person runs it, through the analyst api."""
        if action not in self.policies.approval.per_action or zone not in ZONE_RULE:
            return self._deny(action, "POL-DEFAULT-DENY", [])
        mode, raised = self._mode(action, zone, amount, currency, country, supervised_mode)
        if mode == "human_required":
            return self._deny(action, raised[-1] if raised else "POL-DEFAULT-DENY", raised)
        rule = "POL-TICKET-ALWAYS" if action == "open_case" else ZONE_RULE[zone]
        return Allow(action=action, mode=mode, rule_ids=[rule, *raised], policies_version=self.version)

    # ---------- decide (§4.1) ----------
    def screen(self, inp: DecisionInput) -> Optional[PolicyDecision]:
        """Rules 1–4: session, injection, another customer, a person, a status question, out of scope. None means
        "a dispute: go on" (spec 04 `route` calls it before retrieving the transaction)."""
        for hit, decision, rule in (
                (inp.session_state != "verified", "reauthenticate", "POL-SESSION"),
                (inp.injection_flagged, "deny", "POL-INJECTION"),
                (inp.cross_customer, "deny", "POL-CROSS-CUSTOMER"),
                (inp.intent == "human_request", "connect_person", "POL-HUMAN-REQUEST"),
                (inp.intent == "status_inquiry", "answer_status", "POL-STATUS"),
                # [assumption] the product is judged only once one transaction is identified; unknown is not a card
                (inp.intent == "out_of_scope" or (inp.candidates == 1 and inp.product_type not in CARDS),
                 "deny", "POL-OUT-OF-SCOPE")):
            if hit:
                return self._result(decision, [rule])
        return None

    def decide(self, inp: DecisionInput) -> PolicyDecision:
        """§4.1 in order; the first terminal rule wins and every rule that fired is reported (FR-02)."""
        if (early := self.screen(inp)) is not None:
            return early
        if inp.intent_confidence < self.policies.clarify.intent_confidence_min or inp.candidates != 1:
            return self._clarify(inp, [])
        zone, rules = self._zone(inp)
        modes: dict[str, ApprovalMode] = {}
        for action in self.policies.approval.per_action:
            modes[action], raised = self._mode(action, zone, inp.amount, inp.currency, inp.country, inp.supervised_mode)
            rules += [rule for rule in raised if rule not in rules]
        if zone == "medium" and inp.customer_confirmed is None:
            return self._result("confirm", rules, zone=zone, approval_modes=modes)
        if zone == "medium" and inp.customer_confirmed is False:
            return self._clarify(inp, rules)              # [assumption] "not that charge": identify it again
        rules.append("POL-TICKET-ALWAYS")
        if zone == "high" and modes["block_card"] != "human_required":
            return self._result("block_and_open_case", rules, zone=zone, approval_modes=modes,
                                allowed_actions=["open_case", "block_card"],
                                queue_status_after=self.policies.approval.manual_check_leaves_case_in)
        # [assumption] medium, and high blocked only by supervised mode, have no handoff_reason in the schema: null
        over_gate = zone == "high" and self.amount_tier(inp.amount, inp.currency, inp.country) == "human_required"
        reason = "zone_human" if zone == "human" else "amount_over_case_gate" if over_gate else None
        return self._result("handoff", rules, zone=zone, approval_modes=modes, allowed_actions=["open_case"],
                            handoff_reason=reason, queue_status_after="review")

    def _zone(self, inp: DecisionInput) -> tuple[Zone, list[str]]:
        """Rules 6–9: a null or llm score is zone human with its own id (AC-02); otherwise the score's band (AC-01)."""
        rules = [rule for rule, hit in (("POL-SCORE-NULL", inp.score is None),
                                        ("POL-SCORE-LLM", inp.score_source == "llm")) if hit]
        if rules:
            return "human", rules
        zones = self.policies.zones
        zone = ("high" if inp.score >= zones["high"].score_min
                else "medium" if inp.score >= zones["medium"].score_min else "human")
        return zone, [ZONE_RULE[zone]]

    def _clarify(self, inp: DecisionInput, rules: list[str]) -> PolicyDecision:
        """Rules 5 and 5b (AC-08): ask; once max_clarification_turns questions were asked, hand off to a person."""
        if inp.clarification_turns >= self.policies.clarify.max_clarification_turns:
            return self._result("handoff", [*rules, "POL-CLARIFY-EXHAUSTED"], handoff_reason="clarification_exhausted")
        return self._result("ask", [*rules, "POL-CLARIFY"])

    def _result(self, decision: str, rule_ids: list[str], **fields) -> PolicyDecision:
        guardrails = dict.fromkeys(self.policies.rules[rule].guardrail for rule in rule_ids)
        return PolicyDecision(decision=decision, rule_ids=rule_ids, guardrail_ids=[g for g in guardrails if g],
                              policies_version=self.version, **fields)

    def _deny(self, action: str, policy_id: str, rule_ids: list[str]) -> Deny:
        return Deny(action=action, policy_id=policy_id, guardrail_id=self.policies.rules[policy_id].guardrail,
                    rule_ids=rule_ids or [policy_id], policies_version=self.version)
