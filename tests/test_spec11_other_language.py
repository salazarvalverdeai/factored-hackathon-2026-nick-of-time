"""Spec 11 / G-IN-03: a clear non-ES/PT sentence is a rules reading (`other_language`); ES/PT stay as they were."""
from __future__ import annotations

from datetime import date

import pytest

from nick_of_time.nlu import NLU

TODAY = date(2026, 6, 1)
OTHER = ["I do not recognize a charge on my card, please help me",
         "Je ne reconnais pas un paiement sur ma carte, pouvez vous m'aider",
         "Ich kenne diese Abbuchung nicht und das ist meine Karte"]
SAME = ["no reconozco un cargo de Amazon Prime", "ok", "gracias", "ok gracias thank you", "Netflix", "12345",
        "Não reconheço uma cobrança do Uber, help", "no entiendo, mi tarjeta tiene un charge de Spotify",
        "quiero hablar con un asesor please", "hola, pode me ajudar? no tengo claro el cargo"]


@pytest.mark.parametrize("text", OTHER)
def test_g_in_03_a_clear_sentence_in_another_language_is_flagged(text):
    assert NLU().parse(text, "pt", today=TODAY).other_language is True


@pytest.mark.parametrize("text", SAME)
def test_g_in_03_loanwords_short_inputs_and_code_switching_are_not_another_language(text):
    assert NLU().parse(text, "es", today=TODAY).other_language is False
