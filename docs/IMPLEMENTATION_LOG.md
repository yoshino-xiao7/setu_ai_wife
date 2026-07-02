# Implementation Log

## Current State

The local worker contains:

- Local FastAPI generation service.
- ComfyUI integration.
- Ollama-backed prompt translation.
- SQLite job history.
- Cloud worker polling mode.
- Capability reporting for checkpoints, LoRAs, VAEs, characters, and prompt presets.
- Prompt translation job claiming.
- Local image path reconciliation and delete-command processing.

## Pending Machine-Local Steps

- Keep `.env` machine-specific and uncommitted.
- Keep model files and portable runtimes out of git.
- Run `scripts/check_env.ps1` after changing local paths or runtimes.
