"""
Clinical Report Concordance Checker for MedTwin.
Implements Line 17 of Algorithm 1.

CRITICAL EVIDENCE PRESERVATION PRINCIPLES:
- Flags potential discordance between clinical report statements and image/ECG findings.
- NEVER automatically overwrites either the clinician's report or the model finding.
- Agreement between sources is NOT treated as proof of ground-truth correctness.
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.entities import Case, Finding, ClinicalReportStatement, ConcordanceRecord, ModalityType


def evaluate_report_concordance(case_id: int, db: Session) -> Dict[str, Any]:
    """
    Compares narrative report statements against image and ECG model findings for a case.
    """
    # 1. Fetch statements from clinical reports for this case
    report_statements = db.query(ClinicalReportStatement).filter(
        ClinicalReportStatement.case_id == case_id
    ).all()

    # 2. Fetch image and ECG findings
    model_findings = db.query(Finding).filter(
        Finding.case_id == case_id,
        Finding.modality.in_([ModalityType.IMAGE, ModalityType.ECG])
    ).all()

    concordance_items = []
    discordant_count = 0

    # Clean existing concordance records for this case
    db.query(ConcordanceRecord).filter(ConcordanceRecord.case_id == case_id).delete()

    for finding in model_findings:
        finding_is_abnormal = any(term in finding.label.lower() for term in ["fracture", "arrhythmia", "abnormality", "dislocation", "effusion"])
        
        # Look for matching or related report statement
        matched_statement = None
        for stmt in report_statements:
            stmt_entity_lower = stmt.entity.lower()
            if any(word in finding.category.lower() for word in ["musculoskeletal", "radiograph", "wrist"]) and any(w in stmt_entity_lower for w in ["fracture", "dislocation", "bone", "cortical"]):
                matched_statement = stmt
                break
            elif any(word in finding.category.lower() for word in ["cardiac", "ecg", "rhythm"]) and any(w in stmt_entity_lower for w in ["arrhythmia", "sinus", "fibrillation", "ischemia"]):
                matched_statement = stmt
                break

        if matched_statement:
            report_states_negated = (matched_statement.negation == "NEGATED")
            # Discordance occurs if model predicted abnormality while clinician reported negation, or vice-versa
            is_discordant = (finding_is_abnormal and report_states_negated) or (not finding_is_abnormal and not report_states_negated)
            
            review_flag = "REVIEW_DISCORDANCE" if is_discordant else "CONCORDANT"
            if is_discordant:
                discordant_count += 1
                notes = (
                    f"DISCORDANCE DETECTED: Model detected '{finding.label}', but clinical report states "
                    f"'{matched_statement.entity}' is {matched_statement.negation}. Human clinician review required."
                )
            else:
                notes = f"Model finding '{finding.label}' is consistent with clinical report statement '{matched_statement.source_span}'."

            record = ConcordanceRecord(
                case_id=case_id,
                finding_category=finding.category,
                report_statement_id=matched_statement.id,
                model_finding_id=finding.id,
                report_entity=matched_statement.entity,
                report_status=matched_statement.negation,
                model_label=finding.label,
                is_discordant=is_discordant,
                review_flag=review_flag,
                notes=notes,
                neither_source_overwritten=True
            )
            db.add(record)
            concordance_items.append(record)

    db.commit()

    return {
        "case_id": case_id,
        "total_comparisons": len(concordance_items),
        "discordant_count": discordant_count,
        "items": [
            {
                "id": item.id,
                "finding_category": item.finding_category,
                "report_entity": item.report_entity,
                "report_status": item.report_status,
                "model_label": item.model_label,
                "is_discordant": item.is_discordant,
                "review_flag": item.review_flag,
                "notes": item.notes,
                "neither_source_overwritten": item.neither_source_overwritten
            }
            for item in concordance_items
        ],
        "notice": "Report concordance flags disagreements for human review. Neither source is overwritten."
    }
