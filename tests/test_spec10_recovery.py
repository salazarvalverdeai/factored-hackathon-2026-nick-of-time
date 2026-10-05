"""Spec 10 D-071 (AC-13, AC-14): the dev recovery variants. The harness presses a chip of the last reply the way the web
does, and scores the variants apart from the single-message metrics, in the `second_turn_recovery` block.

Offline: an in-memory httpx transport, and once the api stub (EVAL_MODE, fake provider); no real model."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from eval.harness import Api, metrics, report, run_one, run_set
from eval.harness.client import suggestions, turn_input
from tests.test_spec10_harness import EXAMPLES, final_for

ROOT = Path(__file__).resolve().parents[1]
BLOCK = EXAMPLES[0]
CHIPS = [{"id": "intent_unrecognized", "label": "No reconozco este cargo", "kind": "text", "action": None,
          "href": None},
         {"id": "talk_to_person", "label": "Hablar con una persona", "kind": "action",
          "action": {"type": "request_call", "value": None}, "href": None},
         {"id": "view_case", "label": "Ver mi caso", "kind": "link", "action": None, "href": "/case/K-104233"}]


def sse(turn: dict) -> str:
    """An SSE body as the api sends it: a progress event, then the one turn event."""
    return (f"event: progress\ndata: {json.dumps({'step': 'searching', 'label': 'Buscando'})}\n\n"
            f"event: turn\ndata: {json.dumps(turn)}\n\n")


def variant(case: dict, chip: str, how: str = "chip", case_id: str = "EV-0121") -> dict:
    """A recovery variant of `case`: its messages plus one chip press (or a typed answer)."""
    out = copy.deepcopy(case)
    answer = {"role": "customer", "text": "No reconozco este cargo", **({"chip": chip} if how == "chip" else {})}
    return {**out, "id": case_id, "variant_of": case["id"], "second_turn": how, "messages": [*out["messages"], answer]}


def api_offering(chips: list[dict], seen: list) -> Api:
    """An in-memory api whose every turn offers `chips` and whose final state meets the case's expected block."""
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/eval/seed":
            body = json.loads(request.content)
            return httpx.Response(200, json={"session_id": "S-0000000000000001", "thread_id": "t-1",
                                             "run_id": body["run_id"], "arm": body["arm"], "mode": "replay"})
        if request.url.path.endswith("/runs/stream"):
            return httpx.Response(200, text=sse({"reply": "…", "suggestions": chips}))
        return httpx.Response(200, json=final_for(BLOCK))
    return Api(httpx.Client(transport=httpx.MockTransport(handle), base_url="http://eval.test"))


def inputs(seen: list) -> list[dict]:
    return [json.loads(r.content)["input"] for r in seen if r.url.path.endswith("/runs/stream")]


def test_ac_14_a_text_chip_is_pressed_as_its_label_and_an_action_chip_as_its_action():
    """AC-14: as apps/web/lib/live.ts does: a text chip sends its label as the message; an action chip sends
    `{"messages": [], "action": ...}`, which skips the classifier (spec 04 AC-32). Typed messages are unchanged."""
    for chip, sent in (("intent_unrecognized", {"messages": [{"role": "user", "content": "No reconozco este cargo"}]}),
                       ("talk_to_person", {"messages": [], "action": {"type": "request_call", "value": None}})):
        seen: list = []
        record = run_one(api_offering(CHIPS, seen), variant(BLOCK, chip), "S0", 1)
        assert record["status"] == "ok"
        assert inputs(seen) == [{"messages": [{"role": "user", "content": BLOCK["messages"][0]["text"]}],
                                 "language": "es"}, {**sent, "language": "es"}]


def test_ac_14_a_chip_the_last_reply_did_not_offer_fails_the_run_and_it_stays_counted():
    """AC-14 (with AC-09): a chip that was not offered (or a link chip) cannot be pressed: the run fails, it is not
    dropped, and no turn is sent for it."""
    for offered in ([chip for chip in CHIPS if chip["id"] != "intent_unrecognized"], CHIPS):
        seen: list = []
        pressed = "intent_unrecognized" if offered is not CHIPS else "view_case"
        record = run_one(api_offering(offered, seen), variant(BLOCK, pressed), "S0", 1)
        assert record["status"] == "failed" and "did not offer the chip" in record["error"]
        assert len(inputs(seen)) == 1 and not record["passed"]
    assert metrics.group([record])["second_turn_recovery"]["denominator"] == 1


def test_ac_14_the_chips_are_read_from_the_last_turn_event_only():
    """AC-14: the chips come from the `turn` event of the SSE body (never the reply text); no turn event, no chips."""
    assert [c["id"] for c in suggestions(sse({"reply": "x", "suggestions": CHIPS}).encode())] == [c["id"] for c in CHIPS]
    assert suggestions(b"event: progress\ndata: {}\n\n") == []
    assert turn_input({"text": "hola"}, []) == {"messages": [{"role": "user", "content": "hola"}]}


def test_ac_14_a_chip_press_runs_against_the_api_stub():
    """AC-14 (with AC-12): offline against the api stub, a chip of the stub's turn is pressed and the run completes."""
    api = Api(TestClient(create_app(eval_mode=True), base_url="https://testserver"))
    record = run_set([variant(BLOCK, "s2")], ["S0"], runs=1, api=api, workers=1)[0]
    assert record["status"] == "ok" and record["variant_of"] == "EV-0001" and record["second_turn"] == "chip"


def record(case_id: str, passed: bool, *, variant_of: str | None = None, how: str | None = None,
           language: str = "es", type_: str = "human") -> dict:
    base = run_one(api_offering(CHIPS, []), {**BLOCK, "id": case_id}, "S0", 1)
    return {**base, "case_id": case_id, "passed": passed, "variant_of": variant_of, "second_turn": how,
            "language": language, "type": type_, "segment": "Basic", "expected": {**base["expected"],
                                                                                   "decision": "handoff"}}


def runs() -> list[dict]:
    """Two originals that fail (they end in ask) twice each, and their typed and chip variants."""
    return [record("EV-0105", False), record("EV-0105", False), record("EV-0119", False), record("EV-0119", True),
            record("EV-0123", True, variant_of="EV-0105", how="typed"),
            record("EV-0124", True, variant_of="EV-0105", how="chip"),
            record("EV-0127", False, variant_of="EV-0119", how="typed"),
            record("EV-0128", True, variant_of="EV-0119", how="chip")]


def test_ac_13_recovery_is_reported_apart_with_counts_and_wilson_intervals():
    """AC-13: second_turn_recovery (all, typed, chip) over the variant runs, and second_turn_baseline over the runs
    of the cases they follow, each with numerator, denominator and a 95% Wilson interval."""
    stats = metrics.group(runs())
    got = {name: (stats[name]["numerator"], stats[name]["denominator"]) for name in metrics.RECOVERY}
    assert got == {"second_turn_recovery": (3, 4), "second_turn_recovery_typed": (1, 2),
                   "second_turn_recovery_chip": (2, 2), "second_turn_baseline": (1, 4)}
    low, high = metrics.wilson(3, 4)
    assert stats["second_turn_recovery"] == {"value": 0.75, "numerator": 3, "denominator": 4,
                                             "ci_low": round(low, 4), "ci_high": round(high, 4)}


def test_ac_13_variant_runs_never_change_the_single_message_metrics():
    """AC-13: the §4.1 metrics count the original cases only: adding the variants changes none of them, and a set
    without variants has no recovery block."""
    with_variants, originals = metrics.group(runs()), metrics.group(runs()[:4])
    for name in (*metrics.RATES, *metrics.VALUES):
        assert with_variants[name] == originals[name], name
    assert with_variants["pass_4"]["denominator"] == 2 and not set(metrics.RECOVERY) & set(originals)


def test_ac_13_summary_and_web_summary_carry_the_block_labeled_simulated():
    """AC-13 (with AC-11): summary.csv has the recovery rows (label [simulated], set dev) where variants ran; the web
    summary has the block per arm and counts the variant cases apart from `cases`."""
    rows = [row for row in metrics.summary(runs()) if row["metric"] in metrics.RECOVERY]
    assert rows and {row["label"] for row in rows} == {"[simulated]"} and {row["set"] for row in rows} == {"dev"}
    overall = {row["metric"]: (row["numerator"], row["denominator"]) for row in rows if row["language"] == "all"}
    assert overall["second_turn_recovery"] == (3, 4)
    meta = {"ended_at": "2026-10-05T00:00:00Z", "harness_git_sha": "x", "cases_sha256": "y",
            "protocol": {"status": "SEALED", "sha256": None}, "arms": {}}
    data = report.web_summary(runs(), meta)["data"]
    assert (data["cases"], data["variant_cases"]) == (2, 4)
    block = data["arms"][0]["second_turn_recovery"]
    assert set(block) == set(metrics.RECOVERY) and block["second_turn_recovery"]["numerator"] == 3


def test_ac_13_the_dev_set_feeds_the_block_and_the_held_out_has_none():
    """AC-13: the dev case file carries the variants the block scores (spec 09 AC-12); the held-out never does."""
    dev = [json.loads(line) for line in (ROOT / "eval/cases/dev.jsonl").read_text(encoding="utf-8").splitlines()]
    variants = [case for case in dev if case.get("variant_of")]
    assert len(variants) == 8 and {case["second_turn"] for case in variants} == {"typed", "chip"}
    assert all(case["set"] == "dev" for case in variants)


@pytest.mark.parametrize("name", ["second_turn_recovery", "second_turn_baseline"])
def test_ac_13_a_failed_variant_run_stays_in_the_denominator(name):
    """AC-13 (with AC-09): a failed run is a run that did not pass; it is never dropped from the block."""
    failed = [{**r, "status": "failed", "final_state": None, "passed": False} for r in runs()]
    assert metrics.group(failed)[name]["denominator"] == 4 and metrics.group(failed)[name]["numerator"] == 0
