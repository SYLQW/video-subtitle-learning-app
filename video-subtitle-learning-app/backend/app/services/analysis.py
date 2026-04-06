from __future__ import annotations

import json
from typing import Any, Iterator

from backend.app.services.llm_common import OpenAICompatibleConfig, post_chat_json, stream_chat_text


ANALYSIS_SYSTEM_PROMPT = """You are an English learning assistant.
Analyze one subtitle segment for a Chinese learner.

Rules:
1. Return valid JSON only.
2. Explain clearly in Simplified Chinese.
3. Keep explanations concise but useful.
4. Do not use markdown.

Return this JSON shape:
{
  "improved_translation": "...",
  "natural_translation": "...",
  "keywords": [{"word":"...","meaning":"...","note":"..."}],
  "grammar_points": ["..."],
  "structure_explanation": "...",
  "learning_tip": "...",
  "questions_to_ask": ["..."]
}
"""


def _analysis_payload(
    *,
    text: str,
    existing_translation: str,
    previous_text: str | None = None,
    next_text: str | None = None,
) -> dict[str, str]:
    return {
        "text": text,
        "existing_translation": existing_translation,
        "previous_text": previous_text or "",
        "next_text": next_text or "",
    }


def analyze_sentence(
    *,
    text: str,
    existing_translation: str,
    model: str,
    base_url: str,
    api_key: str,
    previous_text: str | None = None,
    next_text: str | None = None,
) -> dict[str, Any]:
    payload = _analysis_payload(
        text=text,
        existing_translation=existing_translation,
        previous_text=previous_text,
        next_text=next_text,
    )
    config = OpenAICompatibleConfig(base_url=base_url, api_key=api_key, model=model, timeout_seconds=180.0)
    content = post_chat_json(config, ANALYSIS_SYSTEM_PROMPT, payload, temperature=0.3)
    return json.loads(content)


def stream_sentence_analysis(
    *,
    text: str,
    existing_translation: str,
    model: str,
    base_url: str,
    api_key: str,
    previous_text: str | None = None,
    next_text: str | None = None,
) -> Iterator[str]:
    payload = _analysis_payload(
        text=text,
        existing_translation=existing_translation,
        previous_text=previous_text,
        next_text=next_text,
    )
    config = OpenAICompatibleConfig(base_url=base_url, api_key=api_key, model=model, timeout_seconds=180.0)
    return stream_chat_text(config, ANALYSIS_SYSTEM_PROMPT, payload, temperature=0.3)

