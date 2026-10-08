@echo off
chcp 65001 >nul

:: ============================================================================
:: start_threadlink_shell.bat  --  D13-R1
:: Purpose : open a PLAIN cmd at the project root WITHOUT activating the venv
::           use this when you need the system `python` or plain cmd behavior
:: Usage   : start_threadlink_shell.bat
:: Note    : differs from start_threadlink_venv.bat by NOT calling activate.bat
:: ============================================================================

title Threadlink Shell
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink

echo ============================================
echo   Threadlink Shell
echo ============================================
echo [OK] 已激活cmd
echo 当前目录: %CD%
echo 输入 exit 关闭本窗口
echo.

cmd /k