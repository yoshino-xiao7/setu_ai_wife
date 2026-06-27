$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-BasePython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & $PyLauncher.Source -3.12 @Arguments
        return
    }

    $UserPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $UserPython) {
        & $UserPython @Arguments
        return
    }

    $PythonExe = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonExe) {
        & $PythonExe.Source @Arguments
        return
    }

    throw "Python 3.12 was not found. Install it first, then reopen PowerShell."
}

if (!(Test-Path ".venv")) {
    Invoke-BasePython -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Edit DEFAULT_CHECKPOINT before generating images." -ForegroundColor Yellow
}

& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 7861
