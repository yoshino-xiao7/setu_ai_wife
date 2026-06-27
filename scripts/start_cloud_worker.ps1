$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (!(Test-Path ".venv")) {
    throw "Missing .venv. Run scripts/start_service.ps1 once before starting the cloud worker."
}

if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Fill CLOUD_API_URL and AI_WORKER_TOKEN, then run again." -ForegroundColor Yellow
    exit 1
}

& ".\.venv\Scripts\python.exe" -m app.cloud_worker
