# IMPLEMENTATION LOG

## 2026-06-27

- Created the local FastAPI service skeleton.
- Added SQLite-backed job history.
- Added ComfyUI API client for queueing prompts, polling history, and copying generated images into `outputs/`.
- Added Ollama prompt translation with fallback template mode.
- Added basic prompt safety rejection for requests that combine suspected minor terms with explicit sexual terms.
- Added static local-only Web UI.
- Added Windows helper scripts and installation/deployment/model/operations documentation.
- Installed Python 3.12, Git, 7-Zip, Visual C++ Redistributable, and Ollama.
- Downloaded `qwen3:4b` for Ollama prompt translation.
- Downloaded and extracted `ComfyUI_windows_portable_nvidia_cu126.7z` into `tools\ComfyUI_windows_portable`.
- Verified the local service at `http://127.0.0.1:7861`.
- Verified ComfyUI starts at `http://127.0.0.1:8188`.
- Detected GPU: NVIDIA GeForce RTX 3060 Laptop GPU, 6GB VRAM.
- Configured default checkpoint: `waiIllustriousSDXL_v170.safetensors`.
- Completed an end-to-end generation test. Output: `outputs\4f4f0942485a409c926cb9e96d8c3f80.png`.
- Added character LoRA preset support through `config\characters.json`, `/api/characters`, and `/api/loras`.
- Added `docs\CHARACTER_LORA.md` for article-style character preset setup.
- Added `cartethyia-noob-v5.safetensors` as the `Cartethyia` preset and verified a LoRA generation. Output: `outputs\26f5d029c5924d3f99a431d39cfec454.png`.
- Moved the project into `setu_ai_wife\` and verified both local endpoints still work from the new path.
- Added cloud worker mode for the independent AI drawing cloud service.
- Added capability scanning for local checkpoints, LoRA files, VAE files, and character presets.
- Added worker polling for cloud jobs, local FastAPI generation, cloud completion, and optional local output cleanup.
- Removed local prompt safety blocking from the FastAPI translate/generate entry points for the v1 no-blocking requirement.
- Added `docs\CLOUD_WORKER.md` for cloud worker configuration, startup, OSS flow, and troubleshooting.
- Added checkpoint metadata support and configured `waiIllustriousSDXL_v170.safetensors` to display as `二次元动漫 WAI`.

## Pending machine-local steps

- Add optional LoRA files and tune default generation settings.
