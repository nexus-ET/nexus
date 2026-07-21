# One-time setup for a free named Cloudflare tunnel (stable URL for Meta webhooks).
#
# Prerequisites:
#   - cloudflared in PATH (winget install Cloudflare.cloudflared)
#   - A domain on Cloudflare (free plan is fine)
#
# Usage (from backend root):
#   .\scripts\setup_cloudflare_tunnel.ps1
#   .\scripts\setup_cloudflare_tunnel.ps1 -Hostname nexus-dev.yourdomain.com
#
param(
    [string]$TunnelName = "nexus-dev",
    [string]$Hostname = "",
    [int]$BackendPort = 0
)

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $BackendRoot ".env"
$CloudflaredDir = Join-Path $BackendRoot "cloudflared"
$ConfigFile = Join-Path $CloudflaredDir "config.yml"
$CredentialsDir = Join-Path $CloudflaredDir "credentials"

function Read-EnvPort {
    if (-not (Test-Path $EnvFile)) { return 8002 }
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*NEXUS_PORT\s*=\s*(\d+)') { return [int]$Matches[1] }
    }
    return 8002
}

function Set-EnvKey {
    param([string]$Key, [string]$Value)
    $lines = if (Test-Path $EnvFile) { Get-Content $EnvFile } else { @() }
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=") {
            $found = $true
            "$Key=$Value"
        } else { $line }
    }
    if (-not $found) { $out += "$Key=$Value" }
    $out | Set-Content $EnvFile -Encoding utf8
}

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error "cloudflared not found. Install: winget install Cloudflare.cloudflared"
}

if ($BackendPort -le 0) { $BackendPort = Read-EnvPort }

$OriginCert = Join-Path $env:USERPROFILE ".cloudflared\cert.pem"
if (-not (Test-Path $OriginCert)) {
    Write-Host ""
    Write-Host "Step 1: Log in to Cloudflare (browser will open)." -ForegroundColor Cyan
    Write-Host "Choose the account that owns your domain." -ForegroundColor DarkGray
    Write-Host ""
    & cloudflared tunnel login
    if ($LASTEXITCODE -ne 0) { throw "cloudflared tunnel login failed" }
}

if (-not $Hostname) {
    Write-Host ""
    Write-Host "Enter the public hostname for this dev tunnel." -ForegroundColor Cyan
    Write-Host "Example: nexus-dev.yourdomain.com (domain must be on Cloudflare DNS)" -ForegroundColor DarkGray
    $Hostname = Read-Host "Hostname"
}
$Hostname = $Hostname.Trim().ToLower()
$hostPattern = '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
if (-not $Hostname -or -not [regex]::IsMatch($Hostname, $hostPattern)) {
    throw "Invalid hostname: $Hostname"
}

Write-Host ""
Write-Host "Step 2: Create tunnel '$TunnelName' (skip if it already exists)..." -ForegroundColor Cyan
$createOut = & cloudflared tunnel create $TunnelName 2>&1 | Out-String
Write-Host $createOut
if ($createOut -match 'already exists') {
    Write-Host "Tunnel '$TunnelName' already exists - continuing." -ForegroundColor Yellow
}

$UserCloudflared = Join-Path $env:USERPROFILE ".cloudflared"
$tunnelId = $null
$listJsonRaw = & cloudflared tunnel list --output json 2>&1 | Out-String
try {
    $tunnels = $listJsonRaw | ConvertFrom-Json
    if ($tunnels -isnot [System.Array]) { $tunnels = @($tunnels) }
    $found = $tunnels | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
    if ($found -and $found.id) { $tunnelId = [string]$found.id }
} catch {
    # cloudflared may print non-JSON noise; fall through to table parse
}
if (-not $tunnelId) {
    # Fallback: parse table output (UUID then tunnel name)
    $listTable = & cloudflared tunnel list 2>&1 | Out-String
    $uuidPattern = '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s+' + [regex]::Escape($TunnelName) + '\b'
    $m = [regex]::Match($listTable, $uuidPattern)
    if ($m.Success) { $tunnelId = $m.Groups[1].Value }
}
$credSource = $null
if ($tunnelId) {
    $byId = Join-Path $UserCloudflared "$tunnelId.json"
    if (Test-Path $byId) { $credSource = Get-Item $byId }
}
if (-not $credSource) {
    $credSource = Get-ChildItem $UserCloudflared -Filter "*.json" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "config.json" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

if (-not $credSource) {
    $listOut = & cloudflared tunnel list 2>&1 | Out-String
    Write-Host $listOut
    throw "No tunnel credentials JSON found in $UserCloudflared. Run: cloudflared tunnel create $TunnelName"
}

New-Item -ItemType Directory -Force -Path $CredentialsDir | Out-Null
$credDest = Join-Path $CredentialsDir "$TunnelName.json"
Copy-Item -Force $credSource.FullName $credDest
Write-Host "Credentials copied to $credDest" -ForegroundColor Green

$credRelative = "credentials/$TunnelName.json"
$configYaml = @(
    "tunnel: $TunnelName"
    "credentials-file: $credRelative"
    ""
    "ingress:"
    "  - hostname: $Hostname"
    "    service: http://127.0.0.1:$BackendPort"
    "  - service: http_status:404"
) -join "`n"
$configYaml | Set-Content $ConfigFile -Encoding utf8
Write-Host "Wrote $ConfigFile" -ForegroundColor Green

Write-Host ""
Write-Host "Step 3: Route DNS $Hostname -> tunnel '$TunnelName'..." -ForegroundColor Cyan
$routeOut = & cloudflared tunnel route dns $TunnelName $Hostname 2>&1 | Out-String
Write-Host $routeOut
if ($LASTEXITCODE -ne 0 -and $routeOut -notmatch 'already exists') {
    throw "DNS route failed. Ensure the domain is on Cloudflare and the hostname is valid."
}

$publicBase = "https://$Hostname"
Set-EnvKey "NEXUS_TUNNEL_MODE" "named"
Set-EnvKey "NEXUS_TUNNEL_NAME" $TunnelName
Set-EnvKey "PUBLIC_TUNNEL_BASE" $publicBase
Set-EnvKey "NEXUS_TUNNEL_ENABLED" "true"

Write-Host ""
Write-Host "Done. Stable tunnel URL:" -ForegroundColor Green
Write-Host "  $publicBase"
Write-Host ""
Write-Host "Meta WhatsApp webhook (set once in Meta Developer Console):" -ForegroundColor Cyan
Write-Host "  $publicBase/api/webhook"
Write-Host ""
Write-Host "Verify token: WEBHOOK_VERIFY_TOKEN in backend/.env"
Write-Host "Subscribe to the 'messages' field on your WhatsApp Business Account."
Write-Host ""
Write-Host "Start dev stack: .\dev.ps1"
