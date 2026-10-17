# D14-R2: compose bootstrap
# up --build -> db healthy -> migrate -> superuser -> seed -> repo --check -> sync (0/0/0) -> 22-set assert
$ErrorActionPreference = "Stop"

function Run([string]$cmd) {
    Write-Host "==> $cmd"
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { throw "step failed (exit $LASTEXITCODE): $cmd" }
}

Run "docker compose up -d --build"

Write-Host "==> waiting for db healthy"
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    $h = docker compose ps --format "{{.Health}}" db 2>$null
    if ($h -match "healthy") { $healthy = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $healthy) { throw "db did not become healthy" }

Run "docker compose exec -T web python manage.py migrate"
Run "docker compose exec -T -e DJANGO_SUPERUSER_PASSWORD=demo-pass-2026 web python manage.py createsuperuser --noinput --username admin --email admin@example.com"
Run "docker compose exec -T web python manage.py load_demo_seed --flush"

Write-Host "==> make_demo_repo --check (host-generated repo must match; no --force here)"
Run "docker compose exec -T web python scripts/make_demo_repo.py --check"

Write-Host "==> sync_git_repo (expect added=0 updated=0 missing=0 = cross-env SHA identity)"
$sync = (docker compose exec -T web python manage.py sync_git_repo 2>&1 | Out-String)
Write-Host $sync
if ($sync -notmatch "added=0 updated=0 missing=0") { throw "sync mismatch: expected 0/0/0" }

Run "docker compose exec -T web python scripts/demo_terminal_assert.py --expect base"

Write-Host "BOOTSTRAP OK"