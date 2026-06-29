@echo off
REM ──────────────────────────────────────────────────────────────────
REM  NeuroSight — Register Windows Task Scheduler Job
REM  Run this ONCE (right-click → Run as administrator)
REM  After this, Windows will wake your PC from sleep every Sunday
REM  at 2 AM and retrain the models automatically.
REM ──────────────────────────────────────────────────────────────────

REM Self-elevate if not already admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo  Registering NeuroSight_AutoRetrain task...
echo.

REM Find Python executable
set "PYTHON="
if exist "d:\Neuro\tf311_fyp\Scripts\python.exe" (
    set "PYTHON=d:\Neuro\tf311_fyp\Scripts\python.exe"
) else (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        if not defined PYTHON set "PYTHON=%%i"
    )
)

if not defined PYTHON (
    echo ERROR: Python not found!
    pause
    exit /b 1
)

echo  Python : %PYTHON%
echo  Script : d:\Neuro\backend\scheduler\retrain_jobs.py
echo.

REM Register the task via schtasks (works without PowerShell elevation issues)
schtasks /Create /F /TN "NeuroSight_AutoRetrain" ^
    /TR "\"%PYTHON%\" \"d:\Neuro\backend\scheduler\retrain_jobs.py\" --now" ^
    /SC WEEKLY /D SUN /ST 02:00 ^
    /RL HIGHEST ^
    /RU "%USERNAME%" ^
    /IT

if %errorlevel%==0 (
    echo.
    echo  SUCCESS! Task registered.
    echo.
    echo  What happens now:
    echo    - Every Sunday at 2:00 AM Windows will WAKE your PC from sleep
    echo    - Retrains AAPL, NVDA, TSLA, GOLD models with the latest data
    echo    - Logs saved to: d:\Neuro\backend\logs\retrain.log
    echo    - If your PC is in SLEEP mode: it will wake, retrain, then sleep again
    echo    - If your PC is fully SHUT DOWN: it cannot run (no computer can)
    echo.
    echo  To verify: open Task Scheduler and look for NeuroSight_AutoRetrain
    echo  To test now: run   python retrain_jobs.py --now
    echo  To check model ages: run   python retrain_jobs.py --status
    echo.
) else (
    echo.
    echo  Task registration failed. Try right-clicking this file and
    echo  selecting "Run as administrator".
    echo.
)

REM Also enable "Wake timers" in Windows power plan (required for wake-to-run)
echo  Enabling wake timers in current power plan...
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 >nul 2>&1
powercfg /setactive SCHEME_CURRENT >nul 2>&1
echo  Done.
echo.

pause
