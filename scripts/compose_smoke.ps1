# D14-R2: compose smoke
# 22-set assertion + authenticated /admin/ 200 + /trace/serial/SN-DEMO-001/ 200 with 31 nodes / 37 edges
# 维护性取舍：断言体抽为 scripts/_smoke_body.py，docker compose cp 入容器后执行
#   —— 理由：避免 PowerShell -> docker -> manage.py shell -c 的多层引号转义（易错且难诊断）。
$ErrorActionPreference = "Stop"

Write-Host "==> 22-set terminal assertion"
docker compose exec -T web python scripts/demo_terminal_assert.py --expect base
if ($LASTEXITCODE -ne 0) { throw "terminal assertion failed" }

Write-Host "==> copying smoke body into container"
docker compose cp scripts/_smoke_body.py web:/tmp/_smoke_body.py
if ($LASTEXITCODE -ne 0) { throw "copy smoke body failed" }

Write-Host "==> http smoke (admin / trace chain)"
docker compose exec -T web python /tmp/_smoke_body.py
if ($LASTEXITCODE -ne 0) { throw "smoke FAIL" }

Write-Host "SMOKE PASS"