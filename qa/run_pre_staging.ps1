# Nexus pre-staging QA orchestrator (Windows PowerShell)
# Runs Phases 1–5, writes reports under qa/reports/<timestamp>/
param(
    [switch]$SkipPlaywright,
    [switch]$SkipPytest,
    [switch]$SkipLoad
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Out = Join-Path $Root "qa\reports\$Stamp"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$failures = @()
function Invoke-Step($Name, $ScriptBlock) {
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    try {
        & $ScriptBlock
        Write-Host "PASS: $Name" -ForegroundColor Green
        "$Name=PASS" | Add-Content (Join-Path $Out "summary.txt")
    } catch {
        Write-Host "FAIL: $Name — $($_.Exception.Message)" -ForegroundColor Red
        "$Name=FAIL $($_.Exception.Message)" | Add-Content (Join-Path $Out "summary.txt")
        $script:failures += $Name
    }
}

# Phase 0 — Staging post-deploy / pre-BAU smoke (sequences, Meta booking templates, TOEFL)
Invoke-Step "Phase0 Staging smoke gates" {
    Push-Location (Join-Path $Root "backend")
    try {
        $uatEnv = Join-Path $Root "uat\.env"
        if (Test-Path $uatEnv) {
            Get-Content $uatEnv | ForEach-Object {
                if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
                $parts = $_.Split('=', 2)
                if ($parts.Length -eq 2) {
                    [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
                }
            }
        }
        $base = $env:STAGING_SMOKE_BASE_URL
        if (-not $base) { $base = $env:UAT_BASE_URL }
        if (-not $base) { $base = "http://127.0.0.1:5175" }
        & .\.venv\Scripts\python.exe scripts\staging_post_deploy_smoke.py --base-url $base
        if ($LASTEXITCODE -ne 0) { throw "staging_post_deploy_smoke exit $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}

# Phase 2+3+4 — Pytest QA package
if (-not $SkipPytest) {
    Invoke-Step "Phase2-4 Pytest (API/WhatsApp/RBAC)" {
        Push-Location (Join-Path $Root "backend")
        try {
            $pytestOut = Join-Path $Out "pytest-qa"
            New-Item -ItemType Directory -Force -Path $pytestOut | Out-Null
            & .\.venv\Scripts\python.exe -m pytest tests/qa test_university_matching_service.py test_security_audit_controls.py test_bootstrap_alembic.py `
                --junitxml=(Join-Path $pytestOut "junit.xml") `
                -q --tb=short
            if ($LASTEXITCODE -ne 0) { throw "pytest exit $LASTEXITCODE" }
        } finally {
            Pop-Location
        }
    }
}

# Phase 5 load
if (-not $SkipLoad) {
    Invoke-Step "Phase5 Shortlist load" {
        Push-Location (Join-Path $Root "backend")
        try {
            & .\.venv\Scripts\python.exe (Join-Path $Root "qa\load\shortlist_load.py")
            if ($LASTEXITCODE -ne 0) { throw "load exit $LASTEXITCODE" }
        } finally {
            Pop-Location
        }
    }
}

# Phase 1 SIT + Phase 5 E2E (Playwright)
if (-not $SkipPlaywright) {
    Invoke-Step "Phase1+5 Playwright SIT/E2E UAT" {
        Push-Location (Join-Path $Root "uat")
        try {
            if (-not (Test-Path ".env")) { throw "uat/.env missing — set UAT_BASE_URL, UAT_EMAIL, UAT_PASSWORD" }
            & npm test
            if ($LASTEXITCODE -ne 0) { throw "playwright exit $LASTEXITCODE" }
            & npm run summary
            Copy-Item reports\results.json (Join-Path $Out "playwright-results.json") -Force -ErrorAction SilentlyContinue
            Copy-Item reports\summary.md (Join-Path $Out "playwright-summary.md") -Force -ErrorAction SilentlyContinue
        } finally {
            Pop-Location
        }
    }
}

Write-Host ""
Write-Host "=== UAT Summary ===" -ForegroundColor Cyan
$uatSummary = Join-Path $Root "uat\reports\summary.md"
if (Test-Path $uatSummary) {
    Get-Content $uatSummary | Write-Host
    Copy-Item $uatSummary (Join-Path $Out "playwright-summary.md") -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "(No uat/reports/summary.md yet — Playwright may have been skipped.)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Reports folder: $Out"
if ($failures.Count -eq 0) {
    Write-Host "ALL PHASES GREEN — ready for staging gate" -ForegroundColor Green
    "OVERALL=PASS" | Add-Content (Join-Path $Out "summary.txt")
    exit 0
}

Write-Host "FAILED PHASES: $($failures -join ', ')" -ForegroundColor Red
"OVERALL=FAIL" | Add-Content (Join-Path $Out "summary.txt")
exit 1
