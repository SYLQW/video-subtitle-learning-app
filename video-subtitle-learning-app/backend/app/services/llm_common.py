from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class OpenAICompatibleConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 120.0


def post_chat_json(
    config: OpenAICompatibleConfig,
    system_prompt: str,
    user_payload: Any,
    temperature: float = 0.2,
) -> str:
    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    user_content = user_payload if isinstance(user_payload, str) else json.dumps(user_payload, ensure_ascii=False)

    with httpx.Client(timeout=config.timeout_seconds) as client:
        response = client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

