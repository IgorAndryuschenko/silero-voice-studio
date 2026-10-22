@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1" %*
if errorlevel 1 (
    echo.
    echo Setup failed. See .setup\launcher.log for details.
    pause
    exit /b 1
)
