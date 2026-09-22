# Start NEXUS local development with an SSH tunnel to the VPS Postgres.
#
# One-liner (from anywhere):
#   powershell -ExecutionPolicy Bypass -File E:\NEXUS\start-dev.ps1
#
# What this does:
#   1. Single-owner SSH DB tunnel on 127.0.0.1:15432 (clears stale listeners)
#      with ServerAliveInterval=10 + ExitOnForwardFailure
#   2. Hard gate: waits until TCP accepts AND SELECT 1 succeeds
#   3. Background watchdog probes Postgres (not just ssh alive) and restarts tunnel
#   4. Runs backend\dev.ps1 (full stack: backend + frontend + Cloudflare tunnel)
#   5. On exit / Ctrl+C, stops the watchdog and the SSH tunnel if this script started them
#
# Two different "tunnels" (do not confuse them):
#   - SSH DB tunnel (this script): Hostinger Postgres on 127.0.0.1:15432
#   - Cloudflare tunnel ([tunnel] / cloudflared in run_dev.py): public HTTPS for Meta webhooks
#     Windows defaults: --protocol http2 + --edge-ip-version 4 + auto-restart watchdog
#
# Env overrides (optional):
#   NEXUS_SSH_HOST           default 187.127.186.63
#   NEXUS_SSH_USER           default root
#   NEXUS_SSH_LOCAL_PORT     default 15432
#   NEXUS_SSH_IDENTITY_FILE  default %USERPROFILE%\.ssh\nexus_vps
#
# No DB/SSH password is stored here - uses IdentityFile (or agent if you override).
#
# Flags are forwarded to backend\dev.ps1 (named splat):
#   .\start-dev.ps1 -NoTunnel -BackendOnly -Reload -Port 8003
#
# Hostinger note: this script sets NEXUS_SKIP_STARTUP_DB_SYNC=1 unless already set,
# because create_all/sync_schema over the SSH tunnel often hangs and uvicorn exits
# with Windows code -1 (unsigned 4294967295) before /docs is ready.

param(
    [switch]$Reload,
    [switch]$BackendOnly,
    [switch]$NoTunnel,
    [switch]$NoFrontend,
    [int]$Port = 0,
    [int]$FrontendPort = 0,
    [string]$BindHost = "",
    [switch]$SkipSshTunnel,
    [switch]$KeepSshTunnel,
    [switch]$ForceTunnelRestart
)

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$BackendRoot = Join-Path $RepoRoot "backend"
$DevPs1 = Join-Path $BackendRoot "dev.ps1"
. (Join-Path $RepoRoot "scripts\NexusDbTunnel.ps1")

if (-not (Test-Path $DevPs1)) {
    Write-Error "Missing $DevPs1"
}

$tunnelState = $null
$relayJob = $null
$exitCode = 0
$prefix = Get-NexusDbTunnelLogPrefix

try {
    if (-not $SkipSshTunnel) {
        if ($ForceTunnelRestart) {
            $cfg = Get-NexusDbTunnelConfig
            Stop-NexusDbTunnelPort -PortNumber $cfg.LocalPort
        }
        # Always take ownership + attach Postgres-probing watchdog (never reuse without watchdog).
        $tunnelState = Ensure-NexusDbTunnel -RepoRoot $RepoRoot -AttachWatchdog
        if ($tunnelState.WatchdogJob) {
            $relayJob = Start-Job -ScriptBlock {
                param($WatchJob)
                while ($true) {
                    Start-Sleep -Seconds 2
                    try {
                        $lines = Receive-Job -Job $WatchJob -ErrorAction SilentlyContinue
                        foreach ($line in @($lines)) {
                            if ($line) { Write-Output $line }
                        }
                    } catch { }
                    if ($WatchJob.State -ne "Running") { break }
                }
            } -ArgumentList $tunnelState.WatchdogJob
        }
    }

    $forward = @{}
    if ($Reload) { $forward["Reload"] = $true }
    if ($BackendOnly) { $forward["BackendOnly"] = $true }
    if ($NoTunnel) { $forward["NoTunnel"] = $true }
    if ($NoFrontend) { $forward["NoFrontend"] = $true }
    if ($Port -gt 0) { $forward["Port"] = $Port }
    if ($FrontendPort -gt 0) { $forward["FrontendPort"] = $FrontendPort }
    if ($BindHost) { $forward["BindHost"] = $BindHost }

    if (-not $env:NEXUS_SKIP_STARTUP_DB_SYNC -or $env:NEXUS_SKIP_STARTUP_DB_SYNC.Trim() -eq "") {
        $env:NEXUS_SKIP_STARTUP_DB_SYNC = "1"
        Write-Host "NEXUS_SKIP_STARTUP_DB_SYNC=1 (SSH tunnel DB; skip heavy startup DDL)." -ForegroundColor DarkGray
    }

    Write-Host "Starting local stack via backend\dev.ps1 ..." -ForegroundColor Cyan
    & $DevPs1 @forward
    $exitCode = $LASTEXITCODE
} finally {
    if ($relayJob) {
        Stop-Job -Job $relayJob -ErrorAction SilentlyContinue
        # Drain any last watchdog lines
        try {
            Receive-Job -Job $relayJob -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
        } catch { }
        Remove-Job -Job $relayJob -Force -ErrorAction SilentlyContinue
    }
    if ($tunnelState -and $tunnelState.WatchdogJob) {
        Stop-Job -Job $tunnelState.WatchdogJob -ErrorAction SilentlyContinue
        Remove-Job -Job $tunnelState.WatchdogJob -Force -ErrorAction SilentlyContinue
    }

    if ($tunnelState -and $tunnelState.Started) {
        $localPort = $tunnelState.Config.LocalPort
        if ($KeepSshTunnel -or ($null -ne $exitCode -and $exitCode -ne 0)) {
            Write-Host ("{0} leaving tunnel running on port {1} (-KeepSshTunnel or non-zero exit)." -f $prefix, $localPort) -ForegroundColor DarkGray
        } else {
            Write-Host ("{0} stopping tunnel on port {1}..." -f $prefix, $localPort) -ForegroundColor DarkGray
            Stop-NexusDbTunnelPort -PortNumber $localPort -Quiet
        }
    } elseif ($tunnelState -and -not $tunnelState.Started -and -not $SkipSshTunnel) {
        Write-Host ("{0} pre-existing tunnel left running on port {1}" -f $prefix, $tunnelState.Config.LocalPort) -ForegroundColor DarkGray
    }
}

if ($null -ne $exitCode -and $exitCode -ne 0) {
    exit $exitCode
}
