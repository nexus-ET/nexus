# Open an SSH tunnel to Hostinger VPS Postgres for pgAdmin / psql / local app.
# Single-owner: clears stale :15432 listeners, aggressive keepalives, Postgres SELECT 1
# probe + auto-restart. Same defaults as start-dev.ps1.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File E:\NEXUS\start-hostinger-db-tunnel.ps1
#   powershell -ExecutionPolicy Bypass -File E:\NEXUS\start-hostinger-db-tunnel.ps1 -Background
#   powershell -ExecutionPolicy Bypass -File E:\NEXUS\start-hostinger-db-tunnel.ps1 -ForceRestart
#
# One restart command (full stack):
#   powershell -ExecutionPolicy Bypass -File E:\NEXUS\start-dev.ps1
#
# Then in pgAdmin connect to:
#   Host: 127.0.0.1
#   Port: 15432  (or NEXUS_SSH_LOCAL_PORT)
#   Maintenance DB: nexus_edutrust_dev  OR  nexus_edutrust
#   Username:       nexus_dev_et_admin  OR  nexus_et_admin
#   Password:       from VPS /var/www/nexus/backend/.env (DATABASE_URL) - not stored here
#
# Env overrides (optional):
#   NEXUS_SSH_HOST           default 187.127.186.63
#   NEXUS_SSH_USER           default root
#   NEXUS_SSH_LOCAL_PORT     default 15432
#   NEXUS_SSH_IDENTITY_FILE  default %USERPROFILE%\.ssh\nexus_vps
#
# Logs: [db-tunnel] healthy / [db-tunnel] restarting because ...
# Ctrl+C stops the foreground watcher (and the tunnel it owns).

param(
    [switch]$Background,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
. (Join-Path $RepoRoot "scripts\NexusDbTunnel.ps1")

$cfg = Get-NexusDbTunnelConfig
$prefix = Get-NexusDbTunnelLogPrefix

if ($Background) {
    $self = $MyInvocation.MyCommand.Path
    Write-Host ("{0} starting watcher (minimized, keepalives + Postgres probe)..." -f $prefix) -ForegroundColor Cyan
    $argList = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $self
    )
    if ($ForceRestart) { $argList += "-ForceRestart" }
    $watchProc = Start-Process -FilePath "powershell" -ArgumentList $argList -WindowStyle Minimized -PassThru

    $ready = Wait-NexusDbTunnelHealthy -RepoRoot $RepoRoot -TimeoutSec $cfg.ProbeTimeoutSec -Attempts 50 -DelaySec 0.5
    if (-not $ready) {
        if (-not $watchProc.HasExited) {
            Stop-Process -Id $watchProc.Id -Force -ErrorAction SilentlyContinue
        }
        Write-Error ("{0} timed out waiting for SELECT 1 on 127.0.0.1:{1}." -f $prefix, $cfg.LocalPort)
    }
    Write-Host ("{0} healthy on 127.0.0.1:{1} (watcher pid {2})" -f $prefix, $cfg.LocalPort, $watchProc.Id) -ForegroundColor Green
    Write-Host "Staging: nexus_edutrust / nexus_et_admin | Dev: nexus_edutrust_dev / nexus_dev_et_admin"
    exit 0
}

Write-Host ("{0} Hostinger SSH DB tunnel (single-owner + SELECT 1 watchdog)" -f $prefix) -ForegroundColor Cyan
Write-Host ("  pgAdmin: 127.0.0.1:{0}  |  Ctrl+C stops this tunnel" -f $cfg.LocalPort) -ForegroundColor DarkGray

if ($ForceRestart -or -not (Test-NexusDbTunnelHealthy -RepoRoot $RepoRoot -TimeoutSec $cfg.ProbeTimeoutSec -Quiet)) {
    $null = Start-NexusDbTunnelSsh -Config $cfg -ForceRestart
    $ready = Wait-NexusDbTunnelHealthy -RepoRoot $RepoRoot -TimeoutSec $cfg.ProbeTimeoutSec -Attempts 40 -DelaySec 0.5
    if (-not $ready) {
        Stop-NexusDbTunnelPort -PortNumber $cfg.LocalPort -Quiet
        Write-Error ("{0} failed to become healthy. Check SSH key/host and VPS Postgres." -f $prefix)
    }
} else {
    Write-Host ("{0} already healthy - attaching foreground watchdog (will restart on flap)" -f $prefix) -ForegroundColor Green
}

$sshArgs = Get-NexusSshTunnelArgs -Config $cfg

try {
    while ($true) {
        if (-not (Test-NexusLocalPortListening -PortNumber $cfg.LocalPort)) {
            Write-Host ("{0} starting ssh (foreground child)..." -f $prefix) -ForegroundColor Cyan
            $p = Start-Process -FilePath "ssh" -ArgumentList $sshArgs -PassThru -NoNewWindow
            while (-not $p.HasExited) {
                if (Test-NexusDbTunnelHealthy -RepoRoot $RepoRoot -TimeoutSec $cfg.ProbeTimeoutSec -Quiet) {
                    Write-Host ("{0} healthy" -f $prefix) -ForegroundColor Green
                    break
                }
                Start-Sleep -Seconds 1
            }
            if ($p.HasExited) {
                Write-Host ("{0} restarting because ssh exited (code {1})" -f $prefix, $p.ExitCode) -ForegroundColor Yellow
                Start-Sleep -Seconds $cfg.RestartDelaySec
                continue
            }
        }

        while ($true) {
            Start-Sleep -Seconds $cfg.WatchdogPollSec
            $portOk = Test-NexusLocalPortListening -PortNumber $cfg.LocalPort
            $selectOk = $false
            if ($portOk) {
                $selectOk = Test-NexusDbTunnelHealthy -RepoRoot $RepoRoot -TimeoutSec $cfg.ProbeTimeoutSec -Quiet
            }
            if ($portOk -and $selectOk) {
                continue
            }
            $reason = if (-not $portOk) {
                ("local port {0} not listening" -f $cfg.LocalPort)
            } else {
                "SELECT 1 failed (half-open SSH / Postgres unreachable)"
            }
            Write-Host ("{0} restarting because {1}" -f $prefix, $reason) -ForegroundColor Yellow
            Stop-NexusDbTunnelPort -PortNumber $cfg.LocalPort
            Start-Sleep -Seconds $cfg.RestartDelaySec
            break
        }
    }
} finally {
    Write-Host ("{0} stopping (clearing port {1})..." -f $prefix, $cfg.LocalPort) -ForegroundColor DarkGray
    Stop-NexusDbTunnelPort -PortNumber $cfg.LocalPort -Quiet
}
