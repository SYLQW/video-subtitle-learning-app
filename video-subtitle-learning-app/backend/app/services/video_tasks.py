from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any, Callable
from uuid import uuid4


RUNNING_STATUSES = {"queued", "running"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VideoTask:
    id: str
    video_id: int
    mode: str
    status: str = "queued"
    stage: str = "queued"
    message: str = ""
    error: str = ""
    result: dict[str, Any] | None = None
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = field(default_factory=_utc_now)


_lock = Lock()
_tasks_by_id: dict[str, VideoTask] = {}
_active_task_by_video: dict[int, str] = {}


def _serialize_task(task: VideoTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "video_id": task.video_id,
        "mode": task.mode,
        "status": task.status,
        "stage": task.stage,
        "message": task.message,
        "error": task.error,
        "result": task.result,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "updated_at": task.updated_at,
    }


def _active_task_locked(video_id: int) -> VideoTask | None:
    task_id = _active_task_by_video.get(video_id)
    if not task_id:
        return None

    task = _tasks_by_id.get(task_id)
    if task and task.status in RUNNING_STATUSES:
        return task

    _active_task_by_video.pop(video_id, None)
    return None


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        task = _tasks_by_id.get(task_id)
        return _serialize_task(task) if task else None


def get_active_task_for_video(video_id: int) -> dict[str, Any] | None:
    with _lock:
        task = _active_task_locked(video_id)
        return _serialize_task(task) if task else None


def update_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    with _lock:
        task = _tasks_by_id.get(task_id)
        if not task:
            return None

        for name, value in fields.items():
            if hasattr(task, name):
                setattr(task, name, value)

        task.updated_at = _utc_now()
        return _serialize_task(task)


def _finish_task(task_id: str, *, status: str, stage: str, message: str, error: str = "", result: dict[str, Any] | None = None) -> None:
    with _lock:
        task = _tasks_by_id.get(task_id)
        if not task:
            return

        task.status = status
        task.stage = stage
        task.message = message
        task.error = error
        task.result = result
        task.finished_at = _utc_now()
        task.updated_at = task.finished_at
        if _active_task_by_video.get(task.video_id) == task_id:
            _active_task_by_video.pop(task.video_id, None)


def _run_task(task_id: str, runner: Callable[[str], dict[str, Any]]) -> None:
    update_task(
        task_id,
        status="running",
        started_at=_utc_now(),
        stage="starting",
        message="任务已启动。",
        error="",
    )
    try:
        result = runner(task_id)
    except Exception as exc:  # noqa: BLE001
        _finish_task(
            task_id,
            status="failed",
            stage="failed",
            message="处理失败。",
            error=str(exc),
        )
        return

    _finish_task(
        task_id,
        status="completed",
        stage="completed",
        message="处理完成。",
        result=result,
    )


def start_video_task(video_id: int, mode: str, runner: Callable[[str], dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    with _lock:
        existing = _active_task_locked(video_id)
        if existing:
            return _serialize_task(existing), False

        task = VideoTask(
            id=uuid4().hex,
            video_id=video_id,
            mode=mode,
            message="任务已排队。",
        )
        _tasks_by_id[task.id] = task
        _active_task_by_video[video_id] = task.id

    thread = Thread(target=_run_task, args=(task.id, runner), daemon=True)
    thread.start()
    return _serialize_task(task), True
