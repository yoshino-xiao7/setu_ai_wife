# AGENTS.md

## Project Overview

Setu AI Wife is the Windows-only local AI drawing worker for XueLiang Cloud. It runs local ComfyUI image generation, exposes a local FastAPI service, and can poll the cloud backend for AI drawing jobs.

This repository is not expected to exist on every macOS development machine. Frontend and backend tasks should treat it as optional unless the user is working on local AI drawing, ComfyUI, worker polling, model metadata, or prompt generation.

## Stack

- Python 3.12
- FastAPI
- SQLite for local job history
- ComfyUI Portable on Windows
- PowerShell startup scripts
- Optional Ollama prompt translation

## Key Paths

- `app/main.py`: FastAPI application and local API routes.
- `app/cloud_worker.py`: Cloud worker polling, job claiming, generation, and upload loop.
- `app/comfyui.py`: ComfyUI client integration.
- `app/prompting.py`: Prompt assembly and translation-facing logic.
- `app/prompt_knowledge.py`: Prompt knowledge loading.
- `app/config.py`: Environment and runtime settings.
- `config/characters.json`: Character presets.
- `config/lora_metadata.json`: LoRA metadata.
- `config/checkpoint_metadata.json`: Checkpoint metadata.
- `config/prompt_knowledge.json`: Prompt knowledge data.
- `workflows/`: ComfyUI workflow JSON.
- `scripts/`: Windows PowerShell startup and environment check scripts.
- `docs/`: Installation, deployment, model, operations, and worker notes.

## Common Commands

Check Windows local dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
```

Start local ComfyUI plus FastAPI service:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1
```

Start ComfyUI, FastAPI service, and cloud worker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_all.ps1
```

## Development Rules

- Keep this project Windows-local unless the user explicitly asks for cross-platform support.
- Do not commit `.env`, local databases, logs, outputs, ComfyUI portable tools, model files, or other heavy runtime assets.
- Keep machine-specific paths in `.env` or local shell configuration. Do not hard-code user home directories in committed files.
- Preserve the default local binding behavior. ComfyUI and FastAPI should remain local-only unless the user explicitly asks to expose them.
- For cloud worker contract changes, inspect the backend AI generation worker endpoints in `../setu_api_full` and the frontend AI drawing flow in `../setu_cloud`.
- For model, LoRA, character, or prompt changes, inspect the relevant `config/` JSON and prompt code before editing.
- If docs render as garbled text in PowerShell, read them as UTF-8.

## Verification Guidance

- For config or startup changes, run `scripts\check_env.ps1`.
- For worker changes, inspect logs under `logs/` locally but do not commit them.
- For cloud contract changes, verify the matching backend compile/tests when practical and confirm frontend API types remain compatible.
