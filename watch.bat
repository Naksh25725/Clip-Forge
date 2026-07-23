@echo off
rem Live progress window for ClipForge — safe to close and reopen anytime.
title ClipForge progress
cd /d "%~dp0"
python scripts\watch_progress.py
pause
