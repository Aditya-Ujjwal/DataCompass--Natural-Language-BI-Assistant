$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv\Scripts\python.exe")) { Write-Host "Create the venv first: python -m venv .venv"; exit 1 }
& .\.venv\Scripts\python.exe -m uvicorn app:app --app-dir backend --reload
