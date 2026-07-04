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
    $processes = @()
    try {
        $processes = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $commandLine = $_.CommandLine
                $processId = $_.ProcessId
                $processId -ne $currentPid -and
                    $commandLine -and
                    ($patterns | Where-Object { $commandLine -match $_ } | Select-Object -First 1)
            }
    }
    catch {
        Write-Host "[WARN] Cannot read process command lines: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    if (-not $processes -or $processes.Count -eq 0) {
        $controlPids = @(Get-ListeningPids -Port (Get-ControlPort))
        if ($controlPids.Count -gt 0) {
            Write-Host "[KEEP] AI control service pid(s): $($controlPids -join ',')" -ForegroundColor Cyan
        }
        $localServicePids = @(Get-ListeningPids -Port "7861")
        $comfyPids = @(Get-ListeningPids -Port "8188")
        $targetPids = @($localServicePids + $comfyPids | Select-Object -Unique)
        $comfyPython = (Join-Path $Root "tools\ComfyUI_windows_portable\python_embeded\python.exe").ToLowerInvariant()
        $processes = Get-Process -ErrorAction SilentlyContinue |
            Where-Object {
                $path = ""
                try {
                    if ($_.Path) {
                        $path = $_.Path.ToLowerInvariant()
                    }
                }
                catch {
                    $path = ""
                }
                $_.Id -ne $currentPid -and
                    ($controlPids -notcontains [int]$_.Id) -and
                    (($targetPids -contains [int]$_.Id) -or $path -eq $comfyPython)
            } |
            ForEach-Object {
                [pscustomobject]@{
                    ProcessId = $_.Id
                    Name = $_.ProcessName
                }
            }
    }

    foreach ($process in $processes) {
        Write-Host "[STOP] pid=$($process.ProcessId) $($process.Name)" -ForegroundColor Yellow
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Get-ControlPort {
    $envValues = Read-DotEnv $EnvPath
    $port = $envValues["AI_CONTROL_PORT"]
    if ([string]::IsNullOrWhiteSpace($port)) {
        $port = "7878"
    }
    return $port
}

function Get-ListeningPids {
    param([string]$Port)

    $detected = @()
    try {
        $escapedPort = [regex]::Escape($Port)
        netstat -ano |
            Select-String -Pattern "127\.0\.0\.1:$escapedPort\s+.*LISTENING\s+(\d+)" |
            ForEach-Object {
                if ($_.Matches[0].Groups[1].Value) {
                    $detected += [int]$_.Matches[0].Groups[1].Value
                }
            }
    }
    catch {
        Write-Host "[WARN] Cannot detect AI control service pid: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    return $detected
}

Send-QqBotShutdownNotice
Stop-LocalAiProcesses
Write-Output "AI drawing stack stop command completed."
