@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo =============================================================
echo   CyberShorts Bot - Windows Setup
echo =============================================================
echo.

:: -- Check Python --------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Download Python 3.10+ from https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER% found.

:: -- Check FFmpeg --------------------------------------------------------------
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ffmpeg not found in PATH.
    echo           Download from: https://ffmpeg.org/download.html
    echo           Extract and add the bin\ folder to your PATH environment variable.
    echo           The bot will not be able to assemble videos without FFmpeg.
    echo.
) else (
    echo [OK] FFmpeg found.
)

:: -- Check Ollama --------------------------------------------------------------
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama not found in PATH.
    echo           Download from: https://ollama.ai/
    echo           After installing, run: ollama serve ^& ollama pull llama3.2
    echo.
) else (
    echo [OK] Ollama found.
)

:: -- Create virtual environment ------------------------------------------------
if not exist "venv\" (
    echo.
    echo [SETUP] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

:: -- Activate venv -------------------------------------------------------------
echo.
echo [SETUP] Activating virtual environment...
call venv\Scripts\activate.bat

:: -- Upgrade pip ---------------------------------------------------------------
echo [SETUP] Upgrading pip...
python -m pip install --quiet --upgrade pip

:: -- Install dependencies ------------------------------------------------------
echo [SETUP] Installing Python dependencies...
pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check requirements.txt and your internet connection.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

:: -- Copy .env.example --------------------------------------------------------
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [SETUP] Created .env from .env.example
    echo         Open .env and fill in your API keys before running the bot.
) else (
    echo [OK] .env already exists.
)

:: -- Create required directories -----------------------------------------------
echo [SETUP] Creating output directories...
if not exist "output\"          mkdir output
if not exist "logs\"            mkdir logs
if not exist "assets\audio\"    mkdir assets\audio
if not exist "assets\videos\"   mkdir assets\videos
if not exist "assets\temp\"     mkdir assets\temp
if not exist "assets\subtitles\" mkdir assets\subtitles
echo [OK] Directories ready.

:: -- Done ----------------------------------------------------------------------
echo.
echo =============================================================
echo   Setup complete!
echo =============================================================
echo.
echo   Next steps:
echo.
echo   1. Edit .env with your API keys
echo        notepad .env
echo.
echo   2. Start Ollama (in a separate terminal):
echo        ollama serve
echo        ollama pull llama3.2
echo.
echo   3. Place credentials.json in this folder (YouTube OAuth)
echo        See docs\setup.md for instructions.
echo.
echo   4. Test news fetching:
echo        venv\Scripts\python.exe main.py --plan-only
echo.
echo   5. Test video creation (no upload):
echo        venv\Scripts\python.exe main.py --create-only
echo.
echo   6. Full run with upload:
echo        venv\Scripts\python.exe main.py
echo.
echo =============================================================
pause
