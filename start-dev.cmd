@echo off
REM Starter MG Dubbing Studio fra prosjektets venv
cd /d "%~dp0"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8080
