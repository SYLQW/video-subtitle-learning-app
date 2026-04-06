from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.analysis import analyze_sentence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sentence analysis on one bilingual subtitle segment.")
    parser.add_argument("bilingual_json", type=Path, help="Path to *.bilingual.json")
    parser.add_argument("--segment-id", type=int, default=1, help="Subtitle segment id to analyze")
    parser.add_argument("--model", default="qwen3.6-plus", help="Model for advanced translation / sentence analysis")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.base_url or not args.api_key:
        raise SystemExit("Missing --base-url/--api-key or OPENAI_BASE_URL/OPENAI_API_KEY.")

    data = json.loads(args.bilingual_json.read_text(encoding="utf-8"))
    segments = data["bilingual_segments"]
    index = args.segment_id - 1
    segment = segments[index]
    previous_text = segments[index - 1]["en"] if index > 0 else ""
    next_text = segments[index + 1]["en"] if index + 1 < len(segments) else ""

    result = analyze_sentence(
        text=segment["en"],
        existing_translation=segment["zh"],
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        previous_text=previous_text,
        next_text=next_text,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

