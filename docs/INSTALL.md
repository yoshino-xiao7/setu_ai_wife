# INSTALL

This guide starts from a fresh Windows machine.

## 1. Install base tools

Open PowerShell as a normal user and install the basics:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id Microsoft.VCRedist.2015+.x64 -e
winget install --id 7zip.7zip -e
winget install --id Ollama.Ollama -e
```

Close and reopen PowerShell, then verify:

```powershell
py --version
git --version
ollama --version
nvidia-smi
```

If `nvidia-smi` is missing, install the latest NVIDIA driver before continuing.

## 2. Install Ollama model

```powershell
ollama pull qwen3:4b
ollama run qwen3:4b
```

Exit the chat after confirming it responds.

## 3. Install ComfyUI Portable

1. Download the current Windows portable build from the ComfyUI project page or official docs.
2. Extract it to a stable path, for example `C:\AI\ComfyUI_windows_portable`.
3. Start with the NVIDIA launcher, usually `run_nvidia_gpu.bat`.
4. Open `http://127.0.0.1:8188`.

## 4. Add models

Place files under the ComfyUI portable tree:

- Checkpoints: `ComfyUI\models\checkpoints`
- LoRA: `ComfyUI\models\loras`
- VAE: `ComfyUI\models\vae`

Do not use commercial or redistributed models unless their license allows it.

## 5. Install this local service

From this repository:

```powershell
Copy-Item .env.example .env
notepad .env
powershell -ExecutionPolicy Bypass -File scripts/start_service.ps1
```

Set `DEFAULT_CHECKPOINT` in `.env` to the exact checkpoint filename shown in ComfyUI.

