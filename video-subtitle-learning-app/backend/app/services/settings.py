from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from backend.app.services.database import get_setting_json, upsert_setting_json
from backend.app.services.llm_common import API_STYLE_CHAT


DEFAULT_SETTINGS: dict[str, Any] = {
    "profiles": {
        "llm": [
            {
                "id": "profile-qwen-translation",
                "name": "Qwen Turbo",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "",
                "model": "qwen-turbo",
                "api_style": API_STYLE_CHAT,
            },
            {
                "id": "profile-qwen-analysis",
                "name": "Qwen Analysis",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "",
                "model": "qwen3.6-plus",
                "api_style": API_STYLE_CHAT,
            },
        ]
    },
    "translation": {
        "provider": "deeplx",
        "deeplx_url": "",
        "llm_profile_id": "profile-qwen-translation",
        "source_lang": "EN",
        "target_lang": "ZH",
        "batch_size": 1,
    },
    "analysis": {
        "profile_id": "profile-qwen-analysis",
        "stream": True,
    },
    "transcription": {
        "model_size": "base.en",
        "device": "cuda",
        "compute_type": "float16",
    },
}


def _merge_dict(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_profile(profile: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    normalized = {
        "id": profile.get("id") or f"profile-{uuid4().hex[:8]}",
        "name": str(profile.get("name") or fallback_name),
        "base_url": str(profile.get("base_url") or ""),
        "api_key": str(profile.get("api_key") or ""),
        "model": str(profile.get("model") or ""),
        "api_style": str(profile.get("api_style") or API_STYLE_CHAT),
    }
    return normalized


def _migrate_legacy_profiles(settings: dict[str, Any]) -> dict[str, Any]:
    llm_profiles = settings.get("profiles", {}).get("llm")
    if llm_profiles:
        normalized_profiles = [_normalize_profile(profile, f"LLM Profile {index + 1}") for index, profile in enumerate(llm_profiles)]
        settings["profiles"]["llm"] = normalized_profiles
        return settings

    translation = settings["translation"]
    analysis = settings["analysis"]

    translation_profile = _normalize_profile(
        {
            "id": "profile-qwen-translation",
            "name": "Legacy Translation",
            "base_url": translation.get("llm_base_url", ""),
            "api_key": translation.get("llm_api_key", ""),
            "model": translation.get("llm_model", ""),
            "api_style": translation.get("llm_api_style", API_STYLE_CHAT),
        },
        "Legacy Translation",
    )
    analysis_profile = _normalize_profile(
        {
            "id": "profile-qwen-analysis",
            "name": "Legacy Analysis",
            "base_url": analysis.get("base_url", ""),
            "api_key": analysis.get("api_key", ""),
            "model": analysis.get("model", ""),
            "api_style": analysis.get("api_style", API_STYLE_CHAT),
        },
        "Legacy Analysis",
    )

    profiles: list[dict[str, Any]] = [translation_profile]
    if translation_profile["id"] != analysis_profile["id"] or translation_profile != analysis_profile:
        profiles.append(analysis_profile)

    settings["profiles"]["llm"] = profiles
    settings["translation"]["llm_profile_id"] = translation_profile["id"]
    settings["analysis"]["profile_id"] = analysis_profile["id"]
    return settings


def _ensure_selected_profiles(settings: dict[str, Any]) -> dict[str, Any]:
    profiles = settings["profiles"]["llm"]
    if not profiles:
        profiles.extend(deepcopy(DEFAULT_SETTINGS["profiles"]["llm"]))

    profile_ids = {profile["id"] for profile in profiles}
    if settings["translation"].get("llm_profile_id") not in profile_ids:
        settings["translation"]["llm_profile_id"] = profiles[0]["id"]
    if settings["analysis"].get("profile_id") not in profile_ids:
        settings["analysis"]["profile_id"] = profiles[0]["id"]
    return settings


def _drop_legacy_fields(settings: dict[str, Any]) -> dict[str, Any]:
    for key in ("llm_base_url", "llm_api_key", "llm_model", "llm_api_style"):
        settings["translation"].pop(key, None)
    for key in ("base_url", "api_key", "model", "api_style"):
        settings["analysis"].pop(key, None)
    return settings


def _normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = _merge_dict(DEFAULT_SETTINGS, settings)
    normalized = _migrate_legacy_profiles(normalized)
    normalized = _ensure_selected_profiles(normalized)
    normalized = _drop_legacy_fields(normalized)
    return normalized


def get_app_settings() -> dict[str, Any]:
    stored = get_setting_json("app_settings") or {}
    return _normalize_settings(stored)


def save_app_settings(payload: dict[str, Any]) -> dict[str, Any]:
    merged = _merge_dict(get_app_settings(), payload)
    normalized = _normalize_settings(merged)
    upsert_setting_json("app_settings", normalized)
    return normalized


def get_llm_profile(settings: dict[str, Any], profile_id: str | None) -> dict[str, Any]:
    profiles = settings.get("profiles", {}).get("llm", [])
    if not profiles:
        raise ValueError("No LLM profiles configured.")
    if profile_id:
        for profile in profiles:
            if profile["id"] == profile_id:
                return profile
    return profiles[0]
