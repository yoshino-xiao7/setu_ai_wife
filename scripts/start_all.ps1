$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot

& (Join-Path $Root "scripts\start_comfyui.ps1")
Start-Sleep -Seconds 8
& (Join-Path $Root "scripts\start_service.ps1")

