<#
.SYNOPSIS
  演示前恢复脚本（D13-R1）：确定性重建 prod 演示库到 D11/D12 终态。

.DESCRIPTION
  序列（步骤失败即中止，退出码非 0）：
    0) scripts/make_demo_repo.py（缺失则生成）+ --check 确定性自检
    1) 删除 db.sqlite3
    2) migrate --noinput
    3) createsuperuser --noinput（环境变量注入；用户名 admin）
    4) load_demo_seed --flush
    5) 清理 documents/uploads/ 演示上传产物（rm db 清不掉磁盘文件）
    6) sync_git_repo（GIT_READONLY_ROOTS=.data）
    7) 三类真实调用各 1 条 needs_review（bom_selection→run6 / traceability→run7 /
       requirement→run8；顺序固定以对齐 D11/D12 口径）
    8) scripts/demo_terminal_assert.py 终态断言（22 集合 + 8 行矩阵 + TL=39 + run ids）

  可重复执行且确定性：连续两次执行产出一致的终态（id 恒为 6/7/8）。
  沙箱无 LLM 出网时用 -SkipLive 跳过第 7 步，仅验证确定性 bootstrap
  （终态断言降级为 --expect base）。

.PARAMETER SkipLive
  跳过三类真实 LLM 调用（沙箱 / 离线自检用）。

.PARAMETER Python
  解释器路径；默认 .venv\Scripts\python.exe（不存在则用 python）。

.PARAMETER SuperuserPassword
  演示超管密码；默认取环境变量 DEMO_ADMIN_PASSWORD，再缺省为 demo-pass-2026。

.EXAMPLE
  # 推荐：使用启动器（内置 PowerShell 全路径回退，兼容 powershell 不在 PATH）
  start_threadlink_demo_reset.bat
  start_threadlink_demo_reset.bat -SkipLive

  # 或手工调用（powershell 不在 PATH 时用全路径）
  %SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File scripts\demo_reset.ps1 -SkipLive
#>
[CmdletBinding()]
param(
    [switch]$SkipLive,
    [string]$Python = "",
    [string]$SuperuserPassword = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $Python) {
    $candidate = Join-Path $Root ".venv\Scripts\python.exe"
    $Python = if (Test-Path $candidate) { $candidate } else { "python" }
}
if (-not $SuperuserPassword) {
    $SuperuserPassword = if ($env:DEMO_ADMIN_PASSWORD) { $env:DEMO_ADMIN_PASSWORD } else { "demo-pass-2026" }
}

$env:DJANGO_SUPERUSER_USERNAME = "admin"
$env:DJANGO_SUPERUSER_PASSWORD = $SuperuserPassword
$env:DJANGO_SUPERUSER_EMAIL = "admin@threadlink.example.com"
# 种子仓库位于 .data/demo-repo；覆盖 .env 中可能过窄的白名单（load_dotenv 不覆盖既有环境变量）。
$env:GIT_READONLY_ROOTS = ".data"

function Invoke-Step {
    param([string]$Label, [scriptblock]$Body)
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0) { throw "步骤失败：$Label（exit=$LASTEXITCODE）" }
}

Write-Host "演示库恢复开始（Python=$Python；SkipLive=$SkipLive）" -ForegroundColor Green

if (-not (Test-Path (Join-Path $Root ".data\demo-repo\.git"))) {
    Invoke-Step "0/7 生成演示 Git 仓库（.data/demo-repo 缺失）" { & $Python scripts/make_demo_repo.py --force }
}
Invoke-Step "0/7 make_demo_repo --check（确定性自检）" { & $Python scripts/make_demo_repo.py --check }

if (Test-Path (Join-Path $Root "db.sqlite3")) {
    Write-Host "==> 1/7 删除 db.sqlite3" -ForegroundColor Cyan
    Remove-Item (Join-Path $Root "db.sqlite3") -Force
}

Invoke-Step "2/7 migrate" { & $Python manage.py migrate --noinput }
Invoke-Step "3/7 createsuperuser" { & $Python manage.py createsuperuser --noinput }
Invoke-Step "4/8 load_demo_seed --flush" { & $Python manage.py load_demo_seed --flush }

$uploads = Join-Path $Root "documents\uploads"
if (Test-Path $uploads) {
    Write-Host "==> 5/8 清理 documents/uploads/ 演示上传产物" -ForegroundColor Cyan
    Get-ChildItem -Path $uploads -File -Force | Remove-Item -Force
}

Invoke-Step "6/8 sync_git_repo" { & $Python manage.py sync_git_repo }

if (-not $SkipLive) {
    Invoke-Step "7/8 bom_selection → run 6" { & $Python manage.py run_bom_selection --project DEMO-GW }
    Invoke-Step "7/8 traceability → run 7" { & $Python manage.py run_traceability SN-DEMO-001 }
    # requirement Agent 无 management command；用独立脚本调用（避免 `shell -c` 内联引号被 PowerShell 拆散）
    Invoke-Step "7/8 requirement → run 8" { & $Python scripts/run_requirement_demo.py --project DEMO-GW --document DOC-001 --username admin }
}

if ($SkipLive) {
    Invoke-Step "8/8 终态断言（--expect base）" { & $Python scripts/demo_terminal_assert.py --expect base }
} else {
    Invoke-Step "8/8 终态断言（--expect full）" { & $Python scripts/demo_terminal_assert.py --expect full }
}

Write-Host "演示库恢复完成。" -ForegroundColor Green