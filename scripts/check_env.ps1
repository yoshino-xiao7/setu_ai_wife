$fallbacks = @{
    "python" = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")
    "git" = @("$env:ProgramFiles\Git\cmd\git.exe")
    "ollama" = @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe")
    "7z" = @("$env:ProgramFiles\7-Zip\7z.exe")
}

$commands = @("python", "git", "winget", "ollama", "7z", "nvidia-smi")

foreach ($command in $commands) {
    if ($fallbacks.ContainsKey($command)) {
        $fallback = $fallbacks[$command] | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($fallback) {
            Write-Host "[OK] $command -> $fallback" -ForegroundColor Green
            continue
        }
    }

    $found = Get-Command $command -ErrorAction SilentlyContinue
    if ($found) {
        Write-Host "[OK] $command -> $($found.Source)" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] $command" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Expected local endpoints after startup:"
Write-Host "ComfyUI: http://127.0.0.1:8188"
Write-Host "Service: http://127.0.0.1:7861"
