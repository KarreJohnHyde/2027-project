<#
  Installs the third-party research models' code into the main .venv: nnU-Net, TotalSegmentator and RadGraph,
  from the source trees in the project, with every package already in .venv held at its current version.
  Weights are not downloaded here (they are in artifacts/third_party; see docs/research/RESEARCH_CAPABILITY_BLOCKERS.md).

    powershell -File scripts/setup_third_party_models.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Constraints = Join-Path $env:TEMP "medtwin-venv-constraints.txt"

# Hold every installed package at its version; the install may only add packages.
(& uv pip freeze --python $Python) | Where-Object { $_ -match "==" } | Where-Object { $_ -notmatch "^(transformers|huggingface-hub|tokenizers|safetensors)==" } |
    Set-Content -Encoding ascii $Constraints
& uv pip install --python $Python -c $Constraints -r (Join-Path $Root "backend\requirements-third-party.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency install failed." }
& uv pip install --python $Python --no-deps (Join-Path $Root "nnUNet-master") (Join-Path $Root "TotalSegmentator-master")
if ($LASTEXITCODE -ne 0) { throw "nnU-Net / TotalSegmentator install failed." }

# Preserve upstream and omit its conflicting top-level tests package.
$Build = Join-Path $Root "_derived\vendor\radgraph-tf5-v2"
& $Python (Join-Path $Root "scripts\build_radgraph_tf5.py") --reuse-if-verified
if ($LASTEXITCODE -ne 0) { throw "RadGraph compatibility source verification failed." }
& uv pip install --python $Python --no-deps --reinstall-package radgraph $Build
if ($LASTEXITCODE -ne 0) { throw "RadGraph install failed." }
if (Test-Path (Join-Path $Root ".venv\Lib\site-packages\tests")) { throw "A top-level 'tests' package is installed; it would shadow backend/tests." }

& $Python -c "import totalsegmentator, nnunetv2, radgraph, transformers; print('totalsegmentator ok; radgraph ok; transformers', transformers.__version__)"
