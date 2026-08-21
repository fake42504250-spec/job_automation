@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\job-automation.exe" (
  echo Run setup_windows.ps1 first.
  pause
  exit /b 1
)
call .venv\Scripts\job-automation.exe run
pause

