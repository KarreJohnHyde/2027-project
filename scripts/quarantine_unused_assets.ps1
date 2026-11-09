# Reversible alternative to permanent removal. Uses only the previously audited plan.
param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath('D:\project')
$quarantineRoot = [IO.Path]::GetFullPath('D:\MedTwin_Removed_Datasets_2026-11-06\additional-cleanup')
$auditRoot = Join-Path $projectRoot 'artifacts\audits\cleanup-2026-11-06'
$plan = Get-Content -LiteralPath (Join-Path $auditRoot 'plan.json') -Raw | ConvertFrom-Json
$moves = @()
foreach ($item in $plan.items) {
    $source = [IO.Path]::GetFullPath($item.path)
    # The earlier quarantine is already outside the project; leave it alone.
    if ($source -eq 'D:\MedTwin_Removed_Datasets_2026-11-06') { continue }
    $prefix = $projectRoot.TrimEnd('\') + '\'
    if (-not $source.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Source outside project: $source"
    }
    $relative = $source.Substring($prefix.Length)
    $destination = [IO.Path]::GetFullPath((Join-Path $quarantineRoot $relative))
    if (-not $destination.StartsWith($quarantineRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Destination outside quarantine: $destination"
    }
    if (Test-Path -LiteralPath $destination) { throw "Destination already exists: $destination" }
    if (-not (Test-Path -LiteralPath $source)) { throw "Source missing: $source" }
    if ((Get-Item -LiteralPath $source -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Source is a filesystem link: $source"
    }
    $moves += [pscustomobject]@{from=$source; to=$destination; bytes=$item.bytes; reason=$item.reason}
}
if ($DryRun) { $moves | Format-Table from,to; return }
$result = [pscustomobject]@{status='MOVING'; moved=@(); retained_previous_quarantine='D:\MedTwin_Removed_Datasets_2026-11-06'; reclaimed_bytes=0}
foreach ($move in $moves) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $move.to) | Out-Null
    Move-Item -LiteralPath $move.from -Destination $move.to -ErrorAction Stop
    if ((Test-Path -LiteralPath $move.from) -or -not (Test-Path -LiteralPath $move.to)) {
        throw "Move could not be verified: $($move.from)"
    }
    $result.moved += $move
    $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $auditRoot 'result.json') -Encoding utf8
    Write-Output "Moved $($move.from)"
}
$result.status='REMOVED_FROM_PROJECT_REVERSIBLY'
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $auditRoot 'result.json') -Encoding utf8
