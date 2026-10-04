"""ES/PT date parser (spec 11 §4, AC-08).

Absolute dates are `YYYY-MM-DD`, `DD/MM/YYYY` (day first, as in LATAM) and "3 de junio" / "3 de junho". Relative ones
("ayer", "el martes", "ontem", "hace 3 dias") resolve against the `today` the caller passes (the session's clock,
ADR 0020). This module never reads the system clock. A weekday means its most recent occurrence strictly before today,
because a dispute is about a charge that already happened.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from .text import fold

_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
             "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4}   # PT "-feira" is optional
_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
           "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
           "janeiro": 1, "fevereiro": 2, "marco": 3, "maio": 5, "junho": 6, "setembro": 9, "outubro": 10,
           "novembro": 11, "dezembro": 12}
_OFFSETS = [(r"\b(?:anteayer|antier|antes de ayer|anteontem)\b", 2), (r"\b(?:ayer|ontem)\b", 1),
            (r"\b(?:hoy|hoje)\b", 0)]

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2}) de (" + "|".join(_MONTHS) + r")(?: de (\d{4}))?\b")
_AGO = re.compile(r"\b(?:hace|ha) (\d{1,3}) dias?\b")
_WEEKDAY = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")(?:-feira)?\b")


def _safe(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(text: str, today: date) -> Optional[date]:
    """The first date the text mentions, as a `date`, or None. `today` is the session's today."""
    t = fold(text)
    if m := _ISO.search(t):
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    if m := _DMY.search(t):
        return _safe(int(m[3]), int(m[2]), int(m[1]))
    if m := _DAY_MONTH.search(t):
        month, day = _MONTHS[m[2]], int(m[1])
        if m[3]:
            return _safe(int(m[3]), month, day)
        found = _safe(today.year, month, day)
        if found and found > today:                      # "15 de diciembre" said in June means last year
            found = _safe(today.year - 1, month, day)
        return found
    for pattern, days in _OFFSETS:
        if re.search(pattern, t):
            return today - timedelta(days=days)
    if m := _AGO.search(t):
        return today - timedelta(days=int(m[1]))
    if m := _WEEKDAY.search(t):
        back = (today.weekday() - _WEEKDAYS[m[1]]) % 7 or 7
        return today - timedelta(days=back)
    return None
