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
:: ============================================================================

:: 看门狗分支：被 start 以 --watchdog <PID> 调用时进入，不执行主流程
if "%~1"=="--watchdog" goto watchdog

title Threadlink Dev Server
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink

echo ============================================
echo   Threadlink Django 开发服务器
echo ============================================
echo.

:: 激活虚拟环境
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] 虚拟环境已激活
) else (
    echo [WARN] 未找到 .venv，请先运行: python -m venv .venv
    pause
    exit /b 1
)

echo.
echo [1/4] 清理启动前的僵尸进程...
call :kill_port_8000

:: 获取本窗口 cmd 的 PID（此刻标题尚未被 runserver 修改），供看门狗判定窗口是否已关闭
set "SELF_PID="
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID)).ParentProcessId" 2^>nul`) do set "SELF_PID=%%i"
if not defined SELF_PID (
    for /f "tokens=2 delims=," %%i in ('tasklist /V /FI "WINDOWTITLE eq Threadlink Dev Server" /FO CSV /NH 2^>nul') do set "SELF_PID=%%~i"
)

if defined SELF_PID (
    echo [2/4] 启动看门狗（关闭本窗口后自动清理僵尸进程）...
    start "Threadlink Watchdog" /min cmd /c "%~f0 --watchdog %SELF_PID%"
) else (
    echo [2/4] [WARN] 未能获取本窗口 PID，看门狗未启动（仍保留启动前/停止后清理）
)

echo [3/4] 启动 Django 开发服务器...
echo [4/4] 服务器就绪后自动用 Edge 打开 admin 页面
echo.
echo 访问地址:
echo   http://127.0.0.1:8000/        - 主站点
echo   http://127.0.0.1:8000/admin/  - 管理后台
echo.
echo 按 Ctrl+C 停止服务；直接关闭本窗口后看门狗会自动清理
echo.

:: 异步延迟 5 秒后用 Edge 打开 admin 页面
:: 放在 runserver 之前，否则会被前台运行的服务器阻塞
start "" /min cmd /c "timeout /t 5 /nobreak >nul && start msedge http://127.0.0.1:8000/admin/"

:: 前台运行服务器
:: --noreload 关闭自动重载，减少 Windows 上关窗后残留的子进程
python manage.py runserver 127.0.0.1:8000 --noreload

:: ---------- 服务器正常退出（Ctrl+C）后清理 ----------
echo.
echo 正在清理僵尸进程...
call :kill_port_8000
echo 服务已停止。
pause
exit /b 0

:: ============ 子过程：清理占用 8000 端口的僵尸进程 ============
:kill_port_8000
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo       结束僵尸进程 PID %%p
    taskkill /F /PID %%p >nul 2>&1
)
exit /b 0

:: ============ 看门狗：主窗口关闭后清理 8000 ============
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
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
exit /b 0
