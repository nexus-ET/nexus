@echo off
REM Start the full NEXUS dev stack (backend + frontend + Cloudflare tunnel).
REM Pass through args, e.g. dev.bat --backend-only --no-tunnel
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\run_dev.py %*
