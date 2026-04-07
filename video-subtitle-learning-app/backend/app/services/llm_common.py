from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator

import httpx


API_STYLE_CHAT = "chat_completions"
API_STYLE_RESPONSES = "responses"


@dataclass
class OpenAICompatibleConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 120.0
    api_style: str = API_STYLE_CHAT


def _should_disable_thinking(config: OpenAICompatibleConfig) -> bool:
    model_name = (config.model or "").lower()
    base_url = (config.base_url or "").lower()
    return config.api_style == API_STYLE_RESPONSES and "doubao" in model_name and "ark.cn-beijing.volces.com" in base_url


def _stringify_payload(user_payload: Any) -> str:
    return user_payload if isinstance(user_payload, str) else json.dumps(user_payload, ensure_ascii=False)


def _normalize_endpoint(base_url: str, api_style: str) -> str:
    base = re.sub(r"(?<!:)//+", "/", (base_url or "").strip()).rstrip("/")
    if api_style == API_STYLE_RESPONSES:
        if base.endswith("/responses/chat/completions"):
            return base.removesuffix("/chat/completions")
        if base.endswith("/responses"):
            return base
        if base.endswith("/chat/completions"):
            return f"{base.removesuffix('/chat/completions')}/responses"
        return f"{base}/responses"
    if base.endswith("/responses/chat/completions"):
        return f"{base.removesuffix('/responses/chat/completions')}/chat/completions"
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/responses"):
        return f"{base.removesuffix('/responses')}/chat/completions"
    return f"{base}/chat/completions"


def resolve_endpoint(base_url: str, api_style: str) -> str:
    return _normalize_endpoint(base_url, api_style)


def _request_body(config: OpenAICompatibleConfig, system_prompt: str, user_payload: Any, temperature: float, stream: bool) -> dict[str, Any]:
    user_content = _stringify_payload(user_payload)
    if config.api_style == API_STYLE_RESPONSES:
        payload = {
            "model": config.model,
            "instructions": system_prompt,
            "input": user_content,
        }
        if _should_disable_thinking(config):
            payload["thinking"] = {"type": "disabled"}
        if stream:
            payload["stream"] = True
        return payload

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


def _extract_responses_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text
    return ""


def _extract_chat_message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""

    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text:
                text_parts.append(text)
        return "".join(text_parts)
    return ""


def _extract_chat_completion_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {})
    return _extract_chat_message_text(message)


def _extract_chat_stream_delta(chunk: dict[str, Any]) -> str:
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    delta = choices[0].get("delta", {})
    if isinstance(delta, str):
        return delta
    if not isinstance(delta, dict):
        return ""

    content = delta.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text:
                text_parts.append(text)
        return "".join(text_parts)
    return ""


def post_chat_json(
    config: OpenAICompatibleConfig,
    system_prompt: str,
    user_payload: Any,
    temperature: float = 0.2,
) -> str:
    endpoint = _normalize_endpoint(config.base_url, config.api_style)
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
        if config.api_style == API_STYLE_RESPONSES:
            return _extract_responses_text(data)
        return _extract_chat_completion_text(data)


def stream_chat_text(
    config: OpenAICompatibleConfig,
    system_prompt: str,
    user_payload: Any,
    temperature: float = 0.2,
) -> Iterator[str]:
    endpoint = _normalize_endpoint(config.base_url, config.api_style)
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
            current_event = ""
            for raw_line in response.iter_lines():
                if raw_line is None:
                    continue
                line = raw_line.strip()
                if not line:
                    current_event = ""
                    continue
                if line.startswith("event:"):
                    current_event = line.removeprefix("event:").strip()
                    continue
                if not line.startswith("data:"):
                    continue

                payload = line.removeprefix("data:").strip()
                if payload == "[DONE]":
                    break

                chunk = json.loads(payload)
                if config.api_style == API_STYLE_RESPONSES:
                    if current_event in {"response.output_text.delta", "output_text.delta"}:
                        delta = chunk.get("delta") or chunk.get("text") or ""
                        if delta:
                            yield delta
                    elif current_event == "error":
                        raise RuntimeError(chunk.get("message") or chunk.get("error", {}).get("message") or "Responses API stream error.")
                else:
                    delta = _extract_chat_stream_delta(chunk)
                    if delta:
                        yield delta
