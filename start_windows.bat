@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\job-automation.exe" (
  echo Run setup_windows.ps1 first.
  pause
  exit /b 1
)
start "" http://127.0.0.1:8000
call .venv\Scripts\job-automation.exe start
pause

