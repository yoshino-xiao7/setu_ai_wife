$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ComfyRoot = Join-Path $Root "tools\ComfyUI_windows_portable"
$Launcher = Join-Path $ComfyRoot "run_nvidia_gpu.bat"

if (!(Test-Path $Launcher)) {
    throw "ComfyUI launcher not found at $Launcher. Follow docs/INSTALL.md to download and extract ComfyUI Portable."
}

# ComfyUI-bsk_UI prints check-mark/cross characters while registering its
# routes.  On a Chinese Windows code page the custom node can then crash a
# second time while ComfyUI is logging an earlier compatibility warning.
# Force UTF-8 for the child process so a bad custom-node log cannot take down
# the whole ComfyUI server.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8:replace"

Start-Process -FilePath $Launcher -WorkingDirectory $ComfyRoot -WindowStyle Hidden
Write-Host "ComfyUI is starting at http://127.0.0.1:8188"
