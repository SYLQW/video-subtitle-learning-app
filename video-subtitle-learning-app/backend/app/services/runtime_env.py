from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

from backend.app.services.app_paths import (
    get_app_root,
    get_ffmpeg_dir,
    get_ffmpeg_executable,
    get_ffprobe_executable,
    get_model_root,
    is_portable_mode,
)
from backend.app.services.transcription import resolve_local_model_path


def _command_version(command: str) -> tuple[bool, str | None, str]:
    executable = shutil.which(command) if Path(command).name == command else command
    if not executable:
        return False, None, "not found"

    try:
        completed = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return False, executable, str(exc)

    output = (completed.stdout or completed.stderr or "").splitlines()
    version_line = output[0].strip() if output else ""
    if completed.returncode == 0:
        return True, executable, version_line
    return False, executable, version_line or f"exit code {completed.returncode}"


def _list_local_models(model_root: Path) -> list[str]:
    if not model_root.exists():
        return []

    required = {"config.json", "tokenizer.json", "vocabulary.txt", "model.bin"}
    models: list[str] = []

    for candidate in model_root.rglob("*"):
        if not candidate.is_dir():
            continue
        names = {item.name for item in candidate.iterdir() if item.is_file()}
        if required.issubset(names):
            models.append(str(candidate.relative_to(model_root)).replace("\\", "/"))

    return sorted(set(models))


def _candidate_cuda_dirs() -> list[Path]:
    candidate_dirs: list[Path] = []
    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path:
        candidate_dirs.append(Path(cuda_path) / "bin")

    if os.name == "nt":
        for drive in [Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"]:
            if not drive.exists():
                continue
            candidate_dirs.extend((drive / "NVIDIA GPU Computing Toolkit" / "CUDA").glob("v*\\bin"))
    return [directory for directory in candidate_dirs if directory.exists()]


def _candidate_cudnn_files() -> list[Path]:
    matches: list[Path] = []
    path_entries = [Path(entry) for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]

    if os.name == "nt":
        for entry in path_entries:
            if not entry.exists():
                continue
            matches.extend(entry.glob("cudnn*.dll"))
        for drive in [Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"]:
            if not drive.exists():
                continue
            matches.extend((drive / "NVIDIA" / "CUDNN").glob("v*\\bin\\*\\x64\\cudnn*.dll"))
    else:
        for entry in path_entries:
            if not entry.exists():
                continue
            matches.extend(entry.glob("libcudnn*"))
    return [path for path in matches if path.exists()]


def _detect_gpu() -> dict[str, Any]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {
            "gpu_detected": False,
            "nvidia_smi_available": False,
            "gpu_name": "",
            "message": "nvidia-smi not found",
        }

    try:
        completed = subprocess.run(
            [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "gpu_detected": False,
            "nvidia_smi_available": True,
            "gpu_name": "",
            "message": str(exc),
        }

    names = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    return {
        "gpu_detected": completed.returncode == 0 and bool(names),
        "nvidia_smi_available": True,
        "gpu_name": ", ".join(names),
        "message": names[0] if names else (completed.stderr or f"exit code {completed.returncode}").strip(),
    }


def _probe_whisper_cuda(model_path: Path | None) -> tuple[bool, str]:
    if model_path is None:
        return False, "current model is not available locally"

    try:
        WhisperModel(str(model_path), device="cuda", compute_type="float16")
        return True, "CUDA initialization succeeded"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def get_runtime_status(*, current_model_size: str, device_preference: str = "cuda", compute_type: str = "float16") -> dict[str, Any]:
    model_root = get_model_root()
    ffmpeg_ok, ffmpeg_path, ffmpeg_version = _command_version(get_ffmpeg_executable())
    ffprobe_ok, ffprobe_path, ffprobe_version = _command_version(get_ffprobe_executable())

    local_models = _list_local_models(model_root)
    current_model_path = resolve_local_model_path(current_model_size)
    current_model_found = current_model_path is not None and current_model_path.exists()

    gpu_info = _detect_gpu()
    cuda_dirs = _candidate_cuda_dirs()
    cudnn_files = _candidate_cudnn_files()
    whisper_cuda_ready, whisper_message = _probe_whisper_cuda(current_model_path) if gpu_info["gpu_detected"] else (False, "GPU not detected")

    preferred = str(device_preference or "cuda").strip().lower()
    effective_device = "cpu" if preferred == "cpu" else ("cuda" if whisper_cuda_ready else "cpu")
    effective_compute_type = compute_type if effective_device == "cuda" else "int8"

    return {
        "portable_mode": is_portable_mode(),
        "app_root": str(get_app_root()),
        "ffmpeg": {
            "found": ffmpeg_ok,
            "path": ffmpeg_path or "",
            "version": ffmpeg_version,
        },
        "ffprobe": {
            "found": ffprobe_ok,
            "path": ffprobe_path or "",
            "version": ffprobe_version,
        },
        "models": {
            "model_root": str(model_root),
            "model_root_found": model_root.exists(),
            "local_models": local_models,
            "current_model": current_model_size,
            "current_model_found": current_model_found,
            "current_model_path": str(current_model_path) if current_model_path else "",
        },
        "gpu": {
            "detected": bool(gpu_info["gpu_detected"]),
            "nvidia_smi_available": bool(gpu_info["nvidia_smi_available"]),
            "name": gpu_info["gpu_name"],
            "message": gpu_info["message"],
        },
        "cuda": {
            "available": bool(cuda_dirs),
            "candidate_dirs": [str(path) for path in cuda_dirs],
        },
        "cudnn": {
            "available": bool(cudnn_files),
            "candidate_files": [str(path) for path in cudnn_files[:12]],
        },
        "whisper_cuda": {
            "ready": whisper_cuda_ready,
            "message": whisper_message,
        },
        "effective_device": effective_device,
        "effective_compute_type": effective_compute_type,
        "ffmpeg_dir": str(get_ffmpeg_dir()),
    }
