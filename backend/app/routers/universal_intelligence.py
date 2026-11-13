"""Authenticated read-only case evidence and typed local retrieval."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.entities import User
from app.schemas.universal_intelligence import CopilotQuery, CopilotResponse, EvidenceGraph
from app.services.auth import get_current_user, verify_case_access
from app.services.universal_evidence import build_graph
from app.services.universal_copilot import query_case

router = APIRouter(tags=["Universal Research Intelligence"])


@router.get("/cases/{case_id}/evidence-graph", response_model=EvidenceGraph)
def evidence_graph(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db, access="read")
    return build_graph(case, db)


@router.post("/cases/{case_id}/copilot/query", response_model=CopilotResponse)
def copilot_query(case_id: int, request: CopilotQuery, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db, access="read")
    return query_case(case, request, db)
