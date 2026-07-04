@echo off
setlocal

set "SERVICE_NAME=XueliangAiControlService"
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "PROJECT_PTH=%ROOT%\.venv\Lib\site-packages\xueliang_ai_worker.pth"

net session >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Please run this file as Administrator.
  exit /b 1
)

cd /d "%ROOT%"

if not exist "%PYTHON%" (
  echo [ERROR] Missing Python virtual environment: %PYTHON%
  exit /b 1
)

sc query "%SERVICE_NAME%" >nul 2>&1
if not errorlevel 1 (
  sc stop "%SERVICE_NAME%" >nul 2>&1
  timeout /t 3 /nobreak >nul
)

"%PYTHON%" -m app.windows_control_service remove
if errorlevel 1 (
  echo [ERROR] Failed to remove Windows service.
  exit /b 1
)

if exist "%PROJECT_PTH%" del "%PROJECT_PTH%" >nul 2>&1
echo [OK] Removed Windows service: %SERVICE_NAME%
exit /b 0
