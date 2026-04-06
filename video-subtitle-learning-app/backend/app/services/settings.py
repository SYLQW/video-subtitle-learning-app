from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.app.services.database import get_setting_json, upsert_setting_json


DEFAULT_SETTINGS: dict[str, Any] = {
    "translation": {
        "provider": "deeplx",
        "deeplx_url": "",
        "llm_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "llm_api_key": "",
        "llm_model": "qwen-turbo",
        "source_lang": "EN",
        "target_lang": "ZH",
        "batch_size": 1,
    },
    "analysis": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "",
        "model": "qwen3.6-plus",
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


def get_app_settings() -> dict[str, Any]:
    stored = get_setting_json("app_settings") or {}
    return _merge_dict(DEFAULT_SETTINGS, stored)


def save_app_settings(payload: dict[str, Any]) -> dict[str, Any]:
    merged = _merge_dict(get_app_settings(), payload)
    upsert_setting_json("app_settings", merged)
    return merged

