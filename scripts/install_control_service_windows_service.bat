@echo off
setlocal

set "SERVICE_NAME=XueliangAiControlService"
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "SERVICE_DIR=%ROOT%\tools\windows_service"
set "SERVICE_SRC=%ROOT%\scripts\windows_service\XueliangAiControlService.cs"
set "SERVICE_EXE=%SERVICE_DIR%\XueliangAiControlService.exe"
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

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

if not exist "%CSC%" (
  echo [ERROR] Missing C# compiler: %CSC%
  exit /b 1
)

if not exist "%SERVICE_SRC%" (
  echo [ERROR] Missing service source: %SERVICE_SRC%
  exit /b 1
)

if not exist "%ROOT%\.env" (
  echo [ERROR] Missing .env. Configure cloud/control environment before installing the service.
  exit /b 1
)

if not exist "%SERVICE_DIR%" mkdir "%SERVICE_DIR%"
echo [INFO] Compiling Windows service wrapper...
"%CSC%" /nologo /target:exe /out:"%SERVICE_EXE%" /reference:System.ServiceProcess.dll "%SERVICE_SRC%"
if errorlevel 1 (
  echo [ERROR] Failed to compile Windows service wrapper.
  exit /b 1
)

sc query "%SERVICE_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo [INFO] Existing service found. Reinstalling...
  sc stop "%SERVICE_NAME%" >nul 2>&1
  timeout /t 3 /nobreak >nul
  sc delete "%SERVICE_NAME%" >nul
  timeout /t 3 /nobreak >nul
)

sc create "%SERVICE_NAME%" binPath= "\"%SERVICE_EXE%\" \"%ROOT%\"" DisplayName= "Xueliang AI Control Service" start= auto obj= LocalSystem type= own
if errorlevel 1 (
  echo [ERROR] Failed to install Windows service.
  exit /b 1
)

sc failure "%SERVICE_NAME%" reset= 86400 actions= restart/60000/restart/60000/restart/60000 >nul
sc failureflag "%SERVICE_NAME%" 1 >nul
sc description "%SERVICE_NAME%" "Keeps Xueliang AI control endpoint 127.0.0.1:7878 alive and polling cloud control commands." >nul

sc start "%SERVICE_NAME%"
if errorlevel 1 (
  echo [WARN] Service installed but did not start. Check logs\windows-control-service.log.
  exit /b 0
)

timeout /t 5 /nobreak >nul
netstat -ano | findstr ":7878" >nul
if errorlevel 1 (
  echo [WARN] Service started but 127.0.0.1:7878 is not listening yet. Check logs\windows-control-service.log.
  exit /b 0
)

echo [OK] Installed Windows service: %SERVICE_NAME%
echo [OK] Startup: Automatic
echo [OK] Recovery: restart after 60 seconds on failure
echo [OK] Logs: %ROOT%\logs\windows-control-service.log
exit /b 0
