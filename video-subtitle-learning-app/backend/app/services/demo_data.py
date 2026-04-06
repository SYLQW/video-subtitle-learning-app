from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PLAYGROUND_ROOT = PROJECT_ROOT.parent
TEST_VIDEO_DIR = PLAYGROUND_ROOT / "测试视频"
TRANSLATION_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "translations"
ANALYSIS_CACHE_DIR = PROJECT_ROOT / "outputs" / "analysis"


def _latest_file(directory: Path, suffix: str) -> Path:
    files = sorted(
        [path for path in directory.glob(f"*{suffix}") if path.is_file()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No file matching *{suffix} in {directory}")
    return files[0]


def get_demo_video_path() -> Path:
    videos = sorted(TEST_VIDEO_DIR.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in videos:
        if path.is_file():
            return path
    raise FileNotFoundError(f"No demo video found in {TEST_VIDEO_DIR}")


def get_latest_bilingual_path() -> Path:
    return _latest_file(TRANSLATION_OUTPUT_DIR, ".bilingual.json")


def load_latest_bilingual_payload() -> dict[str, Any]:
    path = get_latest_bilingual_path()
    return json.loads(path.read_text(encoding="utf-8"))


def get_segment_by_id(payload: dict[str, Any], segment_id: int) -> dict[str, Any]:
    for segment in payload["bilingual_segments"]:
        if int(segment["id"]) == segment_id:
            return segment
    raise KeyError(f"Segment id {segment_id} not found")


def get_neighbor_text(payload: dict[str, Any], segment_id: int) -> tuple[str, str]:
    segments = payload["bilingual_segments"]
    for index, segment in enumerate(segments):
        if int(segment["id"]) != segment_id:
            continue
        previous_text = segments[index - 1]["en"] if index > 0 else ""
        next_text = segments[index + 1]["en"] if index + 1 < len(segments) else ""
        return previous_text, next_text
    raise KeyError(f"Segment id {segment_id} not found")


def get_analysis_cache_path(source_path: str, segment_id: int, model_name: str) -> Path:
    ANALYSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    source_stem = Path(source_path).stem
    safe_model = model_name.replace("/", "-")
    return ANALYSIS_CACHE_DIR / f"{source_stem}.segment-{segment_id}.{safe_model}.analysis.json"

