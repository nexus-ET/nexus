# Promote latest NEXUS code from develop (E:\NEXUS) to staging (E:\NEXUS-staging / GitHub staging branch).
#
# Uses git worktrees: develop lives in the main folder; staging lives in NEXUS-staging.
# Secrets (.env) are gitignored and are NOT copied — adjust staging .env manually on each server.
#
# Usage:
#   .\backend\deploy\promote-to-staging.ps1
#   .\backend\deploy\promote-to-staging.ps1 -Message "WhatsApp intake fixes"
#   .\backend\deploy\promote-to-staging.ps1 -VpsHost root@187.127.186.63
#   .\backend\deploy\promote-to-staging.ps1 -SkipDevelopPush -DryRun
#
param(
    [string]$Message = "Promote develop to staging",
    [string]$DevelopRoot = "E:\NEXUS",
    [string]$StagingRoot = "E:\NEXUS-staging",
    [string]$DevelopBranch = "develop",
    [string]$StagingBranch = "staging",
    [string]$VpsHost = "",
    [switch]$SkipDevelopPush,
    [switch]$SkipDeploy,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [string]$WorkDir,
        [string[]]$GitArgs
    )
    Push-Location $WorkDir
    try {
        Write-Host "  git $($GitArgs -join ' ')" -ForegroundColor DarkGray
        if ($DryRun) { return }
        & git @GitArgs
        if ($LASTEXITCODE -ne 0) {
            throw "git $($GitArgs -join ' ') failed with exit $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

Write-Host "=== NEXUS: promote $DevelopBranch -> $StagingBranch ===" -ForegroundColor Green
Write-Host "  Develop:  $DevelopRoot"
Write-Host "  Staging:  $StagingRoot"
if ($DryRun) {
    Write-Host "  DRY RUN — no commits, merges, or pushes will be made." -ForegroundColor Yellow
}

if (-not (Test-Path $DevelopRoot)) {
    throw "Develop root not found: $DevelopRoot"
}
if (-not (Test-Path $StagingRoot)) {
    Write-Host ""
    Write-Host "Staging worktree not found. Run once from develop root:" -ForegroundColor Yellow
    Write-Host "  .\setup-instances.ps1"
    exit 1
}

# --- 1. Commit & push develop -------------------------------------------------
Set-Location $DevelopRoot
$developBranch = git branch --show-current
if ($developBranch -ne $DevelopBranch) {
    Write-Host ""
    Write-Host "WARNING: $DevelopRoot is on '$developBranch', expected '$DevelopBranch'." -ForegroundColor Yellow
}

$developStatus = git status --porcelain
if ($developStatus) {
    Write-Host ""
    Write-Host "Committing uncommitted changes on $DevelopBranch ..." -ForegroundColor Cyan
    Invoke-Git $DevelopRoot @("add", "-A")
    Invoke-Git $DevelopRoot @("commit", "-m", $Message)
} else {
    Write-Host ""
    Write-Host "No uncommitted changes on $DevelopBranch." -ForegroundColor DarkGray
}

$remotes = git remote
if ($remotes -notcontains "origin") {
    Write-Host ""
    Write-Host "No 'origin' remote. Add GitHub first:" -ForegroundColor Yellow
    Write-Host "  git remote add origin https://github.com/nexus-ET/nexus.git"
    exit 1
}

if (-not $SkipDevelopPush) {
    Write-Host ""
    Write-Host "Pushing $DevelopBranch to origin ..." -ForegroundColor Cyan
    Invoke-Git $DevelopRoot @("push", "origin", $DevelopBranch)
} else {
    Write-Host ""
    Write-Host "Skipping push of $DevelopBranch (-SkipDevelopPush)." -ForegroundColor DarkGray
}

# --- 2. Merge develop into staging worktree -----------------------------------
Set-Location $StagingRoot
$stagingBranch = git branch --show-current
if ($stagingBranch -ne $StagingBranch) {
    throw "Staging worktree is on '$stagingBranch', expected '$StagingBranch'. Check $StagingRoot"
}

$stagingStatus = git status --porcelain
if ($stagingStatus) {
    Write-Host ""
    Write-Host "Staging worktree has uncommitted changes:" -ForegroundColor Yellow
    git status --short
    throw "Commit or stash staging changes before promoting, or reset the staging worktree."
}

Write-Host ""
Write-Host "Fetching origin ..." -ForegroundColor Cyan
Invoke-Git $StagingRoot @("fetch", "origin", $DevelopBranch, $StagingBranch)

Write-Host ""
Write-Host "Merging $DevelopBranch into $StagingBranch ..." -ForegroundColor Cyan
try {
    Invoke-Git $StagingRoot @("merge", "origin/$DevelopBranch", "-m", $Message)
} catch {
    Write-Host ""
    Write-Host "Merge failed — resolve conflicts in $StagingRoot then run:" -ForegroundColor Red
    Write-Host "  cd $StagingRoot"
    Write-Host "  git merge --continue"
    Write-Host "  git push origin $StagingBranch"
    throw
}

# --- 3. Push staging to GitHub ------------------------------------------------
Write-Host ""
Write-Host "Pushing $StagingBranch to origin ..." -ForegroundColor Cyan
Invoke-Git $StagingRoot @("push", "origin", $StagingBranch)

# --- 4. Optional VPS deploy ---------------------------------------------------
if ($VpsHost -and -not $SkipDeploy) {
    Write-Host ""
    Write-Host "Deploying staging on VPS ($VpsHost) ..." -ForegroundColor Cyan
    if (-not $DryRun) {
        ssh $VpsHost "sudo bash /var/www/nexus/backend/deploy/deploy.sh"
    }
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "  GitHub: origin/$StagingBranch updated from $DevelopBranch"
Write-Host "  Local:  $StagingRoot is in sync"
if (-not $VpsHost -and -not $SkipDeploy) {
    Write-Host ""
    Write-Host "Deploy on Hostinger VPS:" -ForegroundColor Cyan
    Write-Host "  ssh root@YOUR_VPS_IP `"sudo bash /var/www/nexus/backend/deploy/deploy.sh`""
    Write-Host "Or re-run with: .\backend\deploy\promote-to-staging.ps1 -VpsHost root@YOUR_VPS_IP"
}
Write-Host ""
Write-Host "Note: .env files are not in git. Copy or verify staging secrets on the server separately."
