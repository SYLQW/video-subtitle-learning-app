from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import srt
from faster_whisper import WhisperModel


@dataclass
class TranscriptSegment:
    index: int
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    source_path: str
    model_size: str
    language: str | None
    language_probability: float | None
    duration_seconds: float | None
    segments: list[TranscriptSegment]


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def transcribe_video(
    video_path: str | Path,
    model_size: str = "small.en",
    device: str = "cuda",
    compute_type: str = "float16",
    beam_size: int = 5,
    vad_filter: bool = True,
    word_timestamps: bool = False,
) -> TranscriptResult:
    source = Path(video_path).expanduser().resolve()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    segments_iter, info = model.transcribe(
        str(source),
        beam_size=beam_size,
        vad_filter=vad_filter,
        word_timestamps=word_timestamps,
    )

    segments: list[TranscriptSegment] = []
    for index, segment in enumerate(segments_iter, start=1):
        text = _normalize_text(segment.text)
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                index=index,
                start=round(float(segment.start), 3),
                end=round(float(segment.end), 3),
                text=text,
            )
        )

    return TranscriptResult(
        source_path=str(source),
        model_size=model_size,
        language=info.language,
        language_probability=info.language_probability,
        duration_seconds=getattr(info, "duration", None),
        segments=segments,
    )


def transcript_to_srt(result: TranscriptResult) -> str:
    subtitles = [
        srt.Subtitle(
            index=segment.index,
            start=timedelta(seconds=segment.start),
            end=timedelta(seconds=segment.end),
            content=segment.text,
        )
        for segment in result.segments
    ]
    return srt.compose(subtitles)


def transcript_to_dict(result: TranscriptResult) -> dict[str, Any]:
    return {
        "source_path": result.source_path,
        "model_size": result.model_size,
        "language": result.language,
        "language_probability": result.language_probability,
        "duration_seconds": result.duration_seconds,
        "segments": [asdict(segment) for segment in result.segments],
    }


def save_transcript_outputs(result: TranscriptResult, output_dir: str | Path) -> tuple[Path, Path]:
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    stem = Path(result.source_path).stem
    json_path = output_path / f"{stem}.transcript.json"
    srt_path = output_path / f"{stem}.en.srt"

    json_path.write_text(
        json.dumps(transcript_to_dict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    srt_path.write_text(transcript_to_srt(result), encoding="utf-8")

    return json_path, srt_path

