"""Spec 18 AC-02: the harness (spec 10) computes its final-state checks with `nick_of_time.audit`, so offline evaluation
and the production audit share one implementation. The harness behavior itself is spec 10 AC-08
(`tests/test_spec10_harness.py`); this file pins that the two are the same code and give the same findings."""
from __future__ import annotations

import pytest

from eval.harness import compare
from nick_of_time import audit
from nick_of_time.contracts import StatusReply


def test_ac_02_the_harness_imports_the_auditors_own_check_functions():
    """AC-02: one implementation: the harness's A5 and A6 are the auditor's functions, not copies."""
    assert compare.check_coherence is audit.check_coherence
    assert compare.check_privacy is audit.check_privacy


@pytest.mark.parametrize("told, exposed", [
    ([], False),                                                                       # nothing told, nothing exposed
    ([{"subject": "PRD-FIXTURE00001", "stated_status": "Blocked", "read_status": "Blocked"}], False),
    ([{"subject": "PRD-FIXTURE00001", "stated_status": "Blocked", "read_status": "Active"}], True),
])
def test_ac_02_harness_findings_equal_the_auditors_on_the_same_final_state(told, exposed):
    """AC-02: for one FinalState, the harness's findings are exactly what the auditor returns on the same records."""
    final = {"status_replies": told, "other_customer_data_exposed": exposed}
    direct = [audit.check_coherence([StatusReply(**r) for r in told]),
              audit.check_privacy({}, other_customer_data_exposed=exposed)]
    assert compare.findings(final) == [f.model_dump(mode="json") for f in direct]
