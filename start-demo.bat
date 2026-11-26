@echo off
setlocal EnableExtensions
title Voice Agency 404
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=.venv\Scripts\python.exe"

rem  start-demo.bat           - sozlash (kerak bo'lsa) va ishga tushirish
rem  start-demo.bat --reset   - kalitlarni va Telegram akkauntini qaytadan kiritish
rem  start-demo.bat --check   - faqat sozlamalarni tekshirish

echo.
echo  ============================================
echo    Voice Agency 404  -  404 jamoasi
echo  ============================================

rem 1. Python 3.14: use it if installed, otherwise install it with winget.
if exist "%PY%" (
    echo  [1/5] Python muhiti tayyor.
    goto packages
)
set "BASEPY="
py -3.14 --version >nul 2>&1 && set "BASEPY=py -3.14"
if not defined BASEPY if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "BASEPY="%LOCALAPPDATA%\Programs\Python\Python314\python.exe""
if not defined BASEPY (
    echo  [1/5] Python 3.14 topilmadi. Avtomatik o'rnatilmoqda...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo        winget yo'q. https://www.python.org/downloads/ dan Python 3.14 x64 ni o'rnating,
        echo        "Add python.exe to PATH" belgisini qo'ying va bu faylni qayta ishga tushiring.
        start "" "https://www.python.org/downloads/"
        goto failed
    )
    winget install -e --id Python.Python.3.14 --scope user --silent --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "BASEPY="%LOCALAPPDATA%\Programs\Python\Python314\python.exe""
)
if not defined BASEPY (
    echo        Python o'rnatilmadi. https://www.python.org/downloads/ dan qo'lda o'rnating.
    goto failed
)
echo  [1/5] Python muhiti yaratilmoqda...
%BASEPY% -m venv .venv
if errorlevel 1 goto failed

:packages
rem 2. Packages: install only when requirements-telegram.txt changed.
fc /b requirements-telegram.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
    echo  [2/5] Paketlar o'rnatilmoqda. Birinchi marta bir necha daqiqa oladi...
    "%PY%" -m pip install --disable-pip-version-check -q --upgrade pip
    "%PY%" -m pip install --disable-pip-version-check -q -r requirements-telegram.txt
    if errorlevel 1 (
        echo        Paketlar o'rnatilmadi. Internetni tekshirib, qayta ishga tushiring.
        goto failed
    )
    copy /y requirements-telegram.txt .venv\requirements.installed >nul
) else (
    echo  [2/5] Paketlar o'rnatilgan.
)

if /i "%~1"=="--check" (
    "%PY%" telegram_login.py --check
    exit /b
)

rem 3-4. Keys (Gemini, Telegram API) and Telegram sign-in. Asks only for what is missing.
if /i "%~1"=="--reset" (
    echo  [3/5] Kalitlar va Telegram akkaunti qaytadan sozlanadi.
    "%PY%" telegram_login.py --reset
    if errorlevel 1 goto failed
    goto run
)
"%PY%" telegram_login.py --check >nul 2>&1
if errorlevel 1 goto setup
if not exist ".telegram\voice-agency.session" goto setup
echo  [3/5] Gemini va Telegram kalitlari tayyor.
echo  [4/5] Telegram sessiyasi tekshirilmoqda...
"%PY%" telegram_login.py --setup
if errorlevel 1 goto failed
goto run
:setup
echo  [3/5] Birinchi sozlash: kalitlar va Telegram akkaunti.
"%PY%" telegram_login.py --setup
if errorlevel 1 goto failed

:run
rem 5. Robot and dashboard. The robot opens the dashboard in the browser once it is connected.
echo.
echo  [5/5] Robot ishga tushmoqda. Telegram ulangach dashboard brauzerda ochiladi:
echo        http://127.0.0.1:8744/
echo        Endi boshqa akkauntdan shu akkauntga Telegram orqali qo'ng'iroq qiling.
echo        To'xtatish uchun shu oynada Ctrl+C bosing.
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
echo  Voice Agency 404 ishga tushmadi. Yuqoridagi xabarni o'qing.
echo  Kalit yoki akkauntni almashtirish uchun:  start-demo.bat --reset
echo  Batafsil log:  .data\robot.log
pause
exit /b 1
