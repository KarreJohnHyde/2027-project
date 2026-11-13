"""Authenticated source hierarchy and optional authorized case associations."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.entities import User
from app.services.auth import get_current_user, verify_case_access
from app.services import universal_structures as service, icd11_source_adapter

router = APIRouter(prefix="/universal/structures", tags=["Whole-body source hierarchy"])


@router.get("/systems")
def systems(current_user: User = Depends(get_current_user)): return service.systems()


@router.get("")
def browse(system: str | None = Query(None, max_length=64), parent_id: str | None = Query(None, max_length=256),
           q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000),
           current_user: User = Depends(get_current_user)):
    try: return service.browse(system, parent_id, q, limit, offset)
    except KeyError: raise HTTPException(404, detail="Unknown source hierarchy parent") from None
    except ValueError as exc: raise HTTPException(422, detail=str(exc)) from exc


@router.get("/icd11/status")
def icd11_status(current_user: User = Depends(get_current_user)): return icd11_source_adapter.status()


@router.get("/icd11/lookup/{entity_id}")
def icd11_lookup(entity_id: str, current_user: User = Depends(get_current_user)):
    try: return icd11_source_adapter.lookup(entity_id)
    except ValueError as exc: raise HTTPException(422, detail=str(exc)) from exc


@router.get("/{node_id:path}/detail")
def detail(node_id: str, case_id: int | None = Query(None, ge=1), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db, access="read") if case_id is not None else None
    result = service.detail(node_id)
    if result is None: raise HTTPException(404, detail="Unknown source hierarchy node")
    if case is not None:
        from app.services.universal_evidence import build_graph
        graph = build_graph(case, db)
        families = service.registry()["families"]
        atlas_ids = {families[s]["atlas_system"] for s in result["node"]["system_ids"] if families[s].get("atlas_system")}
        target_ids = {n["id"] for n in graph["nodes"] if n["kind"] == "anatomy" and n["details"].get("system_id") in atlas_ids}
        sources = {e["source"] for e in graph["edges"] if e["target"] in target_ids and e["relation"] == "LEXICALLY_ASSOCIATED_WITH"}
        result["case_associations"] = {"case_id": case_id, "level": "RECORDED_SCHEMATIC_SYSTEM_ASSOCIATION_ONLY", "exact_structure_mapping": False,
            "items": [{**{k: n.get(k) for k in ("id", "kind", "source_file_id", "finding_id", "assertion", "review_status")}, "active_evidence": n.get("details", {}).get("active_evidence")} for n in graph["nodes"] if n["id"] in sources],
            "truncated": graph["truncated"], "diagnosis_inferred": False}
    return result
