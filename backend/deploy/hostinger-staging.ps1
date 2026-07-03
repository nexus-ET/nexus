# Deploy NEXUS staging to Hostinger VPS (SSH from your Windows PC).
#
# Hostinger runs Linux — the VPS executes hostinger-staging.sh (bash).
# This script SSHs in and runs that deploy for you.
#
# Usage:
#   .\backend\deploy\hostinger-staging.ps1 -VpsHost root@YOUR_VPS_IP
#   .\backend\deploy\hostinger-staging.ps1 -VpsHost root@YOUR_VPS_IP -FrontendOnly
#   .\backend\deploy\hostinger-staging.ps1 -VpsHost root@YOUR_VPS_IP -SkipPull
#
# First-time: set $env:NEXUS_VPS_HOST or pass -VpsHost each time.
#
param(
    [string]$VpsHost = $env:NEXUS_VPS_HOST,
    [switch]$FrontendOnly,
    [switch]$SkipPull,
    [switch]$SkipMigrations
)

$ErrorActionPreference = "Stop"

if (-not $VpsHost) {
    Write-Host @"
Missing VPS host.

  .\backend\deploy\hostinger-staging.ps1 -VpsHost root@YOUR_VPS_IP

Or set once:
  `$env:NEXUS_VPS_HOST = 'root@YOUR_VPS_IP'
"@ -ForegroundColor Yellow
    exit 1
}

$remoteScript = "/var/www/nexus/backend/deploy/hostinger-staging.sh"
$remoteArgs = @()

if ($FrontendOnly) { $remoteArgs += "--frontend-only" }
if ($SkipMigrations) { $remoteArgs += "--skip-migrations" }

$argLine = ($remoteArgs -join " ").Trim()
$remoteCmd = "sudo bash $remoteScript"
if ($argLine) { $remoteCmd += " $argLine" }

Write-Host "==> Hostinger staging deploy" -ForegroundColor Cyan
Write-Host "    VPS:    $VpsHost"
Write-Host "    Remote: $remoteCmd"
Write-Host ""

if (-not $SkipPull) {
    $Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
    Set-Location $Root
    $branch = git branch --show-current
    if ($branch -ne "staging") {
        Write-Host "Local branch is '$branch' (not staging). Push staging to GitHub first:" -ForegroundColor Yellow
        Write-Host "  python backend/scripts/promote_to_staging.py --message `"your release`""
        Write-Host ""
    } else {
        $ahead = git rev-list --count origin/staging..HEAD 2>$null
        if ($ahead -and [int]$ahead -gt 0) {
            Write-Host "WARNING: staging is $ahead commit(s) ahead of origin/staging. Push before deploy:" -ForegroundColor Yellow
            Write-Host "  git push origin staging"
            Write-Host ""
        }
    }
}

ssh $VpsHost $remoteCmd

if ($LASTEXITCODE -ne 0) {
    Write-Error "Remote deploy failed (exit $LASTEXITCODE)."
}

Write-Host ""
Write-Host "Done. Open https://nexus-dev.edutrust.in and hard-refresh (Ctrl+Shift+R)." -ForegroundColor Green
