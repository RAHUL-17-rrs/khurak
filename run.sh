#!/usr/bin/env bash
# Khurak one-command launcher (macOS/Linux). Serves UI + API on http://127.0.0.1:8765
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { cp .env.example .env; echo "Created .env - add GNANI_API_KEY for live mode (mock mode otherwise)."; }
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -q -r backend/requirements.txt
(cd frontend && { [ -d node_modules ] || npm install; } && npm run build)
cd backend
echo -e "\nKhurak running at http://127.0.0.1:8765\n"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8765}"
