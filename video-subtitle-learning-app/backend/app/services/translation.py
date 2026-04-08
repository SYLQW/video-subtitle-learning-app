from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import srt

from backend.app.services.language_support import language_name, normalize_lang_code
from backend.app.services.llm_common import OpenAICompatibleConfig, post_chat_json
from backend.app.services.transcription import TranscriptResult, transcript_to_dict


@dataclass
class DeepLXConfig:
    url: str
    source_lang: str = "AUTO"
    target_lang: str = "ZH"
    timeout_seconds: float = 60.0
    trust_env: bool = True
    max_workers: int = 2
    retries: int = 2


TranslationConfig = OpenAICompatibleConfig


def _translation_system_prompt(source_lang: str, learning_lang: str) -> str:
    return f"""You are a subtitle translator.
Translate each subtitle segment from {language_name(source_lang)} into concise, natural {language_name(learning_lang)}.

Rules:
1. Keep the same segment ids.
2. Return valid JSON only.
3. Do not merge or split segments.
4. Do not add explanations, notes, or markdown.
5. Preserve the meaning and spoken tone.

Return this JSON shape:
{{"translations":[{{"id":1,"text":"..."}}]}}
"""


def _build_user_prompt(segments: list[dict[str, Any]]) -> str:
    payload = [{"id": item["index"], "text": item["text"]} for item in segments]
    return json.dumps(payload, ensure_ascii=False)


def _parse_translation_response(content: str) -> dict[int, str]:
    payload = json.loads(content)
    translations = payload.get("translations", [])
    result: dict[int, str] = {}
    for item in translations:
        segment_id = int(item["id"])
        translated = str(item.get("text") or item.get("translation") or item.get("zh") or "").strip()
        result[segment_id] = translated
    return result


def _segment_payload(
    *,
    segment_id: int,
    start: float,
    end: float,
    source_text: str,
    learning_text: str,
    source_lang: str,
    learning_lang: str,
) -> dict[str, Any]:
    return {
        "id": segment_id,
        "start": start,
        "end": end,
        "source_lang": normalize_lang_code(source_lang),
        "learning_lang": normalize_lang_code(learning_lang),
        "source_text": source_text,
        "learning_text": learning_text,
        # Compatibility keys used by the current frontend.
        "en": source_text,
        "zh": learning_text,
    }


def translate_segments_with_llm(
    transcript: TranscriptResult,
    config: TranslationConfig,
    *,
    source_lang: str,
    learning_lang: str,
    batch_size: int = 1,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    system_prompt = _translation_system_prompt(source_lang, learning_lang)
    for start in range(0, len(transcript.segments), batch_size):
        batch = transcript.segments[start : start + batch_size]
        user_prompt = _build_user_prompt([{"index": seg.index, "text": seg.text} for seg in batch])
        content = post_chat_json(config, system_prompt, user_prompt, temperature=0.2)
        translations = _parse_translation_response(content)
        for segment in batch:
            output.append(
                _segment_payload(
                    segment_id=segment.index,
                    start=segment.start,
                    end=segment.end,
                    source_text=segment.text,
                    learning_text=translations.get(segment.index, ""),
                    source_lang=source_lang,
                    learning_lang=learning_lang,
                )
            )
    return output


def translate_segments_with_deeplx(
    transcript: TranscriptResult,
    config: DeepLXConfig,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = [None] * len(transcript.segments)
    max_workers = min(max(1, int(config.max_workers)), max(1, len(transcript.segments)))

    def translate_one(index: int, segment: Any) -> tuple[int, dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(max(1, int(config.retries)) + 1):
            try:
                with httpx.Client(timeout=config.timeout_seconds, trust_env=config.trust_env) as client:
                    response = client.post(
                        config.url,
                        headers={"Content-Type": "application/json"},
                        json={
                            "text": segment.text,
                            "source_lang": config.source_lang,
                            "target_lang": config.target_lang,
                        },
                    )
                response.raise_for_status()
                payload = response.json()
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= max(1, int(config.retries)):
                    raise RuntimeError(f"DeepLX translation failed for segment {segment.index}: {exc}") from exc
                time.sleep(0.8 * (attempt + 1))
        else:
            raise RuntimeError(f"DeepLX translation failed for segment {segment.index}: {last_error}")
        return (
            index,
            _segment_payload(
                segment_id=segment.index,
                start=segment.start,
                end=segment.end,
                source_text=segment.text,
                learning_text=str(payload.get("data", "")).strip(),
                source_lang=config.source_lang,
                learning_lang=config.target_lang,
            ),
        )

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(translate_one, index, segment)
                for index, segment in enumerate(transcript.segments)
            ]
            for future in as_completed(futures):
                index, translated = future.result()
                output[index] = translated
    except Exception:
        output = []
        for index, segment in enumerate(transcript.segments):
            _, translated = translate_one(index, segment)
            output.append(translated)

    return [item for item in output if item is not None]


def compose_srt(bilingual_segments: list[dict[str, Any]], mode: str) -> str:
    subtitles: list[srt.Subtitle] = []
    for item in bilingual_segments:
        content = _subtitle_content(item, mode)

        subtitles.append(
            srt.Subtitle(
                index=int(item["id"]),
                start=timedelta(seconds=float(item["start"])),
                end=timedelta(seconds=float(item["end"])),
                content=content,
            )
        )
    return srt.compose(subtitles)


def _subtitle_content(item: dict[str, Any], mode: str) -> str:
    source_text = str(item.get("source_text") or item.get("en") or "")
    learning_text = str(item.get("learning_text") or item.get("zh") or "")
    if mode == "source":
        return source_text
    if mode == "learning":
        return learning_text
    if mode == "bilingual":
        return f"{source_text}\n{learning_text}".strip()
    raise ValueError(f"Unsupported subtitle mode: {mode}")


def _vtt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    secs = (total_ms % 60_000) // 1000
    millis = total_ms % 1000
    return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"


def compose_vtt(bilingual_segments: list[dict[str, Any]], mode: str) -> str:
    blocks = ["WEBVTT"]
    for item in bilingual_segments:
        start = _vtt_timestamp(float(item["start"]))
        end = _vtt_timestamp(float(item["end"]))
        content = _subtitle_content(item, mode)
        blocks.append(f"\n{int(item['id'])}\n{start} --> {end}\n{content}")
    return "\n".join(blocks) + "\n"


def save_bilingual_outputs(
    transcript: TranscriptResult,
    bilingual_segments: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    source_lang: str,
    learning_lang: str,
    native_lang: str,
) -> tuple[Path, Path, Path]:
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    stem = Path(transcript.source_path).stem
    bilingual_path = output_path / f"{stem}.bilingual.json"
    learning_srt_path = output_path / f"{stem}.learning.srt"
    bilingual_srt_path = output_path / f"{stem}.bilingual.srt"
    source_srt_path = output_path / f"{stem}.source.srt"
    payload = transcript_to_dict(transcript)
    payload.update(
        {
            "source_lang": normalize_lang_code(source_lang),
            "learning_lang": normalize_lang_code(learning_lang),
            "native_lang": normalize_lang_code(native_lang),
            "bilingual_segments": bilingual_segments,
        }
    )
    bilingual_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    source_srt_path.write_text(compose_srt(bilingual_segments, "source"), encoding="utf-8")
    learning_srt_path.write_text(compose_srt(bilingual_segments, "learning"), encoding="utf-8")
    bilingual_srt_path.write_text(compose_srt(bilingual_segments, "bilingual"), encoding="utf-8")
    return bilingual_path, learning_srt_path, bilingual_srt_path
