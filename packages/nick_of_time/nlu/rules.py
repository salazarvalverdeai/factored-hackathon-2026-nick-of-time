"""B0 rules arm (spec 11 §4, AC-09): ES/PT keyword and pattern lists, regex slots, no model file, no network.

Priority when several intents match: `human_request` > `status_inquiry` > `wrongful_charge` > `unrecognized_charge`
> `out_of_scope`. A customer who asks for a person is never blocked, even inside a dispute message (AC-10). Status wins
over a dispute only when the dispute words are absent, or come with a past "already reported" form and no "another
charge"; `dispute_detected` is true whenever dispute words are present, so the graph still runs the dispute path
(spec 11 §6 and §8, decision D-020).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from .dates import _MONTHS, parse_date
from .injection import injection_flagged
from .text import fold

ARM, VERSION = "B0", "b0-v1"

_STAFF = r"(?:persona|humano|agente|asesor|ejecutivo|operador|atendente|pessoa|representante|gerente|supervisor)"
_PERSON = r"(?:alguem|alguien|" + _STAFF + ")"
# a request form of pasar/passar/comunicar: with the pronoun attached ("pásame") or right before it ("me pasa",
# "que me pase", "me passa"), or an imperative that opens the message; past forms ("me pasé", "me comuniqué",
# "passei") and third persons ("mi hijo pasa con el gerente") stay out
_ASK = (r"(?:\b(?:pas(?:ame|eme|enme|arme|arnos)|comuni(?:came|carme|carnos|queme|quenme))"
        r"|(?:(?<=\bme )|(?<=\bnos ))(?:pas(?:a|as|an|en|ar)|comuni(?:ca|cas|can|car|quen)|pass(?:a|am|ar|arem|e|em))"
        r"|(?<=\bque me )(?:pase|comunique)|^(?:pasa|pasen|passa|passe|passem|comunica|comuniquen))")
_CHARGE = r"(?:cargo|compra|cobro|cobranca|debito|transacao|transaccion|movimiento|consumo)"
_CHARGES = (r"(?:cargos?|compras?|cobros?|cobrancas?|debitos?|consumos?|movimientos?|transaccion(?:es)?|transacao|transacoes"
            r"|lancamentos?)")
# [assumption] a dispute noun opens a dispute only after a first-person want that is not negated ("quiero", not
# "ya no quiero"), or at the start of the message, then up to two opening verbs and an optional article: "quiero abrir
# una disputa" opens one; "necesito noticias de la disputa" or "¿cuándo me van a hacer el contracargo?" do not
_OPEN_VERB = r"(?:abrir|presentar|registrar|hacer|levantar|iniciar|fazer|pedir|solicitar|interponer|realizar|efetuar)"
_OPEN = (r"(?:(?<!\bno )(?<!\bnao )\b(?:quiero|quero|necesito|preciso|gostaria|deseo|desejo) (?:(?:de|" + _OPEN_VERB
         + r") ){0,2}|^" + _OPEN_VERB + r" (?:" + _OPEN_VERB + r" )?)(?:(?:un|una|um|uma|o|el|a|la) )?")
_INTENT_RULES: list[tuple[str, list[str]]] = [
    ("human_request", [
        # "comuni-" needs a person after it: "me comunico con ustedes por un cargo" is an opener, not a request
        r"\b(?!passei\b)(?:hablar|conversar|comuni\w*|pas\w*|falar|passar) (?:\w+ ){0,2}(?:con|com|para|a) "
        r"(?:un |una |um |uma |o |a )?" + _PERSON,
        # ES "el/la" and PT "pra/pro" only after a request form, and not "el gerente de la tienda"
        _ASK + r" (?:\w+ ){0,2}(?:con|com|para|pra|pro|a) (?:un |una |um |uma |o |a |el |la )?" + _PERSON
        + r"(?! (?:de|del|da|do)\b)",
        r"^(?:hablar|conversar|falar) (?:con|com|pra|pro) (?:el |la |o |a )?" + _PERSON + r"(?! (?:de|del|da|do)\b)",
        r"\b(?:quiero|necesito|quero|preciso|prefiero|prefiro) (?:(?!si |se )\w+ ){0,3}(?:un |una |um |uma |o |a )?" + _PERSON,
        # a message that is only the person word ("Supervisor", "Un asesor", "Humano por favor", "Atendente, por favor")
        r"^(?:un |una |um |uma |o |a |el |la )?" + _STAFF + r"(?: humano| real)?(?:,? por favor)?[.!? ]*$",
        r"\b(?:atienda|atiende|atenda|atendid[oa] por) (?:\w+ )?" + _PERSON,
        r"\b(?:atencion|atendimento) (?:humana|humano|personal)\b",
        # English (the customer must always reach a person, whatever the language): "can I talk to a person please?"
        r"\b(?:talk|speak|chat|connect|transfer|put) (?:\w+ ){0,3}(?:to|with|through) (?:a |an |the |some |my )?(?:real |live |human )?"
        r"(?:person|human|agent|representative|rep|someone|somebody|operator|advisor|supervisor|manager)\b",
        r"\b(?:want|need|get|give) (?:\w+ ){0,2}(?:a |an |the )?(?:real |live )?(?:human|person|agent|representative|operator)\b",
    ]),
    ("status_inquiry", [
        r"\b(?:como va|como esta|como anda|en que va|en que esta|como esta indo|status|estado(?! de cuenta)|andamento|novedades|"
        r"novidades|noticias)\b.*\b(?:caso|reclamo|reclamacion|disputa|tarjeta|cartao|chamado|protocolo|contestacao)\b",
        r"\b(?:ya|ja)\b.*\b(?:bloquearon|bloqueada|bloqueado|bloquearam|bloqueou|bloqueo)\b",
        r"\b(?:estado|status|situacao) (?:de|do|da) (?:mi |meu |minha )?(?:caso|reclamo|disputa|tarjeta|cartao)\b",
        r"\b(?:mi|meu) (?:caso|chamado)\b.*\b(?:avance|avanzo|progreso|resolvieron|resolveram|resolvido)\b",
    ]),
    ("wrongful_charge", [
        r"\b(?:cobraron|cobrado|cobraram|cobrou|(?:me|nos|le) cobro|cargaron|debitaron|debitado|debitaram)\b.*"
        r"\b(?:dos veces|2 veces|doble|duas vezes|2 vezes|de mas|a mais|dobro|otra vez|de novo)\b",
        r"\b(?:cobro|cargo|cobranca|debito|compra) (?:duplicad[oa]|doble|repetid[oa]|em duplicidade)\b",
        r"\bdoble (?:cobro|cargo)\b|\bcobranca em duplicidade\b",
        r"\b(?:monto|importe|valor) (?:incorrecto|erroneo|equivocado|errado|incorreto)\b",
        r"\b(?:no recibi|nao recebi|nunca llego|nunca chegou)\b",
        r"\b(?:cancele|cancelei|cancelamos|devolvi|devolvei|reembolso|reembolsaron)\b.*\b(?:cobr|cargo|debit)\w*",
        # EV-0107: charged for a service the customer does not have or never contracted
        r"\b(?:cobraron|cobrado|cobraram|cobrou|(?:me|nos|le) cobro|cargaron|debitaron|debitado|debitaram)\b.*"
        r"\b(?:no|nao) (?:(?:contrate|contratei|solicite|solicitei|assinei|suscribi)\b|(?:tengo|tenho|uso) (?:\w+ ){0,2}"
        r"(?:servicio|servico|suscripcion|assinatura|plan|plano|membresia)\b)",
    ]),
    ("unrecognized_charge", [
        r"\b(?:no|nao) (?:reconozco|reconheco|conozco|fui yo|fui eu|fue mio|foi eu|foi meu)\b",
        r"\b(?:no|nao) (?:hice|fiz|realice|realizei|autorice|autorizei|compre|comprei|reconhecemos)\b",
        r"\b(?:desconozco|desconheco|desconhecida|desconocida|desconocido|desconhecido)\b",
        r"\b(?:cargo|compra|cobro|cobranca|movimiento|transacao|lancamento)\b.*"
        r"\b(?:raro|extrano|sospechos\w*|suspeit\w*|estranh\w*|fraud\w*|indebid\w*|no autorizad\w*|nao autorizad\w*)\b",
        r"\b(?:fraude|fraudulent\w*|clonaron|clonaram|clonado|robaron mi tarjeta|roubaram meu cartao)\b",
        r"\b(?:disputar|desconocer|contestar|impugnar|reportar|informar|reclamar) (?:\w+ ){0,2}"
        r"(?:cargo|compra|cobro|cobranca|debito|transacao|movimiento)\b",
        r"\b(?:no es mi[oa]|nao e (?:meu|minha))\b",
    ]),
]
# 11c dispute readings: they set dispute_detected, and open a dispute only when no status rule fires or another charge
# is named, so a status question that restates its dispute ("¿cómo va mi caso? Quiero el contracargo ya") stays a
# status question with the flag (D-020 (a))
_DISPUTE_11C = [re.compile(p) for p in [
        # not "informar", nor a charge still to come: "quiero informar/reportar un consumo que voy a hacer" is a travel
        # notice
        r"\b(?:disputar|desconocer|contestar|impugnar|reportar|reclamar) (?:\w+ ){0,2}(?:transaccion|consumo)\b"
        r"(?! que (?:voy|vamos|vou|vai|va|van) )",
        # plurals only next to a charge noun: "esos cargos no son míos", not "esos problemas no son míos"
        r"\b" + _CHARGES + r"(?: \w+){0,3} (?:no son mi[oa]s|nao sao (?:meus|minhas))\b",
        r"\b(?:no son mi[oa]s|nao sao (?:meus|minhas))(?: \w+){0,2} " + _CHARGES + r"\b",
        r"\bno (?:es|son) mis? " + _CHARGES + r"\b",
        r"\b(?:alguien|alguem) (?:uso|usou|ha usado|esta usando|utilizo|utilizou|ha utilizado|esta utilizando) "
        r"(?:(?:o|a) )?(?:mi|meu|minha) (?:tarjeta|cartao)\b",
        # the strong nouns need no charge noun; reclamo, reclamacao and aclaracion (also generic words) do
        _OPEN + r"(?:disputa|contracargo|chargeback|contestacao|estorno)\b",
        _OPEN + r"(?:reclamo|reclamacao|aclaracion) (?:\w+ ){0,2}" + _CHARGE + r"\b",
]]
_COMPILED = [(intent, [re.compile(p) for p in pats]) for intent, pats in _INTENT_RULES]
# asking to be called; skipped right after a negation ("prefiero que no me llamen", "nao precisa ligacao")
_CALL = re.compile(r"\b(?:que me llamen?|llamenme|llamame|me llamen|me liguem?|me liga|llamar(?:me|nos))\b"
                   r"|\b(?:me|nos) (?:pueden|puede|podrian|podria) llamar\b|\bpodem? me ligar\b"
                   r"|\b(?:quiero|necesito|pido|solicito|quero|preciso|peco) (?:\w+ ){0,2}(?:llamada|ligacao)\b")
_NEGATED = re.compile(r"\b(?:no|nao|sin|sem)(?: \w+){0,2} $")
# [assumption] a person request is refused only right after "sin/sem", or after "no/não" plus this closed list and
# nothing else. A pronoun counts only after a listed word ("me hace falta" aside): "no quiero que me pasen con un
# asesor" and "não precisa me passar" are refusals, "¿no me pasa con un asesor?" and "sin que me pasen con un asesor no
# puedo" are requests. "si no / se não" (= otherwise), a question and a later "sino / mas sim / e sim" keep the request.
_REFUSAL = re.compile(r"\b(?:(?<!\bsi )(?<!\bse )(?:no|nao) (?:(?:quiero|quero|necesito|preciso|precisa|precisam|deseo"
                      r"|desejo|(?:me )?hace falta|es necesario|e necessario|hay que|tengo que|tenho que|que)"
                      r"(?: me| te| le| nos)? )*|(?:sin|sem) )$")
_BUT = re.compile(r"\b(?:sino|mas sim|e sim)\b")        # "no quiero un asesor sino un supervisor": still a request
_ASKED = re.compile(r"[^.,;:!?]*\?")                    # "¿no es necesario hablar con un asesor?": still a request
# "already reported": the ES past tense differs from the noun "reporte" and the command "registre" only by its accent,
# so it is read before folding; an unaccented form counts only after ya/lo/la. PT -ei forms are unambiguous.
_REPORTED_ES = re.compile(r"\b(?:report|reclam|registr|denunci)é\b")
_REPORTED = re.compile(r"\b(?:(?:ya|lo|la) (?:reporte|reclame|registre|denuncie)|reportei|reclamei|registrei|denunciei"
                       r"|(?:habia|tinha) (?:reportado|reclamado|registrado|denunciado))\b")
# [assumption] EV-0120: a clear topic outside disputes (credit limit, loans, balance, a new account, interest, points)
# reads out_of_scope above τ, so rule 4 abstains (G-IN-04); never with a charge word, which D-032 asks about instead
_OUT_OF_SCOPE = re.compile(
    r"\b(?:aumentar|subir|ampliar|elevar|incrementar|aumento|ampliacion|ampliacao)\b(?: \w+){0,4} (?:limite|cupo)\b"
    r"|\b(?:prestamos?|emprestimos?|financiamiento|financiamento|hipoteca"
    r"|credito (?:personal|pessoal|hipotecario|imobiliario|consignado))\b"
    r"|\b(?:cual|cuanto|qual|quanto|consultar|ver)\b(?: \w+){0,3} saldo\b|\babrir (?:una |uma )?(?:cuenta|conta)\b"
    r"|\b(?:tasa|taxa)s? de (?:interes|juros)\b|\b(?:mis|meus) (?:puntos|pontos|millas|milhas)\b")
_REPORTS = re.compile(r"\b" + _CHARGES + r"\b|\bcobr\w*|\bdebit\w*")
_ANOTHER = re.compile(r"\b(?:otro|otra|outro|outra) (?:cargo|cobro|compra|cobranca|debito|movimiento|transacao)\b")
# words of one language only (shared words such as "que", "me", "no", "compra" or "caso" carry no signal)
_PT_WORDS = {"nao", "voce", "voces", "meu", "minha", "meus", "minhas", "um", "uma", "o", "os", "do", "da", "dos", "das",
             "na", "em", "com", "e", "eu", "isso", "essa", "esse", "ja", "foi", "fiz", "ontem", "hoje", "duas", "vezes",
             "cartao", "cobranca", "cobrancas", "cobraram", "reconheco", "desconheco", "quero", "preciso", "falar",
             "pessoa", "atendente", "obrigado", "outra", "outro", "lembro", "podem", "tem", "pela", "mesma", "agora",
             "mostre", "errado", "adicionar", "conta", "fatura", "extrato"}
_ES_WORDS = {"yo", "mi", "mis", "un", "una", "el", "los", "las", "del", "al", "en", "con", "y", "es", "ya", "ayer",
             "hoy", "dos", "veces", "tarjeta", "cargo", "cargos", "cobro", "cobraron", "reconozco", "desconozco", "hice",
             "quiero", "necesito", "hablar", "persona", "gracias", "otro", "otra", "recuerdo", "monto", "muestrame",
             "agregar", "cuenta", "pueden", "ahora", "pero", "va", "cual", "hay", "eso", "esa", "misma", "asesor"}

# Bare "$" and "pesos" stay currency None on purpose: the NLU has no session, the country comes from the session and
# MX gold amounts are USD (spec 02 §4.2), so guessing MXN would be wrong. `search_transaction` resolves it.
_CURRENCY = {"mx$": "MXN", "u$s": "USD", "r$": "BRL", "reais": "BRL", "real": "BRL", "brl": "BRL", "us$": "USD", "usd": "USD", "dolares": "USD",
             "dolar": "USD", "dolares americanos": "USD", "mxn": "MXN", "ars": "ARS", "cop": "COP", "eur": "EUR"}
_CUR = r"(?:r\$|us\$|u\$s|mx\$|usd|brl|mxn|ars|cop|eur|\$|pesos?|reais|real|dolares|dolar)"
_NUM = r"\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_AMOUNT_BEFORE = re.compile(rf"(?<![\w/-])({_CUR})\s*({_NUM})(?![\d/-])")
_AMOUNT_AFTER = re.compile(rf"(?<![\w/-])({_NUM})\s*({_CUR})(?!\w)")
_AMOUNT_CUE = re.compile(rf"\b(?:cargo|compra|cobro|cobranca|monto|importe|valor|por|de|pagos?)\s+({_NUM})(?![\d/-])")
# "13 abril" (day + month name, no "de") is a date too, so its day never reads as an amount ("pesos 13 abril")
_DATE_NOISE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2} de [a-zç]+(?: de \d{4})?|\b\d{1,2} (?:" + "|".join(_MONTHS)
                         + r")\b", re.I)
_MERCHANT = re.compile(r"\b(?:en|em|de|do|da)\s+((?:[A-ZÁÉÍÓÚÑÃÕÇ][\w&'.-]*)(?:\s+[A-ZÁÉÍÓÚÑÃÕÇ][\w&'.-]*){0,3})(?![\w$])")
_THOUSANDS = re.compile(r"(\d+(?:[.,]\d{1,2})?) ?mil\b")
_MIL_COMPOUND = re.compile(r"\d[.,]\d{3}(?:[.,]\d+)? ?mil\b|\bmil (?:e|y) \d")   # "2,500 mil", "15 mil e 500": unsafe
# [assumption] a second figure after "mil" ("7 mil 500", "dos mil quinientos", "2 mil cinco pesos") or "mil millones"
# reads as no amount. Only that span is blanked, so another amount in the same message still reads.
_MIL_CUR = r"(?:pesos?|reais|real|dolares|dolar|usd|brl|mxn|ars|cop|eur)"
_HUNDREDS = (r"(?:cien|ciento|cem|cento|(?:dos|tres|cuatro|seis|sete|ocho|nove)cient[oa]s|quinient[oa]s|(?:du|tre)zent[oa]s"
             r"|(?:quatro|seis|sete|oito|nove)cent[oa]s|quinhent[oa]s)")
_TENS = (r"(?:once|doce|trece|catorce|quince|dieci\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta"
         r"|noventa|onze|doze|treze|catorze|quatorze|quinze|dez[ea]sseis|dez[ea]ssete|dezoito|dez[ea]nove|vinte|trinta"
         r"|quarenta|cinquenta|sessenta|oitenta)")
_MIL_UNSAFE = re.compile(r"(?:\d+(?:[.,]\d+)? ?|\S+ )?(?<![a-z])mil(?: (?:millon|milhao|milho)\w*|,? (?:(?:e|y) )?(?:"
                         + _HUNDREDS + "|" + _TENS + r")\b|,? (?:(?:e|y) )?(?:\d{1,3}|dos|dois|duas|tres|cuatro|quatro"
                         r"|cinco|seis|siete|sete|ocho|oito|nueve|nove|diez|dez)(?=\s*(?:" + _MIL_CUR + r"\b|\$|[.,;!?)]|$)))")
# [assumption] "dos mil pesos" and a bare "mil pesos" read as 2000 and 1000 only after a word that can come before an
# amount (de, por, cobraron, pagué...) or at the start: "veinte mil", "ciento dos mil" or "más de mil" give no amount
_WORD_NUM = {"un": 1, "uno": 1, "um": 1, "dos": 2, "dois": 2, "duas": 2, "tres": 3, "cuatro": 4, "quatro": 4, "cinco": 5,
             "seis": 6, "siete": 7, "sete": 7, "ocho": 8, "oito": 8, "nueve": 9, "nove": 9, "diez": 10, "dez": 10}
_LEAD = (r"(^|(?<!menos )(?<!mas )(?<!mais )(?<!cerca )(?<!perto )(?<!alrededor )(?<!acima )(?<!arriba )\b(?:de|por|son"
         r"|fueron|foram|era|eran|cobraron|cobraram|cobrou|cobro|debitaron|debitaram|pague|paguei|gaste|gastei|los|las|os) )")
_WORD_MIL = re.compile(_LEAD + r"(" + "|".join(_WORD_NUM) + r") mil\b")
_BARE_MIL = re.compile(_LEAD + r"mil(?= ?(?:" + _MIL_CUR + r")\b|\$)")
_MILLIONS = re.compile(r"\d+(?:[.,]\d+)? ?(?:millon|millones|milhao|milhoes)\b")
_NOT_MERCHANT = {"Hola", "Oi", "Ola", "Mexico", "Brasil", "Argentina", "Colombia", "Ayer", "Ontem"}


def _to_decimal(raw: str) -> Optional[str]:
    """'1.250,50' / '1,250.50' / '1,250' / '89,90' -> '1250.50' / '1250.50' / '1250' / '89.90'."""
    s = raw.replace(" ", "")
    seps = [i for i, c in enumerate(s) if c in ".,"]
    if seps:
        last = seps[-1]
        tail = s[last + 1:]
        if len(tail) == 3:
            s = re.sub(r"[.,]", "", s)                       # a 3-digit tail is thousands, not decimals
        else:
            s = re.sub(r"[.,]", "", s[:last]) + "." + tail
    try:
        return str(Decimal(s))
    except InvalidOperation:
        return None


def _amount(text: str) -> tuple[Optional[str], Optional[str]]:
    t = _DATE_NOISE.sub(" ", fold(text))
    if _MIL_COMPOUND.search(t):
        return None, None                                    # never guess a multiplier: no amount beats a wrong one
    t = _MILLIONS.sub(" ", _MIL_UNSAFE.sub(" ", t))
    found = _first_amount(t)
    if found[0] is None:                                     # a word "mil" reads only when no digit amount does
        t = _WORD_MIL.sub(lambda m: f"{m[1]}{_WORD_NUM[m[2]]} mil", t)
        found = _first_amount(_BARE_MIL.sub(lambda m: f"{m[1]}1 mil", t))
    return found


def _first_amount(t: str) -> tuple[Optional[str], Optional[str]]:
    t = _THOUSANDS.sub(lambda m: format((Decimal(_to_decimal(m[1]) or "0") * 1000).normalize(), "f"), t)
    for pattern, num_idx, cur_idx in ((_AMOUNT_BEFORE, 2, 1), (_AMOUNT_AFTER, 1, 2)):
        if m := pattern.search(t):
            return _to_decimal(m[num_idx]), _CURRENCY.get(m[cur_idx])
    if m := _AMOUNT_CUE.search(t):
        return _to_decimal(m[1]), None
    return None, None


def _merchant(text: str) -> Optional[str]:
    for m in _MERCHANT.finditer(text):
        if m[1] not in _NOT_MERCHANT:
            return m[1]
    return None


def detect_language(text: str, hint: Optional[str] = None) -> str:
    if hint in ("es", "pt"):
        return hint
    words = re.findall(r"[a-z]+", fold(text))                # punctuation stripped: "caso?" counts as "caso"
    pt, es = sum(w in _PT_WORDS for w in words), sum(w in _ES_WORDS for w in words)
    return "pt" if pt > es else "es"


# [assumption] G-IN-03: a clear sentence in another language (English, French, German) is answered by rule, never by a
# model. Words of those languages only, none shared with ES/PT; it takes 3 of them, more than the ES/PT words seen, so
# a loanword ("Amazon Prime", "ok", "thank you") inside Spanish or Portuguese never counts.
_OTHER_WORDS = {"i", "my", "the", "you", "your", "is", "are", "was", "were", "this", "that", "with", "from", "have", "has",
                "not", "don't", "didn't", "did", "what", "why", "and", "to", "of", "need", "help", "want", "card", "charge",
                "recognize", "unauthorized", "bank", "please", "hello", "hi", "lost", "can", "could", "would", "me",
                "je", "mon", "ma", "pas", "est", "les", "des", "une", "pour", "et", "carte", "bonjour", "ne", "reconnais",
                "ich", "nicht", "und", "der", "die", "das", "ist", "ein", "eine", "kann", "mein", "meine", "karte", "hallo",
                "habe", "kenne"}
_OTHER_WORDS -= {"me", "ma", "to", "ne", "e"}              # "me" is ES/PT, "ma" PT-adjacent, "to" and "ne" too short
_SHARED_WORDS = {"de", "que", "no", "la", "lo", "se", "su", "por", "para", "me", "te", "a", "e", "o", "es", "mas", "muy",
                 "com", "como", "tengo", "tenho", "una", "uma", "un", "um"}


def other_language(text: str) -> bool:
    """True only for a clear non-ES/PT sentence: at least 4 words, 3 of another language and more of them than ES/PT."""
    words = re.findall(r"[a-z']+", fold(text))
    foreign = sum(w in _OTHER_WORDS for w in words)
    known = sum(w in _PT_WORDS or w in _ES_WORDS or w in _SHARED_WORDS for w in words)
    return len(words) >= 4 and foreign >= 3 and foreign > known


def _refused(t: str, m: re.Match) -> bool:
    """A person request right after a refusal is no request, unless it is a question or a correction follows."""
    if not (r := _REFUSAL.search(t[:m.start()])):
        return False
    return not (t[:r.start()].endswith("¿") or _ASKED.match(t, m.start()) or _BUT.search(t, m.start()))


def classify_intent(text: str) -> tuple[str, float, bool]:
    """(intent, confidence, dispute_detected). The confidence is fixed: 0.9 for a match (above the policy floor
    `clarify.intent_confidence_min`), 0.5 for no match."""
    t = fold(text)
    # a refused person request ("no quiero hablar con un asesor") is no request; other intents ignore negation
    hits = {intent for intent, patterns in _COMPILED
            if any(not (intent == "human_request" and _refused(t, m)) for p in patterns for m in p.finditer(t))}
    if any(not _NEGATED.search(t[:m.start()]) for m in _CALL.finditer(t)):
        hits.add("human_request")
    dispute = bool(hits & {"wrongful_charge", "unrecognized_charge"})
    reported = _REPORTED_ES.search(unicodedata.normalize("NFC", text.lower())) or _REPORTED.search(t)
    if "status_inquiry" in hits and dispute and (not reported or _ANOTHER.search(t)):
        hits.discard("status_inquiry")                        # a new dispute is not a read-only status question
    if any(p.search(t) for p in _DISPUTE_11C):
        dispute = True
        if _ANOTHER.search(t):
            hits.discard("status_inquiry")
        if "status_inquiry" not in hits:
            hits.add("unrecognized_charge")
    for intent, _ in _COMPILED:
        if intent in hits:
            return intent, 0.9, dispute
    if _OUT_OF_SCOPE.search(t) and not _REPORTS.search(t):
        return "out_of_scope", 0.9, False                     # a clear topic outside disputes (EV-0120)
    return "out_of_scope", 0.5, False                         # no rule fired: the arm does not know


def parse_rules(text: str, language_hint: Optional[str], today: date) -> dict:
    """B0 reading of one message; `today` is the session's today (never the system clock)."""
    intent, confidence, dispute = classify_intent(text)
    amount, currency = _amount(text)
    found = parse_date(text, today)
    foreign = intent == "out_of_scope" and other_language(text)
    return {
        "intent": intent, "confidence": confidence, "dispute_detected": dispute, "language": detect_language(text, language_hint),
        "slots": {"amount": amount, "currency": currency, "date": found.isoformat() if found else None,
                  "merchant": _merchant(text)},
        "injection_flagged": injection_flagged(text), "other_language": foreign, "arm": ARM, "version": VERSION,
    }
