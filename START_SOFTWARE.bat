@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"
title Enterprise Knowledge Assistant

echo ============================================================
echo   Enterprise Knowledge Assistant - One-Click Launcher
echo ============================================================
echo.

REM --- Create working folders (never deletes anything) --------
if not exist "logs"        mkdir "logs"
if not exist "data"        mkdir "data"
if not exist "output"      mkdir "output"
if not exist "demo"        mkdir "demo"

set "LOGFILE=logs\startup.log"
echo [%date% %time%] launcher started > "%LOGFILE%"

REM --- Check Python -------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on your PATH.
    echo.
    echo   Fix: install Python 3.10 or newer from
    echo        https://www.python.org/downloads/
    echo        and tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo [check] %%v

REM --- Create virtual environment ----------------------------
if not exist ".venv" (
    echo [setup] Creating virtual environment .venv ...
    python -m venv ".venv"
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment. See messages above.
        pause
        exit /b 1
    )
)

REM --- Activate venv -----------------------------------------
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Could not activate the virtual environment.
    pause
    exit /b 1
)

REM --- Install dependencies ----------------------------------
echo [setup] Installing dependencies (first run may take a few minutes) ...
python -m pip install --upgrade pip >> "%LOGFILE%" 2>&1
pip install -r requirements.txt >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    echo         Open "%LOGFILE%" to see what went wrong.
    pause
    exit /b 1
)
echo [setup] Dependencies ready.

REM --- Create .env from template if missing ------------------
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [setup] Created .env from .env.example (offline demo profile).
    )
)

REM --- Optional: detect Ollama (only informational) ----------
where ollama >nul 2>&1
if not errorlevel 1 (
    echo [info ] Ollama detected. To use it, edit .env (see docs\CONFIGURATION.md).
) else (
    echo [info ] Ollama not detected - running the offline demo profile.
)

echo.
echo ------------------------------------------------------------
echo   Starting server at  http://127.0.0.1:8000
echo   Dashboard opens automatically in your browser.
echo   Setup log: logs\startup.log   (runtime logs show below)
echo   Keep this window OPEN while using the app; close it to stop.
echo ------------------------------------------------------------
echo.

REM --- Open the dashboard a few seconds after the server boots
start "" cmd /c "timeout /t 5 >nul && start http://127.0.0.1:8000/dashboard"

REM --- Run the server in the foreground (live logs visible) ---
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
set "EXITCODE=%errorlevel%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [ERROR] The server stopped unexpectedly (exit code %EXITCODE%).
    echo         Common causes:
    echo           - Port 8000 is already in use (close the other app or change the port)
    echo           - A dependency failed to import (see messages above / logs\startup.log)
    echo.
    pause
    exit /b %EXITCODE%
)

echo.
echo Server stopped.
pause
endlocal
