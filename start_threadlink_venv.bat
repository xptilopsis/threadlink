@echo off
chcp 65001 >nul

:: ============================================================================
:: start_threadlink_venv.bat  --  D13-R1
:: Purpose : open an interactive cmd with the project venv ACTIVE
::           calls .venv\Scripts\activate.bat, then cmd /k
:: Usage   : start_threadlink_venv.bat
:: Result  : prompt shows (.venv); `python` resolves to the venv interpreter
:: Note    : console text is ASCII only (non-ASCII echo in a .bat is mis-parsed
::           by cmd under non-UTF-8 code pages).
:: ============================================================================

title Threadlink Venv Shell
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink

if not exist ".venv\Scripts\activate.bat" (
    echo [WARN] .venv\Scripts\activate.bat not found.
    echo        Run: python -m venv .venv
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo ============================================
echo   Threadlink venv shell
echo ============================================
echo [OK] venv .venv activated
echo Current dir: %CD%
echo Prompt should now show (.venv)
echo Type exit to close this window
echo.

cmd /k