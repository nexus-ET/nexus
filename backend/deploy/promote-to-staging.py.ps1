# Quick launcher (Windows) — same as promote-to-staging.ps1 but uses Python migration docs
param(
    [string]$Message = "Promote develop to staging",
    [string]$VpsHost = "",
    [switch]$DryRun,
    [switch]$SkipDevelopPush,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

$Args = @("$Root\backend\scripts\promote_to_staging.py", "--message", $Message)
if ($VpsHost) { $Args += @("--vps", $VpsHost) }
if ($DryRun) { $Args += "--dry-run" }
if ($SkipDevelopPush) { $Args += "--skip-develop-push" }
if ($SkipDeploy) { $Args += "--skip-deploy" }

& $Py @Args
