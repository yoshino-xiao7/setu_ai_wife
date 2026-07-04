$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
$WorkerPidPath = Join-Path $LogDir "cloud-worker.pid"
$escapedRoot = [Regex]::Escape($Root)

if (Test-Path $WorkerPidPath) {
    $processId = (Get-Content $WorkerPidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($processId -match "^\d+$" -and (Get-Process -Id ([int]$processId) -ErrorAction SilentlyContinue)) {
        Write-Output "worker=true"
        exit 0
    }
}

$worker = $null
try {
    $worker = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object {
            $_.CommandLine -and
                $_.CommandLine -match $escapedRoot -and
                $_.CommandLine -match "app\.cloud_worker"
        } |
        Select-Object -First 1
}
catch {
    Write-Output "worker=false"
    exit 0
}

if ($null -ne $worker) {
    Write-Output "worker=true"
}
else {
    Write-Output "worker=false"
}
