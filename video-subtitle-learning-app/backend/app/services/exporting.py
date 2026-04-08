from __future__ import annotations

import subprocess
from pathlib import Path

from backend.app.services.translation import compose_srt


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPORT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "exports"


def _subtitle_filename(stem: str, subtitle_mode: str) -> Path:
    return EXPORT_OUTPUT_DIR / f"{stem}.{subtitle_mode}.srt"


def ensure_subtitle_export(stem: str, bilingual_segments: list[dict], subtitle_mode: str) -> Path:
    EXPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _subtitle_filename(stem, subtitle_mode)
    output_path.write_text(compose_srt(bilingual_segments, subtitle_mode), encoding="utf-8")
    return output_path


def _escape_subtitles_filter_path(path: Path) -> str:
    escaped = path.resolve().as_posix().replace(":", r"\:")
    escaped = escaped.replace("'", r"\'")
    escaped = escaped.replace("[", r"\[").replace("]", r"\]")
    return escaped


def export_video_with_subtitles(
    *,
    source_video_path: str | Path,
    stem: str,
    bilingual_segments: list[dict],
    subtitle_mode: str,
    video_mode: str,
) -> Path:
    EXPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_path = Path(source_video_path).expanduser().resolve()
    subtitle_path = ensure_subtitle_export(stem, bilingual_segments, subtitle_mode)
    if video_mode == "soft":
        output_path = EXPORT_OUTPUT_DIR / f"{stem}.{subtitle_mode}.softsub.mp4"
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-i",
            str(subtitle_path),
            "-map",
            "0:v",
            "-map",
            "0:a?",
            "-map",
            "1:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            f"title={subtitle_mode}",
            str(output_path),
        ]
    elif video_mode == "burned":
        output_path = EXPORT_OUTPUT_DIR / f"{stem}.{subtitle_mode}.burned.mp4"
        subtitle_filter = f"subtitles='{_escape_subtitles_filter_path(subtitle_path)}'"
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-vf",
            subtitle_filter,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "copy",
            str(output_path),
        ]
    else:
        raise ValueError(f"Unsupported video export mode: {video_mode}")

    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return output_path
