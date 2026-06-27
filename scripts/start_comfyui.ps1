$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ComfyRoot = Join-Path $Root "tools\ComfyUI_windows_portable"
$Launcher = Join-Path $ComfyRoot "run_nvidia_gpu.bat"

if (!(Test-Path $Launcher)) {
    throw "ComfyUI launcher not found at $Launcher. Follow docs/INSTALL.md to download and extract ComfyUI Portable."
}

Start-Process -FilePath $Launcher -WorkingDirectory $ComfyRoot -WindowStyle Hidden
Write-Host "ComfyUI is starting at http://127.0.0.1:8188"

