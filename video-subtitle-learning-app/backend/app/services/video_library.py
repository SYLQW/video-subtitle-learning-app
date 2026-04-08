from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.services.database import LIBRARY_VIDEO_DIR, delete_video, get_video, list_videos, upsert_artifact, upsert_video


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PLAYGROUND_ROOT = PROJECT_ROOT.parent
TEST_VIDEO_DIR = PLAYGROUND_ROOT / "测试视频"
TRANSCRIPT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "transcripts"
TRANSLATION_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "translations"


def sync_video_library() -> None:
    directories = [
        ("demo", TEST_VIDEO_DIR),
        ("library", LIBRARY_VIDEO_DIR),
    ]
    for source, directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.iterdir():
            if not path.is_file():
                continue
            upsert_video(str(path.resolve()), path.stem, source=source)
            sync_artifacts_for_stem(path.stem)


def sync_artifacts_for_stem(stem: str) -> None:
    transcript_json = TRANSCRIPT_OUTPUT_DIR / f"{stem}.transcript.json"
    source_srt = TRANSCRIPT_OUTPUT_DIR / f"{stem}.source.srt"
    legacy_en_srt = TRANSCRIPT_OUTPUT_DIR / f"{stem}.en.srt"
    bilingual_json = TRANSLATION_OUTPUT_DIR / f"{stem}.bilingual.json"
    learning_srt = TRANSLATION_OUTPUT_DIR / f"{stem}.learning.srt"
    legacy_zh_srt = TRANSLATION_OUTPUT_DIR / f"{stem}.zh.srt"
    bilingual_srt = TRANSLATION_OUTPUT_DIR / f"{stem}.bilingual.srt"
    upsert_artifact(
        stem,
        transcript_json_path=str(transcript_json) if transcript_json.exists() else None,
        en_srt_path=str(source_srt if source_srt.exists() else legacy_en_srt) if (source_srt.exists() or legacy_en_srt.exists()) else None,
        bilingual_json_path=str(bilingual_json) if bilingual_json.exists() else None,
        zh_srt_path=str(learning_srt if learning_srt.exists() else legacy_zh_srt) if (learning_srt.exists() or legacy_zh_srt.exists()) else None,
        bilingual_srt_path=str(bilingual_srt) if bilingual_srt.exists() else None,
    )


def list_library_items() -> list[dict[str, Any]]:
    return list_videos()


def get_video_session(video_id: int) -> dict[str, Any]:
    video = get_video(video_id)
    if not video:
        raise FileNotFoundError(f"Video id {video_id} not found")

    segments: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    transcript_payload: dict[str, Any] = {}

    if video.get("transcript_json_path"):
        transcript_path = Path(video["transcript_json_path"])
        if transcript_path.exists():
            transcript_payload = json.loads(transcript_path.read_text(encoding="utf-8"))
            for item in transcript_payload.get("segments", []):
                segment_id = item.get("id") or item.get("index")
                source_text = item.get("text") or item.get("source_text") or item.get("en") or ""
                learning_text = item.get("learning_text") or item.get("zh") or ""
                segments.append(
                    {
                        **item,
                        "id": segment_id,
                        "source_text": source_text,
                        "learning_text": learning_text,
                        "en": source_text,
                        "zh": learning_text,
                    }
                )

    if video.get("bilingual_json_path"):
        bilingual_path = Path(video["bilingual_json_path"])
        if bilingual_path.exists():
            payload = json.loads(bilingual_path.read_text(encoding="utf-8"))
            raw_segments = payload.get("bilingual_segments", [])
            segments = []
            for item in raw_segments:
                source_text = item.get("source_text") or item.get("en") or ""
                learning_text = item.get("learning_text") or item.get("zh") or ""
                segments.append(
                    {
                        **item,
                        "source_text": source_text,
                        "learning_text": learning_text,
                        "en": source_text,
                        "zh": learning_text,
                    }
                )

    return {
        "video": video,
        "title": video["title"],
        "video_url": f"/api/videos/{video_id}/stream",
        "segments": segments,
        "has_transcript": bool(video.get("transcript_json_path")),
        "has_translation": bool(video.get("bilingual_json_path")),
        "source_lang": payload.get("source_lang") or transcript_payload.get("language"),
        "learning_lang": payload.get("learning_lang"),
        "native_lang": payload.get("native_lang"),
    }


def delete_video_item(video_id: int) -> dict[str, Any]:
    video = get_video(video_id)
    if not video:
        raise FileNotFoundError(f"Video id {video_id} not found")

    video_path = Path(video["path"]).expanduser().resolve()
    allowed_roots = [LIBRARY_VIDEO_DIR.resolve(), TEST_VIDEO_DIR.resolve()]
    if any(video_path.is_relative_to(root) for root in allowed_roots) and video_path.exists():
        video_path.unlink()

    output_paths = [
        TRANSCRIPT_OUTPUT_DIR / f"{video['stem']}.transcript.json",
        TRANSCRIPT_OUTPUT_DIR / f"{video['stem']}.source.srt",
        TRANSCRIPT_OUTPUT_DIR / f"{video['stem']}.en.srt",
        TRANSLATION_OUTPUT_DIR / f"{video['stem']}.bilingual.json",
        TRANSLATION_OUTPUT_DIR / f"{video['stem']}.learning.srt",
        TRANSLATION_OUTPUT_DIR / f"{video['stem']}.zh.srt",
        TRANSLATION_OUTPUT_DIR / f"{video['stem']}.bilingual.srt",
    ]
    for path in output_paths:
        if path.exists():
            path.unlink()

    deleted = delete_video(video_id)
    if not deleted:
        raise FileNotFoundError(f"Video id {video_id} not found")
    return deleted


def save_uploaded_video(filename: str, content: bytes) -> dict[str, Any]:
    target_path = LIBRARY_VIDEO_DIR / filename
    target_path.write_bytes(content)
    video_id = upsert_video(str(target_path.resolve()), target_path.stem, source="upload")
    sync_artifacts_for_stem(target_path.stem)
    video = get_video(video_id)
    if not video:
        raise FileNotFoundError("Failed to register uploaded video")
    return video
