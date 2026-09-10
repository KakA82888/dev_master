@echo off
REM One-click start for Windows (cmd). ASCII-only file on purpose:
REM non-ASCII characters in .bat files can be mangled by the console codepage.
REM
REM Usage:
REM   scripts\start.bat           skip build when app\frontend\dist exists
REM   scripts\start.bat --build   force rebuild frontend

cd /d "%~dp0.."

set HOST=127.0.0.1
set PORT=8000

REM --- Step 1: frontend build -------------------------------------------------
if "%1"=="--build" goto build
if not exist "app\frontend\dist\index.html" goto build
echo [1/2] Frontend dist found - skipping build (use --build to force rebuild)
goto start

:build
echo [1/2] Building frontend (npm install ^&^& npm run build) ...
pushd app\frontend
call npm install
call npm run build
popd

REM --- Step 2: start backend (serves API + dist) ------------------------------
:start
echo [2/2] Starting backend on http://%HOST%:%PORT%  (Ctrl+C to stop)
python -m uvicorn app.backend.main:app --host %HOST% --port %PORT%
