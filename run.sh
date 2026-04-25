#!/usr/bin/env bash
# Convenience launcher for the LangGraph Multi-Agent web app.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and set GROQ_API_KEY before running."
fi

if [ ! -d .venv ]; then
  echo "Creating virtualenv at .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip >/dev/null
pip install -r backend/requirements.txt

exec uvicorn app.main:app \
  --app-dir backend \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8000}" \
  --reload
