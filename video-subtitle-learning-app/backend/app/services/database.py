from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
LIBRARY_VIDEO_DIR = DATA_DIR / "videos"
DB_PATH = DATA_DIR / "app.sqlite3"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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

            CREATE TABLE IF NOT EXISTS notebooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('word', 'sentence')),
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                source_lang TEXT,
                learning_lang TEXT,
                native_lang TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS word_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notebook_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                meaning TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                source_sentence TEXT NOT NULL DEFAULT '',
                learning_sentence TEXT NOT NULL DEFAULT '',
                source_lang TEXT,
                learning_lang TEXT,
                native_lang TEXT,
                segment_id INTEGER,
                video_id INTEGER,
                video_stem TEXT,
                video_title TEXT NOT NULL DEFAULT '',
                start_time REAL,
                end_time REAL,
                analysis_model TEXT NOT NULL DEFAULT '',
                analysis_payload_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sentence_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notebook_id INTEGER NOT NULL,
                source_text TEXT NOT NULL DEFAULT '',
                learning_text TEXT NOT NULL DEFAULT '',
                source_lang TEXT,
                learning_lang TEXT,
                native_lang TEXT,
                segment_id INTEGER,
                video_id INTEGER,
                video_stem TEXT,
                video_title TEXT NOT NULL DEFAULT '',
                start_time REAL,
                end_time REAL,
                analysis_model TEXT NOT NULL DEFAULT '',
                analysis_payload_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
            );
            """
        )


def _loads_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def _stringify_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _normalize_notebook_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {"word", "sentence"}:
        raise ValueError("Notebook type must be 'word' or 'sentence'.")
    return normalized


def _touch_notebook(connection: sqlite3.Connection, notebook_id: int) -> None:
    connection.execute(
        "UPDATE notebooks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (notebook_id,),
    )


def _ensure_notebook(connection: sqlite3.Connection, notebook_id: int, expected_type: str | None = None) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
    if not row:
        raise ValueError(f"Notebook id {notebook_id} not found.")
    notebook = dict(row)
    if expected_type and notebook["type"] != expected_type:
        raise ValueError(f"Notebook id {notebook_id} is not a {expected_type} notebook.")
    return notebook


def _parse_word_entry(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["analysis_payload"] = _loads_json(payload.pop("analysis_payload_json", None))
    return payload


def _parse_sentence_entry(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["analysis_payload"] = _loads_json(payload.pop("analysis_payload_json", None))
    return payload


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


def delete_video(video_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                videos.id,
                videos.stem,
                videos.title,
                videos.path,
                videos.source
            FROM videos
            WHERE videos.id = ?
            """,
            (video_id,),
        ).fetchone()
        if not row:
            return None

        video = dict(row)
        connection.execute("DELETE FROM analysis_cache WHERE video_stem = ?", (video["stem"],))
        connection.execute("DELETE FROM artifacts WHERE video_stem = ?", (video["stem"],))
        connection.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        return video


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


def list_notebooks() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                notebooks.*,
                CASE
                    WHEN notebooks.type = 'word'
                        THEN (SELECT COUNT(*) FROM word_entries WHERE word_entries.notebook_id = notebooks.id)
                    ELSE (SELECT COUNT(*) FROM sentence_entries WHERE sentence_entries.notebook_id = notebooks.id)
                END AS entry_count
            FROM notebooks
            ORDER BY notebooks.type ASC, notebooks.updated_at DESC, notebooks.id DESC
            """
        ).fetchall()
    return _rows_to_dicts(rows)


def get_notebook(notebook_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                notebooks.*,
                CASE
                    WHEN notebooks.type = 'word'
                        THEN (SELECT COUNT(*) FROM word_entries WHERE word_entries.notebook_id = notebooks.id)
                    ELSE (SELECT COUNT(*) FROM sentence_entries WHERE sentence_entries.notebook_id = notebooks.id)
                END AS entry_count
            FROM notebooks
            WHERE notebooks.id = ?
            """,
            (notebook_id,),
        ).fetchone()
    return _row_to_dict(row)


def create_notebook(payload: dict[str, Any]) -> dict[str, Any]:
    notebook_type = _normalize_notebook_type(str(payload.get("type") or ""))
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Notebook name is required.")

    description = str(payload.get("description") or "").strip()
    source_lang = str(payload.get("source_lang") or "").strip() or None
    learning_lang = str(payload.get("learning_lang") or "").strip() or None
    native_lang = str(payload.get("native_lang") or "").strip() or None

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO notebooks (
                type,
                name,
                description,
                source_lang,
                learning_lang,
                native_lang,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (notebook_type, name, description, source_lang, learning_lang, native_lang),
        )
        notebook_id = int(cursor.lastrowid)
    notebook = get_notebook(notebook_id)
    if not notebook:
        raise ValueError("Failed to create notebook.")
    return notebook


def update_notebook(notebook_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    updates: list[str] = []
    values: list[Any] = []

    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Notebook name is required.")
        updates.append("name = ?")
        values.append(name)
    if "description" in payload:
        updates.append("description = ?")
        values.append(str(payload.get("description") or "").strip())
    if "source_lang" in payload:
        updates.append("source_lang = ?")
        values.append(str(payload.get("source_lang") or "").strip() or None)
    if "learning_lang" in payload:
        updates.append("learning_lang = ?")
        values.append(str(payload.get("learning_lang") or "").strip() or None)
    if "native_lang" in payload:
        updates.append("native_lang = ?")
        values.append(str(payload.get("native_lang") or "").strip() or None)

    if not updates:
        notebook = get_notebook(notebook_id)
        if not notebook:
            raise ValueError(f"Notebook id {notebook_id} not found.")
        return notebook

    with get_connection() as connection:
        _ensure_notebook(connection, notebook_id)
        connection.execute(
            f"""
            UPDATE notebooks
            SET {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (*values, notebook_id),
        )
    notebook = get_notebook(notebook_id)
    if not notebook:
        raise ValueError(f"Notebook id {notebook_id} not found.")
    return notebook


def delete_notebook(notebook_id: int) -> dict[str, Any] | None:
    notebook = get_notebook(notebook_id)
    if not notebook:
        return None
    with get_connection() as connection:
        connection.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
    return notebook


def list_word_entries(notebook_id: int) -> list[dict[str, Any]]:
    with get_connection() as connection:
        _ensure_notebook(connection, notebook_id, "word")
        rows = connection.execute(
            """
            SELECT *
            FROM word_entries
            WHERE notebook_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (notebook_id,),
        ).fetchall()
    return [_parse_word_entry(row) for row in rows]


def list_sentence_entries(notebook_id: int) -> list[dict[str, Any]]:
    with get_connection() as connection:
        _ensure_notebook(connection, notebook_id, "sentence")
        rows = connection.execute(
            """
            SELECT *
            FROM sentence_entries
            WHERE notebook_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (notebook_id,),
        ).fetchall()
    return [_parse_sentence_entry(row) for row in rows]


def add_word_entry(notebook_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    word = str(payload.get("word") or "").strip()
    if not word:
        raise ValueError("Word is required.")

    source_sentence = str(payload.get("source_sentence") or "").strip()
    video_id = payload.get("video_id")
    meaning = str(payload.get("meaning") or "").strip()
    note = str(payload.get("note") or "").strip()
    learning_sentence = str(payload.get("learning_sentence") or "").strip()
    source_lang = str(payload.get("source_lang") or "").strip() or None
    learning_lang = str(payload.get("learning_lang") or "").strip() or None
    native_lang = str(payload.get("native_lang") or "").strip() or None
    video_stem = str(payload.get("video_stem") or "").strip() or None
    video_title = str(payload.get("video_title") or "").strip()
    analysis_model = str(payload.get("analysis_model") or "").strip()
    analysis_payload_json = _stringify_json(payload.get("analysis_payload"))

    with get_connection() as connection:
        notebook = _ensure_notebook(connection, notebook_id, "word")
        duplicate = connection.execute(
            """
            SELECT id
            FROM word_entries
            WHERE notebook_id = ?
              AND word = ?
              AND ifnull(source_sentence, '') = ifnull(?, '')
              AND ifnull(video_id, -1) = ifnull(?, -1)
            """,
            (notebook_id, word, source_sentence, video_id),
        ).fetchone()
        if duplicate:
            entry_id = int(duplicate["id"])
            connection.execute(
                """
                UPDATE word_entries
                SET
                    meaning = CASE WHEN ? <> '' THEN ? ELSE meaning END,
                    note = CASE WHEN ? <> '' THEN ? ELSE note END,
                    source_sentence = CASE WHEN ? <> '' THEN ? ELSE source_sentence END,
                    learning_sentence = CASE WHEN ? <> '' THEN ? ELSE learning_sentence END,
                    source_lang = COALESCE(?, source_lang),
                    learning_lang = COALESCE(?, learning_lang),
                    native_lang = COALESCE(?, native_lang),
                    segment_id = COALESCE(?, segment_id),
                    video_id = COALESCE(?, video_id),
                    video_stem = COALESCE(?, video_stem),
                    video_title = CASE WHEN ? <> '' THEN ? ELSE video_title END,
                    start_time = COALESCE(?, start_time),
                    end_time = COALESCE(?, end_time),
                    analysis_model = CASE WHEN ? <> '' THEN ? ELSE analysis_model END,
                    analysis_payload_json = COALESCE(?, analysis_payload_json),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    meaning,
                    meaning,
                    note,
                    note,
                    source_sentence,
                    source_sentence,
                    learning_sentence,
                    learning_sentence,
                    source_lang or notebook.get("source_lang"),
                    learning_lang or notebook.get("learning_lang"),
                    native_lang or notebook.get("native_lang"),
                    payload.get("segment_id"),
                    video_id,
                    video_stem,
                    video_title,
                    video_title,
                    payload.get("start_time"),
                    payload.get("end_time"),
                    analysis_model,
                    analysis_model,
                    analysis_payload_json,
                    entry_id,
                ),
            )
            _touch_notebook(connection, notebook_id)
            row = connection.execute("SELECT * FROM word_entries WHERE id = ?", (entry_id,)).fetchone()
            if not row:
                raise ValueError("Failed to load duplicated word entry.")
            entry = _parse_word_entry(row)
            entry["duplicate"] = True
            return entry

        cursor = connection.execute(
            """
            INSERT INTO word_entries (
                notebook_id,
                word,
                meaning,
                note,
                source_sentence,
                learning_sentence,
                source_lang,
                learning_lang,
                native_lang,
                segment_id,
                video_id,
                video_stem,
                video_title,
                start_time,
                end_time,
                analysis_model,
                analysis_payload_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                notebook_id,
                word,
                meaning,
                note,
                source_sentence,
                learning_sentence,
                source_lang or str(notebook.get("source_lang") or "").strip() or None,
                learning_lang or str(notebook.get("learning_lang") or "").strip() or None,
                native_lang or str(notebook.get("native_lang") or "").strip() or None,
                payload.get("segment_id"),
                video_id,
                video_stem,
                video_title,
                payload.get("start_time"),
                payload.get("end_time"),
                analysis_model,
                analysis_payload_json,
            ),
        )
        entry_id = int(cursor.lastrowid)
        _touch_notebook(connection, notebook_id)
        row = connection.execute("SELECT * FROM word_entries WHERE id = ?", (entry_id,)).fetchone()

    if not row:
        raise ValueError("Failed to create word entry.")
    entry = _parse_word_entry(row)
    entry["duplicate"] = False
    return entry


def add_sentence_entry(notebook_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    source_text = str(payload.get("source_text") or "").strip()
    learning_text = str(payload.get("learning_text") or "").strip()
    if not source_text and not learning_text:
        raise ValueError("Sentence text is required.")

    video_id = payload.get("video_id")
    segment_id = payload.get("segment_id")
    source_lang = str(payload.get("source_lang") or "").strip() or None
    learning_lang = str(payload.get("learning_lang") or "").strip() or None
    native_lang = str(payload.get("native_lang") or "").strip() or None
    video_stem = str(payload.get("video_stem") or "").strip() or None
    video_title = str(payload.get("video_title") or "").strip()
    analysis_model = str(payload.get("analysis_model") or "").strip()
    analysis_payload_json = _stringify_json(payload.get("analysis_payload"))

    with get_connection() as connection:
        notebook = _ensure_notebook(connection, notebook_id, "sentence")
        duplicate = connection.execute(
            """
            SELECT id
            FROM sentence_entries
            WHERE notebook_id = ?
              AND ifnull(segment_id, -1) = ifnull(?, -1)
              AND ifnull(video_id, -1) = ifnull(?, -1)
            """,
            (notebook_id, segment_id, video_id),
        ).fetchone()
        if duplicate:
            entry_id = int(duplicate["id"])
            connection.execute(
                """
                UPDATE sentence_entries
                SET
                    source_text = CASE WHEN ? <> '' THEN ? ELSE source_text END,
                    learning_text = CASE WHEN ? <> '' THEN ? ELSE learning_text END,
                    source_lang = COALESCE(?, source_lang),
                    learning_lang = COALESCE(?, learning_lang),
                    native_lang = COALESCE(?, native_lang),
                    video_stem = COALESCE(?, video_stem),
                    video_title = CASE WHEN ? <> '' THEN ? ELSE video_title END,
                    start_time = COALESCE(?, start_time),
                    end_time = COALESCE(?, end_time),
                    analysis_model = CASE WHEN ? <> '' THEN ? ELSE analysis_model END,
                    analysis_payload_json = COALESCE(?, analysis_payload_json),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    source_text,
                    source_text,
                    learning_text,
                    learning_text,
                    source_lang or notebook.get("source_lang"),
                    learning_lang or notebook.get("learning_lang"),
                    native_lang or notebook.get("native_lang"),
                    video_stem,
                    video_title,
                    video_title,
                    payload.get("start_time"),
                    payload.get("end_time"),
                    analysis_model,
                    analysis_model,
                    analysis_payload_json,
                    entry_id,
                ),
            )
            _touch_notebook(connection, notebook_id)
            row = connection.execute("SELECT * FROM sentence_entries WHERE id = ?", (entry_id,)).fetchone()
            if not row:
                raise ValueError("Failed to load duplicated sentence entry.")
            entry = _parse_sentence_entry(row)
            entry["duplicate"] = True
            return entry

        cursor = connection.execute(
            """
            INSERT INTO sentence_entries (
                notebook_id,
                source_text,
                learning_text,
                source_lang,
                learning_lang,
                native_lang,
                segment_id,
                video_id,
                video_stem,
                video_title,
                start_time,
                end_time,
                analysis_model,
                analysis_payload_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                notebook_id,
                source_text,
                learning_text,
                source_lang or str(notebook.get("source_lang") or "").strip() or None,
                learning_lang or str(notebook.get("learning_lang") or "").strip() or None,
                native_lang or str(notebook.get("native_lang") or "").strip() or None,
                segment_id,
                video_id,
                video_stem,
                video_title,
                payload.get("start_time"),
                payload.get("end_time"),
                analysis_model,
                analysis_payload_json,
            ),
        )
        entry_id = int(cursor.lastrowid)
        _touch_notebook(connection, notebook_id)
        row = connection.execute("SELECT * FROM sentence_entries WHERE id = ?", (entry_id,)).fetchone()

    if not row:
        raise ValueError("Failed to create sentence entry.")
    entry = _parse_sentence_entry(row)
    entry["duplicate"] = False
    return entry


def delete_word_entry(notebook_id: int, entry_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        _ensure_notebook(connection, notebook_id, "word")
        row = connection.execute(
            "SELECT * FROM word_entries WHERE id = ? AND notebook_id = ?",
            (entry_id, notebook_id),
        ).fetchone()
        if not row:
            return None
        connection.execute("DELETE FROM word_entries WHERE id = ? AND notebook_id = ?", (entry_id, notebook_id))
        _touch_notebook(connection, notebook_id)
    return _parse_word_entry(row)


def delete_sentence_entry(notebook_id: int, entry_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        _ensure_notebook(connection, notebook_id, "sentence")
        row = connection.execute(
            "SELECT * FROM sentence_entries WHERE id = ? AND notebook_id = ?",
            (entry_id, notebook_id),
        ).fetchone()
        if not row:
            return None
        connection.execute("DELETE FROM sentence_entries WHERE id = ? AND notebook_id = ?", (entry_id, notebook_id))
        _touch_notebook(connection, notebook_id)
    return _parse_sentence_entry(row)


def get_notebook_export_payload(notebook_id: int) -> dict[str, Any] | None:
    notebook = get_notebook(notebook_id)
    if not notebook:
        return None
    if notebook["type"] == "word":
        entries = list_word_entries(notebook_id)
    else:
        entries = list_sentence_entries(notebook_id)
    return {
        "notebook": notebook,
        "entries": entries,
    }
