$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an Administrator PowerShell window to update the existing control service.'
}

$serviceName = 'XueliangAiControlService'
$service = Get-Service -Name $serviceName -ErrorAction Stop
$source = Join-Path $Root 'scripts\windows_service\XueliangAiControlService.cs'
$candidate = Join-Path $Root 'tools\windows_service\XueliangAiControlService.next.exe'
$installed = Join-Path $Root 'tools\windows_service\XueliangAiControlService.exe'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler '/nologo' '/target:exe' "/out:$candidate" '/reference:System.ServiceProcess.dll' $source
if ($LASTEXITCODE -ne 0) { throw 'Control service compilation failed; the running service was left untouched.' }

Stop-Service -Name $serviceName -ErrorAction Stop
$service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(30))
try {
    Copy-Item -LiteralPath $candidate -Destination $installed -Force
}
finally {
    Start-Service -Name $serviceName
}

$readyUntil = (Get-Date).AddSeconds(30)
do {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:7878/health' -TimeoutSec 3
        if ($health.ok -and $health.tasks.autoRecovery -and $health.tasks.cloudControl) {
            Write-Output 'Control service updated: cloud control and automatic recovery tasks are running.'
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $readyUntil)
throw 'The updated control service did not become healthy. Check logs/control-service-*.log.'
