@echo off
setlocal
title Voice Agency 404
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=.venv\Scripts\python.exe"

echo.
echo  Voice Agency 404
echo  ----------------

rem 1. Python environment, created once.
if not exist "%PY%" (
    echo  [1/4] Python muhiti yaratilmoqda...
    py -3.14 -m venv .venv
    if errorlevel 1 (
        echo  Python 3.14 topilmadi. python.org dan Python 3.14 x64 o'rnating.
        goto failed
    )
) else (
    echo  [1/4] Python muhiti tayyor.
)

rem 2. Packages: install only when requirements-telegram.txt changed.
fc /b requirements-telegram.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
    echo  [2/4] Paketlar o'rnatilmoqda...
    "%PY%" -m pip install --disable-pip-version-check -q -r requirements-telegram.txt
    if errorlevel 1 goto failed
    copy /y requirements-telegram.txt .venv\requirements.installed >nul
) else (
    echo  [2/4] Paketlar o'rnatilgan.
)

if "%~1"=="--check" (
    "%PY%" telegram_login.py --check
    exit /b
)

rem 3. Keys and Telegram session: ask only when something is missing.
"%PY%" telegram_login.py --check >nul 2>&1
if errorlevel 1 goto setup
if not exist ".telegram\voice-agency.session" goto setup
echo  [3/4] Kalitlar va Telegram sessiyasi tayyor.
goto run
:setup
echo  [3/4] Kalitlar yoki Telegram sessiyasi kerak.
"%PY%" telegram_login.py --setup
if errorlevel 1 goto failed

:run
rem 4. Robot and dashboard. Restart automatically if Telegram drops the connection.
echo  [4/4] Robot ishga tushmoqda. Dashboard: http://127.0.0.1:8744/
echo        To'xtatish uchun Ctrl+C bosing.
echo.
set /a restarts=0
set /a crashes=0
:loop
"%PY%" -u telegram_call_test.py
if errorlevel 1 (
    set /a crashes+=1
) else (
    set /a crashes=0
)
if %crashes% geq 3 goto failed
set /a restarts+=1
if %restarts% gtr 20 (
    echo  Telegram aloqasi ko'p marta uzildi. Internetni tekshiring.
    goto failed
)
echo.
echo  Telegram aloqasi uzildi. 5 soniyadan keyin qayta ulanadi...
set "VOICE404_NO_BROWSER=1"
timeout /t 5 /nobreak >nul
goto loop

:failed
echo.
echo  Voice Agency 404 ishga tushmadi. Yuqoridagi xatoni o'qing.
echo  Telegram sessiyasi eskirgan bo'lsa, .telegram papkasini o'chirib qayta ishga tushiring.
pause
exit /b 1
