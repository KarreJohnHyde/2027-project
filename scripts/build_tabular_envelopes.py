"""Write the input envelope of every UCI tabular research model and record it in its registry bundle.

The envelope comes from the development part only (the same seeded split as training): for each numeric feature the
observed minimum and maximum and its missing share; for each categorical feature the categories seen. Serving refuses
values outside it (often a units mistake, and in any case outside the model's evidence). No checkpoint is changed.

  python scripts/build_tabular_envelopes.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_training import tabular  # noqa: E402
from ml_training.common import REPORTS, relative  # noqa: E402


def envelope(name: str, spec: dict) -> dict:
    features, y, groups, target = spec["load"]()
    dev = tabular.split(y, groups.astype(str), features) == "train"
    rows = features[dev]
    fields = []
    for column in features.columns:
        series = rows[column]
        missing = float(series.isna().mean())
        if pd.api.types.is_numeric_dtype(series):
            field = {"name": column, "type": "number", "min": float(series.min()), "max": float(series.max()),
                     "development_missing_share": round(missing, 4), "may_be_blank": missing > 0}
            observed = series.dropna().unique()
            # A coded field (few whole-number values, e.g. sex 0/1 or chest-pain type 1-4) accepts only its observed codes.
            if len(observed) <= 10 and all(float(value).is_integer() for value in observed):
                field["allowed_values"] = sorted(float(value) for value in observed)
            fields.append(field)
        else:
            fields.append({"name": column, "type": "category", "categories": sorted(str(v) for v in series.dropna().unique()),
                           "development_missing_share": round(missing, 4), "may_be_blank": missing > 0})
    return {"model_id": spec["model_id"], "target": target, "source": f"UCI dataset {spec['uci']} (development part only, seed {tabular.SEED})",
            "units": "as defined in the UCI dataset documentation for this table", "development_rows": int(dev.sum()), "fields": fields,
            "rules": ["values outside the development range are refused", "coded fields accept only their development codes",
                      "unknown categories are refused",
                      "blank values are imputed only for fields that were blank in development; more than half blank is refused"]}


def main() -> int:
    registry_path = ROOT / "model_registry" / "models.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for name, spec in tabular.COHORTS.items():
        data = envelope(name, spec)
        path = REPORTS / f"{spec['model_id']}_input_envelope.json"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for model in registry["models"]:
            if model["model_id"] == spec["model_id"]:
                model["artifact_bundle"]["input_envelope_path"] = relative(path)
                model["artifact_bundle"]["input_envelope_sha256"] = digest
        print(f"{spec['model_id']}: {len(data['fields'])} fields from {data['development_rows']} development rows")
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
