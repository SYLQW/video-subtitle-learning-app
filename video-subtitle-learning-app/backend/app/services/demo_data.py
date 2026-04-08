from __future__ import annotations

import hashlib
from pathlib import Path

from backend.app.services.app_paths import get_analysis_output_dir


def get_analysis_cache_path(source_path: str, segment_id: int, model_name: str, segment_text: str) -> Path:
    analysis_cache_dir = get_analysis_output_dir()
    analysis_cache_dir.mkdir(parents=True, exist_ok=True)
    source_stem = Path(source_path).stem
    safe_model = model_name.replace("/", "-")
    text_hash = hashlib.sha1(segment_text.encode("utf-8")).hexdigest()[:10]
    return analysis_cache_dir / f"{source_stem}.segment-{segment_id}.{text_hash}.{safe_model}.analysis.json"
