from __future__ import annotations

from typing import Iterable


LANGUAGE_NAMES: dict[str, str] = {
    "AUTO": "Auto Detect",
    "EN": "English",
    "ZH": "Simplified Chinese",
    "JA": "Japanese",
    "KO": "Korean",
    "FR": "French",
    "DE": "German",
    "ES": "Spanish",
    "RU": "Russian",
    "IT": "Italian",
    "PT": "Portuguese",
}


def normalize_lang_code(value: str | None, default: str = "AUTO") -> str:
    normalized = str(value or default).strip().replace("-", "_").upper()
    if normalized in {"AUTO", "AUTO_DETECT"}:
        return "AUTO"
    return normalized or default


def language_name(code: str | None) -> str:
    normalized = normalize_lang_code(code)
    return LANGUAGE_NAMES.get(normalized, normalized)


def whisper_language(code: str | None) -> str | None:
    normalized = normalize_lang_code(code)
    if normalized == "AUTO":
        return None
    return normalized.lower()


def ensure_unique_languages(values: Iterable[str | None]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_lang_code(value, default="")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered
