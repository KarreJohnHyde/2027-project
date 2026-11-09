"""Which analysis of a report is current.

Analysing a report again stores a new run beside the earlier ones. Earlier runs keep their statements,
reviews and corrections as history; only the latest successful analysis of each upload is current. Views
built from statements use the current analysis, so a report analysed twice is not shown (or counted) twice.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.models.entities import ClinicalReportStatement, EvidenceStatus, Finding, InferenceRun, ModalityType


def superseded_report_run_ids(db: Session, case_ids: Iterable[int]) -> set[int]:
    """Successful report analyses of the given cases that a later successful analysis of the same upload replaced."""
    ids = list(case_ids)
    if not ids:
        return set()
    rows = (db.query(InferenceRun.id, InferenceRun.file_id)
            .join(Finding, Finding.inference_run_id == InferenceRun.id)
            .filter(InferenceRun.case_id.in_(ids), InferenceRun.modality == ModalityType.REPORT,
                    InferenceRun.status != EvidenceStatus.ERROR, Finding.failure_reason.is_(None))
            .distinct().all())
    latest: dict[int, int] = {}
    for run_id, file_id in rows:
        latest[file_id] = max(run_id, latest.get(file_id, run_id))
    return {run_id for run_id, file_id in rows if run_id != latest[file_id]}


def current_statements(db: Session, case_ids: Iterable[int]):
    """SQL criterion for ClinicalReportStatement rows that belong to their upload's current analysis."""
    superseded = superseded_report_run_ids(db, case_ids)
    if not superseded:
        return true()
    return ClinicalReportStatement.finding_id.notin_(select(Finding.id).where(Finding.inference_run_id.in_(superseded)))
