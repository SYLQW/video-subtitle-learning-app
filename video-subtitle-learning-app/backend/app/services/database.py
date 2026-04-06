from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
LIBRARY_VIDEO_DIR = DATA_DIR / "videos"
DB_PATH = DATA_DIR / "app.sqlite3"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stem TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL DEFAULT 'library',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                video_stem TEXT PRIMARY KEY,
                transcript_json_path TEXT,
                en_srt_path TEXT,
                bilingual_json_path TEXT,
                zh_srt_path TEXT,
                bilingual_srt_path TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS analysis_cache (
                video_stem TEXT NOT NULL,
                segment_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                segment_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (video_stem, segment_id, model_name, segment_hash)
            );
            """
        )


def get_setting_json(key: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return json.loads(row["value_json"])


def upsert_setting_json(key: str, payload: dict[str, Any]) -> None:
    value_json = json.dumps(payload, ensure_ascii=False)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value_json),
        )


def upsert_video(path: str, title: str, source: str = "library") -> int:
    stem = Path(path).stem
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO videos (stem, title, path, source, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(path) DO UPDATE SET
                title = excluded.title,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (stem, title, path, source),
        )
        row = connection.execute("SELECT id FROM videos WHERE path = ?", (path,)).fetchone()
    return int(row["id"])


def list_videos() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                videos.id,
                videos.stem,
                videos.title,
                videos.path,
                videos.source,
                videos.updated_at,
                artifacts.transcript_json_path,
                artifacts.bilingual_json_path
            FROM videos
            LEFT JOIN artifacts ON artifacts.video_stem = videos.stem
            ORDER BY videos.updated_at DESC, videos.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_video(video_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                videos.id,
                videos.stem,
                videos.title,
                videos.path,
                videos.source,
                videos.updated_at,
                artifacts.transcript_json_path,
                artifacts.en_srt_path,
                artifacts.bilingual_json_path,
                artifacts.zh_srt_path,
                artifacts.bilingual_srt_path
            FROM videos
            LEFT JOIN artifacts ON artifacts.video_stem = videos.stem
            WHERE videos.id = ?
            """,
            (video_id,),
        ).fetchone()
    return dict(row) if row else None


def upsert_artifact(video_stem: str, **paths: str | None) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO artifacts (
                video_stem,
                transcript_json_path,
                en_srt_path,
                bilingual_json_path,
                zh_srt_path,
                bilingual_srt_path,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_stem) DO UPDATE SET
                transcript_json_path = excluded.transcript_json_path,
                en_srt_path = excluded.en_srt_path,
                bilingual_json_path = excluded.bilingual_json_path,
                zh_srt_path = excluded.zh_srt_path,
                bilingual_srt_path = excluded.bilingual_srt_path,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                video_stem,
                paths.get("transcript_json_path"),
                paths.get("en_srt_path"),
                paths.get("bilingual_json_path"),
                paths.get("zh_srt_path"),
                paths.get("bilingual_srt_path"),
            ),
        )


def get_analysis_cache(
    *,
    video_stem: str,
    segment_id: int,
    model_name: str,
    segment_hash: str,
) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT payload_json
            FROM analysis_cache
            WHERE video_stem = ? AND segment_id = ? AND model_name = ? AND segment_hash = ?
            """,
            (video_stem, segment_id, model_name, segment_hash),
        ).fetchone()
    if not row:
        return None
    return json.loads(row["payload_json"])


def upsert_analysis_cache(
    *,
    video_stem: str,
    segment_id: int,
    model_name: str,
    segment_hash: str,
    payload: dict[str, Any],
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO analysis_cache (video_stem, segment_id, model_name, segment_hash, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_stem, segment_id, model_name, segment_hash) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (video_stem, segment_id, model_name, segment_hash, json.dumps(payload, ensure_ascii=False)),
        )

