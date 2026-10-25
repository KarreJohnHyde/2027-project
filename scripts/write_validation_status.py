"""Writes model_registry/validation_status.json from the live registry gates.

Both gates are recomputed (checkpoint files are re-hashed): clinical activation, which
requires VALIDATED with a complete bundle, and research-only inference. Run from the
repository root with the backend environment: python scripts/write_validation_status.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.model_registry import list_models  # noqa: E402


def main() -> int:
    registry = list_models()
    models = []
    for model in registry["models"]:
        entry = {
            "model_id": model["model_id"], "status": model["status"], "registry_state": model["registry_state"],
            "validated": model.get("validated", False), "supported_modalities": model.get("supported_modalities", []),
            "clinical_activation": {"eligible": model["activation"]["eligible"], "blockers": model["activation"]["blockers"]},
        }
        if "research_gate" in model:
            entry["research_inference"] = model["research_gate"]
            entry["held_out_evaluation"] = model.get("held_out_evaluation")
            entry["evaluation_report_path"] = model["artifact_bundle"].get("evaluation_report_path")
            entry["checkpoint_sha256"] = model["artifact_bundle"].get("checkpoint_sha256")
        models.append(entry)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/write_validation_status.py",
        "summary": {
            "models": len(models),
            "clinically_activatable": sum(1 for item in models if item["clinical_activation"]["eligible"]),
            "research_runnable": sum(1 for item in models if item.get("research_inference", {}).get("allowed")),
        },
        "definitions": {
            "clinical_activation": "Requires status VALIDATED, validated=true, a complete artifact bundle, verified licence and matching checkpoint hash.",
            "research_inference": "Requires research_inference=true, READY_UNVALIDATED or VALIDATED, verified licence, evaluation report and matching checkpoint hash. Outputs are research-only.",
        },
        "models": models,
    }
    target = ROOT / "model_registry" / "validation_status.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}: {payload['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
