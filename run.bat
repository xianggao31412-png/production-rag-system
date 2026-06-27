@echo off
REM Start the Enterprise Knowledge Assistant (API + dashboard) on Windows.
setlocal
cd /d "%~dp0"

if not exist ".venv" (
  echo [setup] creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [setup] installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

if not exist ".env" (
  echo [setup] no .env found - copying .env.example ^(demo profile, runs offline^)
  copy /Y .env.example .env >nul
)

echo [run] starting on http://localhost:8000  (dashboard at /dashboard)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
endlocal
