from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import srt

from backend.app.services.llm_common import OpenAICompatibleConfig, post_chat_json
from backend.app.services.transcription import TranscriptResult, transcript_to_dict


TRANSLATION_SYSTEM_PROMPT = """You are a subtitle translator.
Translate each English subtitle segment into concise, natural Simplified Chinese.

Rules:
1. Keep the same segment ids.
2. Return valid JSON only.
3. Do not merge or split segments.
4. Do not add explanations, notes, or markdown.
5. Preserve the meaning and spoken tone.

Return this JSON shape:
{"translations":[{"id":1,"zh":"..."}]}
"""


TranslationConfig = OpenAICompatibleConfig


def _build_user_prompt(segments: list[dict[str, Any]]) -> str:
    payload = [{"id": item["index"], "text": item["text"]} for item in segments]
    return json.dumps(payload, ensure_ascii=False)


def _parse_translation_response(content: str) -> dict[int, str]:
    payload = json.loads(content)
    translations = payload.get("translations", [])
    result: dict[int, str] = {}
    for item in translations:
        segment_id = int(item["id"])
        zh = str(item["zh"]).strip()
        result[segment_id] = zh
    return result


def translate_transcript_segments(
    transcript: TranscriptResult,
    config: TranslationConfig,
    batch_size: int = 12,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for start in range(0, len(transcript.segments), batch_size):
        batch = transcript.segments[start : start + batch_size]
        user_prompt = _build_user_prompt([{"index": seg.index, "text": seg.text} for seg in batch])
        content = post_chat_json(config, TRANSLATION_SYSTEM_PROMPT, user_prompt, temperature=0.2)
        translations = _parse_translation_response(content)

        for segment in batch:
            output.append(
                {
                    "id": segment.index,
                    "start": segment.start,
                    "end": segment.end,
                    "en": segment.text,
                    "zh": translations.get(segment.index, ""),
                }
            )

    return output


def _compose_srt(bilingual_segments: list[dict[str, Any]], mode: str) -> str:
    subtitles: list[srt.Subtitle] = []
    for item in bilingual_segments:
        if mode == "zh":
            content = item["zh"]
        elif mode == "bilingual":
            content = f'{item["en"]}\n{item["zh"]}'
        else:
            raise ValueError(f"Unsupported SRT mode: {mode}")

        subtitles.append(
            srt.Subtitle(
                index=item["id"],
                start=timedelta(seconds=float(item["start"])),
                end=timedelta(seconds=float(item["end"])),
                content=content,
            )
        )
    return srt.compose(subtitles)


def save_bilingual_outputs(
    transcript: TranscriptResult,
    bilingual_segments: list[dict[str, Any]],
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    stem = Path(transcript.source_path).stem
    bilingual_path = output_path / f"{stem}.bilingual.json"
    zh_srt_path = output_path / f"{stem}.zh.srt"
    bilingual_srt_path = output_path / f"{stem}.bilingual.srt"
    payload = transcript_to_dict(transcript)
    payload["bilingual_segments"] = bilingual_segments
    bilingual_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    zh_srt_path.write_text(_compose_srt(bilingual_segments, "zh"), encoding="utf-8")
    bilingual_srt_path.write_text(_compose_srt(bilingual_segments, "bilingual"), encoding="utf-8")
    return bilingual_path, zh_srt_path, bilingual_srt_path
