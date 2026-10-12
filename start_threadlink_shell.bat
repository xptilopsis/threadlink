@echo off
chcp 65001 >nul

:: ============================================================================
:: start_threadlink_shell.bat  --  D13-R1
:: Purpose : open a PLAIN cmd at the project root WITHOUT activating the venv
::           use this when you need the system `python` or plain cmd behavior
:: Usage   : start_threadlink_shell.bat
:: Note    : differs from start_threadlink_venv.bat by NOT calling activate.bat;
::           console text is ASCII only (cmd code-page safety).
:: ============================================================================

title Threadlink Shell
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink

echo ============================================
echo   Threadlink shell (no venv)
echo ============================================
echo [OK] plain cmd ready
echo Current dir: %CD%
echo Type exit to close this window
echo.

cmd /k