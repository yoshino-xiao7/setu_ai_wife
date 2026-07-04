param(
    [string]$TaskName = "XueliangAiControlService"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $Root "scripts\start_control_service.ps1"

if (!(Test-Path $ScriptPath)) {
    throw "Control service startup script not found: $ScriptPath"
}

try {
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
        -WorkingDirectory $Root

    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Days 365) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Force | Out-Null

    Write-Host "Installed scheduled task: $TaskName" -ForegroundColor Green
    Write-Host "Run it now with: Start-ScheduledTask -TaskName $TaskName"
}
catch {
    Write-Host "[WARN] Scheduled task install failed: $($_.Exception.Message)" -ForegroundColor Yellow
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    $command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""
    New-Item -Path $runKey -Force | Out-Null
    Set-ItemProperty -Path $runKey -Name $TaskName -Value $command
    Write-Host "Installed current-user startup entry: $TaskName" -ForegroundColor Green
}
