"""Typed-value research inference for the tabular classifiers (contract and run). Results are not stored as patient evidence."""

from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User
from app.services import tabular_inference
from app.services.audit_service import log_audit_event
from app.services.auth import get_current_user
from app.services.model_inference import InferenceNotPermitted

router = APIRouter(tags=["Tabular research models"])


class TabularInferenceRequest(BaseModel):
    values: dict[str, Optional[Union[float, str]]] = Field(..., max_length=200)

    model_config = ConfigDict(extra="forbid")


@router.get("/research-models/{model_id}/tabular-contract")
def read_tabular_contract(model_id: str, _: User = Depends(get_current_user)):
    try:
        return tabular_inference.contract(model_id)
    except InferenceNotPermitted as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/research-models/{model_id}/tabular-inference")
def run_tabular_inference(model_id: str, request: TabularInferenceRequest, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    try:
        result = tabular_inference.predict(model_id, request.values)
    except InferenceNotPermitted as exc:
        log_audit_event(db=db, action="TABULAR_RESEARCH_INFERENCE_REFUSED", resource_type="MODEL", resource_id=model_id, user=current_user,
                        details={"model_id": model_id, "reason": str(exc).split(":", 1)[0]})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # The values themselves are never written to the audit trail.
    log_audit_event(db=db, action="TABULAR_RESEARCH_INFERENCE", resource_type="MODEL", resource_id=model_id, user=current_user,
                    details={"model_id": model_id, "fields_given": sum(value is not None for value in request.values.values()),
                             "imputed_fields": len(result["imputed_fields"])})
    return result
