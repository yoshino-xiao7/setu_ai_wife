$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $Root ".env"
Set-Location $Root

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

function Send-QqBotShutdownNotice {
    $envValues = Read-DotEnv $EnvPath
    $botUrl = $envValues["QQ_BOT_SHUTDOWN_NOTICE_URL"]
    if ([string]::IsNullOrWhiteSpace($botUrl)) {
        $botUrl = $envValues["QQ_BOT_SEND_MESSAGE_URL"]
    }
    if ([string]::IsNullOrWhiteSpace($botUrl)) {
        $botUrl = $envValues["QQ_BOT_SEND_IMAGE_URL"]
    }
    if ([string]::IsNullOrWhiteSpace($botUrl)) {
        return
    }

    $headers = @{ "User-Agent" = "Xueliang-AI-Control/0.1" }
    $botToken = $envValues["QQ_BOT_TOKEN"]
    if (![string]::IsNullOrWhiteSpace($botToken)) {
        $headers["Authorization"] = "Bearer $botToken"
    }
    $payload = @{
        type = "worker_shutdown"
        workerId = $envValues["AI_WORKER_ID"]
        workerName = $envValues["AI_WORKER_NAME"]
        workerVersion = $envValues["AI_WORKER_VERSION"]
        message = '"AI \u7ed8\u56fe Worker \u5df2\u505c\u6b62\u3002"' | ConvertFrom-Json
    } | ConvertTo-Json -Compress

    try {
        Invoke-RestMethod -Uri $botUrl -Method Post -Headers $headers -Body $payload -ContentType "application/json" -TimeoutSec 5 | Out-Null
    }
    catch {
        Write-Host "[WARN] Failed to send QQ bot shutdown notice: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

function Stop-LocalAiProcesses {
    $patterns = @(
        "app\.cloud_worker",
        "uvicorn app\.main:app --host 127\.0\.0\.1 --port 7861",
        "scripts\\start_cloud_worker\.ps1",
        "scripts\\start_service\.ps1",
        "start_comfyui\.ps1",
        "run_nvidia_gpu\.bat",
        "ComfyUI\\main\.py"
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

Send-QqBotShutdownNotice
Stop-LocalAiProcesses
Write-Output "AI drawing stack stop command completed."
