# Push NEXUS to GitHub and optionally trigger VPS deploy.
#
# Usage:
#   .\backend\deploy\push-and-deploy.ps1
#   .\backend\deploy\push-and-deploy.ps1 -Message "fix webhook" -VpsHost root@YOUR_VPS_IP
#
param(
    [string]$Message = "Update NEXUS",
    [string]$VpsHost = "",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")

Set-Location $Root

if (-not (Test-Path (Join-Path $Root ".git"))) {
    Write-Host "Initializing git repository..." -ForegroundColor Cyan
    git init
    git branch -M $Branch
}

$status = git status --porcelain
if ($status) {
    git add .
    git commit -m $Message
} else {
    Write-Host "No local changes to commit." -ForegroundColor DarkGray
}

$remotes = git remote
if ($remotes -notcontains "origin") {
    Write-Host ""
    Write-Host "No 'origin' remote. Add your GitHub repo:" -ForegroundColor Yellow
    Write-Host "  git remote add origin https://github.com/YOUR_USER/nexus.git"
    Write-Host "  git push -u origin $Branch"
    exit 1
}

git push origin $Branch

if ($VpsHost) {
    Write-Host ""
    Write-Host "Deploying on VPS..." -ForegroundColor Cyan
    ssh $VpsHost "sudo bash /var/www/nexus/backend/deploy/deploy.sh"
}

Write-Host ""
Write-Host "Done. Pushed to origin/$Branch" -ForegroundColor Green
if (-not $VpsHost) {
    Write-Host "On VPS run: sudo bash /var/www/nexus/backend/deploy/deploy.sh"
}
