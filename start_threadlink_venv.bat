@echo off
chcp 65001 >nul

:: ============================================================================
:: start_threadlink_venv.bat  --  D13-R1
:: Purpose : open an interactive cmd with the project venv ACTIVE
::           calls .venv\Scripts\activate.bat, then cmd /k
:: Usage   : start_threadlink_venv.bat
:: Result  : prompt shows (.venv); `python` resolves to the venv interpreter
:: ============================================================================

title Threadlink Venv Shell
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink

if not exist ".venv\Scripts\activate.bat" (
    echo [WARN] 未找到 .venv，请先运行: python -m venv .venv
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo ============================================
echo   Threadlink 虚拟环境 Shell
echo ============================================
echo [OK] 已激活虚拟环境 .venv
echo 当前目录: %CD%
echo 提示符前应显示 (.venv)
echo 输入 exit 关闭本窗口
echo.

cmd /k