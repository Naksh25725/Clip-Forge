@echo off
rem ── ClipForge launcher ──────────────────────────────────────────────
rem Opens three windows you can actually see:
rem   1. ClipForge engine   — the backend (FFmpeg / Whisper / Groq work)
rem   2. ClipForge app      — the web interface
rem   3. ClipForge progress — live progress bar with time estimates
rem Close a window (or Ctrl+C inside it) to stop that piece.

title ClipForge launcher
cd /d "%~dp0"

start "ClipForge engine  (API on :8000)" cmd /k "cd /d "%~dp0backend" && python -m uvicorn app.main:app --port 8000"
start "ClipForge app  (:3000)" cmd /k "cd /d "%~dp0frontend" && npm run dev"
start "ClipForge progress" cmd /k "cd /d "%~dp0" && python scripts\watch_progress.py"

echo Waiting for the app to come up...
timeout /t 8 /nobreak >nul
start "" http://localhost:3000
exit
