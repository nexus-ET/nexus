# One-time setup: two local NEXUS instances via git worktree.
#
#   E:\NEXUS          -> branch develop  -> .\backend\dev.ps1
#   E:\NEXUS-staging  -> branch staging  -> .\backend\staging-local.ps1
#
# Usage (from E:\NEXUS):
#   .\setup-instances.ps1
#
param(
    [string]$StagingRoot = "E:\NEXUS-staging"
)

$ErrorActionPreference = "Stop"
$DevRoot = $PSScriptRoot
$DevBackend = Join-Path $DevRoot "backend"
$StagingBackend = Join-Path $StagingRoot "backend"

function Invoke-Git {
    param([string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) { throw "git $($GitArgs -join ' ') failed with exit $LASTEXITCODE" }
}

function Test-GitBranch {
    param([string]$Name)
    git show-ref --verify --quiet "refs/heads/$Name" 2>$null
    return $LASTEXITCODE -eq 0
}

function Ensure-Venv {
    param([string]$BackendPath)
    $venvPython = Join-Path $BackendPath ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return }
    Write-Host "Creating venv in $BackendPath ..." -ForegroundColor Cyan
    Push-Location $BackendPath
    python -m venv .venv
    .\.venv\Scripts\pip.exe install --upgrade pip
    .\.venv\Scripts\pip.exe install -r requirements.txt
    .\.venv\Scripts\pip.exe install "psycopg[binary]"
    Pop-Location
}

function Ensure-FrontendDeps {
    param([string]$RepoRoot)
    $frontend = Join-Path $RepoRoot "frontend"
    if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
        Write-Host "npm install in $frontend ..." -ForegroundColor Cyan
        Push-Location $frontend
        npm install
        Pop-Location
    }
}

function Set-EnvKey {
    param([string]$EnvFile, [string]$Key, [string]$Value)
    if (-not (Test-Path $EnvFile)) { return }
    $lines = Get-Content $EnvFile
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

Write-Host "=== NEXUS two-instance setup ===" -ForegroundColor Green
Set-Location $DevRoot

$stashName = "setup-instances-$(Get-Date -Format 'yyyyMMddHHmmss')"
$hadStash = $false
$status = git status --porcelain
if ($status) {
    Write-Host "Stashing uncommitted changes ..." -ForegroundColor Yellow
    Invoke-Git @("stash", "push", "-u", "-m", $stashName)
    $hadStash = $true
}

if (-not (Test-GitBranch "develop")) {
    Invoke-Git @("branch", "develop")
    Write-Host "Created branch: develop" -ForegroundColor Green
}
if (-not (Test-GitBranch "staging")) {
    Invoke-Git @("branch", "staging")
    Write-Host "Created branch: staging" -ForegroundColor Green
}

Invoke-Git @("checkout", "develop")

if (-not (Test-Path $StagingRoot)) {
    Write-Host "Adding worktree at $StagingRoot (branch staging) ..." -ForegroundColor Cyan
    Invoke-Git @("worktree", "add", $StagingRoot, "staging")
} else {
    Write-Host "Worktree already exists: $StagingRoot" -ForegroundColor DarkGray
}

if ($hadStash) {
    Invoke-Git @("stash", "pop")
}

# Dev .env
$devEnv = Join-Path $DevBackend ".env"
if (-not (Test-Path $devEnv)) {
    Copy-Item (Join-Path $DevBackend ".env.development.example") $devEnv
    Write-Host "Created $devEnv from example - add your Neon dev DATABASE_URL." -ForegroundColor Yellow
} else {
    Set-EnvKey $devEnv "NEXUS_INSTANCE" "development"
    Set-EnvKey $devEnv "NEXUS_PORT" "8002"
    Set-EnvKey $devEnv "NEXUS_FRONTEND_PORT" "5175"
    Set-EnvKey $devEnv "NEXUS_TUNNEL_ENABLED" "true"
    Set-EnvKey $devEnv "FRONTEND_URL" "http://127.0.0.1:5175"
}

# Staging-local .env
$stagingEnv = Join-Path $StagingBackend ".env"
if (Test-Path $devEnv) {
    if (-not (Test-Path $stagingEnv)) {
        Copy-Item $devEnv $stagingEnv
        Write-Host "Copied dev .env -> staging-local .env (adjusting ports)." -ForegroundColor Cyan
    }
    Set-EnvKey $stagingEnv "NEXUS_INSTANCE" "staging-local"
    Set-EnvKey $stagingEnv "ENVIRONMENT" "staging"
    Set-EnvKey $stagingEnv "NEXUS_PORT" "8003"
    Set-EnvKey $stagingEnv "NEXUS_FRONTEND_PORT" "5176"
    Set-EnvKey $stagingEnv "NEXUS_TUNNEL_ENABLED" "false"
    Set-EnvKey $stagingEnv "FRONTEND_URL" "http://127.0.0.1:5176"
    Set-EnvKey $stagingEnv "PUBLIC_TUNNEL_BASE" "https://nexus-dev.edutrust.in"
    Write-Host "Staging-local .env ready at $stagingEnv" -ForegroundColor Green
    Write-Host "IMPORTANT: set a separate DATABASE_URL for staging Neon DB." -ForegroundColor Yellow
} elseif (-not (Test-Path $stagingEnv)) {
    Copy-Item (Join-Path $DevBackend ".env.staging.local.example") $stagingEnv
}

Ensure-Venv $DevBackend
Ensure-Venv $StagingBackend
Ensure-FrontendDeps $DevRoot
Ensure-FrontendDeps $StagingRoot

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "  DEV:            $DevRoot          (branch develop)"
Write-Host "                  cd backend; .\dev.ps1"
Write-Host "                  http://127.0.0.1:5175"
Write-Host ""
Write-Host "  STAGING-LOCAL:  $StagingRoot  (branch staging)"
Write-Host "                  cd backend; .\staging-local.ps1"
Write-Host "                  http://127.0.0.1:5176"
Write-Host ""
Write-Host "  HOSTINGER:      git push origin staging -> deploy on VPS"
Write-Host "  Open both in Cursor: NEXUS.code-workspace"
