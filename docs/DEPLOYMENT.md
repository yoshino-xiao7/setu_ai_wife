# Deployment

## Local Ports

- ComfyUI: `http://127.0.0.1:8188`
- Local AI service: `http://127.0.0.1:7861`
- Ollama: `http://127.0.0.1:11434`

## Startup Order

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_all.ps1
```

Manual order:

1. ComfyUI
2. Local FastAPI service
3. Cloud worker

## Configuration

Copy `.env.example` to `.env` and set local model paths, default checkpoint, `CLOUD_API_URL`, and `AI_WORKER_TOKEN`.

Machine-specific paths must stay in `.env` or local shell profiles, not committed docs or scripts.

## Smoke Tests

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
.\.venv\Scripts\python.exe -m compileall app
```

Open `http://127.0.0.1:7861` and verify the health panel before allowing cloud jobs.
