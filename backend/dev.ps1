# Start the full NEXUS dev stack (backend + frontend + Cloudflare tunnel).
# Ports are read from backend/.env - see NEXUS_PORT, NEXUS_FRONTEND_PORT, etc.
#
# Usage:
#   .\dev.ps1                      # full stack (default)
#   .\dev.ps1 -BackendOnly         # backend only
#   .\dev.ps1 -NoTunnel            # backend + frontend, no tunnel
#   .\dev.ps1 -Reload              # uvicorn auto-reload (may leave zombie workers)
#   .\dev.ps1 -Port 8003           # override backend port for this run
#
# Stable Meta webhook URL (one-time):
#   .\scripts\setup_cloudflare_tunnel.ps1
#   then set NEXUS_TUNNEL_MODE=named in .env and run .\dev.ps1
#
param(
    [switch]$Reload,
    [switch]$BackendOnly,
    [switch]$NoTunnel,
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

$argsList = @("scripts/run_dev.py")
if ($Reload) { $argsList += "--reload" }
if ($BackendOnly) { $argsList += "--backend-only" }
if ($NoTunnel) { $argsList += "--no-tunnel" }
if ($NoFrontend) { $argsList += "--no-frontend" }
if ($Port -gt 0) { $argsList += @("--port", $Port) }
if ($FrontendPort -gt 0) { $argsList += @("--frontend-port", $FrontendPort) }
if ($BindHost) { $argsList += @("--host", $BindHost) }

& $python @argsList
