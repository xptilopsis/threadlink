@echo off
chcp 65001 >nul
title Threadlink Demo Reset
cd /d "%~dp0"

:: ============================================================================
:: start_threadlink_demo_reset.bat  --  D13-R1
:: Purpose : deterministically rebuild the demo DB to the terminal state
::           clean seed + runs 6/7/8 needs_review, via scripts\demo_reset.ps1
:: Usage   : start_threadlink_demo_reset.bat            -- full run, needs LLM
::           start_threadlink_demo_reset.bat -SkipLive  -- offline self-check
:: Note    : calls Windows PowerShell by FULL PATH, so it works even when
::           `powershell` is not on PATH. Extra args are passed through and the
::           exit code is propagated.
:: ============================================================================

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"

echo ============================================
echo   Threadlink demo DB reset  D13-R1
echo ============================================
echo   script : scripts\demo_reset.ps1
echo   purpose: rebuild demo DB to terminal state
echo            clean seed + runs 6/7/8 needs_review
echo   usage  : add -SkipLive to skip live LLM calls
echo   deps   : .venv ; LLM reachable for full run ; see .env
echo ============================================
echo.

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\demo_reset.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [OK] demo DB reset completed, exit code 0.
) else (
    echo [FAIL] demo DB reset failed, exit code %RC%.
)
pause
exit /b %RC%