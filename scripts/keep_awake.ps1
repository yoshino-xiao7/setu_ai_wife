$ErrorActionPreference = "Stop"

$signature = @"
using System;
using System.Runtime.InteropServices;

public static class SleepGuard {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

Add-Type -TypeDefinition $signature -ErrorAction SilentlyContinue

$ES_CONTINUOUS = [uint32]"0x80000000"
$ES_SYSTEM_REQUIRED = [uint32]"0x00000001"
$ES_DISPLAY_REQUIRED = [uint32]"0x00000002"
$ES_AWAYMODE_REQUIRED = [uint32]"0x00000040"
$flags = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_DISPLAY_REQUIRED -bor $ES_AWAYMODE_REQUIRED

Write-Host "[keep-awake] started at $(Get-Date -Format o)"
Write-Host "[keep-awake] preventing sleep while this process is running."

try {
    while ($true) {
        [SleepGuard]::SetThreadExecutionState($flags) | Out-Null
        Start-Sleep -Seconds 30
    }
}
finally {
    [SleepGuard]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
    Write-Host "[keep-awake] stopped at $(Get-Date -Format o)"
}
