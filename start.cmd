@echo off
REM ============================================================
REM  MG Dubbing Studio - ett-klikks oppstart (Windows)
REM  Forste gang: lager virtuelt miljo og installerer avhengigheter.
REM  Deretter: starter serveren og apner nettleseren.
REM ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [FEIL] Python ble ikke funnet. Installer Python 3.11+ fra https://www.python.org/downloads/
    echo        Husk aa huke av "Add python.exe to PATH" under installasjonen.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Forste gangs oppsett - dette tar et par minutter...
    python -m venv .venv
    if errorlevel 1 ( echo [FEIL] Kunne ikke lage virtuelt miljo. & pause & exit /b 1 )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
    ".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
    if errorlevel 1 ( echo [FEIL] Installasjon feilet. Sjekk internettilgang. & pause & exit /b 1 )
    echo.
    echo Oppsett ferdig!
    echo TIPS: For lokal transkribering/oversettelse ^(uten API-nokkel^), kjor i tillegg:
    echo       .venv\Scripts\pip install -r requirements.txt
    echo.
)

echo Starter MG Dubbing Studio paa http://localhost:8080 ...
start "" "http://localhost:8080"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8080
pause
