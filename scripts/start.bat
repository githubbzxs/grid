@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0.."

set "HOST=%GRID_HOST%"
if "%HOST%"=="" set "HOST=0.0.0.0"

set "PORT=%GRID_PORT%"
if "%PORT%"=="" set "PORT=9999"

if not exist ".venv" (
  python -m venv .venv
)

".venv\\Scripts\\python" -m pip install --upgrade pip >nul
".venv\\Scripts\\pip" install -r "apps\\server\\requirements.txt"

set "GRID_DATA_DIR=%cd%\\data"

echo WebUI: http://127.0.0.1:%PORT%/
start "" "http://127.0.0.1:%PORT%/"

".venv\\Scripts\\python" -m uvicorn app.main:app --app-dir "apps\\server" --host "%HOST%" --port "%PORT%"
