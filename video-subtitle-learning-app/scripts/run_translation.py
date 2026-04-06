from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.transcription import TranscriptResult, TranscriptSegment
from backend.app.services.translation import (
    TranslationConfig,
    save_bilingual_outputs,
    translate_transcript_segments,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate transcript JSON into bilingual subtitle data.")
    parser.add_argument("transcript_json", type=Path, help="Path to *.transcript.json output.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs") / "translations")
    parser.add_argument("--model", default="qwen-turbo")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--batch-size", type=int, default=12)
    return parser.parse_args()


def load_transcript(path: Path) -> TranscriptResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    return TranscriptResult(
        source_path=data["source_path"],
        model_size=data["model_size"],
        language=data.get("language"),
        language_probability=data.get("language_probability"),
        duration_seconds=data.get("duration_seconds"),
        segments=[TranscriptSegment(**segment) for segment in data["segments"]],
    )


def main() -> None:
    args = parse_args()
    if not args.base_url or not args.api_key:
        raise SystemExit("Missing --base-url/--api-key or OPENAI_BASE_URL/OPENAI_API_KEY.")

    transcript = load_transcript(args.transcript_json.resolve())
    config = TranslationConfig(base_url=args.base_url, api_key=args.api_key, model=args.model)
    bilingual_segments = translate_transcript_segments(
        transcript=transcript,
        config=config,
        batch_size=args.batch_size,
    )
    output_path, zh_srt_path, bilingual_srt_path = save_bilingual_outputs(
        transcript,
        bilingual_segments,
        args.output_dir,
    )

    print(f"segments={len(bilingual_segments)}")
    print(f"output={output_path}")
    print(f"zh_srt={zh_srt_path}")
    print(f"bilingual_srt={bilingual_srt_path}")
    for item in bilingual_segments[:3]:
        print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    main()
