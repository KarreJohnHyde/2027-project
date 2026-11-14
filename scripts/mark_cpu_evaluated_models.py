"""Record evaluation_device "cpu" on registry entries whose held-out evaluation ran on CPU (2026-11-14 CPU queues).

Only models whose run config shows CUDA was unavailable are marked. Serving then reproduces float32 instead of the
CUDA autocast precision assumed for older GPU-trained checkpoints.

  python scripts/mark_cpu_evaluated_models.py <model_id> [...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(model_ids: list[str]) -> int:
    path = ROOT / "model_registry" / "models.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    for model in registry["models"]:
        if model["model_id"] not in model_ids:
            continue
        run_dir = (ROOT / model["artifact_bundle"]["checkpoint_path"]).parent
        config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        environment = json.dumps(config.get("environment", {})).lower()
        if '"cuda_available": true' in environment.replace(" ", "") or config.get("config", {}).get("device") == "cuda":
            print(f"{model['model_id']}: run config shows CUDA; not marked")
            continue
        model["evaluation_device"] = "cpu"
        print(f"{model['model_id']}: evaluation_device = cpu ({run_dir.name})")
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
