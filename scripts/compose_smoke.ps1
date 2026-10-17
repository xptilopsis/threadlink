# D14-R2: compose smoke
# 22-set assertion + authenticated /admin/ 200 + /trace/serial/SN-DEMO-001/ 200 with 31 nodes / 37 edges
$ErrorActionPreference = "Stop"

Write-Host "==> 22-set terminal assertion"
docker compose exec -T web python scripts/demo_terminal_assert.py --expect base
if ($LASTEXITCODE -ne 0) { throw "terminal assertion failed" }

$code = "from django.test import Client; from django.contrib.auth import get_user_model; c=Client(); c.force_login(get_user_model().objects.get(username='admin')); r1=c.get('/admin/'); r2=c.get('/trace/serial/SN-DEMO-001/?format=json'); j=r2.json(); print('ADMIN', r1.status_code); print('TRACE', r2.status_code, 'nodes', j.get('nodes'), 'edges', j.get('edges')); ok=(r1.status_code==200 and r2.status_code==200 and j.get('nodes')==31 and j.get('edges')==37); print('SMOKE', 'PASS' if ok else 'FAIL'); raise SystemExit(0 if ok else 1)"

Write-Host "==> http smoke (admin / trace chain)"
docker compose exec -T web python manage.py shell -c $code
if ($LASTEXITCODE -ne 0) { throw "smoke FAIL" }

Write-Host "SMOKE PASS"