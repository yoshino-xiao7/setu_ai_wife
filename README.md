# Local AI Drawing Service

Windows-local AI drawing service for Chinese prompts, ComfyUI image generation, and a local history gallery.

The service binds to `127.0.0.1` by default. ComfyUI does image generation, FastAPI provides the local API/UI, SQLite stores job history, and Ollama is used when available to convert Chinese intent into English/tag prompts.

## Quick Start

1. Follow [docs/INSTALL.md](docs/INSTALL.md) to install Git, Python, Ollama, and ComfyUI Portable.
2. Copy `.env.example` to `.env` and adjust model names.
3. Start ComfyUI at `http://127.0.0.1:8188`.
4. Start this service:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_service.ps1
```

5. Open `http://127.0.0.1:7861`.

Character LoRA presets are documented in [docs/CHARACTER_LORA.md](docs/CHARACTER_LORA.md).

Cloud worker integration for the cloud backend is documented in [docs/CLOUD_WORKER.md](docs/CLOUD_WORKER.md).
