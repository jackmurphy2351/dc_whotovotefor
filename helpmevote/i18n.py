"""Language selection and UI-chrome translation.

Content (candidate bios, questions, etc.) is translated in ``data_loader`` via
per-language overlays. This module handles the other half: choosing the active
language for a request and translating the ~140 fixed UI strings that live in
``content/<lang>/ui.yaml`` (flat ``dotted.key: "text"`` maps).
"""

from datetime import date
from pathlib import Path

import yaml
from flask import current_app, g

# Add new languages here (and ship a content/<lang>/ overlay + ui.yaml).
SUPPORTED_LANGUAGES = ("en", "es")
DEFAULT_LANGUAGE = "en"


def load_ui(content_dir: Path, lang: str) -> dict:
    """Load the flat ui.yaml map for ``lang`` (English lives at content/en/)."""
    path = content_dir / lang / "ui.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def current_lang() -> str:
    lang = getattr(g, "lang", None)
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def get_content():
    """The AppContent for the active language, falling back to English.

    ``config["CONTENT"]`` is authoritative for the default language, so tests that
    override it (without building ``CONTENT_BY_LANG``) keep working. Other
    languages come from ``CONTENT_BY_LANG`` and fall back to English.
    """
    lang = current_lang()
    if lang == DEFAULT_LANGUAGE:
        return current_app.config["CONTENT"]
    by_lang = current_app.config.get("CONTENT_BY_LANG") or {}
    return by_lang.get(lang) or current_app.config["CONTENT"]


def translate_ui(key: str, lang: str | None = None) -> str:
    """UI string for ``key``: active language, then English, then the key itself
    (so a missing string is visible during QA rather than silently blank)."""
    lang = lang or current_lang()
    by_lang = current_app.config.get("UI_BY_LANG", {})
    value = by_lang.get(lang, {}).get(key)
    if value is None:
        value = by_lang.get(DEFAULT_LANGUAGE, {}).get(key)
    return value if value is not None else key


def format_date(value: date, lang: str | None = None) -> str:
    """Localized long date, e.g. 'June 16, 2026' (en) / '16 de junio de 2026' (es).

    Driven by ui.yaml keys ``date.long_format`` (a ``{day}/{month}/{year}``
    template) and ``date.month.<n>`` (month names). Falls back to ISO format."""
    if not isinstance(value, date):
        return str(value)
    lang = lang or current_lang()
    fmt = translate_ui("date.long_format", lang)
    month = translate_ui(f"date.month.{value.month}", lang)
    if fmt == "date.long_format":  # key missing — safe fallback
        return value.isoformat()
    return fmt.format(day=value.day, month=month, year=value.year)


def plural(n: int, singular_key: str, plural_key: str, lang: str | None = None) -> str:
    """Pick the singular or plural UI key based on count (2-form languages)."""
    return translate_ui(singular_key if n == 1 else plural_key, lang)
