@echo off
title ExamGuard Pro — Backend Server
color 0B

echo.
echo  =========================================================
echo   EXAMGUARD PRO — Starting Backend
echo  =========================================================
echo.

cd /d "%~dp0backend"

REM Check if venv exists, create if not
if not exist "venv\Scripts\activate.bat" (
    echo  [1/3] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo  ERROR: Python not found. Install Python 3.10+ from python.org
        pause
        exit /b 1
    )
    echo  [2/3] Installing dependencies (this takes a few minutes first time)...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    echo  [1/3] Virtual environment found.
    call venv\Scripts\activate.bat
)

echo.
echo  [3/3] Starting FastAPI server on http://localhost:8000
echo.
echo  API docs: http://localhost:8000/docs
echo  Frontend: open frontend\index.html in Chrome/Edge
echo.
echo  Press Ctrl+C to stop the server.
echo  =========================================================
echo.

python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

pause
