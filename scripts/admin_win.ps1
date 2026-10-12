<#
.SYNOPSIS
  Windows helpers for start_threadlink_admin.bat.

.DESCRIPTION
  Keeps complex PowerShell out of the .bat file (a .bat calling the inline
  `-Command "... ( ... ) ... | ... { ... }"` form is mis-parsed by cmd).

  Actions:
    kill    - kill processes listening on -Port (default 8000)
    parent  - write the parent PID of this PowerShell process (the calling cmd
              window) to the file given by -Out
    prepare - kill -Port AND write the parent PID to -Out in ONE process
              (launcher startup: avoids a second PowerShell cold start)
    open    - poll until the server is up, warm up the admin pages + ALL their
              static assets (first-view costs are one-time), then open Edge at
              /admin/ so the very first view is already warm.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\admin_win.ps1 -Action kill -Port 8000
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\admin_win.ps1 -Action parent -Out %TEMP%\threadlink_self_pid.txt
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\admin_win.ps1 -Action open -Port 8000
#>

param(
    [Parameter(Mandatory = $true)][ValidateSet("kill", "parent", "open", "prepare")][string]$Action,
    [int]$Port = 8000,
    [string]$Out = ""
)

switch ($Action) {
    "kill" {
        $pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pids) {
            if ($procId) {
                Write-Host "       kill PID $procId"
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
    }
    "prepare" {
        # Launcher startup helper: clean -Port AND write the calling cmd window PID
        # to -Out, all in ONE PowerShell process. Doing both here avoids a second
        # ~1.5s PowerShell cold start before `runserver` (startup-time fix).
        $pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pids) {
            if ($procId) {
                Write-Host "       kill PID $procId"
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
        if ($Out) {
            $parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
            [System.IO.File]::WriteAllText($Out, "$parent")
        }
    }
    "parent" {
        if (-not $Out) { throw "-Out is required for action=parent" }
        $parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
        [System.IO.File]::WriteAllText($Out, "$parent")
    }
    "open" {
        # The FIRST page view pays one-time costs (admin template compilation,
        # mimetypes init, OS file cache, AV first-scan) and later views are
        # instant. So warm up the admin page + ALL its static assets BEFORE
        # opening the browser -> the user's very first view is already warm.
        $edgeArgs = @("--no-first-run", "--no-default-browser-check", "--no-proxy-server")
        # Poll until the dev server accepts connections (max ~20s).
        $deadline = (Get-Date).AddSeconds(20)
        $ready = $false
        while (-not $ready -and (Get-Date) -lt $deadline) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/admin/login/" -TimeoutSec 2 | Out-Null
                $ready = $true
            } catch {
                Start-Sleep -Milliseconds 250
            }
        }
        # Warm up the admin pages + every static asset the admin base/login/index use.
        $urls = @(
            "/admin/login/",
            "/admin/",
            "/static/admin/css/base.css",
            "/static/admin/css/dark_mode.css",
            "/static/admin/css/login.css",
            "/static/admin/css/dashboard.css",
            "/static/admin/css/nav_sidebar.css",
            "/static/admin/css/responsive.css",
            "/static/admin/css/forms.css",
            "/static/admin/js/nav_sidebar.js",
            "/static/admin/js/theme.js",
            "/static/admin/js/core.js"
        )
        foreach ($u in $urls) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port$u" -TimeoutSec 10 | Out-Null
            } catch { }
        }
        # Open Edge only after warm-up, so its first view is warm.
        try { Start-Process "msedge" -ArgumentList ($edgeArgs + "http://127.0.0.1:$Port/admin/") -ErrorAction SilentlyContinue } catch { }
    }
}