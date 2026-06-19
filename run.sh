#!/usr/bin/env bash
# Start the Enterprise Knowledge Assistant (API + dashboard).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[setup] creating virtual environment..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[setup] installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f ".env" ]; then
  echo "[setup] no .env found — copying .env.example (demo profile, runs offline)"
  cp .env.example .env
fi

echo "[run] starting on http://localhost:8000  (dashboard at /dashboard)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
