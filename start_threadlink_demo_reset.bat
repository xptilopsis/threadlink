@echo off
chcp 65001 >nul
title Threadlink Demo Reset
cd /d "%~dp0"

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"

echo ============================================
echo   Threadlink 演示库恢复（D13-R1）
echo ============================================
echo   脚本: scripts\demo_reset.ps1
echo   用途: 确定性重建演示库到终态
echo         （干净种子 + runs 6/7/8 needs_review）
echo   参数: 追加 -SkipLive 跳过真实 LLM 调用（离线自检）
echo   依赖: .venv、LLM 可达（完整恢复）；配置见 .env
echo ============================================
echo.

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\demo_reset.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [OK] 演示库恢复完成（退出码 0）。
) else (
    echo [FAIL] 演示库恢复失败（退出码 %RC%）。
)
pause
exit /b %RC%