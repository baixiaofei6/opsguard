@echo off
chcp 65001 >nul
title OpsGuard TUI
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul
if errorlevel 1 set "PY=C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

echo Starting OpsGuard TUI...
echo.
"%PY%" src\opsguard.py --tui
echo.
echo TUI exited.
pause
