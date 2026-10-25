<#
.SYNOPSIS
  Runs the MedTwin verification suite and records what actually executed.

.DESCRIPTION
  Steps: backend pytest, frontend typecheck / lint / production build, privacy scan of
  the working tree (and Git history with -History), and optionally the browser
  walkthrough against the isolated QA stack (-Browser; starts scripts/dev.ps1 -Mode qa
  when no stack is running). Each step's command, exit code, duration and output tail
  are written to artifacts/verify/<UTC stamp>.json; nothing is reported as passed unless
  its command exited 0.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
  powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -Browser -History
  powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -Browser -BrowserSections "routes,validation"
  # A full browser run requires one public-research image binding for every runnable
  # image_2d registry entry; omitted/duplicate/model-mismatched bindings fail closed.
  powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -Browser -BrowserModelImages "gi_kvasir_seg_polyp_segmenter:ENDOSCOPY=D:\public-kvasir.jpg","hematology_cnmc_all_classifier:MICROSCOPY=D:\public-cnmc.bmp"
#>
param(
    [switch]$Browser,
    [switch]$History,
    [string]$BrowserSections = "",
    [string[]]$BrowserImages = @(),
    [string[]]$BrowserModelImages = @(),
    [string]$QaState = (Join-Path $env:TEMP "medtwin-qa")
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$outDir = Join-Path $Root "artifacts\verify"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$steps = New-Object System.Collections.Generic.List[object]

function Invoke-Step([string]$Name, [string]$WorkingDirectory, [string]$Command) {
    Write-Host "==> $Name"
    $watch = [Diagnostics.Stopwatch]::StartNew()
    Push-Location $WorkingDirectory
    try {
        $output = & cmd.exe /d /c "$Command 2>&1"
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $tail = @($output | Select-Object -Last 25) -join "`n"
    $steps.Add([ordered]@{ name = $Name; command = $Command; cwd = $WorkingDirectory; exit_code = $code; passed = ($code -eq 0); seconds = [math]::Round($watch.Elapsed.TotalSeconds, 1); output_tail = $tail })
    Write-Host ("    {0} (exit {1}, {2:N1}s)" -f $(if ($code -eq 0) { "PASS" } else { "FAIL" }), $code, $watch.Elapsed.TotalSeconds)
}

Invoke-Step "backend-pytest" (Join-Path $Root "backend") "`"$Python`" -m pytest -q -p no:cacheprovider"
Invoke-Step "frontend-typecheck" $Root "npm run -s typecheck"
Invoke-Step "frontend-lint" $Root "npm run -s lint"
Invoke-Step "frontend-build" $Root "npm run -s build"
Invoke-Step "privacy-scan-tree" $Root "`"$Python`" -I scripts\privacy_scan.py --tree"
if ($History) { Invoke-Step "privacy-scan-history" $Root "`"$Python`" -I scripts\privacy_scan.py --history" }

if ($Browser) {
    $startedStack = $false
    if (-not (Test-Path (Join-Path $QaState "stack.json"))) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "dev.ps1") -Mode qa -StateDir $QaState -Fresh
        $startedStack = $LASTEXITCODE -eq 0
    }
    $imageArgs = ($BrowserImages | ForEach-Object { "--image `"$_`"" }) -join " "
    $modelImageArgs = ($BrowserModelImages | ForEach-Object { "--model-image `"$_`"" }) -join " "
    $sectionArgs = if ($BrowserSections) { "--sections `"$BrowserSections`"" } else { "" }
    $walkOut = Join-Path $QaState "walkthrough-$stamp"
    Invoke-Step "browser-walkthrough" (Join-Path $Root "tools\browser-qa") "node walkthrough.mjs --state `"$QaState`" --out `"$walkOut`" $sectionArgs $imageArgs $modelImageArgs"
    if ($startedStack) { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "dev.ps1") -Stop -StateDir $QaState | Out-Null }
}

$commit = (& git -C $Root rev-parse HEAD 2>$null)
$dirty = [bool](& git -C $Root status --porcelain 2>$null)
$summary = [ordered]@{ run_at = (Get-Date).ToUniversalTime().ToString("o"); git_commit = $commit; working_tree_dirty = $dirty; steps = $steps; all_passed = -not ($steps | Where-Object { -not $_.passed }) }
$report = Join-Path $outDir "$stamp.json"
$summary | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $report
Write-Host "Report: $report"
if (-not $summary.all_passed) { exit 1 }
