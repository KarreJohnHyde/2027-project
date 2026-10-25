"""Case evidence -> anatomical system association for the Anatomy Studio.

Canonical mapping states (the studio renders each differently):

SPATIALLY_REGISTERED        Image-derived finding placed by validated registration.
                            Always empty: no registration is validated.
REGION_VERIFIED             A report statement naming a region that resolves to a
                            labelled atlas structure, whose report finding a
                            clinician has CONFIRMED. Highlights one structure.
SCHEMATIC_ORGAN_ONLY        Organ-level association from documented text, an
                            organ-associated analyte, or DICOM BodyPartExamined.
                            Highlights the organ schematically, never a location.
NOT_MAPPABLE                No defensible anatomical association.

The legacy ``mapping_category`` field is retained temporarily for existing clients;
``mapping_state`` is the directive-aligned authoritative field.

Statements about family members are excluded from patient anatomy entirely.
Metabolic markers (glucose, HbA1c) are deliberately not mapped to the pancreas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import ClinicalReportStatement, Finding, HumanReview, MedicalMeasurement, ModalityType, UploadedFile
from app.services import upload_store
from app.services.imaging_readers import ImagingReadError, read_metadata
from app.services.terminology import ANALYTES_BY_NAME, ANATOMY_SYSTEMS

SYSTEM_LABELS = {
    "heart": "Heart", "lungs": "Lungs", "brain": "Brain", "liver": "Liver", "pancreas": "Pancreas",
    "intestines": "Intestines", "nervous": "Nervous system", "skeletal": "Skeletal system",
    "hybrid": "Hybrid full body", "kidneys": "Kidneys and nephrons",
}
MAPPING_CATEGORIES = ("SPATIALLY_REGISTERED", "VERIFIED_ANATOMICAL_REGION", "SCHEMATIC_ORGAN_ASSOCIATION", "UNSUPPORTED_MAPPING")
MAPPING_STATES = ("SPATIALLY_REGISTERED", "REGION_VERIFIED", "SCHEMATIC_ORGAN_ONLY", "NOT_MAPPABLE")
LEGACY_CATEGORY = {
    "SPATIALLY_REGISTERED": "SPATIALLY_REGISTERED",
    "REGION_VERIFIED": "VERIFIED_ANATOMICAL_REGION",
    "SCHEMATIC_ORGAN_ONLY": "SCHEMATIC_ORGAN_ASSOCIATION",
    "NOT_MAPPABLE": "UNSUPPORTED_MAPPING",
}


def _latest_reviews(db: Session, finding_ids: set[int]) -> dict[int, HumanReview]:
    if not finding_ids:
        return {}
    rows = (
        db.query(HumanReview)
        .filter(HumanReview.finding_id.in_(finding_ids))
        .order_by(HumanReview.reviewed_at.asc(), HumanReview.id.asc())
        .all()
    )
    latest: dict[int, HumanReview] = {}
    for row in rows:
        latest[row.finding_id] = row
    return latest


def _mapped(base: dict[str, Any], state: str, reason: str) -> dict[str, Any]:
    return {**base, "mapping_state": state, "mapping_category": LEGACY_CATEGORY[state], "reason": reason}


def _review_provenance(review: HumanReview | None) -> dict[str, Any] | None:
    if review is None:
        return None
    return {
        "review_id": review.id,
        "reviewer_id": review.reviewer_id,
        "scope": "FINDING_LEVEL",
        "status": review.review_status,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "original_output_preserved": review.original_output_preserved,
    }


def _source_hash(finding: Finding) -> str | None:
    run = finding.inference_run
    return run.file.file_hash if run and run.file else None


def _statement_item(statement: ClinicalReportStatement, review: HumanReview | None) -> dict[str, Any]:
    base = {
        "kind": "REPORT_STATEMENT",
        "id": statement.id,
        "finding_id": statement.finding_id,
        "source_file_id": statement.finding.inference_run.file_id if statement.finding and statement.finding.inference_run else None,
        "label": statement.entity,
        "entity_text": statement.entity_text or statement.entity,
        "assertion": statement.negation,
        "certainty": statement.certainty or "NOT_ASSESSED_V1",
        "temporality": statement.temporality,
        "comparison": statement.comparison,
        "documented_region": statement.anatomical_site,
        "laterality": statement.laterality,
        "source_span": statement.source_span,
        "review_status": review.review_status if review else "PENDING_HUMAN_REVIEW",
        "clinician_confirmation": _review_provenance(review),
        "source_hash": _source_hash(statement.finding),
        "extractor_version": statement.extractor_version,
        "system": statement.anatomy_system,
        "atlas_structure_id": None,
        "candidate_atlas_structure_id": statement.atlas_structure_id,
    }
    if not statement.anatomy_system:
        return _mapped(base, "NOT_MAPPABLE", "No organ is documented or implied by the entity.")
    if statement.atlas_structure_id and review and review.review_status == "CONFIRMED" and review.original_output_preserved:
        return _mapped(
            {**base, "atlas_structure_id": statement.atlas_structure_id},
            "REGION_VERIFIED",
            "Documented region resolves to a labelled atlas structure and the source extraction was confirmed by a clinician.",
        )
    reason = "Organ-level association from documented text."
    if statement.atlas_structure_id:
        reason += " A documented region matches an atlas structure but awaits clinician confirmation."
    return _mapped(base, "SCHEMATIC_ORGAN_ONLY", reason)


def _measurement_item(measurement: MedicalMeasurement) -> dict[str, Any]:
    analyte = ANALYTES_BY_NAME.get(measurement.name)
    system = measurement.anatomy_system or (analyte.system if analyte else None)
    association = measurement.association or (analyte.association if analyte else None)
    base = {
        "kind": "MEASUREMENT",
        "id": measurement.id,
        "source_file_id": measurement.source_file_id,
        "label": measurement.display_name,
        "value": measurement.value,
        "result_operator": measurement.result_operator or "=",
        "unit": measurement.unit,
        "documented_date": measurement.documented_date,
        "documented_flag": measurement.documented_flag,
        "source_span": measurement.source_span,
        "association": association,
        "system": system,
        "atlas_structure_id": None,
    }
    if association == "METABOLIC_MARKER":
        return _mapped({**base, "system": None}, "NOT_MAPPABLE", "Metabolic marker; not an anatomical finding of any organ.")
    if not system:
        return _mapped(base, "NOT_MAPPABLE", "Systemic measurement without an organ association.")
    return _mapped(base, "SCHEMATIC_ORGAN_ONLY", f"Analyte associated with the organ ({association or 'biochemical'}); carries no location.")


def _imaging_items(upload: UploadedFile) -> list[dict[str, Any]]:
    base = {"kind": "IMAGING_STUDY", "id": upload.id, "source_file_id": upload.id, "label": upload.filename, "atlas_structure_id": None}
    try:
        with upload_store.materialize(Path(upload.file_path)) as plain:
            metadata = read_metadata(plain)
    except (ImagingReadError, OSError, HTTPException) as exc:
        return [_mapped({**base, "system": None}, "NOT_MAPPABLE", f"Metadata unreadable: {exc}")]
    systems = metadata.get("body_part_systems") or []
    if not systems:
        return [_mapped(
            {**base, "system": None, "container": metadata.get("container")},
            "NOT_MAPPABLE",
            "No anatomical metadata (BodyPartExamined) is available for this image.",
        )]
    return [_mapped(
        {**base, "system": system, "container": metadata.get("container"), "body_part": metadata.get("body_part")},
        "SCHEMATIC_ORGAN_ONLY",
        f"DICOM BodyPartExamined '{metadata.get('body_part')}' associates the study with this region; findings are not localised.",
    ) for system in systems]


def _research_finding_item(finding: Finding, review: HumanReview | None) -> dict[str, Any]:
    provenance = finding.evidence_provenance if isinstance(finding.evidence_provenance, dict) else {}
    output = provenance.get("output") if isinstance(provenance.get("output"), dict) else {}
    system = provenance.get("anatomy_system_of_model")
    if system not in ANATOMY_SYSTEMS:
        system = None
    base = {
        "kind": "MODEL_FINDING",
        "id": finding.id,
        "finding_id": finding.id,
        "source_file_id": finding.inference_run.file_id if finding.inference_run else None,
        "source_hash": provenance.get("source_file_sha256"),
        "label": finding.label,
        "system": system,
        "atlas_structure_id": None,
        "candidate_atlas_structure_id": None,
        "review_status": review.review_status if review else "PENDING_HUMAN_REVIEW",
        "clinician_confirmation": _review_provenance(review),
        "evidence_status": provenance.get("output_status"),
        "model_id": provenance.get("model_id"),
        "checkpoint_sha256": provenance.get("checkpoint_sha256"),
        "dataset_version": provenance.get("dataset_version"),
        "evaluation_report_path": provenance.get("evaluation_report_path"),
        "output_type": output.get("type"),
        "source_coordinate_space": output.get("coordinate_space"),
    }
    if not system:
        return _mapped(base, "NOT_MAPPABLE", "The research model has no verified organ mapping in its recorded provenance.")
    if not review or review.review_status != "CONFIRMED" or not review.original_output_preserved:
        return _mapped(
            base,
            "NOT_MAPPABLE",
            "The model registry names an organ, but the research output awaits clinician confirmation and cannot be linked to anatomy.",
        )
    return _mapped(
        base,
        "SCHEMATIC_ORGAN_ONLY",
        "Clinician-confirmed research output associated with the model registry's organ only; source-image coordinates are not registered to the atlas.",
    )


def build_case_anatomy_evidence(db: Session, case_id: int) -> dict[str, Any]:
    statements = db.query(ClinicalReportStatement).filter(ClinicalReportStatement.case_id == case_id).all()
    measurements = db.query(MedicalMeasurement).filter(MedicalMeasurement.case_id == case_id).all()
    images = db.query(UploadedFile).filter(
        UploadedFile.case_id == case_id, UploadedFile.modality == ModalityType.IMAGE, UploadedFile.is_associated.is_(True)
    ).all()
    findings = db.query(Finding).filter(Finding.case_id == case_id).all()
    research_findings = [
        finding for finding in findings
        if isinstance(finding.evidence_provenance, dict) and finding.evidence_provenance.get("source") == "MODEL_INFERENCE"
    ]
    reviews = _latest_reviews(db, {statement.finding_id for statement in statements} | {finding.id for finding in research_findings})

    excluded = []
    items = []
    for statement in statements:
        if (statement.experiencer or "PATIENT") != "PATIENT":
            excluded.append({"kind": "REPORT_STATEMENT", "id": statement.id, "label": statement.entity, "reason": "FAMILY_HISTORY_NOT_PATIENT_EVIDENCE"})
            continue
        items.append(_statement_item(statement, reviews.get(statement.finding_id)))
    items.extend(_measurement_item(measurement) for measurement in measurements)
    items.extend(_research_finding_item(finding, reviews.get(finding.id)) for finding in research_findings)
    for upload in images:
        items.extend(_imaging_items(upload))

    systems: dict[str, Any] = {}
    for system_id in ANATOMY_SYSTEMS:
        scoped = [item for item in items if item.get("system") == system_id] if system_id != "hybrid" else [item for item in items if item.get("system")]
        counts = {category: sum(1 for item in scoped if item["mapping_category"] == category) for category in MAPPING_CATEGORIES}
        state_counts = {state: sum(1 for item in scoped if item["mapping_state"] == state) for state in MAPPING_STATES}
        systems[system_id] = {
            "system_id": system_id,
            "label": SYSTEM_LABELS[system_id],
            "items": scoped,
            "counts": counts,
            "state_counts": state_counts,
            "highlight": {
                "organ_schematic": state_counts["SCHEMATIC_ORGAN_ONLY"] > 0,
                "verified_structures": sorted({item["atlas_structure_id"] for item in scoped if item["mapping_state"] == "REGION_VERIFIED"}),
                "spatially_registered": sorted({item["atlas_structure_id"] for item in scoped if item["mapping_state"] == "SPATIALLY_REGISTERED" and item["atlas_structure_id"]}),
            },
        }
    return {
        "case_id": case_id,
        "mapping_states": MAPPING_STATES,
        "mapping_categories": MAPPING_CATEGORIES,
        "spatial_registration": {"status": "REGISTRATION_UNAVAILABLE", "reason": "No validated image-to-atlas registration exists; no finding is placed at a location."},
        "systems": systems,
        "unsupported": [item for item in items if item["mapping_state"] == "NOT_MAPPABLE"],
        "excluded": excluded,
    }
