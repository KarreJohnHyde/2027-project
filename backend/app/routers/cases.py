"""
Case and Examination Management Router.
Strict case-level authorization is enforced on every operation.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import (
    Case, CaseMembership, Examination, User, UserRole, ModalityType,
    Finding, UploadedFile, ClinicalReportStatement, DocumentedAttribute,
    MultimodalFusionRecord, ConcordanceRecord, EvidenceStatus,
    OrderedPackage, LabInvestigationReport, MedicalMeasurement
)
from app.schemas.entities import CaseCreate, CaseResponse, ExaminationCreate, ExaminationResponse
from app.services.auth import get_current_user, verify_case_access
from app.services.audit_service import log_audit_event
from app.services.effective_evidence import MEASUREMENT_FIELDS, STATEMENT_FIELDS, correction_index, effective_record
from app.services.measurement_identity import duplicate_map, occurrences
from app.services import upload_store

router = APIRouter(prefix="/cases", tags=["Case Management"])


@router.get("", response_model=List[CaseResponse])
def list_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns cases authorized for the requesting user.
    Admins can view all cases; clinicians and researchers view their authorized cases.
    """
    if current_user.role == UserRole.ADMIN:
        cases = db.query(Case).all()
    else:
        # Patient and caregiver links open the portal only, not the clinical case list.
        shared = db.query(CaseMembership.case_id).filter(CaseMembership.user_id == current_user.id, CaseMembership.role.in_(("VIEWER", "EDITOR")))
        cases = db.query(Case).filter((Case.created_by_id == current_user.id) | (Case.id.in_(shared))).all()
    return cases


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    case_in: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check pseudonymous id uniqueness
    existing = db.query(Case).filter(Case.pseudonymous_id == case_in.pseudonymous_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Case with pseudonymous ID '{case_in.pseudonymous_id}' already exists."
        )

    new_case = Case(
        pseudonymous_id=case_in.pseudonymous_id,
        patient_ref=case_in.patient_ref,
        description=case_in.description,
        created_by_id=current_user.id
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Add initial examinations if specified
    if case_in.examinations:
        for ex in case_in.examinations:
            exam = Examination(
                case_id=new_case.id,
                exam_date=ex.exam_date,
                modality=ex.modality,
                clinical_indication=ex.clinical_indication
            )
            db.add(exam)
        db.commit()
        db.refresh(new_case)

    log_audit_event(
        db=db,
        action="CASE_CREATED",
        resource_type="CASE",
        resource_id=str(new_case.id),
        user=current_user,
        details={"pseudonymous_id": new_case.pseudonymous_id}
    )

    return new_case


@router.get("/{case_id}", response_model=CaseResponse)
def get_case_detail(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db, access="read")
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db)

    # Erasure is intentionally narrower than ordinary case editing: only the
    # creator or an administrator may delete a complete case and its evidence.
    if current_user.role != UserRole.ADMIN and case.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the case creator or an administrator may delete a case.",
        )

    # Validate every unique physical object before changing database state. The
    # store is content-addressed, so an object referenced by another case must be
    # retained even after this case's metadata is deleted.
    file_rows = db.query(UploadedFile).filter(UploadedFile.case_id == case_id).all()
    cleanup_candidates: dict[str, str] = {}
    shared_objects: set[str] = set()
    missing_objects: set[str] = set()
    for row in file_rows:
        previous_path = cleanup_candidates.get(row.stored_filename)
        if previous_path is not None and Path(previous_path) != Path(row.file_path):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Case deletion stopped because stored-object metadata is inconsistent.",
            )
        cleanup_candidates[row.stored_filename] = row.file_path

    for stored_filename, file_path in cleanup_candidates.items():
        shared = db.query(UploadedFile.id).filter(
            UploadedFile.case_id != case_id,
            UploadedFile.stored_filename == stored_filename,
        ).first()
        if shared:
            shared_objects.add(stored_filename)
            continue
        try:
            if upload_store.resolve_managed_file(Path(file_path), stored_filename) is None:
                missing_objects.add(stored_filename)
        except upload_store.ManagedStorageDeletionError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Case deletion stopped because a stored-object path failed the safety check.",
            ) from exc

    db.delete(case)
    db.commit()

    deleted_count = 0
    cleanup_errors = 0
    for stored_filename, file_path in cleanup_candidates.items():
        if stored_filename in shared_objects or stored_filename in missing_objects:
            continue
        # Recheck after the metadata commit. If another case acquired a reference,
        # preserve the shared object. This is conservative under concurrent use.
        still_referenced = db.query(UploadedFile.id).filter(
            UploadedFile.stored_filename == stored_filename,
        ).first()
        if still_referenced:
            shared_objects.add(stored_filename)
            continue
        try:
            deleted_count += int(upload_store.delete_managed_file(Path(file_path), stored_filename))
        except upload_store.ManagedStorageDeletionError:
            cleanup_errors += 1

    log_audit_event(
        db=db,
        action="CASE_DELETED",
        resource_type="CASE",
        resource_id=str(case_id),
        user=current_user,
        details={
            "retention_action": "CASE_ERASURE",
            "stored_objects_deleted": deleted_count,
            "stored_objects_missing": len(missing_objects),
            "stored_objects_preserved_shared": len(shared_objects),
            "stored_object_cleanup_errors": cleanup_errors,
        },
    )

    if cleanup_errors:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Case metadata was deleted, but one or more managed objects require administrator cleanup.",
        )


# ---------------- Examination Endpoints ----------------
@router.post("/{case_id}/examinations", response_model=ExaminationResponse, status_code=status.HTTP_201_CREATED)
def add_examination(
    case_id: int,
    exam_in: ExaminationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db)
    
    exam = Examination(
        case_id=case.id,
        exam_date=exam_in.exam_date,
        modality=exam_in.modality,
        clinical_indication=exam_in.clinical_indication
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)

    log_audit_event(
        db=db,
        action="EXAMINATION_ADDED",
        resource_type="EXAMINATION",
        resource_id=str(exam.id),
        user=current_user,
        details={"case_id": case_id, "modality": exam.modality.value}
    )

    return exam


@router.get("/{case_id}/examinations", response_model=List[ExaminationResponse])
def list_examinations(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db, access="read")
    return case.examinations


@router.get("/{case_id}/stats")
def get_case_stats(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db, access="read")
    files = db.query(UploadedFile).filter(UploadedFile.case_id == case.id).all()
    images_count = sum(1 for f in files if f.modality == ModalityType.IMAGE)
    ecg_count = sum(1 for f in files if f.modality == ModalityType.ECG)
    reports_count = sum(1 for f in files if f.modality == ModalityType.REPORT)
    
    findings = db.query(Finding).filter(Finding.case_id == case.id).all()
    pending_count = sum(1 for f in findings if f.review_status == EvidenceStatus.PENDING_HUMAN_REVIEW)
    completed_count = sum(1 for f in findings if f.review_status == EvidenceStatus.COMPLETED)
    rejected_count = sum(1 for f in findings if f.review_status in (EvidenceStatus.REJECT, EvidenceStatus.ERROR))

    latest_fusion = db.query(MultimodalFusionRecord).filter(
        MultimodalFusionRecord.case_id == case.id
    ).order_by(MultimodalFusionRecord.created_at.desc()).first()
    
    concordance_flags = db.query(ConcordanceRecord).filter(
        ConcordanceRecord.case_id == case.id,
        ConcordanceRecord.is_discordant == True
    ).count()

    orders_count = db.query(OrderedPackage).filter(OrderedPackage.case_id == case.id).count()
    lab_reports_count = db.query(LabInvestigationReport).filter(LabInvestigationReport.case_id == case.id).count()

    return {
        "case_id": str(case.id),
        "pseudonym": case.pseudonymous_id,
        "total_files": len(files),
        "images_count": images_count,
        "ecg_count": ecg_count,
        "reports_count": reports_count,
        "findings_count": len(findings),
        "pending_reviews_count": pending_count,
        "completed_count": completed_count,
        "rejected_count": rejected_count,
        "fusion_status": latest_fusion.fused_status.value if latest_fusion else "NOT_RUN",
        "concordance_flags_count": concordance_flags,
        "orders_count": orders_count,
        "lab_reports_count": lab_reports_count,
        "is_demo_data": any(f.is_demo for f in findings) if findings else True
    }


@router.get("/{case_id}/effective-evidence")
def get_case_effective_evidence(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reviewed view: every extracted statement and measurement with its original values,
    the values after an approved, independently decided correction, and the correction state.
    Source rows are never modified; unapproved proposals do not change effective values."""
    case = verify_case_access(case_id, current_user, db, access="read")
    measurement_corrections, statement_corrections = correction_index(db, case.id)
    measurements = (
        db.query(MedicalMeasurement)
        .filter(MedicalMeasurement.case_id == case.id)
        .order_by(MedicalMeasurement.id.asc())
        .all()
    )
    statements = (
        db.query(ClinicalReportStatement)
        .filter(ClinicalReportStatement.case_id == case.id)
        .order_by(ClinicalReportStatement.id.asc())
        .all()
    )
    return {
        "case_id": case.id,
        "measurements": [
            {"measurement_id": item.id, **effective_record(serialize_measurement(item), measurement_corrections.get(item.id, []), MEASUREMENT_FIELDS)}
            for item in measurements
        ],
        "statements": [
            {"statement_id": item.id, **effective_record(serialize_statement(item), statement_corrections.get(item.id, []), STATEMENT_FIELDS)}
            for item in statements
        ],
        "notice": "Effective values reflect approved corrections only; original extraction and source text are unchanged.",
    }


@router.get("/{case_id}/statements")
def get_case_statements(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db, access="read")
    stmts = db.query(ClinicalReportStatement).filter(
        ClinicalReportStatement.case_id == case.id
    ).all()
    
    return [serialize_statement(s) for s in stmts]


def serialize_statement(s: ClinicalReportStatement) -> Dict[str, Any]:
    return {
        "id": str(s.id),
        "case_id": str(s.case_id),
        "finding_id": str(s.finding_id),
        "source_file_id": str(s.finding.inference_run.file_id) if s.finding and s.finding.inference_run else None,
        "entity": s.entity,
        "entity_text": s.entity_text or s.entity,
        "entity_start": s.entity_start,
        "entity_end": s.entity_end,
        "category": s.category,
        "negation": s.negation,
        "is_negated": s.negation.upper() == "NEGATED",
        "certainty": s.certainty or "NOT_ASSESSED_V1",
        "temporality": s.temporality,
        "experiencer": s.experiencer or "PATIENT",
        "comparison": s.comparison,
        "section": s.section,
        "anatomical_site": s.anatomical_site,
        "laterality": s.laterality,
        "anatomy_system": s.anatomy_system,
        "atlas_structure_id": s.atlas_structure_id,
        "cues": s.cues or [],
        "source_span": s.source_span,
        "source_span_start": s.source_span_start,
        "source_span_end": s.source_span_end,
        "char_start": s.source_span_start or 0,
        "char_end": s.source_span_end or len(s.source_span),
        "confidence": None,
        "extraction_method": "TRANSPARENT_RULE_BASELINE",
        "extractor_version": s.extractor_version or "rules-v1.0.0",
        "created_at": s.created_at.isoformat(),
    }


def documented_range_position(item: MedicalMeasurement) -> str:
    """Arithmetic position against the interval documented in the same source only."""
    if (item.result_operator or "=") != "=":
        return "INDETERMINATE_CENSORED_RESULT"
    if item.reference_low is None and item.reference_high is None:
        # Printed strata that do not resolve to one interval for this patient stay indeterminate.
        return "INDETERMINATE_PRINTED_STRATA" if item.reference_options else "NO_DOCUMENTED_INTERVAL"
    if item.reference_low is not None and item.value < item.reference_low:
        return "BELOW_DOCUMENTED_INTERVAL"
    if item.reference_high is not None and item.value > item.reference_high:
        return "ABOVE_DOCUMENTED_INTERVAL"
    return "WITHIN_DOCUMENTED_INTERVAL"


def serialize_measurement(item: MedicalMeasurement) -> Dict[str, Any]:
    return {
        "id": item.id,
        "case_id": item.case_id,
        "examination_id": item.examination_id,
        "source_file_id": item.source_file_id,
        "finding_id": item.finding_id,
        "name": item.name,
        "display_name": item.display_name,
        "value": item.value,
        "result_operator": item.result_operator or "=",
        "unit": item.unit,
        "raw_value": item.raw_value,
        "raw_unit": item.raw_unit,
        "source_span": item.source_span,
        "source_span_start": item.source_span_start,
        "source_span_end": item.source_span_end,
        "source_page": item.source_page,
        "source_bbox": item.source_bbox,
        "source_bbox_coordinate_space": item.source_bbox_coordinate_space,
        "source_image_width": item.source_image_width,
        "source_image_height": item.source_image_height,
        "extraction_method": item.extraction_method,
        "review_status": item.review_status.value,
        "canonical_code": item.canonical_code,
        "code_system": item.code_system,
        "code_mapping_status": item.code_mapping_status,
        "reference_low": item.reference_low,
        "reference_high": item.reference_high,
        "reference_low_inclusive": item.reference_low_inclusive,
        "reference_high_inclusive": item.reference_high_inclusive,
        "reference_text": item.reference_text,
        "reference_source": item.reference_source,
        "documented_flag": item.documented_flag,
        "reference_options": item.reference_options or [],
        "reference_selection": item.reference_selection,
        "documented_category": item.documented_category,
        "documented_range_position": documented_range_position(item),
        "conversion_status": item.conversion_status or "AS_DOCUMENTED",
        "documented_date": item.documented_date,
        "anatomy_system": item.anatomy_system,
        "association": item.association,
        "specimen": item.specimen or "NOT_DOCUMENTED",
        "laboratory_method": item.laboratory_method or "NOT_DOCUMENTED",
        "laboratory_name": item.laboratory_name or "NOT_DOCUMENTED",
        "extractor_version": item.extractor_version,
        "source_hash": item.source_file.file_hash if item.source_file else None,
        "extraction_uncertainty": "NOT_ESTIMATED_RULE_EXTRACTION",
        "created_at": item.created_at.isoformat(),
    }


@router.get("/{case_id}/measurements")
def get_case_measurements(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return explicit numeric values with source spans and review state."""
    verify_case_access(case_id, current_user, db, access="read")
    measurements = (
        db.query(MedicalMeasurement)
        .filter(MedicalMeasurement.case_id == case_id)
        .order_by(MedicalMeasurement.created_at.asc(), MedicalMeasurement.id.asc())
        .all()
    )
    duplicates = duplicate_map(measurements)
    grouped = occurrences(measurements)
    serialized = []
    for item in measurements:
        record = serialize_measurement(item)
        record["duplicate_of_measurement_id"] = duplicates.get(item.id)
        record["source_occurrences"] = grouped.get(item.id, []) if item.id not in duplicates else []
        serialized.append(record)
    return serialized


@router.get("/{case_id}/attributes")
def get_case_documented_attributes(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dates, age and sex exactly as documented in uploaded sources."""
    verify_case_access(case_id, current_user, db, access="read")
    rows = (
        db.query(DocumentedAttribute)
        .filter(DocumentedAttribute.case_id == case_id)
        .order_by(DocumentedAttribute.id.asc())
        .all()
    )
    return [
        {
            "id": row.id,
            "source_file_id": row.source_file_id,
            "finding_id": row.finding_id,
            "name": row.name,
            "value_text": row.value_text,
            "value_number": row.value_number,
            "unit": row.unit,
            "parse_status": row.parse_status,
            "raw_text": row.raw_text,
            "source_span": row.source_span,
            "source_span_start": row.source_span_start,
            "source_span_end": row.source_span_end,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/{case_id}/timeline")
def get_case_timeline(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db, access="read")
    exams = db.query(Examination).filter(
        Examination.case_id == case.id
    ).order_by(Examination.exam_date.asc()).all()

    timeline = []
    for ex in exams:
        timeline.append({
            "id": str(ex.id),
            "case_id": str(ex.case_id),
            "timestamp": ex.exam_date.isoformat(),
            "examination_type": ex.modality.value,
            "clinician_notes": ex.clinical_indication,
            "created_at": ex.created_at.isoformat()
        })
    return timeline
