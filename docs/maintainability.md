# Local AI Worker Maintainability Guide

These rules apply to `setu_ai_wife`, the Windows-local AI drawing worker and ComfyUI integration.

## Core Direction

- Keep the local worker local-first. Do not expose FastAPI or ComfyUI beyond `127.0.0.1` unless the user explicitly asks for it.
- Keep machine-specific paths, tokens, model locations, and runtime switches in `.env` or local configuration. Do not commit them.
- Keep cloud contract behavior deliberate. When worker request or response fields change, inspect `../setu_api_full` and `../setu_cloud`.
- Prefer small focused functions around ComfyUI workflow building, prompt assembly, worker polling, upload completion, and local job persistence.
- Do not mix UI behavior, ComfyUI graph transformation, cloud polling, and database writes in the same function.

## Suggested Boundaries

- `app/main.py`: FastAPI routes, request binding, local API responses, and delegation.
- `app/cloud_worker.py`: cloud polling loop, job claiming, completion/failure reporting, and worker lifecycle.
- `app/comfyui.py`: ComfyUI HTTP/WebSocket integration and workflow execution.
- `app/prompting.py`: prompt assembly, translation-facing logic, and prompt tag normalization.
- `app/presets.py`: model, LoRA, character, checkpoint, and prompt preset loading.
- `app/db.py`: local SQLite persistence only.
- `app/config.py`: environment parsing and runtime settings.
- `config/*.json`: local metadata and preset data.
- `workflows/*.json`: ComfyUI workflow templates.
- `scripts/*.ps1`: Windows startup and environment checks.

## Worker Rules

- Treat worker job handling as a state machine: claim, generate, upload/complete, or fail.
- Keep failure reporting explicit so cloud jobs do not stay stuck in running states.
- Avoid swallowing exceptions without logging enough context for local troubleshooting.
- Keep retry, timeout, cleanup, and output retention behavior easy to audit.
- Do not delete generated outputs by default unless the configured cleanup behavior clearly allows it.
- Do not make cloud backend calls from random helpers; keep cloud communication in the worker boundary.

## ComfyUI And Prompt Rules

- Keep ComfyUI workflow mutation centralized and predictable.
- Validate dimensions, checkpoint, LoRA names, character masks, and inpaint inputs before sending work to ComfyUI.
- Preserve single-character, dual-character, inpaint, prompt-only, and style preset paths when touching generation code.
- Prompt presets or disabled options must not leak into generated prompts unless they are explicitly enabled by the cloud request.
- Model metadata should be read from `config/` files and actual ComfyUI model directories, not hard-coded into Python logic.

## Cloud Contract Checklist

When changing cloud worker behavior, verify these areas deliberately:

- Capability reporting still includes expected checkpoints, LoRAs, VAEs, characters, and prompt presets.
- Claim, heartbeat/status, complete, and fail endpoints still match backend DTOs.
- Uploaded image bytes, filenames, content types, NSFW mode, visibility, and trace fields match backend expectations.
- Worker token and worker id handling remains compatible with `setu_api_full`.
- Frontend asset selectors in `setu_cloud` still receive metadata in the shape they expect.

## Verification

For local worker changes, run the relevant checks:

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe -m pytest
```

For cloud contract changes, also verify the backend and frontend projects when practical.
