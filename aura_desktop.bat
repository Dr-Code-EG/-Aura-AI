@echo off
REM Launcher for Aura Desktop on Windows. Double-click this file.
setlocal

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Make sure Python 3.10+ is installed.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

if not exist "venv\Lib\site-packages\PyQt6" (
    echo Installing dependencies (first run only)...
    python -m pip install --upgrade pip
    python -m pip install -r requirements-desktop.txt
)

python aura_desktop.py %*
