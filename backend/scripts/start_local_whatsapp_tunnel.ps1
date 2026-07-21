# Expose local backend (8002) via ngrok and register Meta WhatsApp webhook.
# Use when running: .\dev.ps1 -NoTunnel
#
# Usage (from backend root):
#   .\scripts\start_local_whatsapp_tunnel.ps1

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path $PSScriptRoot -Parent
Set-Location $BackendRoot

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    throw "ngrok not found in PATH. Install ngrok, then retry."
}

$backendUp = Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue
if (-not $backendUp) {
    throw "Backend is not listening on 127.0.0.1:8002. Start .\dev.ps1 -NoTunnel first."
}

Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Start-Process -FilePath "ngrok" -ArgumentList @("http", "127.0.0.1:8002", "--log=stdout") -WindowStyle Hidden
Write-Host "Waiting for ngrok public URL..." -ForegroundColor Cyan

$publicUrl = $null
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $tunnels = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
        $https = $tunnels.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
        if ($https -and $https.public_url) {
            $publicUrl = $https.public_url.TrimEnd("/")
            break
        }
    } catch {
        # ngrok API not ready yet
    }
}

if (-not $publicUrl) {
    throw "Could not read ngrok public URL from http://127.0.0.1:4040/api/tunnels"
}

Write-Host "Tunnel: $publicUrl" -ForegroundColor Green

$python = Join-Path $BackendRoot ".venv\Scripts\python.exe"
& $python "scripts/sync_whatsapp_webhook.py" --callback-url "$publicUrl/api/webhook"
if ($LASTEXITCODE -ne 0) {
    throw "Webhook sync failed."
}

Write-Host ""
Write-Host "Inbound WhatsApp replies should now appear on AI Active." -ForegroundColor Green
Write-Host "Keep this ngrok process running while you test." -ForegroundColor DarkGray
