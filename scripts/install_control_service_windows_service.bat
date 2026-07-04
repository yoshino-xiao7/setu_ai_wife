@echo off
setlocal

set "SERVICE_NAME=XueliangAiControlService"
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"

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

if not exist "%ROOT%\.env" (
  echo [ERROR] Missing .env. Configure cloud/control environment before installing the service.
  exit /b 1
)

"%PYTHON%" -c "import win32serviceutil" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing pywin32 into local virtual environment...
  "%PYTHON%" -m pip install pywin32
  if errorlevel 1 (
    echo [ERROR] Failed to install pywin32.
    exit /b 1
  )
)

sc query "%SERVICE_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo [INFO] Existing service found. Reinstalling...
  sc stop "%SERVICE_NAME%" >nul 2>&1
  timeout /t 3 /nobreak >nul
  "%PYTHON%" -m app.windows_control_service remove
)

"%PYTHON%" -m app.windows_control_service --startup auto install
if errorlevel 1 (
  echo [ERROR] Failed to install Windows service.
  exit /b 1
)

sc failure "%SERVICE_NAME%" reset= 86400 actions= restart/60000/restart/60000/restart/60000 >nul
sc failureflag "%SERVICE_NAME%" 1 >nul
sc description "%SERVICE_NAME%" "Keeps Xueliang AI control endpoint 127.0.0.1:7878 alive and polling cloud control commands." >nul

sc start "%SERVICE_NAME%" >nul
if errorlevel 1 (
  echo [WARN] Service installed but did not start. Check logs\control-service-supervisor.log.
  exit /b 0
)

echo [OK] Installed Windows service: %SERVICE_NAME%
echo [OK] Startup: Automatic
echo [OK] Recovery: restart after 60 seconds on failure
echo [OK] Logs: %ROOT%\logs\control-service-supervisor.log
exit /b 0
