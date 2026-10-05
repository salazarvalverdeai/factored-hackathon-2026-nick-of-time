"""Policy engine (spec 02 §4.1, §4.2, §6): decide() for a turn, check() for one action before a write. Pure: no network,
database, LLM or clock. Every result cites the rule ids that produced it and the policies.yaml version (AC-12)."""
from __future__ import annotations

import math
import unicodedata
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional, Union, get_args

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, field_validator, model_validator

from nick_of_time.contracts import Decision, Intent, ProductType, QueueStatus, Zone
from nick_of_time.policy.model import MODES, POLICIES_PATH, ApprovalMode, Policies, load_policies

CARDS = get_args(ProductType)
GOLD_PRODUCT = {"Tarjeta Débito": "debit", "Tarjeta Crédito": "credit"}      # gold products.product_type (§4.3)
HandoffReason = Literal["zone_human", "zone_medium", "supervised_mode", "amount_over_case_gate", "identity_unverified",
                        "clarification_exhausted", "tool_failure", "language_low_confidence"]   # handoff.schema.json
CallRequest = Literal["active_or_general", "opened_case", "general"]          # where request_call registers the call
ZONE_RULE: dict[str, str] = {"high": "POL-ZONE-HIGH", "medium": "POL-ZONE-MEDIUM", "human": "POL-ZONE-HUMAN"}
EMITTED = {*ZONE_RULE.values(), "POL-SESSION", "POL-INJECTION", "POL-CROSS-CUSTOMER", "POL-HUMAN-REQUEST", "POL-STATUS",
           "POL-OUT-OF-SCOPE", "POL-CLARIFY", "POL-CLARIFY-EXHAUSTED", "POL-SCORE-NULL", "POL-SCORE-LLM",
           "POL-SCORE-SOURCE", "POL-TICKET-ALWAYS", "POL-AMOUNT-GATE", "POL-AMOUNT-UNKNOWN", "POL-SUPERVISED",
           "POL-DEFAULT-DENY"}
REASONS = {"zone_human", "zone_medium", "supervised_mode", "amount_over_case_gate", "clarification_exhausted"}
# D-029 (default, pending the lead; do not flip without the lead): a call request that reports a high-zone charge still
# blocks, like a confirmed dispute (None). Setting here the handoff reason that case carries in review flips it to "open
# the case and call, no block" in the engine (one line; a reason that is not a handoff trigger stops the engine at
# start). A real flip also needs:
#   - a new handoff trigger: none of the current ones describes "the customer asked for a person" on a high-zone case,
#     so handoff.schema.json, policies.yaml handoff.triggers and HandoffReason change together (a contracts/ PR);
#   - new POL-HUMAN-REQUEST and POL-ZONE-HIGH texts, or a new POL- id, because both say the high zone blocks;
#   - a decision on who enforces it: check("block_card", "high", ...) still allows the block on those inputs, so either
#     the graph alone withholds it or check() learns about the call; the AC-05 agreement test was relaxed to
#     "allowed ⊆ checked" for this;
#   - the 4 tests that pin the default: rows 3a-charge-high and 3a-charge-at-tau, the "never removes protection"
#     property at score 72 below the gate, and the first assertion of the D-029 flip test.
D029_CALL_WITHHOLDS_BLOCK_REASON: Optional[HandoffReason] = None


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionInput(_Frozen):
    """One understood turn. No customer_id: it lives only in the session (constitution #3). The score and its source
    come only from get_fraud_score, never from the customer's text (FR-03). The four flags have no default: a caller
    that forgets one gets an error, never "not flagged" (fail closed). Flags are strict bools: 0, 1, "off" or "true"
    are input errors, as in check()."""
    session_state: str                                    # only "verified" passes rule 1
    intent: Intent
    intent_confidence: StrictFloat = Field(ge=0, le=1)     # an int is accepted; True or "0.9" are input errors
    dispute_detected: StrictBool                          # the message also reports a charge (rules 3a, 3b, 4; D-020)
    injection_flagged: StrictBool
    cross_customer: StrictBool
    supervised_mode: StrictBool
    candidates: StrictInt = Field(0, ge=0)
    clarification_turns: StrictInt = Field(0, ge=0)       # clarification questions already sent to the customer
    score: Optional[StrictFloat] = Field(None, ge=0, le=100)
    score_source: Optional[str] = Field(None, pattern=r"^[a-z_]+$")
    amount: Optional[StrictFloat] = None                  # missing, negative or not finite → tier human_required
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    country: Optional[str] = Field(None, pattern=r"^[A-Z]{2}$")
    product_type: Optional[str] = None                    # debit | credit, or the gold label; anything else is not a card
    customer_confirmed: Optional[StrictBool] = None       # on the selected transaction (§6); None = not asked yet
    active_case: Optional[StrictBool] = None              # the customer has an active case (rule 3b); None = not read

    @field_validator("product_type")
    @classmethod
    def _from_gold_label(cls, value: Optional[str]) -> Optional[str]:
        return GOLD_PRODUCT.get(unicodedata.normalize("NFC", value), value) if value else value

    @model_validator(mode="after")
    def _facts_come_from_tools(self) -> DecisionInput:
        if self.score is not None and self.score_source is None:
            raise ValueError("a score needs the source get_fraud_score returned with it (FR-03)")
        if self.candidates == 1 and self.product_type is None:
            raise ValueError("one identified transaction needs its product_type (rule 4)")
        return self


class PolicyDecision(_Frozen):
    decision: Decision
    zone: Optional[Zone] = None
    approval_modes: dict[str, ApprovalMode] = {}          # effective mode per action, once a zone is known
    allowed_actions: list[str] = []                       # what the agent may run this turn; anything else is denied
    handoff_reason: Optional[HandoffReason] = None        # set exactly on a handoff or a case left in review
    request_call: Optional[CallRequest] = None            # register a call request, and where (§6)
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
        missing |= {D029_CALL_WITHHOLDS_BLOCK_REASON} - {None, *policies.handoff.triggers}
        if missing:
            raise ValueError(f"policies.yaml lacks rule ids or handoff triggers the engine emits: {sorted(missing)}")
        self.policies, self.version = policies, policies.version

    @classmethod
    def load(cls, path: Union[str, Path] = POLICIES_PATH) -> PolicyEngine:
        return cls(load_policies(Path(path)))

    # ---------- approval modes (§4.2, FR-04) ----------
    def amount_tier(self, amount: Optional[float], currency: Optional[str], country: Optional[str]) -> ApprovalMode:
        return self._tier(amount, currency, country)[0]

    def _tier(self, amount, currency, country) -> tuple[ApprovalMode, str]:
        """The tier and the rule behind it; USD converts at the gate's usd_rate. [assumption] No gate for the country,
        an amount missing, negative or not finite, or another currency → human_required (POL-AMOUNT-UNKNOWN)."""
        gate, tiers = self.policies.amount_gate.by_country.get(country or ""), self.policies.amount_gate.tiers
        if (gate is None or amount is None or not math.isfinite(amount) or amount < 0
                or currency not in (gate.currency, "USD")):
            return "human_required", "POL-AMOUNT-UNKNOWN"
        local = Decimal(str(amount)) * (Decimal(str(gate.usd_rate)) if currency == "USD" else 1)
        if local <= Decimal(str(gate.low)):
            return tiers.up_to_low, "POL-AMOUNT-GATE"
        return tiers.up_to_high if local <= Decimal(str(gate.high)) else tiers.above_high, "POL-AMOUNT-GATE"

    def _mode(self, action: str, zone: str, amount, currency, country, supervised: bool) -> tuple[ApprovalMode, list]:
        """Stricter of per_action, the amount tier and supervised mode, on money actions only (AC-15); also returns
        the ids of the rules that made it stricter than per_action. The file's switch can only add strictness."""
        approval = self.policies.approval
        base = approval.per_action[action][zone]
        if action not in approval.money_actions:
            return base, []
        tier, tier_rule = self._tier(amount, currency, country)
        supervised = supervised or approval.supervised_mode
        raisers = [(rule, mode) for rule, mode in ((tier_rule, tier),
                                                   ("POL-SUPERVISED", "human_required" if supervised else "auto"))
                   if MODES.index(mode) > MODES.index(base)]
        return max([base, *(m for _, m in raisers)], key=MODES.index), [rule for rule, _ in raisers]

    def _modes(self, zone: str, inp: DecisionInput) -> tuple[dict[str, ApprovalMode], list[str]]:
        modes, raised = {}, []
        for action in self.policies.approval.per_action:
            modes[action], by = self._mode(action, zone, inp.amount, inp.currency, inp.country, inp.supervised_mode)
            raised += [rule for rule in by if rule not in raised]
        return modes, raised

    def check(self, action: str, zone: str, *, supervised_mode: bool, amount: Optional[float] = None,
              currency: Optional[str] = None, country: Optional[str] = None) -> Union[Allow, Deny]:
        """May an automated caller (agent or customer tool) run `action` now? human_required is denied here: only a
        person runs it, through the analyst api. supervised_mode is required and must be a bool: a switch read as
        None is not "off" (fail closed)."""
        if not isinstance(supervised_mode, bool):
            raise TypeError(f"supervised_mode must be a bool, got {supervised_mode!r}")
        if action not in self.policies.approval.per_action or zone not in ZONE_RULE:
            return self._deny(action, "POL-DEFAULT-DENY", [])
        mode, raised = self._mode(action, zone, amount, currency, country, supervised_mode)
        if mode == "human_required":
            return self._deny(action, raised[-1] if raised else "POL-DEFAULT-DENY", raised)
        rule = "POL-TICKET-ALWAYS" if action == "open_case" else ZONE_RULE[zone]
        return Allow(action=action, mode=mode, rule_ids=[rule, *raised], policies_version=self.version)

    # ---------- decide (§4.1) ----------
    @staticmethod
    def _carried(inp: DecisionInput) -> list[str]:
        """Rule 3a or 3b when the turn goes on to the dispute path (D-020): a call request that reports a charge, or a
        status question that reports one from a customer with no active case. Cited first on every later result."""
        if inp.dispute_detected and inp.intent == "human_request":
            return ["POL-HUMAN-REQUEST"]
        if inp.dispute_detected and inp.intent == "status_inquiry" and inp.active_case is False:
            return ["POL-STATUS"]
        return []

    def screen(self, inp: DecisionInput) -> Optional[PolicyDecision]:
        """Rules 1–4: session, injection, another customer, a person, a status question, out of scope. None means
        "a dispute: go on" (spec 04 `route` calls it before retrieving the transaction), also for a call request or a
        status question that goes on to the dispute path (_carried), which decide() completes."""
        call, carried = inp.intent == "human_request", self._carried(inp)
        confident = inp.intent_confidence >= self.policies.clarify.intent_confidence_min
        for hit, decision, rule in (
                (inp.session_state != "verified", "reauthenticate", "POL-SESSION"),
                (inp.injection_flagged, "deny", "POL-INJECTION"),
                (inp.cross_customer, "deny", "POL-CROSS-CUSTOMER"),
                (call and not carried, "connect_person", "POL-HUMAN-REQUEST"),
                (inp.intent == "status_inquiry" and not carried, "answer_status", "POL-STATUS"),
                (not call and ((inp.intent == "out_of_scope" and confident        # D-024: below τ, rule 5 asks
                                and not inp.dispute_detected)                     # D-032: with a charge, rule 5 asks
                               or (inp.candidates == 1 and inp.product_type not in CARDS)),
                 "deny", "POL-OUT-OF-SCOPE")):
            if hit:                                       # rules 1–3 come before 3a/3b, so only rule 4 cites them
                return self._result(decision, [*carried, rule] if rule == "POL-OUT-OF-SCOPE" else [rule],
                                    request_call="active_or_general" if rule == "POL-HUMAN-REQUEST" else None)
        return None

    def decide(self, inp: DecisionInput) -> PolicyDecision:
        """§4.1 in order; the first terminal rule wins and every rule that fired is reported (FR-02)."""
        if (early := self.screen(inp)) is not None:
            return early
        if inp.intent == "human_request":
            return self._call_and_case(inp)
        carried = self._carried(inp)
        if (inp.intent_confidence < self.policies.clarify.intent_confidence_min or inp.candidates != 1
                or inp.intent == "out_of_scope"):         # D-032: an out_of_scope reading that reports a charge
            return self._clarify(inp, carried)
        zone, rules = self._zone(inp)
        modes, raised = self._modes(zone, inp)
        rules = [*carried, *rules, *raised]
        if zone == "medium" and inp.customer_confirmed is None:
            return self._result("confirm", rules, zone=zone, approval_modes=modes)
        if zone == "medium" and inp.customer_confirmed is False:
            return self._clarify(inp, rules)              # [assumption] "not that charge": identify it again
        return self._open(inp, zone, modes, [*rules, "POL-TICKET-ALWAYS"], "handoff")

    def _call_and_case(self, inp: DecisionInput) -> PolicyDecision:
        """Rule 3a with a charge (D-020, D-029): the call goes on the case opened for the one card transaction the
        customer did not reject, and that case follows its zone, so the high zone still blocks. Below τ (D-031), or
        with no such transaction, only the call, on the active case or a general one: nothing is opened or blocked."""
        accepted = inp.intent_confidence >= self.policies.clarify.intent_confidence_min
        if not accepted or inp.candidates != 1 or inp.product_type not in CARDS or inp.customer_confirmed is False:
            return self._result("connect_person", ["POL-HUMAN-REQUEST"], request_call="active_or_general")
        zone, rules = self._zone(inp)
        modes, raised = self._modes(zone, inp)
        return self._open(inp, zone, modes, ["POL-HUMAN-REQUEST", *rules, *raised, "POL-TICKET-ALWAYS"],
                          "connect_person", request_call="opened_case")

    def _open(self, inp: DecisionInput, zone: Zone, modes: dict[str, ApprovalMode], rules: list[str],
              held: Decision, **call) -> PolicyDecision:
        """Rules 7–9 once the case is opened (§4.2): the high zone blocks when no person must approve the block (case in
        verification); otherwise the decision `held` leaves the case in review with the reason a person looks at it."""
        blocks = zone == "high" and modes["block_card"] != "human_required"
        withheld = D029_CALL_WITHHOLDS_BLOCK_REASON if held == "connect_person" else None   # D-029, see the constant
        if blocks and withheld is None:
            return self._result("block_and_open_case", rules, zone=zone, approval_modes=modes,
                                allowed_actions=["open_case", "block_card"],
                                queue_status_after=self.policies.approval.manual_check_leaves_case_in, **call)
        if blocks:
            reason = withheld
        elif zone == "high":                              # per_action makes the block manual_check: a raiser stopped it
            over = self.amount_tier(inp.amount, inp.currency, inp.country) == "human_required"
            reason = "amount_over_case_gate" if over else "supervised_mode"
        else:
            reason = "zone_human" if zone == "human" else "zone_medium"
        return self._result(held, rules, zone=zone, approval_modes=modes, allowed_actions=["open_case"],
                            handoff_reason=reason, queue_status_after="review", **call)

    def _zone(self, inp: DecisionInput) -> tuple[Zone, list[str]]:
        """Rule 6: a null score, an llm score or one from a source that does not decide is zone human, each with its
        own id (AC-02); otherwise rules 7–9 by the score's band (AC-01)."""
        source, deciding = inp.score_source, self.policies.scoring.deciding_sources
        rules = [rule for rule, hit in (("POL-SCORE-NULL", inp.score is None),
                                        ("POL-SCORE-LLM", source == "llm"),
                                        ("POL-SCORE-SOURCE", source not in (None, "llm", *deciding))) if hit]
        if rules:
            return "human", rules
        zones = self.policies.zones
        zone = ("high" if inp.score >= zones["high"].score_min
                else "medium" if inp.score >= zones["medium"].score_min else "human")
        return zone, [ZONE_RULE[zone]]

    def _clarify(self, inp: DecisionInput, rules: list[str]) -> PolicyDecision:
        """Rules 5 and 5b (AC-08): ask; once max_clarification_turns questions were sent, hand off to a person and
        register a general call (D-024): there is no single transaction to open a case for."""
        if inp.clarification_turns >= self.policies.clarify.max_clarification_turns:
            return self._result("handoff", [*rules, "POL-CLARIFY-EXHAUSTED"], handoff_reason="clarification_exhausted",
                                request_call="general")
        return self._result("ask", [*rules, "POL-CLARIFY"])

    def _result(self, decision: str, rule_ids: list[str], **fields) -> PolicyDecision:
        guardrails = dict.fromkeys(self.policies.rules[rule].guardrail for rule in rule_ids)
        return PolicyDecision(decision=decision, rule_ids=rule_ids, guardrail_ids=[g for g in guardrails if g],
                              policies_version=self.version, **fields)

    def _deny(self, action: str, policy_id: str, rule_ids: list[str]) -> Deny:
        return Deny(action=action, policy_id=policy_id, guardrail_id=self.policies.rules[policy_id].guardrail,
                    rule_ids=rule_ids or [policy_id], policies_version=self.version)
