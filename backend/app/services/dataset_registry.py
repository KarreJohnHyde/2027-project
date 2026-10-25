"""Read-only access to the generated MedTwin dataset evidence registry."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_DATASET_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "dataset_registry" / "datasets.json"
)
DEFAULT_DATASET_TASK_AUDIT_PATH = (
    Path(__file__).resolve().parents[3] / "dataset_registry" / "tasks.json"
)


class DatasetRegistryUnavailableError(RuntimeError):
    """Raised when the generated registry cannot be read safely."""


class DatasetTaskAuditUnavailableError(RuntimeError):
    """Raised when the generated task audit cannot be read safely."""


def get_dataset_registry_path() -> Path:
    """Resolve an optional deployment override without accepting request input."""
    configured = os.getenv("DATASET_REGISTRY_PATH")
    return Path(configured).resolve() if configured else DEFAULT_DATASET_REGISTRY_PATH


def get_dataset_task_audit_path() -> Path:
    """Resolve the deployment-controlled task-audit path."""
    configured = os.getenv("DATASET_TASK_AUDIT_PATH")
    return Path(configured).resolve() if configured else DEFAULT_DATASET_TASK_AUDIT_PATH


def load_dataset_registry() -> dict[str, Any]:
    """Load and minimally validate the generated evidence document.

    The returned object is the JSON document as stored on disk. This service
    deliberately does not infer labels, activate datasets, or rewrite status.
    """
    path = get_dataset_registry_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetRegistryUnavailableError(
            "The dataset registry is unavailable or invalid."
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("datasets"), list):
        raise DatasetRegistryUnavailableError(
            "The dataset registry does not contain a datasets list."
        )

    for item in payload["datasets"]:
        if not isinstance(item, dict) or not isinstance(item.get("dataset_id"), str):
            raise DatasetRegistryUnavailableError(
                "The dataset registry contains an invalid dataset record."
            )
    return payload


def load_dataset_task_audit() -> dict[str, Any]:
    """Load the generated task-level audit without changing its conclusions.

    This artifact is intentionally distinct from the path-level discovery
    registry. It records task-specific label, licence, privacy, split, and
    readiness evidence produced by ``scripts/dataset_task_audit.py``.
    """
    path = get_dataset_task_audit_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetTaskAuditUnavailableError(
            "The dataset task audit is unavailable or invalid."
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("datasets"), list):
        raise DatasetTaskAuditUnavailableError(
            "The dataset task audit does not contain a datasets list."
        )
    for dataset in payload["datasets"]:
        if (
            not isinstance(dataset, dict)
            or not isinstance(dataset.get("id"), str)
            or not isinstance(dataset.get("tasks"), list)
        ):
            raise DatasetTaskAuditUnavailableError(
                "The dataset task audit contains an invalid dataset record."
            )
        for task in dataset["tasks"]:
            if (
                not isinstance(task, dict)
                or not isinstance(task.get("task_id"), str)
                or not isinstance(task.get("training_eligible"), bool)
            ):
                raise DatasetTaskAuditUnavailableError(
                    "The dataset task audit contains an invalid task record."
                )
    return payload


def get_dataset(dataset_id: str) -> dict[str, Any] | None:
    """Return an exact registered record by stable identifier."""
    registry = load_dataset_registry()
    return next(
        (item for item in registry["datasets"] if item["dataset_id"] == dataset_id),
        None,
    )
