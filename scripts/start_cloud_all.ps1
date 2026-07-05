param(
    [switch]$DryRun,
    [switch]$SkipCloudConfigCheck,
    [switch]$Restart
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

    $command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" > `"$stdout`" 2> `"$stderr`""
    $process = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/d", "/c", $command) `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -PassThru

    Write-Host "[STARTED] $Name pid=$($process.Id)"
    Write-Host "          stdout: $stdout"
    Write-Host "          stderr: $stderr"
    return $process
}

function Start-LoggedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments
    )

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -PassThru

    $pidPath = Join-Path $LogDir "$Name.pid"
    Set-Content -Path $pidPath -Value $process.Id -Encoding ASCII
    Write-Host "[STARTED] $Name pid=$($process.Id)"
    Write-Host "          pidfile: $pidPath"
    return $process
}

function Test-ProcessIdRunning {
    param([string]$PidPath)

    if (!(Test-Path $PidPath)) {
        return $false
    }

    $processId = (Get-Content $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($processId -notmatch "^\d+$") {
        return $false
    }

    return $null -ne (Get-Process -Id ([int]$processId) -ErrorAction SilentlyContinue)
}

function Test-WorkerAlreadyRunning {
    $pidPath = Join-Path $LogDir "cloud-worker.pid"
    if (Test-ProcessIdRunning $pidPath) {
        return $true
    }

    $escapedRoot = [Regex]::Escape($Root)
    try {
        $process = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $_.CommandLine -match $escapedRoot -and $_.CommandLine -match "app\.cloud_worker"
            } |
            Select-Object -First 1
        return $null -ne $process
    }
    catch {
        Write-Host "[WARN] Cannot inspect cloud worker command line: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

function Test-KeepAwakeRunning {
    $pidPath = Join-Path $LogDir "keep-awake.pid"
    if (Test-ProcessIdRunning $pidPath) {
        return $true
    }

    $escapedRoot = [Regex]::Escape($Root)
    try {
        $process = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $_.CommandLine -match $escapedRoot -and $_.CommandLine -match "scripts\\keep_awake\.ps1"
            } |
            Select-Object -First 1
        return $null -ne $process
    }
    catch {
        Write-Host "[WARN] Cannot inspect keep-awake command line: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

function Send-QqBotLifecycleNotice {
    param([string]$EventType)

    $envValues = Read-DotEnv $EnvPath
    if ($EventType -eq "worker_shutdown") {
        $botUrl = $envValues["QQ_BOT_SHUTDOWN_NOTICE_URL"]
    }
    else {
        $botUrl = $envValues["QQ_BOT_STARTUP_NOTICE_URL"]
    }
    if ([string]::IsNullOrWhiteSpace($botUrl)) {
        $botUrl = $envValues["QQ_BOT_SEND_MESSAGE_URL"]
    }
    if ([string]::IsNullOrWhiteSpace($botUrl)) {
        $botUrl = $envValues["QQ_BOT_SEND_IMAGE_URL"]
    }
    if ([string]::IsNullOrWhiteSpace($botUrl)) {
        return
    }

    $headers = @{ "User-Agent" = "Xueliang-AI-Worker/0.1" }
    $botToken = $envValues["QQ_BOT_TOKEN"]
    if (![string]::IsNullOrWhiteSpace($botToken)) {
        $headers["Authorization"] = "Bearer $botToken"
    }

    $message = if ($EventType -eq "worker_shutdown") {
        '"AI \u7ed8\u56fe Worker \u5df2\u505c\u6b62\u3002"' | ConvertFrom-Json
    }
    else {
        '"AI \u7ed8\u56fe Worker \u5df2\u542f\u52a8\uff0c\u6b63\u5728\u7b49\u5f85\u4efb\u52a1\u3002"' | ConvertFrom-Json
    }
    $payload = @{
        type = $EventType
        workerId = $envValues["AI_WORKER_ID"]
        workerName = $envValues["AI_WORKER_NAME"]
        workerVersion = $envValues["AI_WORKER_VERSION"]
        message = $message
    } | ConvertTo-Json -Compress

    try {
        $body = [System.Text.Encoding]::UTF8.GetBytes($payload)
        Invoke-RestMethod -Uri $botUrl -Method Post -Headers $headers -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 5 | Out-Null
    }
    catch {
        Write-Host "[WARN] Failed to send QQ bot lifecycle notice: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

function Stop-LocalAiProcesses {
    $patterns = @(
        "app\.cloud_worker",
        "uvicorn app\.main:app --host 127\.0\.0\.1 --port 7861",
        "scripts\\start_cloud_worker\.ps1",
        "scripts\\start_service\.ps1"
    )

    $currentPid = $PID
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $commandLine = $_.CommandLine
            $processId = $_.ProcessId
            $processId -ne $currentPid -and
                $commandLine -and
                ($patterns | Where-Object { $commandLine -match $_ } | Select-Object -First 1)
        }

    foreach ($process in $processes) {
        Write-Host "[STOP] pid=$($process.ProcessId) $($process.Name)" -ForegroundColor Yellow
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
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
$keepAwakeScript = Join-Path $Root "scripts\keep_awake.ps1"
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"

foreach ($script in @($serviceScript, $comfyScript, $workerScript, $keepAwakeScript)) {
    if (!(Test-Path $script)) {
        throw "Missing startup script: $script"
    }
}
if (!(Test-Path $venvPython)) {
    throw "Missing Python virtual environment at $venvPython"
}

if ($DryRun) {
    Write-Host "[OK] Dry run passed. Cloud startup scripts and local ComfyUI launcher are present." -ForegroundColor Green
    exit 0
}

Write-Host "Starting local AI drawing stack for cloud users..." -ForegroundColor Cyan

if (Test-KeepAwakeRunning) {
    Write-Host "[READY] Keep-awake guard is already running." -ForegroundColor Green
}
else {
    Start-LoggedProcess "keep-awake" "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $keepAwakeScript) | Out-Null
    Write-Host "[READY] Keep-awake guard is running." -ForegroundColor Green
}

if ($Restart) {
    Write-Host "Restart requested. Stopping local service and cloud worker processes..." -ForegroundColor Yellow
    Send-QqBotLifecycleNotice "worker_shutdown"
    Stop-LocalAiProcesses
    Start-Sleep -Seconds 2
}

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
    Start-LoggedProcess "local-service" $venvPython @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "7861") | Out-Null
    if (!(Test-HttpReady "http://127.0.0.1:7861" 120)) {
        throw "Local AI service did not become ready within 120 seconds. Check logs in $LogDir."
    }
    Write-Host "[READY] Local AI service is ready." -ForegroundColor Green
}

if (Test-WorkerAlreadyRunning) {
    Write-Host "[READY] Cloud worker is already running." -ForegroundColor Green
}
else {
    Start-LoggedProcess "cloud-worker" $venvPython @("-m", "app.cloud_worker") | Out-Null
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

try {
    Start-Process "http://127.0.0.1:7861"
}
catch {
    Write-Host "Could not open the local Worker console automatically. Open http://127.0.0.1:7861 manually." -ForegroundColor Yellow
}
