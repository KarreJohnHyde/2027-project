"""Authenticated, read-only dataset evidence registry endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.entities import User
from app.services.auth import get_current_user
from app.services.dataset_registry import (
    DatasetRegistryUnavailableError,
    DatasetTaskAuditUnavailableError,
    get_dataset,
    load_dataset_registry,
    load_dataset_task_audit,
)


router = APIRouter(tags=["Dataset Registry"])


def _unavailable_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The generated dataset registry is unavailable.",
    )


def _task_audit_unavailable_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The generated dataset task audit is unavailable.",
    )


@router.get("/datasets", response_model=dict[str, Any])
def read_datasets(_: User = Depends(get_current_user)):
    """Return the generated registry without changing its evidence or statuses."""
    try:
        return load_dataset_registry()
    except DatasetRegistryUnavailableError as exc:
        raise _unavailable_error() from exc


@router.get("/datasets/task-audit", response_model=dict[str, Any])
def read_dataset_task_audit(_: User = Depends(get_current_user)):
    """Return the stored task-level audit without inferring new readiness."""
    try:
        return load_dataset_task_audit()
    except DatasetTaskAuditUnavailableError as exc:
        raise _task_audit_unavailable_error() from exc


@router.get("/datasets/{dataset_id}", response_model=dict[str, Any])
def read_dataset(dataset_id: str, _: User = Depends(get_current_user)):
    """Return one exact registry record; no activation endpoint is provided."""
    try:
        dataset = get_dataset(dataset_id)
    except DatasetRegistryUnavailableError as exc:
        raise _unavailable_error() from exc
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' is not registered.",
        )
    return dataset
