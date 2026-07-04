$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$escapedRoot = [Regex]::Escape($Root)

$worker = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
            $_.CommandLine -match $escapedRoot -and
            $_.CommandLine -match "app\.cloud_worker"
    } |
    Select-Object -First 1

if ($null -ne $worker) {
    Write-Output "worker=true"
}
else {
    Write-Output "worker=false"
}
