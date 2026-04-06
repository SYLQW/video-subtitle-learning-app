from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _configure_windows_gpu_runtime() -> None:
    if os.name != "nt":
        return

    candidate_dirs: list[Path] = []

    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path:
        candidate_dirs.extend(
            [
                Path(cuda_path) / "bin",
                Path(cuda_path) / "libnvvp",
            ]
        )

    cudnn_path = os.environ.get("CUDNN_PATH")
    if cudnn_path:
        candidate_dirs.extend(
            [
                Path(cudnn_path) / "bin",
                Path(cudnn_path),
            ]
        )

    for drive in [Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"]:
        if not drive.exists():
            continue
        candidate_dirs.extend((drive / "NVIDIA GPU Computing Toolkit" / "CUDA").glob("v*\\bin"))
        candidate_dirs.extend((drive / "NVIDIA" / "CUDNN").glob("v*\\bin\\*\\x64"))
        candidate_dirs.extend((drive / "NVIDIA" / "CUDNN").glob("v*\\bin"))

    existing_dirs: list[str] = []
    seen: set[str] = set()
    for path in candidate_dirs:
        resolved = str(path.resolve()) if path.exists() else None
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        existing_dirs.append(resolved)

    if not existing_dirs:
        return

    os.environ["PATH"] = os.pathsep.join(existing_dirs + [os.environ.get("PATH", "")])

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        for directory in existing_dirs:
            add_dll_directory(directory)


_configure_windows_gpu_runtime()

from backend.app.services.transcription import save_transcript_outputs, transcribe_video


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe a local video with faster-whisper.")
    parser.add_argument("video_path", type=Path, help="Path to the source video file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs") / "transcripts",
        help="Directory for transcript outputs.",
    )
    parser.add_argument("--model-size", default="small.en", help="Whisper model size.")
    parser.add_argument("--device", default="cuda", help="Inference device, e.g. cuda or cpu.")
    parser.add_argument(
        "--compute-type",
        default="float16",
        help="CTranslate2 compute type, e.g. float16, int8_float16, int8.",
    )
    parser.add_argument("--beam-size", type=int, default=5, help="Beam size for decoding.")
    parser.add_argument(
        "--no-vad-filter",
        action="store_true",
        help="Disable VAD filtering during transcription.",
    )
    parser.add_argument(
        "--no-word-timestamps",
        action="store_true",
        help="Disable word timestamps during transcription.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = transcribe_video(
        video_path=args.video_path,
        model_size=args.model_size,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        vad_filter=not args.no_vad_filter,
        word_timestamps=not args.no_word_timestamps,
    )
    json_path, srt_path = save_transcript_outputs(result, args.output_dir)

    print(f"language={result.language} probability={result.language_probability}")
    print(f"segments={len(result.segments)}")
    print(f"json={json_path}")
    print(f"srt={srt_path}")


if __name__ == "__main__":
    main()
