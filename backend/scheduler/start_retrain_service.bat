@echo off
REM ──────────────────────────────────────────────────────────────────
REM  NeuroSight Auto-Retrain Service
REM  Runs independently of the Flask backend.
REM  Retrains AAPL / NVDA / TSLA / GOLD every Sunday at 02:00 AM.
REM
REM  HOW TO USE
REM  ──────────
REM  1. Double-click this file to start the service in a console window.
REM  2. To add to Windows Task Scheduler (auto-start on boot):
REM       a. Open Task Scheduler → Create Basic Task
REM       b. Trigger: At startup
REM       c. Action:  Start a program
REM          Program:  C:\Path\To\python.exe
REM          Arguments: "D:\Neuro\backend\scheduler\retrain_jobs.py"
REM          Start in:  D:\Neuro\backend\scheduler
REM
REM  COMMANDS
REM  ────────
REM  Retrain right now (one-shot):   python retrain_jobs.py --now
REM  Show model ages and exit:        python retrain_jobs.py --status
REM  Run the weekly scheduler loop:  python retrain_jobs.py
REM ──────────────────────────────────────────────────────────────────

setlocal

REM ── find Python (tries venv first, then system Python) ─────────────
set "PYTHON="

if exist "%~dp0..\..\tf311_fyp\Scripts\python.exe" (
    set "PYTHON=%~dp0..\..\tf311_fyp\Scripts\python.exe"
) else if exist "%~dp0..\tf311_fyp\Scripts\python.exe" (
    set "PYTHON=%~dp0..\tf311_fyp\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo ERROR: Python not found. Please install Python or activate your venv.
        pause
        exit /b 1
    )
)

echo.
echo  NeuroSight Auto-Retrain Service
echo  Python : %PYTHON%
echo  Log    : %~dp0..\..\logs\retrain.log
echo.

%PYTHON% "%~dp0retrain_jobs.py" %*

if %errorlevel% neq 0 (
    echo.
    echo  Service exited with error %errorlevel%
    pause
)
endlocal
