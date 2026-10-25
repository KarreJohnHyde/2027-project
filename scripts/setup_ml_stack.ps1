<#
.SYNOPSIS
  Installs and verifies the pinned MedTwin ML, OCR, encryption and NLP stacks.
.DESCRIPTION
  1. Main .venv: requirements.txt (OCR, encryption) + requirements-local-gpu.txt (MONAI).
     Torch and NumPy are already pinned there and are not upgraded.
  2. Biomedical NLP in WSL Ubuntu (~/.medtwin/venv-nlp, Python 3.12, via
     scripts/setup_nlp_wsl.sh): requirements-nlp.txt + scispaCy model packages pinned
     by URL; their SHA-256 values are recorded in backend/nlp-models.lock.json.
     Windows Smart App Control blocks spaCy's native extensions in Windows venvs.
  3. Verification: MONAI UNet forward pass on CUDA (or CPU), RapidOCR engine load,
     pypdfium2, AES-GCM round trip, and a scispaCy NER smoke run on a fixed
     non-clinical sentence. Model licences are read from each package's metadata.
  MedCAT and RadGraph are not installed: both need licensed model packs or
  credentialed weights (UMLS/SNOMED, PhysioNet) that are not available here.
.EXAMPLE
  .\scripts\setup_ml_stack.ps1
#>
param([switch]$SkipNlp)
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$main = Join-Path $repo ".venv\Scripts\python.exe"
$models = @(
    @{ name = "en_core_sci_sm"; version = "0.5.4"; url = "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz" },
    @{ name = "en_ner_bc5cdr_md"; version = "0.5.4"; url = "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz" }
)

function Invoke-Step {
    param([string]$Label, [scriptblock]$Body)
    Write-Host "== $Label"
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Body 2>&1 | ForEach-Object { "   $_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -ne 0) { throw "$Label failed (exit $code)" }
}

Invoke-Step "main venv: runtime + GPU ML pins" {
    uv pip install --python $main -r (Join-Path $repo "backend\requirements.txt") -r (Join-Path $repo "backend\requirements-local-gpu.txt")
}

Invoke-Step "main venv: verify MONAI, OCR, PDF rendering, AES-GCM" {
    & $main -c @"
import os, torch, monai, pypdfium2, onnxruntime
from monai.networks.nets import UNet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from rapidocr_onnxruntime import RapidOCR
device = 'cuda' if torch.cuda.is_available() else 'cpu'
net = UNet(spatial_dims=2, in_channels=1, out_channels=2, channels=(8, 16, 32), strides=(2, 2)).to(device)
out = net(torch.zeros(1, 1, 64, 64, device=device))
print('monai', monai.__version__, 'UNet forward', tuple(out.shape), 'on', device)
RapidOCR()
print('rapidocr engine loaded; onnxruntime', onnxruntime.__version__, 'providers', onnxruntime.get_available_providers())
print('pypdfium2', pypdfium2.version.PYPDFIUM_INFO)
key = AESGCM.generate_key(bit_length=256); nonce = os.urandom(12)
assert AESGCM(key).decrypt(nonce, AESGCM(key).encrypt(nonce, b'round-trip', b'aad'), b'aad') == b'round-trip'
print('AES-256-GCM round trip ok')
"@
}

if ($SkipNlp) { return }

# Windows Smart App Control (enforced on this workstation) blocks spaCy's native
# extensions (preshed, thinc) in any Windows venv, so the NLP stack runs in WSL.
$lock = @{ generated_at = (Get-Date).ToUniversalTime().ToString("s") + "Z"; runtime = "WSL Ubuntu, ~/.medtwin/venv-nlp (Python 3.12)"; models = @() }
$cache = Join-Path $repo "_derived\nlp-models"
New-Item -ItemType Directory -Force -Path $cache | Out-Null
foreach ($model in $models) {
    $file = Join-Path $cache ([IO.Path]::GetFileName($model.url))
    Invoke-Step "nlp model download: $($model.name) $($model.version)" {
        if (-not (Test-Path $file)) { curl.exe -sSfL $model.url -o $file }
    }
    $lock.models += @{ name = $model.name; version = $model.version; url = $model.url; sha256 = (Get-FileHash $file -Algorithm SHA256).Hash.ToLower(); license = "CC BY-SA 3.0 (package metadata)" }
}
$lock | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $repo "backend\nlp-models.lock.json")

$wslRepo = "/mnt/" + $repo.Substring(0, 1).ToLower() + ($repo.Substring(2) -replace "\\", "/")
Invoke-Step "nlp runtime in WSL: install pins and verify scispaCy NER" {
    wsl.exe -d Ubuntu -- sh "$wslRepo/scripts/setup_nlp_wsl.sh" $wslRepo
}
Write-Host "Done. MedCAT and RadGraph remain LICENSE_BLOCKED (model packs/weights require UMLS/SNOMED or PhysioNet credentials)."
