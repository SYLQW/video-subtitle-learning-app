from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator

import httpx


@dataclass
class OpenAICompatibleConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 120.0


def _build_payload(system_prompt: str, user_payload: Any, temperature: float, stream: bool) -> dict[str, Any]:
    user_content = user_payload if isinstance(user_payload, str) else json.dumps(user_payload, ensure_ascii=False)
    return {
        "model": stream and None or None,
    }


def _request_body(config: OpenAICompatibleConfig, system_prompt: str, user_payload: Any, temperature: float, stream: bool) -> dict[str, Any]:
    user_content = user_payload if isinstance(user_payload, str) else json.dumps(user_payload, ensure_ascii=False)
    payload = {
        "model": config.model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    if stream:
        payload["stream"] = True
    else:
        payload["response_format"] = {"type": "json_object"}
    return payload


def post_chat_json(
    config: OpenAICompatibleConfig,
    system_prompt: str,
    user_payload: Any,
    temperature: float = 0.2,
) -> str:
    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    with httpx.Client(timeout=config.timeout_seconds) as client:
        response = client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json=_request_body(config, system_prompt, user_payload, temperature, stream=False),
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def stream_chat_text(
    config: OpenAICompatibleConfig,
    system_prompt: str,
    user_payload: Any,
    temperature: float = 0.2,
) -> Iterator[str]:
    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    with httpx.Client(timeout=config.timeout_seconds) as client:
        with client.stream(
            "POST",
            endpoint,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json=_request_body(config, system_prompt, user_payload, temperature, stream=True),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    yield delta

