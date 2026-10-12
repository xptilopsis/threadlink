@echo off
chcp 65001 >nul

:: ============================================================================
:: start_threadlink_admin.bat  --  D13-R1
:: Purpose : one-click Django dev server for the demo
::             1) activate .venv            2) kill zombie python on port 8000
::             3) start a watchdog           4) python manage.py runserver --noreload
::             5) auto-open Edge at /admin/  6) cleanup on exit
:: Usage   : start_threadlink_admin.bat
:: Deps    : .venv created ; Microsoft Edge installed
:: Note    : console text is ASCII only (cmd code-page safety). NO inline
::           PowerShell here - port cleanup and PID lookup are delegated to
::           scripts\admin_win.ps1 via `-File` (cmd mis-parses inline
::           `-Command "... ( ... ) ... | ... { ... }"` strings).
:: ============================================================================

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"

:: watchdog branch: invoked as `%~f0 --watchdog <PID>`; skip the main flow
if "%~1"=="--watchdog" goto watchdog

title Threadlink Dev Server
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink

echo ============================================
echo   Threadlink Django dev server
echo ============================================
echo.

:: activate venv
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] venv activated
) else (
    echo [WARN] .venv not found; run: python -m venv .venv
    pause
    exit /b 1
)

echo.
echo [1/4] preparing (clean port 8000 + resolve window PID) ...
:: ONE PowerShell call does both port cleanup and PID lookup (avoids a second
:: ~1.5s PowerShell cold start before runserver).
set "SELF_PID="
set "PIDFILE=%TEMP%\threadlink_self_pid.txt"
if exist "%PIDFILE%" del "%PIDFILE%" >nul 2>&1
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\admin_win.ps1" -Action prepare -Port 8000 -Out "%PIDFILE%" 2>nul
if exist "%PIDFILE%" for /f "usebackq tokens=*" %%i in ("%PIDFILE%") do set "SELF_PID=%%i"
if exist "%PIDFILE%" del "%PIDFILE%" >nul 2>&1
if not defined SELF_PID (
    for /f "tokens=2 delims=," %%i in ('tasklist /V /FI "WINDOWTITLE eq Threadlink Dev Server" /FO CSV /NH 2^>nul') do set "SELF_PID=%%~i"
)

if defined SELF_PID (
    echo [2/4] starting watchdog, auto-cleanup after this window closes ...
    start "Threadlink Watchdog" /min cmd /c "%~f0 --watchdog %SELF_PID%"
) else (
    echo [2/4] [WARN] could not resolve this window PID; watchdog not started
)

echo [3/4] starting Django dev server ...
echo [4/4] Edge will open /admin/ when ready
echo.
echo   http://127.0.0.1:8000/        - site
echo   http://127.0.0.1:8000/admin/  - admin
echo.
echo Press Ctrl+C to stop; closing this window triggers watchdog cleanup
echo.

:: wait, warm the server up (compile templates + prime static cache), then open Edge
:: (async: must not block the foreground runserver below)
start "Threadlink Warmer" /min "%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\admin_win.ps1" -Action open -Port 8000

:: run server in the foreground (--noreload: no orphaned children; --skip-checks: faster boot)
python manage.py runserver 127.0.0.1:8000 --noreload --skip-checks

:: ---------- cleanup after normal exit (Ctrl+C) ----------
echo.
echo cleaning up port 8000 ...
call :kill_port_8000
echo stopped.
pause
exit /b 0

:: ============ subroutine: kill zombie process on port 8000 ============
:kill_port_8000
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\admin_win.ps1" -Action kill -Port 8000 2>nul
exit /b 0

:: ============ watchdog: cleanup port 8000 after the main window closes ============
:watchdog
set "TARGET=%~2"
if not defined TARGET exit /b 1
title Threadlink Watchdog
:wd_loop
ping -n 3 127.0.0.1 >nul
tasklist /FI "PID eq %TARGET%" /NH 2>nul | findstr /R /C:"[0-9]" >nul
if errorlevel 1 goto wd_cleanup
goto wd_loop
:wd_cleanup
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\admin_win.ps1" -Action kill -Port 8000 2>nul
exit /b 0
