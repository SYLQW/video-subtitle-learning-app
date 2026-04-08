from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import srt
from faster_whisper import WhisperModel

from backend.app.services.app_paths import get_app_root, get_data_dir, get_model_root
from backend.app.services.language_support import whisper_language


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
    runtime_device: str | None = None
    runtime_compute_type: str | None = None
    fallback_reason: str | None = None


@dataclass
class WordToken:
    text: str
    start: float
    end: float


SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]*$")


def _configure_windows_gpu_runtime() -> None:
    if os.name != "nt":
        return

    candidate_dirs: list[Path] = []
    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path:
        candidate_dirs.extend([Path(cuda_path) / "bin", Path(cuda_path) / "libnvvp"])

    for drive in [Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"]:
        if not drive.exists():
            continue
        candidate_dirs.extend((drive / "NVIDIA GPU Computing Toolkit" / "CUDA").glob("v*\\bin"))
        candidate_dirs.extend((drive / "NVIDIA GPU Computing Toolkit" / "CUDA").glob("v*\\libnvvp"))
        candidate_dirs.extend((drive / "NVIDIA" / "CUDNN").glob("v*\\bin\\*\\x64"))

    resolved_dirs: list[str] = []
    seen: set[str] = set()
    for directory in candidate_dirs:
        if not directory.exists():
            continue
        resolved = str(directory.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        resolved_dirs.append(resolved)

    if resolved_dirs:
        os.environ["PATH"] = os.pathsep.join(resolved_dirs + [os.environ.get("PATH", "")])
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            for directory in resolved_dirs:
                add_dll_directory(directory)


_configure_windows_gpu_runtime()
PROJECT_ROOT = get_app_root()
LOCAL_MODEL_ROOT = get_model_root()
os.environ.setdefault("HF_HOME", str((get_data_dir() / "huggingface").resolve()))


def _huggingface_cache_root() -> Path:
    custom = os.environ.get("HF_HOME")
    if custom:
        return Path(custom).expanduser().resolve() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _repair_model_cache(model_size: str) -> None:
    cache_root = _huggingface_cache_root()
    repo_dir = cache_root / f"models--Systran--faster-whisper-{model_size}"
    locks_dir = cache_root / ".locks" / f"models--Systran--faster-whisper-{model_size}"

    for incomplete in repo_dir.rglob("*.incomplete") if repo_dir.exists() else []:
        try:
            incomplete.unlink()
        except OSError:
            pass

    if locks_dir.exists():
        try:
            shutil.rmtree(locks_dir)
        except OSError:
            for lock_file in locks_dir.rglob("*.lock"):
                try:
                    lock_file.unlink()
                except OSError:
                    pass


def _resolve_model_path(model_size: str) -> str:
    candidate_paths = [
        LOCAL_MODEL_ROOT / f"faster-whisper-{model_size}",
        LOCAL_MODEL_ROOT / "faster-whisper" / model_size,
        LOCAL_MODEL_ROOT / model_size,
    ]
    required = ["config.json", "tokenizer.json", "vocabulary.txt", "model.bin"]
    for local_path in candidate_paths:
        if local_path.exists() and all((local_path / name).exists() for name in required):
            return str(local_path)
    return model_size


def resolve_local_model_path(model_size: str) -> Path | None:
    resolved = _resolve_model_path(model_size)
    if resolved == model_size:
        return None
    return Path(resolved)


def _normalize_text(text: str) -> str:
    compact = " ".join(text.strip().split())
    return re.sub(r"\s+([,.!?;:])", r"\1", compact)


def _raw_word_text(word: Any) -> str:
    return str(getattr(word, "word", ""))


def _to_word_tokens(raw_segments: list[Any]) -> list[WordToken]:
    tokens: list[WordToken] = []
    for segment in raw_segments:
        for word in getattr(segment, "words", None) or []:
            start = getattr(word, "start", None)
            end = getattr(word, "end", None)
            text = _raw_word_text(word)
            if start is None or end is None or not text.strip():
                continue
            tokens.append(
                WordToken(
                    text=text,
                    start=round(float(start), 3),
                    end=round(float(end), 3),
                )
            )
    return tokens


def _compose_text(tokens: list[WordToken]) -> str:
    return _normalize_text("".join(token.text for token in tokens))


def _is_sentence_boundary(current_tokens: list[WordToken], next_token: WordToken | None) -> bool:
    if not current_tokens:
        return False

    current_text = _compose_text(current_tokens)
    if SENTENCE_END_RE.search(current_text):
        return True

    duration = current_tokens[-1].end - current_tokens[0].start
    next_gap = (next_token.start - current_tokens[-1].end) if next_token else 0.0

    if next_gap >= 1.1 and len(current_text) >= 24:
        return True

    if duration >= 13.0 and len(current_text) >= 80:
        return True

    return False


def _sentence_segments_from_words(word_tokens: list[WordToken]) -> list[TranscriptSegment]:
    if not word_tokens:
        return []

    segments: list[TranscriptSegment] = []
    current_tokens: list[WordToken] = []

    for index, token in enumerate(word_tokens):
        current_tokens.append(token)
        next_token = word_tokens[index + 1] if index + 1 < len(word_tokens) else None
        if not _is_sentence_boundary(current_tokens, next_token):
            continue

        text = _compose_text(current_tokens)
        if text:
            segments.append(
                TranscriptSegment(
                    index=len(segments) + 1,
                    start=current_tokens[0].start,
                    end=current_tokens[-1].end,
                    text=text,
                )
            )
        current_tokens = []

    if current_tokens:
        text = _compose_text(current_tokens)
        if text:
            segments.append(
                TranscriptSegment(
                    index=len(segments) + 1,
                    start=current_tokens[0].start,
                    end=current_tokens[-1].end,
                    text=text,
                )
            )

    return segments


def _fallback_segments(raw_segments: list[Any]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for raw_segment in raw_segments:
        text = _normalize_text(raw_segment.text)
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                index=len(segments) + 1,
                start=round(float(raw_segment.start), 3),
                end=round(float(raw_segment.end), 3),
                text=text,
            )
        )
    return segments


def _resolve_model_size(model_size: str, language: str | None) -> str:
    resolved = str(model_size or "base").strip()
    requested_language = whisper_language(language)
    if resolved.endswith(".en") and requested_language != "en":
        return resolved.removesuffix(".en") or "base"
    return resolved


def resolve_transcription_runtime(
    *,
    device: str,
    compute_type: str,
    language: str | None,
) -> tuple[str, str]:
    return device, compute_type


def _transcript_result_from_dict(payload: dict[str, Any]) -> TranscriptResult:
    return TranscriptResult(
        source_path=str(payload["source_path"]),
        model_size=str(payload["model_size"]),
        language=payload.get("language"),
        language_probability=payload.get("language_probability"),
        duration_seconds=payload.get("duration_seconds"),
        runtime_device=payload.get("runtime_device"),
        runtime_compute_type=payload.get("runtime_compute_type"),
        fallback_reason=payload.get("fallback_reason"),
        segments=[
            TranscriptSegment(
                index=int(segment["index"]),
                start=float(segment["start"]),
                end=float(segment["end"]),
                text=str(segment["text"]),
            )
            for segment in payload.get("segments", [])
        ],
    )


def _format_subprocess_error(completed: subprocess.CompletedProcess[str]) -> str:
    parts = [f"exit code {completed.returncode}"]
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if stdout:
        parts.append(f"stdout: {stdout[-1000:]}")
    if stderr:
        parts.append(f"stderr: {stderr[-1000:]}")
    return "; ".join(parts)


def _run_transcription_subprocess(
    *,
    video_path: str | Path,
    model_size: str,
    device: str,
    compute_type: str,
    beam_size: int,
    vad_filter: bool,
    word_timestamps: bool,
    language: str | None,
) -> TranscriptResult:
    request_payload = {
        "video_path": str(Path(video_path).expanduser().resolve()),
        "model_size": model_size,
        "device": device,
        "compute_type": compute_type,
        "beam_size": beam_size,
        "vad_filter": vad_filter,
        "word_timestamps": word_timestamps,
        "language": language,
    }

    with tempfile.TemporaryDirectory(prefix="video-subtitle-transcribe-") as temp_dir:
        temp_root = Path(temp_dir)
        request_path = temp_root / "request.json"
        output_path = temp_root / "result.json"
        request_path.write_text(json.dumps(request_payload, ensure_ascii=False), encoding="utf-8")

        completed = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "backend.app.services.transcription_worker",
                str(request_path),
                str(output_path),
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RuntimeError(_format_subprocess_error(completed))
        if not output_path.exists():
            raise RuntimeError("transcription worker finished without writing a result file")

        return _transcript_result_from_dict(json.loads(output_path.read_text(encoding="utf-8")))


def _transcribe_video_once(
    video_path: str | Path,
    model_size: str = "base",
    device: str = "cuda",
    compute_type: str = "float16",
    beam_size: int = 5,
    vad_filter: bool = True,
    word_timestamps: bool = True,
    language: str | None = None,
) -> TranscriptResult:
    source = Path(video_path).expanduser().resolve()
    resolved_model_size = _resolve_model_size(model_size, language)
    _repair_model_cache(resolved_model_size)
    model = WhisperModel(_resolve_model_path(resolved_model_size), device=device, compute_type=compute_type)

    segments_iter, info = model.transcribe(
        str(source),
        beam_size=beam_size,
        vad_filter=vad_filter,
        word_timestamps=word_timestamps,
        condition_on_previous_text=False,
        language=whisper_language(language),
    )

    raw_segments = list(segments_iter)
    word_tokens = _to_word_tokens(raw_segments)
    segments = _sentence_segments_from_words(word_tokens)
    if not segments:
        segments = _fallback_segments(raw_segments)

    return TranscriptResult(
        source_path=str(source),
        model_size=resolved_model_size,
        language=info.language,
        language_probability=info.language_probability,
        duration_seconds=getattr(info, "duration", None),
        segments=segments,
        runtime_device=device,
        runtime_compute_type=compute_type,
    )


def transcribe_video(
    video_path: str | Path,
    model_size: str = "base",
    device: str = "cuda",
    compute_type: str = "float16",
    beam_size: int = 5,
    vad_filter: bool = True,
    word_timestamps: bool = True,
    language: str | None = None,
) -> TranscriptResult:
    requested_device = str(device or "cpu").strip().lower()
    requested_compute_type = str(compute_type or "int8").strip().lower()

    try:
        return _run_transcription_subprocess(
            video_path=video_path,
            model_size=model_size,
            device=requested_device,
            compute_type=requested_compute_type,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps,
            language=language,
        )
    except Exception as exc:
        if requested_device == "cpu":
            raise RuntimeError(f"CPU transcription failed: {exc}") from exc

        fallback = _run_transcription_subprocess(
            video_path=video_path,
            model_size=model_size,
            device="cpu",
            compute_type="int8",
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps,
            language=language,
        )
        fallback.fallback_reason = f"GPU transcription failed and fell back to CPU: {exc}"
        return fallback


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
        "runtime_device": result.runtime_device,
        "runtime_compute_type": result.runtime_compute_type,
        "fallback_reason": result.fallback_reason,
        "segments": [asdict(segment) for segment in result.segments],
    }


def save_transcript_outputs(result: TranscriptResult, output_dir: str | Path) -> tuple[Path, Path]:
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    stem = Path(result.source_path).stem
    json_path = output_path / f"{stem}.transcript.json"
    srt_path = output_path / f"{stem}.source.srt"

    json_path.write_text(
        json.dumps(transcript_to_dict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    srt_path.write_text(transcript_to_srt(result), encoding="utf-8")

    return json_path, srt_path
