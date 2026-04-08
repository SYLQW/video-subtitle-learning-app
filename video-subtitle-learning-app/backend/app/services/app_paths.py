from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


@lru_cache(maxsize=1)
def get_app_root() -> Path:
    explicit_root = _env_path("VIDEO_SUBTITLE_APP_ROOT") or _env_path("VIDEO_SUBTITLE_PORTABLE_ROOT")
    return explicit_root or PROJECT_ROOT


def is_portable_mode() -> bool:
    return get_app_root() != PROJECT_ROOT or bool(os.environ.get("VIDEO_SUBTITLE_PORTABLE_MODE"))


def get_data_dir() -> Path:
    return get_app_root() / "data"


def get_db_path() -> Path:
    return get_data_dir() / "app.sqlite3"


def get_library_video_dir() -> Path:
    return get_data_dir() / "videos"


def get_outputs_dir() -> Path:
    return get_app_root() / "outputs"


def get_transcripts_dir() -> Path:
    return get_outputs_dir() / "transcripts"


def get_translations_dir() -> Path:
    return get_outputs_dir() / "translations"


def get_exports_dir() -> Path:
    return get_outputs_dir() / "exports"


def get_analysis_output_dir() -> Path:
    return get_outputs_dir() / "analysis"


def get_logs_dir() -> Path:
    return get_data_dir() / "logs"


def get_temp_dir() -> Path:
    return get_app_root() / "temp"


def get_model_root() -> Path:
    custom_root = _env_path("VIDEO_SUBTITLE_MODEL_ROOT")
    return custom_root or (get_app_root() / "models")


def get_ffmpeg_dir() -> Path:
    return get_app_root() / "ffmpeg"


def get_ffmpeg_executable() -> str:
    candidate = get_ffmpeg_dir() / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    return str(candidate.resolve()) if candidate.exists() else "ffmpeg"


def get_ffprobe_executable() -> str:
    candidate = get_ffmpeg_dir() / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    return str(candidate.resolve()) if candidate.exists() else "ffprobe"


def get_demo_video_dir() -> Path:
    configured = _env_path("VIDEO_SUBTITLE_DEMO_VIDEO_DIR")
    if configured:
        return configured

    project_demo_dir = PROJECT_ROOT.parent / "测试视频"
    if get_app_root() == PROJECT_ROOT and project_demo_dir.exists():
        return project_demo_dir
    return get_app_root() / "测试视频"


def ensure_app_directories() -> None:
    for path in [
        get_data_dir(),
        get_library_video_dir(),
        get_outputs_dir(),
        get_transcripts_dir(),
        get_translations_dir(),
        get_exports_dir(),
        get_analysis_output_dir(),
        get_logs_dir(),
        get_temp_dir(),
        get_model_root(),
    ]:
        path.mkdir(parents=True, exist_ok=True)
