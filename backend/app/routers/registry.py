"""Truthful model and runtime capability registry endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.entities import User
from app.services.auth import get_current_user
from app.services.model_registry import get_capabilities, get_model, list_models


router = APIRouter(tags=["Model & Capability Registry"])


@router.get("/models")
def read_models(_: User = Depends(get_current_user)):
    return list_models()


@router.get("/models/{model_id}")
def read_model(model_id: str, _: User = Depends(get_current_user)):
    model = get_model(model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' is not registered.",
        )
    return model


@router.get("/models/{model_id}/activation")
def read_model_activation(model_id: str, _: User = Depends(get_current_user)):
    model = get_model(model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' is not registered.",
        )
    return {
        "model_id": model_id,
        "activation": model["activation"],
        "message": (
            "The reproducible artifact bundle is complete and eligible for activation."
            if model["activation"]["eligible"]
            else "Activation is blocked until every reported requirement is satisfied."
        ),
    }


@router.get("/capabilities")
def read_capabilities(_: User = Depends(get_current_user)):
    return get_capabilities()
