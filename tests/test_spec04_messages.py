"""Spec 04 — contracts/messages.yaml (offline, no network).

These tests support AC-06, AC-10, AC-11, AC-15, AC-16, AC-18, AC-19, AC-21, AC-25, AC-26, AC-28, AC-29, AC-31,
AC-32 by checking the contract file only; the behavior itself is tested in T2-T6.
"""
import re
from pathlib import Path

import pytest
import yaml

PATH = Path(__file__).resolve().parents[1] / "contracts" / "messages.yaml"
PLACEHOLDER = re.compile(r"\{([a-z_0-9]+)\}")
ALLOWED = {
    "first_name", "case_id", "ruling_deadline", "credit_deadline", "deadline_source",
    "source_url", "verified_on", "amount", "currency", "merchant", "display_amount", "display_currency",
    "rate", "rate_source", "as_of", "last4", "verification_id", "verified_at", "read_at", "status_label",
    "card_label", "action_label", "step_n", "case_url", "receipt_id", "channel", "expected_contact_by",
}
FORBIDDEN = re.compile(
    r"score|puntaje|puntuaci|pontua|policy|policies|pol[ií]tica|rule id|fraud_score|zone|zona|"
    r"riesgo|risco|transcript|transcrip|transcri", re.I)
PROMISE = re.compile(
    r"cr[eé]dito provisional|cr[eé]dito provis|abono|devolver|devolvemos|devolveremos|reembols|estorno|"
    r"a tu favor|a seu favor|devolu[cç]|reintegr|ressarc|acredit(amos|aremos)|\bcreditar(emos)?\b|"
    r"recibir[aá]s (el|los|tu) (dinero|fondos|monto)|receber[aá] (o|os|seu) (dinheiro|valor)", re.I)
DELIVERY = re.compile(r"\benvi[eé]\b|\benviei\b|\benviamos\b|(fue|foi) enviad|entregad|entregue", re.I)
SPEC_CHIPS = {  # spec 04 §4.5 table: id -> (kind, ES label, PT label)
    "report_unrecognized": ("text", "No reconozco un cargo", "Não reconheço uma cobrança"),
    "report_duplicate": ("text", "Me cobraron dos veces", "Me cobraram duas vezes"),
    "check_case": ("text", "¿Cómo va mi caso?", "Como está meu caso?"),
    "none_of_these": ("action", "Ninguno de estos", "Nenhuma dessas"),
    "show_recent": ("text", "Muéstrame mis últimos cargos", "Mostre minhas últimas cobranças"),
    "dont_remember_amount": ("text", "No recuerdo el monto", "Não lembro o valor"),
    "talk_to_person": ("action", "Hablar con una persona", "Falar com uma pessoa"),
    "confirm_yes": ("action", "Sí, continúa", "Sim, continue"),
    "confirm_charge": ("action", "Sí, es ese cargo", "Sim, é essa cobrança"),
    "confirm_no": ("action", "No es ese cargo", "Não é essa cobrança"),
    "view_case": ("link", "Ver mi caso", "Ver meu caso"),
    "send_summary": ("action", "Enviarme el comprobante", "Me envie o comprovante"),
    "request_call": ("action", "Que me llame una persona", "Quero que me liguem"),
    "add_info": ("text", "Agregar información", "Adicionar informações"),
    "request_reevaluation": ("action", "Pedir reevaluación", "Pedir reavaliação"),
    "intent_unrecognized": ("text", "No reconozco este cargo", "Não reconheço esta cobrança"),          # D-071
    "intent_wrongful": ("text", "Lo reconozco, pero el cobro está mal", "Reconheço, mas a cobrança está errada"),
    "report_another": ("text", "Reportar otro cargo", "Informar outra cobrança"),
    "reauthenticate": ("link", "Verificar de nuevo", "Verificar novamente"),
}


def text():
    return PATH.read_text(encoding="utf-8")


def load():
    return yaml.safe_load(text())


def leaves(node, path=()):
    """A leaf is a dict with es or pt; a scalar outside a leaf is yielded empty so the ES/PT test fails."""
    if isinstance(node, dict) and ("es" in node or "pt" in node):
        yield ".".join(path), node
    elif isinstance(node, dict):
        for k, v in node.items():
            if k != "version":
                yield from leaves(v, path + (k,))
    else:
        yield ".".join(path), {}


def test_ac_10_yaml_loads_with_version_and_one_placeholder_syntax():
    data = load()
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["version"])
    for _, leaf in leaves(data):
        for lang in ("es", "pt"):
            assert "{{" not in leaf.get(lang, "") and "%(" not in leaf.get(lang, "")


def test_ac_10_every_template_has_es_and_pt():
    found = list(leaves(load()))
    assert len(found) > 40
    for key, leaf in found:
        for lang in ("es", "pt"):
            assert isinstance(leaf.get(lang), str) and leaf[lang].strip(), f"{key}.{lang}"


def test_ac_10_placeholder_sets_match_between_es_and_pt():
    for key, leaf in leaves(load()):
        assert set(PLACEHOLDER.findall(leaf["es"])) == set(PLACEHOLDER.findall(leaf["pt"])), key


def test_ac_10_es_and_pt_texts_differ():
    for key, leaf in leaves(load()):
        assert leaf["es"] != leaf["pt"], key


def test_adr_0016_every_placeholder_is_allowed_and_documented_in_header():
    header = text().split("version:")[0]
    for key, leaf in leaves(load()):
        names = set(PLACEHOLDER.findall(leaf["es"]))
        assert names <= ALLOWED, (key, names - ALLOWED)
    for name in ALLOWED:
        assert name in header, name


@pytest.mark.parametrize(
    "top", ["greet", "plan", "connect", "suggest", "status", "receipt", "notify", "refuse", "clarify"])
def test_ac_15_ac_16_ac_29_ac_26_spec_names_top_level_keys(top):
    assert top in load()


def test_ac_15_greet_uses_profile_first_name_and_one_to_three_capabilities():
    greet = load()["greet"]
    for lang in ("es", "pt"):
        assert "{first_name}" in greet["hello"][lang]
    assert 1 <= len([k for k in greet if k.startswith("capability_")]) <= 3
    assert "persona" in greet["human_review"]["es"] and "pessoa" in greet["human_review"]["pt"]


def test_ac_16_plan_has_numbered_steps_and_confirmation():
    plan = load()["plan"]
    steps = [v for k, v in plan.items() if k.startswith("step_")]
    assert steps and all("{step_n}" in s["es"] and "{step_n}" in s["pt"] for s in steps)
    assert "confirm_ask" in plan


def test_ac_11_supports_confirm_question_and_confirm_chips():
    data = load()
    assert data["plan"]["confirm_ask"]["es"].startswith("¿")
    assert data["suggest"]["confirm_yes"]["kind"] == "action"
    assert data["suggest"]["confirm_no"]["kind"] == "action"


def test_ac_06_ac_19_status_labels_match_spec_03_and_map_queue_states():
    label = load()["status"]["label"]
    keys = ("received", "in_review", "resolved", "closed")
    assert [label[k]["es"] for k in keys] == ["Recibido", "En revisión", "Resuelto", "Cerrado"]
    assert [label[k]["pt"] for k in keys] == ["Recebido", "Em análise", "Resolvido", "Encerrado"]
    assert [label[k]["from"] for k in keys] == [["new"], ["verification", "review"], ["resolved"], ["closed"]]


def test_ac_06_case_status_has_one_line_per_stored_deadline_and_a_null_variant():
    status = load()["status"]
    assert not {"ruling_deadline", "credit_deadline"} & set(PLACEHOLDER.findall(status["case_read"]["es"]))
    for key in ("ruling_deadline", "credit_deadline"):
        for lang in ("es", "pt"):
            assert {key, "deadline_source"} <= set(PLACEHOLDER.findall(status[key][lang]))
    assert not PLACEHOLDER.search(status["deadline_unknown"]["es"] + status["deadline_unknown"]["pt"])
    assert not re.search(r"deadline_date|deadline_ruling|deadline_credit", text())


def test_ac_19_status_reads_state_the_reading_time_and_failure_has_no_facts():
    status = load()["status"]
    for key in ("card_read", "case_read"):
        for lang in ("es", "pt"):
            assert "{read_at}" in status[key][lang]
    labels = [v[lang] for group in ("label", "card_label") for v in status[group].values() for lang in ("es", "pt")]
    for lang in ("es", "pt"):
        assert not PLACEHOLDER.search(status["read_failed"][lang])
        assert not any(label.lower() in status["read_failed"][lang].lower() for label in labels)


def test_ac_19_card_and_action_labels_are_localized_lookups():
    status = load()["status"]
    assert set(status["card_label"]) == {"active", "blocked", "closed", "suspended"}
    assert set(status["action_label"]) == {"open_case", "block_card", "request_call", "send_case_summary"}
    assert status["card_label"]["blocked"] == {"es": "bloqueada", "pt": "bloqueado"}


def test_ac_18_four_action_states_and_only_verified_carries_a_time():
    status = load()["status"]
    states = ("action_in_progress", "action_requested", "action_verified", "action_not_confirmed")
    for key in states:
        for lang in ("es", "pt"):
            assert "{action_label}" in status[key][lang]
            assert ("{verified_at}" in status[key][lang]) == (key == "action_verified"), (key, lang)
    assert "SIN CONFIRMAR" in status["action_not_confirmed"]["es"]
    assert "SEM CONFIRMAÇÃO" in status["action_not_confirmed"]["pt"]


def test_ac_29_ac_31_ac_32_chip_labels_and_kinds_equal_spec_table():
    suggest = load()["suggest"]
    assert {k: (v["kind"], v["es"], v["pt"]) for k, v in suggest.items()} == SPEC_CHIPS


GREETING = {"es": r"^Listo,", "pt": r"^Pronto,"}  # approved greetings; ES "Pronto" means "soon" and is rejected
TIME_WORDS = re.compile(r"\d|pronto|breve|hoy|hoje|mañana|amanhã|hora|minut|d[ií]a|logo|luego|semana|tarde|"
                        r"momento|enseguida|ahorita|cedo", re.I)


def test_ac_28_d008_connect_keys_exist_and_null_variants_promise_no_time():
    connect = load()["connect"]
    assert {"requested", "requested_no_window", "requested_case", "requested_case_no_window",
            "general_contact"} <= set(connect)
    for dated in ("requested", "requested_case"):
        for lang in ("es", "pt"):
            assert "{expected_contact_by}" in connect[dated][lang], (dated, lang)
            text = connect[f"{dated}_no_window"][lang]
            assert "expected_contact_by" not in text, (dated, lang)
            body = PLACEHOLDER.sub("", re.sub(GREETING[lang], "", text))
            assert not TIME_WORDS.search(body), (dated, lang, body)


def test_ac_21_ac_25_receipt_has_required_facts():
    receipt = load()["receipt"]
    joined = " ".join(v["es"] for v in receipt.values())
    for name in ("last4", "verification_id", "verified_at", "case_id", "ruling_deadline", "credit_deadline",
                 "deadline_source", "source_url", "verified_on", "display_amount", "rate_source"):
        assert "{%s}" % name in joined, name
    assert "verificada" in receipt["card_blocked"]["es"] and "verificado" in receipt["card_blocked"]["pt"]
    assert {"deadline_unknown", "what_a_person_does", "what_ai_did_blocked", "what_ai_did_case_only",
            "what_ai_did_block_unconfirmed", "transaction_no_merchant"} <= set(receipt)
    assert "sent_to" not in receipt


def test_ac_26_send_requested_is_not_delivery():
    """accepted != verified (rule 4): only notify.send_delivered may state a delivery."""
    data = load()
    assert {"send_requested", "send_delivered"} <= set(data["notify"])
    claims = [(f"receipt.{k}", v) for k, v in leaves(data["receipt"])]
    claims.append(("notify.send_requested", data["notify"]["send_requested"]))
    for key, leaf in claims:
        for lang in ("es", "pt"):
            assert not DELIVERY.search(leaf[lang]), f"{key}.{lang}"
    for lang in ("es", "pt"):
        assert "{channel}" in data["notify"]["send_requested"][lang]


def test_never_send_no_internal_terms_in_customer_text():
    """notifications.never_send (policies.yaml): no score, policy ids, zones or transcript, ES/PT."""
    for key, leaf in leaves(load()):
        for lang in ("es", "pt"):
            plain = PLACEHOLDER.sub("", leaf[lang])
            assert not FORBIDDEN.search(plain), f"{key}.{lang}"
            assert not re.search(r"\bPOL-|\bG-[A-Z]+-\d", plain), key
    assert not re.search(r"\{(score|policy_id|rule_id|zone|fraud_score|transcript)\}", text())


def test_rule_6_no_promise_of_outcome_or_credit():
    """CLAUDE.md rule 6: provisional credit is always a human decision; templates never promise it."""
    for key, leaf in leaves(load()):
        assert not PROMISE.search(leaf["es"] + " " + leaf["pt"]), key


ACTION_CLAIM = re.compile(r"bloque[eé]|bloquei|\babr[ií]\b|registr[eé]\b|registrei|envi[eé]\b|enviei|\bcre[eé]\b|"
                          r"criei|cancel[eé]\b|cancelei", re.I)
REFUSAL_REASON = re.compile(r"regla|regra|norma|segurid|seguran|guardrail|inyecci|inje[cç]|porque|pois|ya que|"
                            r"j[aá] que", re.I)


def test_ac_11_msg2_refuse_clarify_declined_state_no_action_time_or_reason():
    """MSG2: each text asks or declines; none states an action or a time; the refusal gives no reason.
    The refuse behavior (DENY, guardrail id, policy_denials) is tested in T2."""
    data = load()
    for group, key in (("refuse", "deny"), ("clarify", "ask_what"), ("plan", "declined")):
        for lang in ("es", "pt"):
            t = data[group][key][lang]
            assert not PLACEHOLDER.search(t), (group, lang)
            assert not TIME_WORDS.search(t), (group, lang)  # \d also rejects "48 horas" (ADR 0023)
            assert not ACTION_CLAIM.search(t), (group, lang)
    for lang in ("es", "pt"):
        assert not REFUSAL_REASON.search(data["refuse"]["deny"][lang]), lang


def test_adr_0023_no_template_promises_48_hours():
    assert not re.search(r"48\s*(h\b|hora)", text(), re.I)


@pytest.mark.parametrize("bad", ["Bloqueé tu tarjeta", "Ya abrí un caso", "registré tu caso", "em 2 dias úteis",
                                 "te llamará pronto", "una regla de seguridad lo impide"])
def test_ac_11_msg2_guard_regexes_catch_known_violations(bad):
    assert ACTION_CLAIM.search(bad) or TIME_WORDS.search(bad) or REFUSAL_REASON.search(bad)
