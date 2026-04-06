import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.app.services.analysis import analyze_sentence
from backend.app.services.demo_data import (
    get_analysis_cache_path,
    get_demo_video_path,
    get_latest_bilingual_path,
    get_neighbor_text,
    get_segment_by_id,
    load_latest_bilingual_payload,
)


app = FastAPI(
    title="Video Subtitle Learning API",
    version="0.1.0",
    description="Backend service for transcription, translation, analysis, and export.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/capabilities")
def capabilities() -> dict[str, object]:
    return {
        "speech_recognition": "faster-whisper",
        "translation": ["deepl", "google", "azure", "local-m2m100"],
        "analysis": ["dictionary", "llm-chat"],
        "modes": ["realtime", "batch"],
    }


@app.get("/api/demo/session")
def demo_session() -> dict[str, object]:
    try:
        payload = load_latest_bilingual_payload()
        video_path = get_demo_video_path()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "title": video_path.stem,
        "video_url": "/api/demo/video",
        "subtitle_source": str(get_latest_bilingual_path()),
        "segments": payload["bilingual_segments"],
    }


@app.get("/api/demo/video")
def demo_video() -> FileResponse:
    try:
        video_path = get_demo_video_path()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(video_path, media_type="video/mp4", filename=video_path.name)


@app.get("/api/demo/analysis")
def demo_analysis(
    segment_id: int = Query(..., ge=1),
    model: str = Query("qwen3.6-plus"),
) -> dict[str, object]:
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not base_url or not api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_BASE_URL or OPENAI_API_KEY.")

    try:
        payload = load_latest_bilingual_payload()
        segment = get_segment_by_id(payload, segment_id)
        previous_text, next_text = get_neighbor_text(payload, segment_id)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    cache_path = get_analysis_cache_path(payload["source_path"], segment_id, model)
    cache_hit = cache_path.exists()
    if cache_hit:
        analysis_result = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        analysis_result = analyze_sentence(
            text=segment["en"],
            existing_translation=segment["zh"],
            model=model,
            base_url=base_url,
            api_key=api_key,
            previous_text=previous_text,
            next_text=next_text,
        )
        cache_path.write_text(json.dumps(analysis_result, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "segment": segment,
        "analysis": analysis_result,
        "model": model,
        "cached": cache_hit,
    }
