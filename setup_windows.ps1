$ErrorActionPreference = "Stop"

Write-Host "Setting up Job Automation..." -ForegroundColor Cyan

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher was not found. Install Python 3.11 or newer from python.org first."
}

if (-not (Test-Path ".venv")) {
    py -3.11 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -e ".[dev]"
& .\.venv\Scripts\job-automation.exe init

Write-Host "" 
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "1. Put your Gmail OAuth file at config\gmail_credentials.json"
Write-Host "2. Edit config\profile.yaml"
Write-Host "3. Double-click start_windows.bat"

