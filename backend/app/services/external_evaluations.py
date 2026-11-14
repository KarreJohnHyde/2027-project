"""Read-only summaries of saved external evaluations of registered models.

An external evaluation here is a research measurement on a public cohort that the model was not trained on, written by an
evaluation script such as ``scripts/evaluate_head_ct_cq500.py``. It is never clinical validation. A saved result is
attached to a registry entry only when it measured the checkpoint that entry registers now (same SHA-256): a result for
an earlier or different checkpoint says nothing about the current one and is left out.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

EVALUATION_DIR = PROJECT_ROOT / "docs" / "validation" / "models"


def _metric(values: dict[str, Any], prefix: str) -> float | None:
    for key, value in values.items():
        if key.startswith(prefix) and isinstance(value, (int, float)):
            return float(value)
    return None


def _label(name: str, values: dict[str, Any]) -> dict[str, Any]:
    interval = values.get("auroc_ci95") or {}
    return {
        "label": name,
        "positives": values.get("positives"),
        "negatives": values.get("negatives"),
        "auroc": values.get("auroc"),
        "auroc_ci95": [interval["low"], interval["high"]] if interval.get("status") == "COMPUTED" else None,
        "sensitivity": _metric(values, "sensitivity"),
        "specificity": _metric(values, "specificity"),
    }


@lru_cache(maxsize=64)
def _read(path: str, _mtime_ns: int) -> dict[str, Any] | None:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cohort = payload.get("cohort") if isinstance(payload, dict) else None
    if not isinstance(cohort, dict) or not isinstance(payload.get("models"), dict) or "dataset" not in payload:
        return None
    # A file that does not state it is not clinical validation is not shown as an external evaluation at all.
    if cohort.get("clinical_validation") is not False:
        return None
    return payload


def _evaluation_files() -> list[Path]:
    try:
        return sorted(path for path in EVALUATION_DIR.glob("*.json") if path.is_file())
    except OSError:
        return []


def external_evaluations_for(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Summaries of saved external evaluations that measured this model's registered checkpoint."""
    registered = str((model.get("artifact_bundle") or {}).get("checkpoint_sha256") or "").lower()
    if not registered:
        return []
    found = []
    for path in _evaluation_files():
        payload = _read(str(path), path.stat().st_mtime_ns)
        if payload is None or model["model_id"] not in payload["models"]:
            continue
        evaluated = str((payload.get("checkpoint_sha256") or {}).get(model["model_id"]) or "").lower()
        if evaluated != registered:
            continue
        result = payload["models"][model["model_id"]]
        cohort = payload["cohort"]
        found.append({
            "dataset": payload["dataset"],
            "reference_standard": payload.get("reference"),
            "scope": cohort.get("scope"),
            "expected_reference_scans": cohort.get("expected_reference_scans"),
            "excluded": [{"scan": scan, "reason": detail.get("reason")}
                         for scan, detail in (cohort.get("excluded_source_defects") or {}).items()],
            "series_selection": payload.get("series_selection"),
            "scans": result.get("scans"),
            "scored": result.get("scored"),
            "refused": result.get("refused"),
            "labels": [_label(name, values) for name, values in (result.get("per_label") or {}).items()],
            "threshold_policy": payload.get("threshold_policy"),
            "metric_population": payload.get("metric_population"),
            "checkpoint_sha256": evaluated,
            "report_path": path.relative_to(PROJECT_ROOT).as_posix() if path.is_relative_to(PROJECT_ROOT) else path.name,
            "clinical_validation": False,
        })
    return found
