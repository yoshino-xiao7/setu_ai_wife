param(
    [switch]$DryRun,
    [switch]$SkipCloudConfigCheck
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
$EnvPath = Join-Path $Root ".env"
$EnvExamplePath = Join-Path $Root ".env.example"

Set-Location $Root
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Read-DotEnv {
    param([string]$Path)

    $result = @{}
    if (!(Test-Path $Path)) {
        return $result
    }

    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (!$trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed -notmatch "^([^=]+)=(.*)$") {
            continue
        }

        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $result[$key] = $value
    }

    return $result
}

function Test-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Start-LoggedScript {
    param(
        [string]$Name,
        [string]$ScriptPath
    )

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdout = Join-Path $LogDir "$Name-$stamp.out.log"
    $stderr = Join-Path $LogDir "$Name-$stamp.err.log"

    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$ScriptPath`"") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru

    Write-Host "[STARTED] $Name pid=$($process.Id)"
    Write-Host "          stdout: $stdout"
    Write-Host "          stderr: $stderr"
    return $process
}

function Test-WorkerAlreadyRunning {
    $escapedRoot = [Regex]::Escape($Root)
    $process = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -match $escapedRoot -and $_.CommandLine -match "app\.cloud_worker"
        } |
        Select-Object -First 1
    return $null -ne $process
}

if (!(Test-Path $EnvPath)) {
    if (Test-Path $EnvExamplePath) {
        Copy-Item $EnvExamplePath $EnvPath
    }
    throw "Created .env from .env.example. Fill CLOUD_API_URL and AI_WORKER_TOKEN, then run this script again."
}

$envValues = Read-DotEnv $EnvPath
$cloudApiUrl = $envValues["CLOUD_API_URL"]
$workerToken = $envValues["AI_WORKER_TOKEN"]

if (!$SkipCloudConfigCheck) {
    if ([string]::IsNullOrWhiteSpace($cloudApiUrl)) {
        throw "CLOUD_API_URL is empty in .env. Set it to your cloud backend base URL, for example https://api.yukiryou.icu"
    }
    if ([string]::IsNullOrWhiteSpace($workerToken)) {
        throw "AI_WORKER_TOKEN is empty in .env. It must match the cloud backend AI_WORKER_TOKEN."
    }
}

$comfyLauncher = Join-Path $Root "tools\ComfyUI_windows_portable\run_nvidia_gpu.bat"
if (!(Test-Path $comfyLauncher)) {
    throw "ComfyUI launcher not found at $comfyLauncher"
}

$serviceScript = Join-Path $Root "scripts\start_service.ps1"
$comfyScript = Join-Path $Root "scripts\start_comfyui.ps1"
$workerScript = Join-Path $Root "scripts\start_cloud_worker.ps1"

foreach ($script in @($serviceScript, $comfyScript, $workerScript)) {
    if (!(Test-Path $script)) {
        throw "Missing startup script: $script"
    }
}

if ($DryRun) {
    Write-Host "[OK] Dry run passed. Cloud startup scripts and local ComfyUI launcher are present." -ForegroundColor Green
    exit 0
}

Write-Host "Starting local AI drawing stack for cloud users..." -ForegroundColor Cyan

if (Test-HttpReady "http://127.0.0.1:8188" 3) {
    Write-Host "[READY] ComfyUI is already responding at http://127.0.0.1:8188" -ForegroundColor Green
}
else {
    Start-LoggedScript "comfyui" $comfyScript | Out-Null
    if (!(Test-HttpReady "http://127.0.0.1:8188" 120)) {
        throw "ComfyUI did not become ready within 120 seconds. Check logs in $LogDir and the ComfyUI console/runtime."
    }
    Write-Host "[READY] ComfyUI is ready." -ForegroundColor Green
}

if (Test-HttpReady "http://127.0.0.1:7861" 3) {
    Write-Host "[READY] Local AI service is already responding at http://127.0.0.1:7861" -ForegroundColor Green
}
else {
    Start-LoggedScript "local-service" $serviceScript | Out-Null
    if (!(Test-HttpReady "http://127.0.0.1:7861" 120)) {
        throw "Local AI service did not become ready within 120 seconds. Check logs in $LogDir."
    }
    Write-Host "[READY] Local AI service is ready." -ForegroundColor Green
}

if (Test-WorkerAlreadyRunning) {
    Write-Host "[READY] Cloud worker is already running." -ForegroundColor Green
}
else {
    Start-LoggedScript "cloud-worker" $workerScript | Out-Null
    Start-Sleep -Seconds 3
    if (!(Test-WorkerAlreadyRunning)) {
        throw "Cloud worker process was not detected after startup. Check logs in $LogDir."
    }
    Write-Host "[READY] Cloud worker is running." -ForegroundColor Green
}

Write-Host ""
Write-Host "Cloud users can generate images when the cloud backend is running and AI_WORKER_TOKEN matches." -ForegroundColor Green
Write-Host "Local UI: http://127.0.0.1:7861"
Write-Host "Logs: $LogDir"
