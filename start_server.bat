@echo off
chcp 65001 >nul
echo Starting NeuroSight Server using tf311_fyp (Python 3.11 with TensorFlow)
echo.

cd backend
d:\Neuro\backend\tf311_fyp\Scripts\python.exe -X utf8 -m uvicorn main:app --reload

pause
