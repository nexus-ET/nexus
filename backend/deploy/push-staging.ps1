# Push staging branch to GitHub and deploy to Hostinger VPS.
#
# Usage:
#   .\backend\deploy\push-staging.ps1
#   .\backend\deploy\push-staging.ps1 -Message "fix webhook" -VpsHost root@187.127.186.63
#
param(
    [string]$Message = "Update NEXUS staging",
    [string]$VpsHost = "",
    [string]$Branch = "staging"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")

Set-Location $Root

$current = git branch --show-current
if ($current -ne $Branch) {
    Write-Host "Switching to branch $Branch ..." -ForegroundColor Cyan
    git checkout $Branch
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
    Write-Host "  git remote add origin https://github.com/nexus-ET/nexus.git"
    Write-Host "  git push -u origin $Branch"
    exit 1
}

git push origin $Branch

if ($VpsHost) {
    Write-Host ""
    Write-Host "Deploying staging on VPS..." -ForegroundColor Cyan
    ssh $VpsHost "sudo bash /var/www/nexus/backend/deploy/deploy.sh"
}

Write-Host ""
Write-Host "Done. Pushed to origin/$Branch" -ForegroundColor Green
if (-not $VpsHost) {
    Write-Host "On VPS run: sudo bash /var/www/nexus/backend/deploy/deploy.sh"
}
