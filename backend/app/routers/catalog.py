"""
Clinical Diagnostic Packages, Imaging Services & Laboratory Results Router for MedTwin.

- Browse health check-up packages, top-up panels and imaging services.
- Order a package or imaging study for a case (names/categories are resolved
  server-side from the catalog; client-supplied labels are never trusted).
- Track order status through ORDERED -> IN_PROGRESS -> COMPLETED (or CANCELLED).
- Record laboratory results transcribed from a laboratory report; each value is
  validated against the test catalog and positioned against the interval the
  laboratory printed (INDETERMINATE without one). Positions are interval
  comparisons, not diagnoses, and always require clinician interpretation.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import LabInvestigationReport, OrderedPackage, UploadedFile, User, UserRole
from app.services.audit_service import log_audit_event
from app.services.auth import get_current_user, require_role, verify_case_access
from app.services.clinical_catalog import (
    get_all_imaging_services,
    get_all_packages,
    get_expanded_package,
    get_orderable_item,
)
from app.services.lab_service import LAB_PANELS, evaluate_result, get_all_lab_tests

router = APIRouter(tags=["Clinical Catalog & Packages"])

ORDER_TRANSITIONS: Dict[str, set] = {
    "ORDERED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}

LAB_RESULTS_NOTICE = (
    "Positions compare a value with the interval printed by the performing laboratory; "
    "without that interval the position is INDETERMINATE and a catalog default is shown "
    "for orientation only. Positions are not a diagnosis and require clinician "
    "interpretation (PENDING_HUMAN_REVIEW)."
)

NOT_DOCUMENTED = "NOT_DOCUMENTED"


# ---------------------------------------------------------------- Schemas
class OrderCreateRequest(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=64)
    clinical_notes: Optional[str] = Field(None, max_length=2000)


class OrderStatusUpdate(BaseModel):
    status: Literal["IN_PROGRESS", "COMPLETED", "CANCELLED"]


class OrderResponse(BaseModel):
    id: int
    case_id: int
    package_id: str
    package_name: str
    category: str
    status: str
    clinical_notes: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LabResultInput(BaseModel):
    code: str
    value: Any
    result_operator: Literal["=", "<", ">", "<=", ">="] = "="
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None


class LabReportCreate(BaseModel):
    ordered_package_id: Optional[int] = None
    # The uploaded document these values were transcribed from, when it is in the case.
    source_file_id: Optional[int] = None
    report_title: Optional[str] = Field(None, max_length=128)
    # Recorded as NOT_DOCUMENTED when omitted; never filled with an assumed laboratory or specimen.
    lab_name: Optional[str] = Field(None, max_length=128)
    sample_type: Optional[str] = Field(None, max_length=64)
    laboratory_method: Optional[str] = Field(None, max_length=128)
    patient_sex: Optional[Literal["M", "F"]] = None
    collection_date: Optional[date] = None
    collection_time: Optional[str] = Field(None, max_length=64)
    reporting_time: Optional[str] = Field(None, max_length=64)
    clinical_summary: Optional[str] = Field(None, max_length=4000)
    results: List[LabResultInput] = Field(..., min_length=1)


class LabReportResponse(BaseModel):
    id: int
    case_id: int
    lab_name: str
    report_title: str
    sample_type: str
    laboratory_method: str
    collection_date: Optional[str]
    collection_time: Optional[str]
    reporting_time: Optional[str]
    clinical_summary: Optional[str]
    ordered_package_id: Optional[int]
    source_file_id: Optional[int]
    entry_method: str
    recorded_by_id: Optional[int]
    patient_sex: Optional[str]
    results: List[Dict[str, Any]]
    flag_counts: Dict[str, int]
    review_status: str = "PENDING_HUMAN_REVIEW"
    notice: str = LAB_RESULTS_NOTICE
    created_at: datetime


def _to_lab_response(rep: LabInvestigationReport) -> LabReportResponse:
    payload = rep.test_results_json or {}
    # Older rows may store a bare list of results
    results = payload.get("results", []) if isinstance(payload, dict) else list(payload)
    meta = payload if isinstance(payload, dict) else {}
    counts: Dict[str, int] = {}
    for r in results:
        counts[r.get("status", "UNKNOWN")] = counts.get(r.get("status", "UNKNOWN"), 0) + 1
    return LabReportResponse(
        id=rep.id,
        case_id=rep.case_id,
        lab_name=rep.lab_name,
        report_title=rep.report_title,
        sample_type=rep.sample_type,
        laboratory_method=meta.get("laboratory_method") or NOT_DOCUMENTED,
        collection_date=meta.get("collection_date"),
        collection_time=rep.collection_time,
        reporting_time=rep.reporting_time,
        clinical_summary=rep.clinical_summary,
        ordered_package_id=meta.get("ordered_package_id"),
        source_file_id=meta.get("source_file_id"),
        # This endpoint has always been the only writer, so older rows are manual entries too.
        entry_method=meta.get("entry_method", "MANUAL_TRANSCRIPTION"),
        recorded_by_id=meta.get("recorded_by_id"),
        patient_sex=meta.get("patient_sex"),
        results=results,
        flag_counts=counts,
        created_at=rep.created_at,
    )


def _documented_or_sentinel(value: Optional[str]) -> str:
    text = (value or "").strip()
    return text or NOT_DOCUMENTED


# ---------------------------------------------------------------- Catalog (public, read-only)
@router.get("/catalog/packages", response_model=List[Dict[str, Any]])
def list_health_packages():
    """Returns all health check-up and top-up packages."""
    return get_all_packages()


@router.get("/catalog/packages/{package_id}", response_model=Dict[str, Any])
def get_health_package(package_id: str):
    """Returns one package with included packages expanded and its lab test codes."""
    pkg = get_expanded_package(package_id)
    if not pkg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Package '{package_id}' not found.")
    return pkg


@router.get("/catalog/imaging", response_model=List[Dict[str, Any]])
def list_imaging_services():
    """Returns imaging services (CT, Ultrasound, Angiography, Cardiac CT)."""
    return get_all_imaging_services()


@router.get("/catalog/lab-tests", response_model=Dict[str, Any])
def list_lab_tests():
    """Returns the laboratory test reference catalog grouped by panel."""
    return {"panels": LAB_PANELS, "tests": get_all_lab_tests(), "notice": LAB_RESULTS_NOTICE}


# ---------------------------------------------------------------- Orders
@router.get("/cases/{case_id}/orders", response_model=List[OrderResponse])
def list_case_orders(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lists packages and imaging studies ordered for a case (newest first)."""
    verify_case_access(case_id, current_user, db, access="read")
    return (
        db.query(OrderedPackage)
        .filter(OrderedPackage.case_id == case_id)
        .order_by(OrderedPackage.created_at.desc(), OrderedPackage.id.desc())
        .all()
    )


@router.post("/cases/{case_id}/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_case_order(
    case_id: int,
    req: OrderCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CLINICIAN)),
):
    """Orders a catalog package or imaging study for a case."""
    verify_case_access(case_id, current_user, db)
    item = get_orderable_item(req.item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{req.item_id}' is not a catalog package or imaging study.",
        )

    order = OrderedPackage(
        case_id=case_id,
        package_id=item["id"],
        package_name=item["name"],
        category=item["category"],
        status="ORDERED",
        ordered_by_id=current_user.id,
        clinical_notes=req.clinical_notes,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    log_audit_event(
        db=db, action="ORDER_CREATED", resource_type="ORDER", resource_id=str(order.id), user=current_user,
        details={"case_id": case_id, "item_id": item["id"], "item_type": item["item_type"]},
    )
    return order


@router.patch("/cases/{case_id}/orders/{order_id}", response_model=OrderResponse)
def update_case_order_status(
    case_id: int,
    order_id: int,
    req: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CLINICIAN)),
):
    """Advances an order's status. Completed and cancelled orders are final."""
    verify_case_access(case_id, current_user, db)
    order = db.query(OrderedPackage).filter(
        OrderedPackage.id == order_id, OrderedPackage.case_id == case_id
    ).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found for case.")
    if req.status not in ORDER_TRANSITIONS.get(order.status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot change order status from {order.status} to {req.status}.",
        )

    previous = order.status
    order.status = req.status
    db.commit()
    db.refresh(order)

    log_audit_event(
        db=db, action="ORDER_STATUS_CHANGED", resource_type="ORDER", resource_id=str(order.id), user=current_user,
        details={"case_id": case_id, "from": previous, "to": order.status},
    )
    return order


# ---------------------------------------------------------------- Laboratory results
@router.get("/cases/{case_id}/lab-reports", response_model=List[LabReportResponse])
def list_case_lab_reports(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lists laboratory reports recorded for a case (newest first)."""
    verify_case_access(case_id, current_user, db, access="read")
    reports = (
        db.query(LabInvestigationReport)
        .filter(LabInvestigationReport.case_id == case_id)
        .order_by(LabInvestigationReport.created_at.desc(), LabInvestigationReport.id.desc())
        .all()
    )
    return [_to_lab_response(r) for r in reports]


@router.post("/cases/{case_id}/lab-reports", response_model=LabReportResponse, status_code=status.HTTP_201_CREATED)
def create_case_lab_report(
    case_id: int,
    req: LabReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CLINICIAN)),
):
    """
    Records laboratory results for a case. When linked to an ordered package,
    every result must belong to that package's laboratory tests.
    """
    verify_case_access(case_id, current_user, db)
    if req.collection_date is not None and req.collection_date > date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Collection date is in the future.")
    if req.source_file_id is not None:
        source = db.query(UploadedFile).filter(UploadedFile.id == req.source_file_id, UploadedFile.case_id == case_id).first()
        if not source:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source document not found in this case.")

    codes = [r.code for r in req.results]
    duplicates = sorted({c for c in codes if codes.count(c) > 1})
    if duplicates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Duplicate test codes: {duplicates}")

    title = req.report_title
    if req.ordered_package_id is not None:
        order = db.query(OrderedPackage).filter(
            OrderedPackage.id == req.ordered_package_id, OrderedPackage.case_id == case_id
        ).first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked order not found for this case.")
        if order.status == "CANCELLED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot record results for a cancelled order.")
        pkg = get_expanded_package(order.package_id)
        if not pkg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Linked order is not a laboratory package.")
        outside = [c for c in codes if c not in pkg["lab_test_codes"]]
        if outside:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tests not part of {pkg['name']}: {outside}",
            )
        title = title or pkg["name"]

    evaluated = []
    errors = []
    for r in req.results:
        try:
            result = evaluate_result(r.code, r.value, req.patient_sex, r.ref_low, r.ref_high)
            result["result_operator"] = r.result_operator
            if r.result_operator != "=" and isinstance(result.get("result_value"), (int, float)):
                result["status"] = "INDETERMINATE"
                result["censoring_note"] = "The printed comparator was preserved; the boundary value was not treated as an exact result."
            evaluated.append(result)
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

    report = LabInvestigationReport(
        case_id=case_id,
        lab_name=_documented_or_sentinel(req.lab_name),
        report_title=title or "Laboratory Investigation Report",
        sample_type=_documented_or_sentinel(req.sample_type),
        patient_name=None,  # Pseudonymized cases never store patient names
        collection_time=req.collection_time,
        reporting_time=req.reporting_time,
        clinical_summary=req.clinical_summary,
        test_results_json={
            "ordered_package_id": req.ordered_package_id,
            "source_file_id": req.source_file_id,
            "collection_date": req.collection_date.isoformat() if req.collection_date else None,
            "laboratory_method": _documented_or_sentinel(req.laboratory_method),
            "entry_method": "MANUAL_TRANSCRIPTION",
            "recorded_by_id": current_user.id,
            "patient_sex": req.patient_sex,
            "results": evaluated,
        },
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    response = _to_lab_response(report)
    log_audit_event(
        db=db, action="LAB_REPORT_RECORDED", resource_type="LAB_REPORT", resource_id=str(report.id),
        user=current_user,
        details={"case_id": case_id, "result_count": len(evaluated), "flag_counts": response.flag_counts},
    )
    return response
