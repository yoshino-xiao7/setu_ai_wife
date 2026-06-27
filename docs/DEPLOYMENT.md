# DEPLOYMENT

## Local ports

- ComfyUI: `http://127.0.0.1:8188`
- Drawing service: `http://127.0.0.1:7861`

The service is intentionally local-only. Keep `HOST=127.0.0.1`.

## Startup order

1. Start Ollama. The Windows installer usually runs it in the background.
2. Start ComfyUI Portable:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_comfyui.ps1
```

3. Start this service:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_service.ps1
```

4. Open `http://127.0.0.1:7861`.

To start both in order:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_all.ps1
```

## Configuration

Copy `.env.example` to `.env`.

Important settings:

- `COMFYUI_URL`: defaults to `http://127.0.0.1:8188`.
- `OLLAMA_URL`: defaults to `http://127.0.0.1:11434`.
- `OLLAMA_MODEL`: defaults to `qwen3:4b`.
- `DEFAULT_CHECKPOINT`: must match a checkpoint filename in ComfyUI.
- `OUTPUT_DIR`: generated images copied from ComfyUI are stored here.
- `DATABASE_PATH`: SQLite job history.

## Installed paths used in this setup

- ComfyUI Portable: `tools\ComfyUI_windows_portable`
- ComfyUI archive: `tools\downloads\ComfyUI_windows_portable_nvidia_cu126.7z`
- Local service virtualenv: `.venv`
- Generated image copies: `outputs`
- Job database: `data\jobs.sqlite3`

## API smoke tests

```powershell
Invoke-RestMethod http://127.0.0.1:7861/api/history
Invoke-RestMethod http://127.0.0.1:7861/api/prompt/translate -Method Post -ContentType "application/json" -Body '{"prompt_cn":"雨夜街角的少女侦探，霓虹灯"}'
```
