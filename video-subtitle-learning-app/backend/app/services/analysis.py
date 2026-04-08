from __future__ import annotations

import json
from typing import Any, Iterator

from backend.app.services.language_support import language_name
from backend.app.services.llm_common import OpenAICompatibleConfig, post_chat_json, stream_chat_text


def _analysis_system_prompt(study_lang: str, native_lang: str, source_lang: str, reference_lang: str) -> str:
    return f"""You are a language learning assistant.
 The learner is studying {language_name(study_lang)} and wants explanations in {language_name(native_lang)}.
 The original source language is {language_name(source_lang)}.
 The reference translation or parallel text is in {language_name(reference_lang)}.
 
 Rules:
 1. Return valid JSON only.
 2. Explain clearly in {language_name(native_lang)}.
 3. Focus on helping the learner understand and learn the study sentence in {language_name(study_lang)}.
 4. The `keywords[].word` values must be exact words or short phrases copied from the study sentence, keeping the original {language_name(study_lang)} text.
 5. Do not replace keywords with translated Chinese paraphrases or synonym summaries.
 6. Use the reference translation only to explain meaning, nuance, or mapping.
 7. If the original source sentence is useful, briefly mention how it maps to the study sentence.
 8. Grammar points must describe the grammar of the study sentence, not the translated Chinese wording.
 9. `improved_translation` and `natural_translation` should both be in {language_name(native_lang)} and should translate the study sentence naturally.
 10. Keep explanations concise but useful.
 11. Do not use markdown.

 Return this JSON shape:
 {{
   "improved_translation": "...",
   "natural_translation": "...",
   "keywords": [{{"word":"...","meaning":"...","note":"..."}}],
   "grammar_points": ["..."],
   "structure_explanation": "...",
   "learning_tip": "...",
   "questions_to_ask": ["..."]
 }}
 """


def _analysis_payload(
    *,
    study_text: str,
    reference_translation: str,
    source_text: str = "",
    study_lang: str,
    reference_lang: str,
    previous_text: str | None = None,
    next_text: str | None = None,
) -> dict[str, str]:
    return {
        "study_text": study_text,
        "reference_translation": reference_translation,
        "source_text": source_text,
        "study_lang": study_lang,
        "reference_lang": reference_lang,
        "previous_text": previous_text or "",
        "next_text": next_text or "",
    }


def analyze_sentence(
    *,
    study_text: str,
    reference_translation: str,
    source_text: str,
    model: str,
    base_url: str,
    api_key: str,
    api_style: str,
    study_lang: str,
    reference_lang: str,
    native_lang: str,
    source_lang: str,
    previous_text: str | None = None,
    next_text: str | None = None,
) -> dict[str, Any]:
    payload = _analysis_payload(
        study_text=study_text,
        reference_translation=reference_translation,
        source_text=source_text,
        study_lang=study_lang,
        reference_lang=reference_lang,
        previous_text=previous_text,
        next_text=next_text,
    )
    config = OpenAICompatibleConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=180.0,
        api_style=api_style,
    )
    content = post_chat_json(
        config,
        _analysis_system_prompt(study_lang, native_lang, source_lang, reference_lang),
        payload,
        temperature=0.3,
    )
    return json.loads(content)


def stream_sentence_analysis(
    *,
    study_text: str,
    reference_translation: str,
    source_text: str,
    model: str,
    base_url: str,
    api_key: str,
    api_style: str,
    study_lang: str,
    reference_lang: str,
    native_lang: str,
    source_lang: str,
    previous_text: str | None = None,
    next_text: str | None = None,
) -> Iterator[str]:
    payload = _analysis_payload(
        study_text=study_text,
        reference_translation=reference_translation,
        source_text=source_text,
        study_lang=study_lang,
        reference_lang=reference_lang,
        previous_text=previous_text,
        next_text=next_text,
    )
    config = OpenAICompatibleConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=180.0,
        api_style=api_style,
    )
    return stream_chat_text(
        config,
        _analysis_system_prompt(study_lang, native_lang, source_lang, reference_lang),
        payload,
        temperature=0.3,
    )
