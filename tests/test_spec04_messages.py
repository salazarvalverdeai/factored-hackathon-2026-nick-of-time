"""Spec 04 — contracts/messages.yaml (offline, no network)."""
import re
from pathlib import Path

import pytest
import yaml

PATH = Path(__file__).resolve().parents[1] / "contracts" / "messages.yaml"
PLACEHOLDER = re.compile(r"\{([a-z_0-9]+)\}")
FORBIDDEN = re.compile(r"score|policy|policies|política|politica|rule id|fraud_score|zone|zona", re.I)
PROMISE = re.compile(r"cr[eé]dito provisional|crédito provisório|devolver|devolveremos|reembols", re.I)


def load():
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def leaves(node, path=()):
    if isinstance(node, dict) and "es" in node:
        yield ".".join(path), node
    elif isinstance(node, dict):
        for k, v in node.items():
            if k != "version":
                yield from leaves(v, path + (k,))


def test_ac_10_yaml_loads_with_version_and_one_placeholder_syntax():
    data = load()
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["version"])
    for _, leaf in leaves(data):
        for lang in ("es", "pt"):
            assert "{{" not in leaf[lang] and "%(" not in leaf[lang]


def test_ac_10_every_template_has_es_and_pt():
    found = list(leaves(load()))
    assert len(found) > 30
    for key, leaf in found:
        for lang in ("es", "pt"):
            assert isinstance(leaf.get(lang), str) and leaf[lang].strip(), f"{key}.{lang}"


def test_ac_10_placeholder_sets_match_between_es_and_pt():
    for key, leaf in leaves(load()):
        assert set(PLACEHOLDER.findall(leaf["es"])) == set(PLACEHOLDER.findall(leaf["pt"])), key


@pytest.mark.parametrize("top", ["greet", "plan", "connect", "suggest", "status", "receipt"])
def test_ac_15_ac_16_ac_29_spec_names_top_level_keys(top):
    assert top in load()


def test_ac_15_greet_uses_profile_first_name_and_max_three_capabilities():
    greet = load()["greet"]
    assert "{first_name}" in greet["hello"]["es"] and "{first_name}" in greet["hello"]["pt"]
    assert len([k for k in greet if k.startswith("capability_")]) <= 3
    assert "persona" in greet["human_review"]["es"] and "pessoa" in greet["human_review"]["pt"]


def test_ac_16_plan_has_numbered_steps_and_confirmation():
    plan = load()["plan"]
    steps = [v for k, v in plan.items() if k.startswith("step_")]
    assert steps and all("{step_n}" in s["es"] for s in steps)
    assert "confirm_ask" in plan


def test_ac_06_ac_19_status_labels_match_spec_03():
    label = load()["status"]["label"]
    keys = ("received", "in_review", "resolved", "closed")
    assert [label[k]["es"] for k in keys] == ["Recibido", "En revisión", "Resuelto", "Cerrado"]
    assert [label[k]["pt"] for k in keys] == ["Recebido", "Em análise", "Resolvido", "Encerrado"]


def test_ac_19_status_reads_state_the_reading_time():
    status = load()["status"]
    for key in ("card_read", "case_read"):
        assert "{read_at}" in status[key]["es"] and "{read_at}" in status[key]["pt"]
    assert "read_failed" in status


def test_ac_29_ac_31_ac_32_suggest_chips_cover_spec_table_with_kinds():
    suggest = load()["suggest"]
    expected = {
        "report_unrecognized": "text", "report_duplicate": "text", "check_case": "text",
        "none_of_these": "action", "show_recent": "text", "dont_remember_amount": "text",
        "talk_to_person": "action", "confirm_yes": "action", "confirm_no": "action",
        "view_case": "link", "send_receipt": "action", "request_call": "action", "add_info": "text",
        "request_reevaluation": "action", "report_another": "text", "reauthenticate": "link",
    }
    assert {k: v["kind"] for k, v in suggest.items()} == expected
    assert suggest["report_unrecognized"]["es"] == "No reconozco un cargo"
    assert suggest["request_call"]["es"] == "Que me llame una persona"


def test_ac_11_ac_16_connect_keys_exist():
    assert {"requested", "requested_case", "general_contact"} <= set(load()["connect"])


def test_ac_21_receipt_has_required_facts():
    receipt = load()["receipt"]
    text = " ".join(v["es"] for v in receipt.values())
    for name in ("last4", "verification_id", "verified_at", "case_id", "deadline_date", "deadline_source"):
        assert "{%s}" % name in text, name
    assert {"what_ai_did", "what_a_person_does"} <= set(receipt)


def test_ac_30_no_forbidden_words_in_customer_text():
    for key, leaf in leaves(load()):
        for lang in ("es", "pt"):
            text = PLACEHOLDER.sub("", leaf[lang])
            assert not FORBIDDEN.search(text), f"{key}.{lang}"
            assert not re.search(r"\bPOL-|\bG-[A-Z]+-\d", text), key
        assert not re.search(r"\{(score|policy_id|rule_id|zone|fraud_score|transcript)\}", leaf["es"])


def test_ac_16_no_promise_of_outcome_or_credit():
    for key, leaf in leaves(load()):
        assert not PROMISE.search(leaf["es"] + " " + leaf["pt"]), key
