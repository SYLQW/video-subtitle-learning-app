from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.services.transcription import _transcribe_video_once, transcript_to_dict


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python -m backend.app.services.transcription_worker <request.json> <result.json>", file=sys.stderr)
        return 2

    request_path = Path(sys.argv[1]).expanduser().resolve()
    result_path = Path(sys.argv[2]).expanduser().resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))

    result = _transcribe_video_once(
        video_path=request["video_path"],
        model_size=request.get("model_size", "base"),
        device=request.get("device", "cpu"),
        compute_type=request.get("compute_type", "int8"),
        beam_size=int(request.get("beam_size", 5)),
        vad_filter=bool(request.get("vad_filter", True)),
        word_timestamps=bool(request.get("word_timestamps", True)),
        language=request.get("language"),
    )

    result_path.write_text(
        json.dumps(transcript_to_dict(result), ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
