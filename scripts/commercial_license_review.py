"""Inventory commercial-rights prerequisites; never manufacture an approval."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / "model_registry/commercial_review.json"
previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"models": []}
existing = {item["model_id"]: item for item in previous["models"]}
rows = []
for model in json.loads((ROOT / "model_registry/models.json").read_text(encoding="utf-8"))["models"]:
    bundle = model["artifact_bundle"]
    checksum = bundle.get("checkpoint_sha256")
    old = existing.get(model["model_id"])
    if old and old.get("checkpoint_sha256") == checksum:
        rows.append(old)
        continue
    rows.append({"model_id": model["model_id"], "checkpoint_sha256": checksum,
                 "declared_data_terms": bundle.get("dataset_license"), "source_repository": model.get("source_repository"),
                 "source_data_rights": "NOT_REVIEWED", "code_rights": "NOT_REVIEWED", "weights_rights": "NOT_REVIEWED",
                 "redistribution_rights": "NOT_REVIEWED", "reviewer": None, "reviewed_at": None,
                 "declared_use": None, "evidence_files": [], "clinical_approval": "NOT_ESTABLISHED"})
target.write_text(json.dumps({"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                             "notice": "Inventory and execution gate; not legal clearance, regulatory approval or clinical validation.",
                             "models": rows}, indent=2) + "\n", encoding="utf-8")
print(f"Inventoried {len(rows)} model entries; no new commercial approval granted")
