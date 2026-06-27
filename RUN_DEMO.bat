@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"
title Enterprise Knowledge Assistant - Showcase Demo

echo ============================================================
echo   Enterprise Knowledge Assistant - Showcase Demo
echo ============================================================
echo.

if not exist "logs" mkdir "logs"

REM --- Check Python -------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on your PATH.
    echo         Install Python 3.10+ from https://www.python.org/downloads/
    echo         and tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

REM --- First-time setup if needed ----------------------------
if not exist ".venv" (
    echo [setup] First run - creating virtual environment and installing deps...
    python -m venv ".venv"
    if errorlevel 1 ( echo [ERROR] venv creation failed. & pause & exit /b 1 )
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip >> "logs\startup.log" 2>&1
    pip install -r requirements.txt >> "logs\startup.log" 2>&1
    if errorlevel 1 (
        echo [ERROR] Dependency install failed. See logs\startup.log
        pause
        exit /b 1
    )
) else (
    call ".venv\Scripts\activate.bat"
)

echo.
echo [run] Launching the showcase demo (offline, no server needed)...
echo.

python run_demo.py
set "EXITCODE=%errorlevel%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [ERROR] The demo exited with code %EXITCODE%.
    echo         See the messages above for details.
)

echo.
pause
endlocal
