# SPDX-License-Identifier: GPL-3.0-or-later
"""Translations for MyHouse (shared code, not a feature).

Same scheme as IngeTrazo's own core.i18n: English is the source language and
the English string is the key. Each other language is a flat JSON file
{english: translation} in  myhouse/i18n/<code>.json  (it.json, es.json …);
a string with no translation stays in English.

    from ._i18n import tr
    tr("Height")                                   # -> "Altezza"
    tr("{n} walls updated", n=3)                   # placeholders by name

The language is the one IngeTrazo runs in. A string MyHouse has no
translation for is then looked up in IngeTrazo's own catalogue, which already
knows common words. To add a language, copy i18n/it.json to i18n/<code>.json
and translate the values; keep the {placeholders} as they are.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import i18n as _core

_DIR = Path(__file__).resolve().parent / "i18n"
_catalog: dict[str, str] = {}
_loaded: str | None = None


def _load(lang: str) -> dict:
    for code in (lang, lang.split("-")[0]):
        path = _DIR / f"{code}.json"
        if code != "en" and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {str(k): str(v) for k, v in data.items()}
            except (OSError, ValueError):
                return {}
    return {}


def tr(text: str, /, **kwargs) -> str:
    """text in IngeTrazo's language; kwargs fill its {placeholders}."""
    global _catalog, _loaded
    lang = _core.current_language()
    if lang != _loaded:
        _catalog, _loaded = _load(lang), lang
    out = _catalog.get(text)
    if out is None:
        out = _core.tr(text)
    if kwargs:
        try:
            out = out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            out = text.format(**kwargs)
    return out
