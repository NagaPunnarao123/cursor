@echo off
title Virtual Cursor - Index Finger Tracking
echo ========================================================
echo   Launching Virtual Cursor Controlled by Index Finger
echo ========================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/2] Checking and installing required packages...
pip install -r requirements.txt

echo.
echo [2/2] Launching Virtual Cursor Application...
echo.
python virtual_cursor.py

pause
