from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from backend.app.services.analysis import analyze_sentence, stream_sentence_analysis
from backend.app.services.database import get_analysis_cache, init_db, upsert_analysis_cache
from backend.app.services.llm_common import OpenAICompatibleConfig, post_chat_json, resolve_endpoint
from backend.app.services.settings import get_app_settings, get_llm_profile, save_app_settings
from backend.app.services.transcription import TranscriptResult, TranscriptSegment, save_transcript_outputs, transcribe_video
from backend.app.services.translation import (
    DeepLXConfig,
    TranslationConfig,
    save_bilingual_outputs,
    translate_segments_with_deeplx,
    translate_segments_with_llm,
)
from backend.app.services.video_library import (
    get_video_session,
    list_library_items,
    save_uploaded_video,
    sync_artifacts_for_stem,
    sync_video_library,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


app = FastAPI(
    title="Video Subtitle Learning API",
    version="0.2.0",
    description="Backend service for transcription, translation, analysis, settings, and local video library management.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    sync_video_library()


def _first_video_id() -> int:
    videos = list_library_items()
    if not videos:
        raise FileNotFoundError("No videos found in local library.")
    return int(videos[0]["id"])


def _load_transcript(path: str) -> TranscriptResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return TranscriptResult(
        source_path=payload["source_path"],
        model_size=payload["model_size"],
        language=payload.get("language"),
        language_probability=payload.get("language_probability"),
        duration_seconds=payload.get("duration_seconds"),
        segments=[TranscriptSegment(**segment) for segment in payload["segments"]],
    )


def _load_bilingual_payload(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _analysis_cache_key(video_stem: str, segment_id: int, model_name: str, segment_text: str) -> tuple[str, int, str, str]:
    return (
        video_stem,
        segment_id,
        model_name,
        hashlib.sha1(segment_text.encode("utf-8")).hexdigest()[:10],
    )


def _build_translation_config(settings: dict[str, Any]) -> tuple[str, Any]:
    translation = settings["translation"]
    provider = translation["provider"]
    if provider == "deeplx":
        return (
            provider,
            DeepLXConfig(
                url=translation["deeplx_url"],
                source_lang=translation["source_lang"],
                target_lang=translation["target_lang"],
            ),
        )

    profile = get_llm_profile(settings, translation.get("llm_profile_id"))
    return (
        provider,
        TranslationConfig(
            base_url=profile["base_url"],
            api_key=profile["api_key"],
            model=profile["model"],
            timeout_seconds=120.0,
            api_style=profile.get("api_style", "chat_completions"),
        ),
    )


def _ensure_bilingual_payload(video_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    session = get_video_session(video_id)
    if not session["has_translation"]:
        raise HTTPException(status_code=400, detail="This video has not been translated yet.")
    video = session["video"]
    return video, _load_bilingual_payload(video["bilingual_json_path"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/settings")
def read_settings() -> dict[str, Any]:
    return get_app_settings()


@app.put("/api/settings")
def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    return save_app_settings(payload)


@app.post("/api/llm/test")
def test_llm_connection(payload: dict[str, Any]) -> dict[str, Any]:
    profile = {
        "base_url": str(payload.get("base_url") or "").strip(),
        "api_key": str(payload.get("api_key") or "").strip(),
        "model": str(payload.get("model") or "").strip(),
        "api_style": str(payload.get("api_style") or "chat_completions").strip(),
    }
    if not profile["base_url"]:
        raise HTTPException(status_code=400, detail="Missing base_url.")
    if not profile["api_key"]:
        raise HTTPException(status_code=400, detail="Missing api_key.")
    if not profile["model"]:
        raise HTTPException(status_code=400, detail="Missing model.")

    config = OpenAICompatibleConfig(
        base_url=profile["base_url"],
        api_key=profile["api_key"],
        model=profile["model"],
        api_style=profile["api_style"],
        timeout_seconds=60.0,
    )
    try:
        preview = post_chat_json(
            config,
            "You are a connectivity test assistant. Reply briefly with OK and one short sentence.",
            "hello",
            temperature=0.1,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "endpoint": resolve_endpoint(profile["base_url"], profile["api_style"]),
        "model": profile["model"],
        "preview": preview[:200],
    }


@app.get("/api/videos")
def list_videos() -> dict[str, Any]:
    sync_video_library()
    return {"videos": list_library_items()}


@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
    video = save_uploaded_video(file.filename, content)
    return {"video": video}


@app.get("/api/session")
def read_session(video_id: int | None = Query(default=None)) -> dict[str, Any]:
    sync_video_library()
    try:
        resolved_video_id = video_id or _first_video_id()
        return get_video_session(resolved_video_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/videos/{video_id}/stream")
def stream_video(video_id: int) -> FileResponse:
    video = get_video_session(video_id)["video"]
    guessed_media_type, _ = mimetypes.guess_type(video["path"])
    return FileResponse(
        video["path"],
        media_type=guessed_media_type or "application/octet-stream",
        filename=Path(video["path"]).name,
    )


@app.post("/api/videos/{video_id}/process")
def process_video(video_id: int) -> dict[str, Any]:
    settings = get_app_settings()
    session = get_video_session(video_id)
    video = session["video"]
    transcription_settings = settings["transcription"]

    transcript = transcribe_video(
        video["path"],
        model_size=transcription_settings["model_size"],
        device=transcription_settings["device"],
        compute_type=transcription_settings["compute_type"],
    )
    transcript_json_path, en_srt_path = save_transcript_outputs(
        transcript,
        PROJECT_ROOT / "outputs" / "transcripts",
    )

    provider, provider_config = _build_translation_config(settings)
    if provider == "deeplx":
        bilingual_segments = translate_segments_with_deeplx(transcript, provider_config)
    else:
        bilingual_segments = translate_segments_with_llm(
            transcript,
            provider_config,
            batch_size=int(settings["translation"]["batch_size"]),
        )

    bilingual_json_path, zh_srt_path, bilingual_srt_path = save_bilingual_outputs(
        transcript,
        bilingual_segments,
        PROJECT_ROOT / "outputs" / "translations",
    )
    sync_artifacts_for_stem(Path(video["path"]).stem)

    return {
        "video_id": video_id,
        "provider": provider,
        "transcript_json_path": str(transcript_json_path),
        "en_srt_path": str(en_srt_path),
        "bilingual_json_path": str(bilingual_json_path),
        "zh_srt_path": str(zh_srt_path),
        "bilingual_srt_path": str(bilingual_srt_path),
    }


@app.get("/api/videos/{video_id}/analysis")
def sentence_analysis(
    video_id: int,
    segment_id: int = Query(..., ge=1),
    model: str | None = Query(default=None),
) -> dict[str, Any]:
    settings = get_app_settings()
    video, payload = _ensure_bilingual_payload(video_id)
    analysis_settings = settings["analysis"]
    analysis_profile = get_llm_profile(settings, analysis_settings.get("profile_id"))
    resolved_model = model or analysis_profile["model"]

    segments = payload["bilingual_segments"]
    try:
        index = next(i for i, item in enumerate(segments) if int(item["id"]) == segment_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail=f"Segment id {segment_id} not found.") from exc

    segment = segments[index]
    previous_text = segments[index - 1]["en"] if index > 0 else ""
    next_text = segments[index + 1]["en"] if index + 1 < len(segments) else ""

    video_stem, cache_segment_id, cache_model, segment_hash = _analysis_cache_key(
        video["stem"],
        segment_id,
        resolved_model,
        segment["en"],
    )
    cached = get_analysis_cache(
        video_stem=video_stem,
        segment_id=cache_segment_id,
        model_name=cache_model,
        segment_hash=segment_hash,
    )
    if cached:
        return {"segment": segment, "analysis": cached, "model": resolved_model, "cached": True}

    analysis_result = analyze_sentence(
        text=segment["en"],
        existing_translation=segment["zh"],
        model=resolved_model,
        base_url=analysis_profile["base_url"],
        api_key=analysis_profile["api_key"],
        api_style=analysis_profile.get("api_style", "chat_completions"),
        previous_text=previous_text,
        next_text=next_text,
    )
    upsert_analysis_cache(
        video_stem=video_stem,
        segment_id=cache_segment_id,
        model_name=cache_model,
        segment_hash=segment_hash,
        payload=analysis_result,
    )
    return {"segment": segment, "analysis": analysis_result, "model": resolved_model, "cached": False}


@app.get("/api/videos/{video_id}/analysis/stream")
def sentence_analysis_stream(
    video_id: int,
    segment_id: int = Query(..., ge=1),
    model: str | None = Query(default=None),
) -> StreamingResponse:
    settings = get_app_settings()
    video, payload = _ensure_bilingual_payload(video_id)
    analysis_settings = settings["analysis"]
    analysis_profile = get_llm_profile(settings, analysis_settings.get("profile_id"))
    resolved_model = model or analysis_profile["model"]

    segments = payload["bilingual_segments"]
    try:
        index = next(i for i, item in enumerate(segments) if int(item["id"]) == segment_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail=f"Segment id {segment_id} not found.") from exc

    segment = segments[index]
    previous_text = segments[index - 1]["en"] if index > 0 else ""
    next_text = segments[index + 1]["en"] if index + 1 < len(segments) else ""

    video_stem, cache_segment_id, cache_model, segment_hash = _analysis_cache_key(
        video["stem"],
        segment_id,
        resolved_model,
        segment["en"],
    )
    cached = get_analysis_cache(
        video_stem=video_stem,
        segment_id=cache_segment_id,
        model_name=cache_model,
        segment_hash=segment_hash,
    )

    def event_stream():
        def emit(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield emit("start", {"segment_id": segment_id, "model": resolved_model})

        if cached:
            yield emit("complete", {"analysis": cached, "cached": True})
            return

        accumulated = ""
        try:
            yield emit("status", {"message": "正在调用模型生成句子解析..."})
            for delta in stream_sentence_analysis(
                text=segment["en"],
                existing_translation=segment["zh"],
                model=resolved_model,
                base_url=analysis_profile["base_url"],
                api_key=analysis_profile["api_key"],
                api_style=analysis_profile.get("api_style", "chat_completions"),
                previous_text=previous_text,
                next_text=next_text,
            ):
                accumulated += delta
                yield emit("delta", {"text": delta})

            analysis_result = json.loads(accumulated)
            upsert_analysis_cache(
                video_stem=video_stem,
                segment_id=cache_segment_id,
                model_name=cache_model,
                segment_hash=segment_hash,
                payload=analysis_result,
            )
            yield emit("complete", {"analysis": analysis_result, "cached": False})
        except Exception as exc:  # noqa: BLE001
            yield emit("error", {"message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
