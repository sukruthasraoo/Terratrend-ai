@echo off
REM TerraTrend AI — one-command start (Windows). Needs Python 3.10+ on PATH.
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist .env copy .env.example .env >nul
echo TerraTrend AI  -^>  http://127.0.0.1:8000   (Ctrl+C to stop)
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000