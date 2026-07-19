@echo off
REM opusfree one-click setup + run for Windows.
REM Double-click this file. It installs what's missing, then starts the web app.
cd /d "%~dp0"

echo == opusfree setup ==

REM 1. Python check
where python >nul 2>&1
if errorlevel 1 (
  echo Python is not installed. Get it from https://python.org/downloads
  echo During install, TICK "Add Python to PATH", then re-run this file.
  pause
  exit /b 1
)

REM 2. ffmpeg check (+ auto-install via winget if available)
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo ffmpeg not found - attempting to install with winget...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  echo If that failed, install ffmpeg manually from https://ffmpeg.org/download.html
  echo then re-run this file.
)

REM 3. Python dependencies
echo Installing Python packages (first time only)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM 4. Launch + open browser
echo Starting opusfree at http://localhost:8500  (close this window to stop it)
start "" http://localhost:8500
python webrun.py
pause
