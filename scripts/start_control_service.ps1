$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (!(Test-Path ".venv")) {
    throw "Missing .venv. Run scripts/start_service.ps1 once before starting the control service."
}

if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Fill AI_CONTROL_TOKEN, then run again." -ForegroundColor Yellow
    exit 1
}

& ".\.venv\Scripts\python.exe" -m app.control_service
