# Cloud Worker Mode

`setu_ai_wife` is the Windows-local AI drawing runtime. In cloud worker mode it does not expose the public business API. It polls the cloud backend, runs local ComfyUI/Ollama work, and reports results back.

## Responsibilities

1. Scan local ComfyUI models and local metadata files.
2. Report checkpoints, LoRAs, VAEs, characters, prompt presets, and worker state to the cloud backend.
3. Claim generation jobs, prompt translation jobs, and local-image deletion commands.
4. Call the local FastAPI service at `LOCAL_AI_URL` for image generation.
5. Read generated local image bytes and complete the cloud job.
6. Keep local archive images unless a cloud admin issues a local-image deletion command.

The cloud server does not need direct access to the worker machine.

## Environment

Copy `.env.example` to `.env` and fill at least:

```dotenv
LOCAL_AI_URL=http://127.0.0.1:7861
CLOUD_API_URL=https://your-api.example.com
AI_WORKER_TOKEN=replace-with-cloud-token
AI_WORKER_ID=local-comfyui-worker
AI_WORKER_NAME=Local ComfyUI Worker
AI_WORKER_VERSION=0.1.0
AI_WORKER_POLL_SECONDS=5
AI_WORKER_CAPABILITY_REPORT_SECONDS=60
AI_WORKER_CLEANUP_OUTPUTS=false
```

`AI_WORKER_TOKEN` must match the cloud backend `AI_WORKER_TOKEN`.

## Model and Metadata Discovery

The worker scans:

- `COMFYUI_MODELS_DIR/checkpoints`
- `COMFYUI_MODELS_DIR/loras`
- `COMFYUI_MODELS_DIR/vae`
- `CHARACTERS_PATH`
- `LORA_METADATA_PATH`
- `CHECKPOINT_METADATA_PATH`
- `PROMPT_PRESETS_PATH`
- `PROMPT_KNOWLEDGE_PATH`

Restart the worker or wait for the next capability report after adding models or metadata.

## Startup

Start all local components:

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_all.ps1
```

Manual startup order:

1. Start ComfyUI and confirm `http://127.0.0.1:8188` works.
2. Start the local FastAPI service:

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_service.ps1
```

3. Start the cloud worker:

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\start_cloud_worker.ps1
```

## Image Flow

1. The cloud backend creates a queued job.
2. The worker claims it and marks it running.
3. Local ComfyUI writes the generated image under `OUTPUT_DIR`.
4. The worker marks the job uploading and posts the image bytes to `/ai-worker/jobs/{id}/complete`.
5. The cloud backend writes the image to private OSS, records hashes and size, and keeps a private retention deadline.
6. The worker reports the local archive path back to the cloud.
7. If the user submits review and an admin approves it, the backend publishes a public copy.

Startup also reconciles old local completed images against cloud history when possible.

## Prompt Translation Flow

The worker also claims `/ai-worker/prompt-translations/claim`, translates prompts through the local prompt pipeline, and completes or fails each translation job.

## Local Deletion Flow

Admins can request local archive deletion from the cloud console. The worker claims commands from `/ai-worker/local-image-deletions/claim`, deletes the local archive path, and reports success or failure.

## Troubleshooting

- No LoRA in `/ai/capabilities`: check `COMFYUI_MODELS_DIR`, metadata JSON files, worker startup, and cloud connectivity.
- Jobs stay `QUEUED`: check `AI_WORKER_TOKEN`, `CLOUD_API_URL`, and the worker control page for claim errors.
- Job is `FAILED`: inspect `workerStage`, `workerDetail`, and local logs.
- Cloud preview is unavailable: check OSS configuration and `AI_MAX_COMPLETE_IMAGE_BYTES`.
- Local generation fails: test generation directly from `http://127.0.0.1:7861` first.

## Verification

```powershell
cd setu_ai_wife
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
.\.venv\Scripts\python.exe -m compileall app
```
