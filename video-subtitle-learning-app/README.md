# Video Subtitle Learning App

This workspace is the initial scaffold for the desktop English-learning subtitle app.

## Current status

- Python virtual environment created with `uv`
- GPU runtime validated for `faster-whisper`
- Base backend dependencies installed
- Frontend and backend folders prepared

## Folder structure

- `backend/`: Python service for transcription, translation, analysis, and export
- `frontend/`: React + Vite + Tauri UI
- `assets/`: sample media, icons, and static assets
- `scripts/`: helper scripts for local development

## Python setup

Create or refresh the environment:

```powershell
uv venv --python 3.11
```

Install dependencies from `pyproject.toml`:

```powershell
uv sync
```

## Backend dev

Start the API service:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## Local transcription

Run offline transcription against a local video:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_transcription.py "C:\path\to\video.mp4" --model-size base.en --device cuda --compute-type float16
```

Outputs are written to:

- `outputs/transcripts/*.transcript.json`
- `outputs/transcripts/*.en.srt`

## Translation strategy

- Realtime subtitle translation can use a generic LLM with an OpenAI-compatible API, such as `qwen-turbo`
- Advanced translation and sentence analysis can use a stronger model, such as `qwen3.6-plus` or `qwen3.6-plus-2026-04-02`

Run LLM subtitle translation:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_translation.py .\outputs\transcripts\example.transcript.json --model qwen-turbo --batch-size 1
```

Run sentence analysis on one subtitle segment:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_sentence_analysis.py .\outputs\translations\example.bilingual.json --segment-id 1 --model qwen3.6-plus
```
