from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse

from backend.app.services.app_paths import (
    ensure_app_directories,
    get_app_root,
    get_transcripts_dir,
    get_translations_dir,
)
from backend.app.services.analysis import analyze_sentence, stream_sentence_analysis
from backend.app.services.database import (
    add_sentence_entry,
    add_word_entry,
    create_notebook,
    delete_notebook,
    delete_sentence_entry,
    delete_word_entry,
    get_analysis_cache,
    get_notebook,
    get_notebook_export_payload,
    init_db,
    list_notebooks,
    list_sentence_entries,
    list_word_entries,
    update_notebook,
    upsert_analysis_cache,
)
from backend.app.services.exporting import ensure_subtitle_export, export_video_with_subtitles
from backend.app.services.language_support import normalize_lang_code
from backend.app.services.llm_common import OpenAICompatibleConfig, post_chat_json, resolve_endpoint
from backend.app.services.notebook_pdf import build_notebook_pdf
from backend.app.services.runtime_env import get_runtime_status
from backend.app.services.settings import get_app_settings, get_llm_profile, save_app_settings
from backend.app.services.transcription import (
    TranscriptResult,
    TranscriptSegment,
    resolve_transcription_runtime,
    save_transcript_outputs,
    transcribe_video,
)
from backend.app.services.translation import (
    DeepLXConfig,
    TranslationConfig,
    compose_vtt,
    save_bilingual_outputs,
    translate_segments_with_deeplx,
    translate_segments_with_llm,
)
from backend.app.services.video_library import (
    delete_video_item,
    get_video_session,
    list_library_items,
    save_uploaded_video,
    sync_artifacts_for_stem,
    sync_video_library,
)
from backend.app.services.video_tasks import get_active_task_for_video, get_task, start_video_task, update_task

PROJECT_ROOT = get_app_root()


app = FastAPI(
    title="Video Subtitle Learning API",
    version="0.2.0",
    description="Backend service for transcription, translation, analysis, settings, and local video library management.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_app_directories()
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


def _build_translation_config(settings: dict[str, Any], *, source_lang: str, learning_lang: str) -> tuple[str, Any]:
    translation = settings["translation"]
    provider = translation["provider"]
    if provider == "deeplx":
        return (
            provider,
            DeepLXConfig(
                url=translation["deeplx_url"],
                source_lang=source_lang,
                target_lang=learning_lang,
                trust_env=bool(translation.get("deeplx_use_proxy", True)),
                max_workers=int(translation.get("deeplx_concurrency", 2)),
                retries=2,
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


def _resolve_source_lang(settings: dict[str, Any], transcript: TranscriptResult) -> str:
    configured = normalize_lang_code(settings["translation"].get("source_lang"), default="AUTO")
    if configured != "AUTO":
        return configured
    return normalize_lang_code(transcript.language, default="AUTO")


def _translate_and_save_video(
    *,
    video: dict[str, Any],
    transcript: TranscriptResult,
    settings: dict[str, Any],
) -> dict[str, Any]:
    translation_settings = settings["translation"]
    source_lang = _resolve_source_lang(settings, transcript)
    learning_lang = normalize_lang_code(translation_settings.get("learning_lang"), default="ZH")
    native_lang = normalize_lang_code(translation_settings.get("native_lang"), default="ZH")

    provider, provider_config = _build_translation_config(
        settings,
        source_lang=source_lang,
        learning_lang=learning_lang,
    )
    if provider == "deeplx":
        bilingual_segments = translate_segments_with_deeplx(transcript, provider_config)
    else:
        bilingual_segments = translate_segments_with_llm(
            transcript,
            provider_config,
            source_lang=source_lang,
            learning_lang=learning_lang,
            batch_size=int(settings["translation"]["batch_size"]),
        )

    bilingual_json_path, learning_srt_path, bilingual_srt_path = save_bilingual_outputs(
        transcript,
        bilingual_segments,
        get_translations_dir(),
        source_lang=source_lang,
        learning_lang=learning_lang,
        native_lang=native_lang,
    )
    sync_artifacts_for_stem(Path(video["path"]).stem)
    return {
        "provider": provider,
        "source_lang": source_lang,
        "learning_lang": learning_lang,
        "native_lang": native_lang,
        "bilingual_json_path": str(bilingual_json_path),
        "learning_srt_path": str(learning_srt_path),
        "zh_srt_path": str(learning_srt_path),
        "bilingual_srt_path": str(bilingual_srt_path),
    }


def _source_srt_output_path(video: dict[str, Any]) -> str:
    return str(get_transcripts_dir() / f"{video['stem']}.source.srt")


def _video_with_task(video: dict[str, Any]) -> dict[str, Any]:
    return {
        **video,
        "active_task": get_active_task_for_video(int(video["id"])),
    }


def _build_export_segments(
    transcript: TranscriptResult | None,
    bilingual_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if bilingual_payload:
        return list(bilingual_payload.get("bilingual_segments", []))
    if not transcript:
        return []
    return [
        {
            "id": segment.index,
            "start": segment.start,
            "end": segment.end,
            "source_text": segment.text,
            "learning_text": "",
            "en": segment.text,
            "zh": "",
        }
        for segment in transcript.segments
    ]


def _download_name(video: dict[str, Any], export_path: Path) -> str:
    return export_path.name if export_path.name.startswith(f"{video['stem']}.") else f"{video['stem']}.{export_path.name}"


def _segment_target_text(segment: dict[str, Any]) -> str:
    return str(segment.get("learning_text") or segment.get("zh") or segment.get("source_text") or segment.get("en") or "")


def _segment_source_text(segment: dict[str, Any]) -> str:
    return str(segment.get("source_text") or segment.get("en") or "")


def _segment_languages(payload: dict[str, Any], settings: dict[str, Any]) -> tuple[str, str, str]:
    translation_settings = settings["translation"]
    source_lang = payload.get("source_lang") or translation_settings.get("source_lang") or "AUTO"
    learning_lang = payload.get("learning_lang") or translation_settings.get("learning_lang") or "ZH"
    native_lang = payload.get("native_lang") or translation_settings.get("native_lang") or "ZH"
    return source_lang, learning_lang, native_lang


def _select_analysis_focus(
    *,
    segment: dict[str, Any],
    source_lang: str,
    learning_lang: str,
    native_lang: str,
) -> tuple[str, str, str, str]:
    source_text = _segment_source_text(segment)
    translated_text = _segment_target_text(segment)
    normalized_source_lang = normalize_lang_code(source_lang, default="AUTO")
    normalized_learning_lang = normalize_lang_code(learning_lang, default="ZH")
    normalized_native_lang = normalize_lang_code(native_lang, default="ZH")

    # Most common learning flow: video is in the foreign language and the learner
    # wants native-language explanations. In that case analysis should stay on the
    # original subtitle text instead of the translated Chinese line.
    if source_text and normalized_source_lang != normalized_native_lang and normalized_learning_lang == normalized_native_lang:
        return source_text, normalized_source_lang, translated_text, normalized_learning_lang

    if translated_text:
        reference_text = source_text if translated_text != source_text else ""
        reference_lang = normalized_source_lang if reference_text else normalized_learning_lang
        return translated_text, normalized_learning_lang, reference_text, reference_lang

    return source_text, normalized_source_lang, translated_text, normalized_learning_lang


def _analysis_context(
    segments: list[dict[str, Any]],
    index: int,
    *,
    source_lang: str,
    learning_lang: str,
    native_lang: str,
) -> tuple[str, str]:
    def study_text_for(item: dict[str, Any]) -> str:
        study_text, _, _, _ = _select_analysis_focus(
            segment=item,
            source_lang=source_lang,
            learning_lang=learning_lang,
            native_lang=native_lang,
        )
        return study_text

    previous_text = study_text_for(segments[index - 1]) if index > 0 else ""
    next_text = study_text_for(segments[index + 1]) if index + 1 < len(segments) else ""
    return previous_text, next_text


def _seconds_label(value: Any) -> str:
    if value is None:
        return ""
    try:
        total = float(value)
    except (TypeError, ValueError):
        return str(value)
    minutes = int(total // 60)
    seconds = total - minutes * 60
    return f"{minutes:02d}:{seconds:06.3f}"


def _safe_export_name(value: str) -> str:
    compact = re.sub(r"\s+", "-", str(value or "").strip())
    cleaned = re.sub(r'[<>:"/\\\\|?*]+', "-", compact)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "notebook"


def _download_headers(filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }


def _http_error_from_value_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status = 404 if "not found" in detail.lower() else 400
    return HTTPException(status_code=status, detail=detail)


def _notebook_export_response(notebook_id: int, export_format: str, pdf_options: dict[str, Any] | None = None) -> Response:
    payload = get_notebook_export_payload(notebook_id)
    if not payload:
        raise HTTPException(status_code=404, detail=f"Notebook id {notebook_id} not found.")

    notebook = payload["notebook"]
    entries = payload["entries"]
    extension = export_format.lower()
    base_name = f"{_safe_export_name(notebook['name'])}.{extension}"

    if extension == "json":
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers=_download_headers(base_name),
        )

    if extension == "csv":
        buffer = io.StringIO()
        if notebook["type"] == "word":
            fieldnames = [
                "word",
                "meaning",
                "note",
                "source_sentence",
                "learning_sentence",
                "video_title",
                "start_time",
                "end_time",
                "created_at",
            ]
            rows = [
                {
                    "word": entry["word"],
                    "meaning": entry["meaning"],
                    "note": entry["note"],
                    "source_sentence": entry["source_sentence"],
                    "learning_sentence": entry["learning_sentence"],
                    "video_title": entry["video_title"],
                    "start_time": _seconds_label(entry["start_time"]),
                    "end_time": _seconds_label(entry["end_time"]),
                    "created_at": entry["created_at"],
                }
                for entry in entries
            ]
        else:
            fieldnames = [
                "source_text",
                "learning_text",
                "video_title",
                "start_time",
                "end_time",
                "created_at",
            ]
            rows = [
                {
                    "source_text": entry["source_text"],
                    "learning_text": entry["learning_text"],
                    "video_title": entry["video_title"],
                    "start_time": _seconds_label(entry["start_time"]),
                    "end_time": _seconds_label(entry["end_time"]),
                    "created_at": entry["created_at"],
                }
                for entry in entries
            ]

        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return Response(content=buffer.getvalue(), media_type="text/csv", headers=_download_headers(base_name))

    if extension == "md":
        lines = [
            f"# {notebook['name']}",
            "",
            f"- 类型: {'词语收集册' if notebook['type'] == 'word' else '句子收集册'}",
            f"- 条目数: {notebook['entry_count']}",
            f"- 源语言: {notebook.get('source_lang') or '未设置'}",
            f"- 学习语言: {notebook.get('learning_lang') or '未设置'}",
            f"- 母语: {notebook.get('native_lang') or '未设置'}",
            "",
        ]
        if notebook.get("description"):
            lines.extend([notebook["description"], ""])

        for index, entry in enumerate(entries, start=1):
            if notebook["type"] == "word":
                lines.extend(
                    [
                        f"## {index}. {entry['word']}",
                        "",
                        f"- 释义: {entry['meaning'] or '未填写'}",
                        f"- 备注: {entry['note'] or '未填写'}",
                        f"- 原句: {entry['source_sentence'] or '未填写'}",
                        f"- 学习语言句子: {entry['learning_sentence'] or '未填写'}",
                        f"- 视频: {entry['video_title'] or '未记录'}",
                        f"- 时间: {_seconds_label(entry['start_time'])} ~ {_seconds_label(entry['end_time'])}",
                        "",
                    ]
                )
            else:
                lines.extend(
                    [
                        f"## {index}. 句子",
                        "",
                        f"- 原句: {entry['source_text'] or '未填写'}",
                        f"- 学习语言句子: {entry['learning_text'] or '未填写'}",
                        f"- 视频: {entry['video_title'] or '未记录'}",
                        f"- 时间: {_seconds_label(entry['start_time'])} ~ {_seconds_label(entry['end_time'])}",
                        "",
                    ]
                )
                analysis_payload = entry.get("analysis_payload") or {}
                if analysis_payload:
                    lines.extend(
                        [
                            f"  - 优化译文: {analysis_payload.get('improved_translation') or '未生成'}",
                            f"  - 句子结构: {analysis_payload.get('structure_explanation') or '未生成'}",
                            "",
                        ]
                    )
        return Response(content="\n".join(lines), media_type="text/markdown", headers=_download_headers(base_name))

    if extension == "pdf":
        return Response(
            content=build_notebook_pdf(payload, pdf_options),
            media_type="application/pdf",
            headers=_download_headers(base_name),
        )

    raise HTTPException(status_code=400, detail="Unsupported export format.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/settings")
def read_settings() -> dict[str, Any]:
    return get_app_settings()


@app.put("/api/settings")
def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    return save_app_settings(payload)


@app.get("/api/runtime/status")
def read_runtime_status() -> dict[str, Any]:
    settings = get_app_settings()
    transcription = settings["transcription"]
    return get_runtime_status(
        current_model_size=str(transcription.get("model_size") or "base"),
        device_preference=str(transcription.get("device") or "cuda"),
        compute_type=str(transcription.get("compute_type") or "float16"),
    )


@app.post("/api/runtime/detect")
def detect_runtime_status() -> dict[str, Any]:
    return read_runtime_status()


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
    return {"videos": [_video_with_task(video) for video in list_library_items()]}


@app.get("/api/notebooks")
def read_notebooks() -> dict[str, Any]:
    return {"notebooks": list_notebooks()}


@app.post("/api/notebooks")
def create_notebook_route(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        notebook = create_notebook(payload)
    except ValueError as exc:
        raise _http_error_from_value_error(exc) from exc
    return {"notebook": notebook}


@app.patch("/api/notebooks/{notebook_id}")
def update_notebook_route(notebook_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        notebook = update_notebook(notebook_id, payload)
    except ValueError as exc:
        raise _http_error_from_value_error(exc) from exc
    return {"notebook": notebook}


@app.delete("/api/notebooks/{notebook_id}")
def delete_notebook_route(notebook_id: int) -> dict[str, Any]:
    notebook = delete_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail=f"Notebook id {notebook_id} not found.")
    return {"deleted": notebook}


@app.get("/api/notebooks/{notebook_id}/words")
def read_word_entries(notebook_id: int) -> dict[str, Any]:
    notebook = get_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail=f"Notebook id {notebook_id} not found.")
    try:
        entries = list_word_entries(notebook_id)
    except ValueError as exc:
        raise _http_error_from_value_error(exc) from exc
    return {"notebook": notebook, "entries": entries}


@app.post("/api/notebooks/{notebook_id}/words")
def create_word_entry_route(notebook_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        entry = add_word_entry(notebook_id, payload)
    except ValueError as exc:
        raise _http_error_from_value_error(exc) from exc
    return {"entry": entry}


@app.delete("/api/notebooks/{notebook_id}/words/{entry_id}")
def delete_word_entry_route(notebook_id: int, entry_id: int) -> dict[str, Any]:
    try:
        deleted = delete_word_entry(notebook_id, entry_id)
    except ValueError as exc:
        raise _http_error_from_value_error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Word entry id {entry_id} not found.")
    return {"deleted": deleted}


@app.get("/api/notebooks/{notebook_id}/sentences")
def read_sentence_entries(notebook_id: int) -> dict[str, Any]:
    notebook = get_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail=f"Notebook id {notebook_id} not found.")
    try:
        entries = list_sentence_entries(notebook_id)
    except ValueError as exc:
        raise _http_error_from_value_error(exc) from exc
    return {"notebook": notebook, "entries": entries}


@app.post("/api/notebooks/{notebook_id}/sentences")
def create_sentence_entry_route(notebook_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        entry = add_sentence_entry(notebook_id, payload)
    except ValueError as exc:
        raise _http_error_from_value_error(exc) from exc
    return {"entry": entry}


@app.delete("/api/notebooks/{notebook_id}/sentences/{entry_id}")
def delete_sentence_entry_route(notebook_id: int, entry_id: int) -> dict[str, Any]:
    try:
        deleted = delete_sentence_entry(notebook_id, entry_id)
    except ValueError as exc:
        raise _http_error_from_value_error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Sentence entry id {entry_id} not found.")
    return {"deleted": deleted}


@app.get("/api/notebooks/{notebook_id}/export")
def export_notebook(
    notebook_id: int,
    format: str = Query(default="json"),
    include_improved_translation: bool = Query(default=True),
    include_structure_explanation: bool = Query(default=True),
    include_learning_tip: bool = Query(default=True),
    include_keywords: bool = Query(default=True),
    include_grammar_points: bool = Query(default=True),
) -> Response:
    normalized_format = str(format or "json").strip().lower()
    pdf_options = None
    if normalized_format == "pdf":
        pdf_options = {
            "include_improved_translation": include_improved_translation,
            "include_structure_explanation": include_structure_explanation,
            "include_learning_tip": include_learning_tip,
            "include_keywords": include_keywords,
            "include_grammar_points": include_grammar_points,
        }
    return _notebook_export_response(notebook_id, normalized_format, pdf_options)


@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
    video = save_uploaded_video(file.filename, content)
    return {"video": video}


@app.delete("/api/videos/{video_id}")
def remove_video(video_id: int) -> dict[str, Any]:
    try:
        deleted = delete_video_item(video_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": deleted}


@app.get("/api/session")
def read_session(video_id: int | None = Query(default=None)) -> dict[str, Any]:
    sync_video_library()
    try:
        resolved_video_id = video_id or _first_video_id()
        session = get_video_session(resolved_video_id)
        session["video"] = _video_with_task(session["video"])
        session["task"] = session["video"]["active_task"]
        return session
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/tasks/{task_id}")
def read_task_status(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task id {task_id} not found.")
    return {"task": task}


def _run_full_video_processing(video_id: int, task_id: str) -> dict[str, Any]:
    settings = get_app_settings()
    try:
        session = get_video_session(video_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    video = session["video"]
    transcription_settings = settings["transcription"]
    translation_settings = settings["translation"]
    resolved_device, resolved_compute_type = resolve_transcription_runtime(
        device=transcription_settings["device"],
        compute_type=transcription_settings["compute_type"],
        language=translation_settings.get("source_lang"),
    )

    update_task(task_id, stage="transcribing", message="正在转写音频...")
    transcript = transcribe_video(
        video["path"],
        model_size=transcription_settings["model_size"],
        device=resolved_device,
        compute_type=resolved_compute_type,
        language=translation_settings.get("source_lang"),
    )
    actual_device = transcript.runtime_device or resolved_device
    actual_compute_type = transcript.runtime_compute_type or resolved_compute_type

    update_task(task_id, stage="saving_transcript", message="正在保存转写结果...")
    transcript_json_path, source_srt_path = save_transcript_outputs(
        transcript,
        get_transcripts_dir(),
    )

    update_task(task_id, stage="translating", message="正在翻译字幕...")
    translation_result = _translate_and_save_video(video=video, transcript=transcript, settings=settings)
    sync_artifacts_for_stem(Path(video["path"]).stem)

    update_task(task_id, stage="finalizing", message="正在整理视频会话数据...")
    return {
        "video_id": video_id,
        "mode": "full",
        "provider": translation_result["provider"],
        "source_lang": translation_result["source_lang"],
        "learning_lang": translation_result["learning_lang"],
        "native_lang": translation_result["native_lang"],
        "runtime_device": actual_device,
        "runtime_compute_type": actual_compute_type,
        "runtime_fallback_reason": transcript.fallback_reason,
        "transcript_json_path": str(transcript_json_path),
        "source_srt_path": str(source_srt_path),
        "en_srt_path": str(source_srt_path),
        "bilingual_json_path": translation_result["bilingual_json_path"],
        "learning_srt_path": translation_result["learning_srt_path"],
        "zh_srt_path": translation_result["zh_srt_path"],
        "bilingual_srt_path": translation_result["bilingual_srt_path"],
    }


def _run_translate_video_processing(video_id: int, task_id: str) -> dict[str, Any]:
    settings = get_app_settings()
    try:
        session = get_video_session(video_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    video = session["video"]
    if not video.get("transcript_json_path"):
        raise HTTPException(status_code=400, detail="This video has no transcript yet. Please run full processing first.")

    transcript_path = Path(video["transcript_json_path"])
    if not transcript_path.exists():
        raise HTTPException(status_code=400, detail="The saved transcript file is missing. Please run full processing first.")

    update_task(task_id, stage="loading_transcript", message="正在读取已保存的转写结果...")
    transcript = _load_transcript(str(transcript_path))

    update_task(task_id, stage="translating", message="正在翻译字幕...")
    translation_result = _translate_and_save_video(video=video, transcript=transcript, settings=settings)
    sync_artifacts_for_stem(Path(video["path"]).stem)

    update_task(task_id, stage="finalizing", message="正在整理视频会话数据...")
    return {
        "video_id": video_id,
        "mode": "translate_only",
        "provider": translation_result["provider"],
        "source_lang": translation_result["source_lang"],
        "learning_lang": translation_result["learning_lang"],
        "native_lang": translation_result["native_lang"],
        "transcript_json_path": str(transcript_path),
        "source_srt_path": _source_srt_output_path(video),
        "en_srt_path": _source_srt_output_path(video),
        "bilingual_json_path": translation_result["bilingual_json_path"],
        "learning_srt_path": translation_result["learning_srt_path"],
        "zh_srt_path": translation_result["zh_srt_path"],
        "bilingual_srt_path": translation_result["bilingual_srt_path"],
    }


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
    task, started = start_video_task(
        video_id,
        "full",
        lambda task_id: _run_full_video_processing(video_id, task_id),
    )
    return JSONResponse(content={"task": task, "started": started}, status_code=202 if started else 200)


@app.post("/api/videos/{video_id}/translate")
def translate_video(video_id: int) -> dict[str, Any]:
    task, started = start_video_task(
        video_id,
        "translate_only",
        lambda task_id: _run_translate_video_processing(video_id, task_id),
    )
    return JSONResponse(content={"task": task, "started": started}, status_code=202 if started else 200)


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
    source_text = _segment_source_text(segment)
    source_lang, learning_lang, native_lang = _segment_languages(payload, settings)
    study_text, study_lang, reference_text, reference_lang = _select_analysis_focus(
        segment=segment,
        source_lang=source_lang,
        learning_lang=learning_lang,
        native_lang=native_lang,
    )
    previous_text, next_text = _analysis_context(
        segments,
        index,
        source_lang=source_lang,
        learning_lang=learning_lang,
        native_lang=native_lang,
    )

    video_stem, cache_segment_id, cache_model, segment_hash = _analysis_cache_key(
        video["stem"],
        segment_id,
        resolved_model,
        f"{study_lang}\n{reference_lang}\n{study_text}\n{reference_text}",
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
        study_text=study_text,
        reference_translation=reference_text,
        source_text=source_text,
        model=resolved_model,
        base_url=analysis_profile["base_url"],
        api_key=analysis_profile["api_key"],
        api_style=analysis_profile.get("api_style", "chat_completions"),
        study_lang=study_lang,
        reference_lang=reference_lang,
        native_lang=native_lang,
        source_lang=source_lang,
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
    source_text = _segment_source_text(segment)
    source_lang, learning_lang, native_lang = _segment_languages(payload, settings)
    study_text, study_lang, reference_text, reference_lang = _select_analysis_focus(
        segment=segment,
        source_lang=source_lang,
        learning_lang=learning_lang,
        native_lang=native_lang,
    )
    previous_text, next_text = _analysis_context(
        segments,
        index,
        source_lang=source_lang,
        learning_lang=learning_lang,
        native_lang=native_lang,
    )

    video_stem, cache_segment_id, cache_model, segment_hash = _analysis_cache_key(
        video["stem"],
        segment_id,
        resolved_model,
        f"{study_lang}\n{reference_lang}\n{study_text}\n{reference_text}",
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
                study_text=study_text,
                reference_translation=reference_text,
                source_text=source_text,
                model=resolved_model,
                base_url=analysis_profile["base_url"],
                api_key=analysis_profile["api_key"],
                api_style=analysis_profile.get("api_style", "chat_completions"),
                study_lang=study_lang,
                reference_lang=reference_lang,
                native_lang=native_lang,
                source_lang=source_lang,
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


@app.get("/api/videos/{video_id}/exports/subtitles")
def export_subtitles(
    video_id: int,
    mode: str = Query(default="bilingual"),
) -> FileResponse:
    normalized_mode = str(mode or "bilingual").strip().lower()
    if normalized_mode not in {"source", "learning", "bilingual"}:
        raise HTTPException(status_code=400, detail="Unsupported subtitle export mode.")

    session = get_video_session(video_id)
    video = session["video"]
    transcript = _load_transcript(video["transcript_json_path"]) if video.get("transcript_json_path") else None
    payload = _load_bilingual_payload(video["bilingual_json_path"]) if video.get("bilingual_json_path") else None

    if normalized_mode != "source" and not payload:
        raise HTTPException(status_code=400, detail="This video has no translated subtitles yet.")

    segments = _build_export_segments(transcript, payload)
    if not segments:
        raise HTTPException(status_code=400, detail="This video has no subtitles to export yet.")

    export_path = ensure_subtitle_export(video["stem"], segments, normalized_mode)
    return FileResponse(
        export_path,
        media_type="application/x-subrip",
        filename=_download_name(video, export_path),
    )


@app.get("/api/videos/{video_id}/tracks/{mode}.vtt")
def video_subtitle_track(video_id: int, mode: str) -> PlainTextResponse:
    normalized_mode = str(mode or "bilingual").strip().lower()
    if normalized_mode not in {"source", "learning", "bilingual"}:
        raise HTTPException(status_code=400, detail="Unsupported subtitle track mode.")

    session = get_video_session(video_id)
    video = session["video"]
    transcript = _load_transcript(video["transcript_json_path"]) if video.get("transcript_json_path") else None
    payload = _load_bilingual_payload(video["bilingual_json_path"]) if video.get("bilingual_json_path") else None

    if normalized_mode != "source" and not payload:
        raise HTTPException(status_code=400, detail="This video has no translated subtitles yet.")

    segments = _build_export_segments(transcript, payload)
    if not segments:
        raise HTTPException(status_code=400, detail="This video has no subtitles yet.")

    return PlainTextResponse(compose_vtt(segments, normalized_mode), media_type="text/vtt")


@app.get("/api/videos/{video_id}/exports/video")
def export_video(
    video_id: int,
    subtitle_mode: str = Query(default="bilingual"),
    video_mode: str = Query(default="soft"),
) -> FileResponse:
    normalized_subtitle_mode = str(subtitle_mode or "bilingual").strip().lower()
    normalized_video_mode = str(video_mode or "soft").strip().lower()
    if normalized_subtitle_mode not in {"source", "learning", "bilingual"}:
        raise HTTPException(status_code=400, detail="Unsupported subtitle mode.")
    if normalized_video_mode not in {"soft", "burned"}:
        raise HTTPException(status_code=400, detail="Unsupported video export mode.")

    session = get_video_session(video_id)
    video = session["video"]
    transcript = _load_transcript(video["transcript_json_path"]) if video.get("transcript_json_path") else None
    payload = _load_bilingual_payload(video["bilingual_json_path"]) if video.get("bilingual_json_path") else None

    if normalized_subtitle_mode != "source" and not payload:
        raise HTTPException(status_code=400, detail="This video has no translated subtitles yet.")

    segments = _build_export_segments(transcript, payload)
    if not segments:
        raise HTTPException(status_code=400, detail="This video has no subtitles to export yet.")

    export_path = export_video_with_subtitles(
        source_video_path=video["path"],
        stem=video["stem"],
        bilingual_segments=segments,
        subtitle_mode=normalized_subtitle_mode,
        video_mode=normalized_video_mode,
    )
    return FileResponse(
        export_path,
        media_type="video/mp4",
        filename=_download_name(video, export_path),
    )
