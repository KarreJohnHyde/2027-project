<#
.SYNOPSIS
  Audits, deduplicates and safely extracts the 24 named MedTwin source archives.
.DESCRIPTION
  Wrapper for scripts/archive_audit_and_extract.py using the project venv.
  Default is audit-only; pass -Extract to extract archives that are safe and not
  already present. Outputs: docs/import/ARCHIVE_MANIFEST.csv, ARCHIVE_REPORT.md,
  docs/import/inventories/, dataset_registry/imported.json and
  logs/archive_import_redacted.log. Re-running is idempotent.
.EXAMPLE
  .\scripts\import_archives.ps1 -Extract
#>
param(
    [string]$Source = "C:\Users\johnn\Downloads",
    [string]$Destination = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "_imports\archives"),
    [switch]$Extract,
    [double]$MinFreeGB = 15,
    [string[]]$Only
)
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Project venv not found at $python" }
$arguments = @("-I", (Join-Path $PSScriptRoot "archive_audit_and_extract.py"), "--source", $Source, "--dest", $Destination, "--min-free-gb", $MinFreeGB)
if ($Extract) { $arguments += "--extract" }
if ($Only) { $arguments += "--only"; $arguments += $Only }
& $python @arguments
exit $LASTEXITCODE
