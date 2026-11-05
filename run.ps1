# Khurak one-command launcher (Windows PowerShell). Serves UI + API on http://127.0.0.1:8765
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env - add GNANI_API_KEY for live mode (mock mode otherwise)." }
if (-not (Test-Path backend/.venv)) { py -3 -m venv backend/.venv }
backend/.venv/Scripts/python -m pip install -q -r backend/requirements.txt
Push-Location frontend
if (-not (Test-Path node_modules)) { npm install }
npm run build
Pop-Location
$env:PYTHONIOENCODING = "utf-8"
Set-Location backend
Write-Host "`nKhurak running at http://127.0.0.1:8765`n"
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
