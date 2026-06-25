# Start the NEXUS staging-local stack (backend + frontend, no tunnel).
# Mirrors production-like config on ports 8003 / 5176 — see backend/.env.
#
# Usage:
#   .\staging-local.ps1
#   .\staging-local.ps1 -Reload
#   .\staging-local.ps1 -BackendOnly
#
param(
    [switch]$Reload,
    [switch]$BackendOnly,
    [switch]$NoFrontend,
    [int]$Port = 0,
    [int]$FrontendPort = 0,
    [string]$BindHost = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Missing venv Python at $python. Run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

$argsList = @("scripts/run_dev.py", "--no-tunnel")
if ($Reload) { $argsList += "--reload" }
if ($BackendOnly) { $argsList += "--backend-only" }
if ($NoFrontend) { $argsList += "--no-frontend" }
if ($Port -gt 0) { $argsList += @("--port", $Port) }
if ($FrontendPort -gt 0) { $argsList += @("--frontend-port", $FrontendPort) }
if ($BindHost) { $argsList += @("--host", $BindHost) }

& $python @argsList
