@echo off
setlocal
cd /d "C:\Users\user\trading\arb"

set LOCKFILE=logs\run_trx_tiny_live.lock
if not exist "%LOCKFILE%" (
  echo [STOP] lock file not found: %LOCKFILE%
  exit /b 0
)

for /f "usebackq delims=" %%p in ("%LOCKFILE%") do set PID=%%p
if "%PID%"=="" (
  echo [STOP] empty pid in lock file.
  del /f /q "%LOCKFILE%" > nul 2>nul
  exit /b 1
)

echo [STOP] stopping pid=%PID%
taskkill /PID %PID% /F > nul 2>nul
if %ERRORLEVEL%==0 (
  echo [STOP] process killed.
) else (
  echo [STOP] process not found or already stopped.
)

del /f /q "%LOCKFILE%" > nul 2>nul
endlocal
