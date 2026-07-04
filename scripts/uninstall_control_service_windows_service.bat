@echo off
setlocal

set "SERVICE_NAME=XueliangAiControlService"
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

net session >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Please run this file as Administrator.
  exit /b 1
)

sc query "%SERVICE_NAME%" >nul 2>&1
if not errorlevel 1 (
  sc stop "%SERVICE_NAME%" >nul 2>&1
  timeout /t 3 /nobreak >nul
  sc delete "%SERVICE_NAME%" >nul
  if errorlevel 1 (
    echo [ERROR] Failed to remove Windows service.
    exit /b 1
  )
)

echo [OK] Removed Windows service: %SERVICE_NAME%
exit /b 0
