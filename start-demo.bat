@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.14 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-telegram.txt
if errorlevel 1 goto failed
if "%~1"=="--check" (
    ".venv\Scripts\python.exe" telegram_login.py --check
    exit /b
)
".venv\Scripts\python.exe" telegram_login.py --setup
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -u telegram_call_test.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Voice Agency 404 could not start. See the error above.
pause
exit /b 1
