#!/usr/bin/env bash
# TerraTrend AI — one-command start (Linux/macOS). Needs Python 3.10+.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "TerraTrend AI  ->  http://127.0.0.1:8000   (Ctrl+C to stop)"
exec python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000