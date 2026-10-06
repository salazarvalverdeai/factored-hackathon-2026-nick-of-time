"""Spec 16 AC-06: the ES · PT · EN interface, checked from the sources (offline, no Node needed).

The full checks run in `apps/web/lib/i18n.test.ts` (`npm test`); these keep the AC gate honest from pytest.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "apps" / "web"
MESSAGES = WEB / "messages"
LOCALE_BLOCK = re.compile(r"^  (en|es|pt): \{$", re.M)
KEY = re.compile(
    r"^\s+([A-Za-z_]\w*):", re.M
)  # one key per line, as the files are written
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _blocks(text: str) -> dict[str, str]:
    """The en, es and pt blocks of one `defineMessages({ en, es, pt })` namespace file."""
    marks = [(m.group(1), m.start()) for m in LOCALE_BLOCK.finditer(text)]
    out = {}
    for i, (loc, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out[loc] = text[
            text.index("\n", start) : end
        ]  # the block's own "en: {" line is not a key
    return out


def _namespaces() -> list[Path]:
    return [
        p
        for p in sorted(MESSAGES.glob("*.ts"))
        if p.stem not in {"define", "en", "es", "pt"}
    ]


def test_ac_06_every_namespace_has_the_same_keys_and_placeholders_in_es_pt_en():
    """AC-06: each dictionary namespace carries the same keys and placeholders in Spanish, Portuguese and English."""
    files = _namespaces()
    assert len(files) >= 10
    for f in files:
        blocks = _blocks(f.read_text(encoding="utf-8"))
        assert set(blocks) == {"en", "es", "pt"}, f.name
        en_keys = sorted(KEY.findall(blocks["en"]))
        en_vars = sorted(PLACEHOLDER.findall(blocks["en"]))
        for loc in ("es", "pt"):
            assert sorted(KEY.findall(blocks[loc])) == en_keys, (
                f"{f.name}: keys differ in {loc}"
            )
            assert sorted(PLACEHOLDER.findall(blocks[loc])) == en_vars, (
                f"{f.name}: placeholders differ in {loc}"
            )


def test_ac_06_the_header_offers_an_accessible_selector_and_the_layout_sets_html_lang():
    """AC-06: ES · PT · EN selector in the header (keyboard, accessible name, announced), default ES, <html lang> from the cookie."""
    i18n = (WEB / "lib" / "i18n.ts").read_text(encoding="utf-8")
    assert 'LOCALES = ["es", "pt", "en"]' in i18n
    assert 'DEFAULT_LOCALE: Locale = "es"' in i18n
    for tag in ('"es-MX"', '"pt-BR"', '"en-US"', 'hourCycle: "h23"'):
        assert tag in i18n
    select = (WEB / "components" / "language-select.tsx").read_text(encoding="utf-8")
    for attr in (
        'role="group"',
        "aria-label=",
        "aria-pressed=",
        'aria-live="polite"',
        "ArrowRight",
        "ArrowLeft",
    ):
        assert attr in select, attr
    header = (WEB / "components" / "site-header.tsx").read_text(encoding="utf-8")
    assert "<LanguageSelect" in header
    layout = (WEB / "app" / "layout.tsx").read_text(encoding="utf-8")
    assert "lang={locale}" in layout and "await getLocale()" in layout
