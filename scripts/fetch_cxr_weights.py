"""Fetch the TorchXRayVision chest-radiograph weights MedTwin's research chest X-ray model uses.

Downloads, once, from the library's GitHub release (github.com/mlmed/torchxrayvision, tag v1)
into artifacts/third_party/torchxrayvision (not in Git), then prints each file's SHA-256 for
model_registry/models.json. MedTwin never downloads weights while serving: without these
files the model reports WEIGHTS_MISSING.

  .venv\\Scripts\\python.exe scripts\\fetch_cxr_weights.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.cxr_research import WEIGHTS_DIR, WEIGHT_FILES  # noqa: E402


def main() -> None:
    import torchxrayvision as xrv

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    cache = str(WEIGHTS_DIR)
    xrv.models.DenseNet(weights="densenet121-res224-all", cache_dir=cache)
    xrv.baseline_models.chestx_det.PSPNet(cache_dir=cache)
    xrv.autoencoders.ResNetAE(weights="101-elastic", cache_dir=cache)
    for role, name in WEIGHT_FILES.items():
        path = WEIGHTS_DIR / name
        print(f"{role}: {name} {path.stat().st_size} bytes sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
