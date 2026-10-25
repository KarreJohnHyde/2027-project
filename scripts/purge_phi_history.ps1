<#
.SYNOPSIS
  Removes the embedded patient laboratory reports from all Git history.

.DESCRIPTION
  Irreversible for the repository (commit IDs change). Runs only with the exact
  authorization phrase. The privacy owner must also supply and explicitly approve
  a pre-existing encrypted/access-controlled backup directory. Steps: precondition
  checks, verified bundle backup, git-filter-repo blob rewrite in an isolated venv,
  reflog expiry and garbage collection, then a redacted history scan that must
  report no findings. This script never pushes. See
  docs/security/PHI_RELEASE_BLOCKER.md.

.EXAMPLE
  .\scripts\purge_phi_history.ps1 -Authorization "I AUTHORIZE REWRITING MEDTWIN GIT HISTORY" -BackupDir "X:\approved-encrypted-evidence" -SecureBackupApproved
#>
param(
    [Parameter(Mandatory = $true)][string]$Authorization,
    [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$BackupDir = "",
    [switch]$SecureBackupApproved,
    [string]$ScannerPython = ""
)
$Phrase = "I AUTHORIZE REWRITING MEDTWIN GIT HISTORY"
if ($Authorization -cne $Phrase) { throw "Authorization phrase does not match; nothing was changed." }
if (-not $SecureBackupApproved -or -not $BackupDir) {
    throw "A privacy-owner-approved encrypted/access-controlled BackupDir and -SecureBackupApproved are required; nothing was changed."
}
if (-not $ScannerPython) { $ScannerPython = Join-Path $Repo ".venv\Scripts\python.exe" }

# Native tools write progress to stderr; judge success by exit code only.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -ne 0) { throw "$Exe $($Arguments -join ' ') failed with exit code $code" }
}
function Invoke-Git { Invoke-Native "git" (@("-C", $Repo) + $args) }

# 1. Preconditions
if (git -C $Repo status --porcelain --untracked-files=no) { throw "Tracked changes are uncommitted; commit or stash them first." }
$remotes = git -C $Repo remote
if ($remotes) { Write-Warning "Remotes exist ($($remotes -join ', ')). Rewritten history needs a coordinated force-push and every clone deleted; this script never pushes." }

# 2. Backup. This bundle contains the sensitive history. Never create it in an
# ordinary folder: the operator must provision and approve its controls first.
if (-not (Test-Path -LiteralPath $BackupDir -PathType Container)) {
    throw "BackupDir must be a pre-existing approved directory; nothing was changed."
}
$BackupDir = (Resolve-Path -LiteralPath $BackupDir).Path
$resolvedRepo = (Resolve-Path -LiteralPath $Repo).Path
$resolvedTemp = (Resolve-Path -LiteralPath $env:TEMP).Path
if ($BackupDir.StartsWith($resolvedRepo, [System.StringComparison]::OrdinalIgnoreCase) -or
    $BackupDir.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupDir must not be inside the repository or temporary directory; nothing was changed."
}
$bundle = Join-Path $BackupDir ("medtwin-pre-purge-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".bundle")
Invoke-Git bundle create $bundle --all
Invoke-Git bundle verify $bundle
Write-Host "Backup bundle: $bundle (contains the identifiers; protect it and delete it after verification)"

# 3. Rewrite with git-filter-repo in an isolated environment
$venv = Join-Path $env:TEMP "medtwin-filter-repo"
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Invoke-Native "uv" @("venv", $venv, "--python", "3.12", "--quiet") }
Invoke-Native "uv" @("pip", "install", "--python", $venvPython, "--quiet", "git-filter-repo==2.47.0")
try { Invoke-Native $venvPython @((Join-Path $PSScriptRoot "purge_phi_history.py"), "--repo", $Repo) }
catch { throw "History rewrite failed ($_); restore from $bundle if needed." }

# 4. Drop every remaining reference to the old objects
Invoke-Git reflog expire --expire=now --expire-unreachable=now --all
Invoke-Git gc --prune=now --quiet
Invoke-Git fsck --full --no-progress

# 5. Verify
try { Invoke-Native $ScannerPython @("-I", (Join-Path $PSScriptRoot "privacy_scan.py"), "--repo", $Repo, "--history", "--report", (Join-Path $Repo "logs\privacy\post-purge.json")) }
catch { throw "Post-purge scan still reports findings; see logs\privacy\post-purge.json." }
Write-Host "History purge verified. Old-to-new commit map: $Repo\.git\filter-repo\commit-map"
Write-Host "Next: update commit IDs cited in docs, delete $bundle once satisfied, and delete any other clones or copies."
