"""Public catalogue-only discovery; case evidence is never returned here."""
from fastapi import APIRouter, HTTPException, Query
from typing import Literal
from app.services import universal_catalogue as catalogue

router = APIRouter(prefix="/universal", tags=["Universal catalogue"])


@router.get("/systems")
def get_systems():
    return catalogue.systems()


@router.get("/catalogue")
def search_catalogue(q: str = Query("", max_length=200), system: str | None = Query(None, max_length=64),
                     kind: Literal["organ", "condition", "structure", "biomarker", "investigation", "classification"] | None = None,
                     limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100_000)):
    try: return catalogue.search(q=q, system=system, kind=kind, limit=limit, offset=offset)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/catalogue/{concept_id:path}")
def get_concept(concept_id: str):
    if len(concept_id) > 256: raise HTTPException(status_code=422, detail="Catalogue identifier is too long")
    result = catalogue.detail(concept_id)
    if result is None: raise HTTPException(status_code=404, detail="Catalogue concept not found")
    return result


@router.get("/capabilities")
def get_capabilities(system: str | None = Query(None, max_length=64)):
    try: return catalogue.capabilities(system)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/terminology/status")
def get_terminology_status():
    from app.services.universal_terminology import status
    return status()
