"""Read-only source matching and chronological baseline evaluation.

These tools reuse canonical evidence/review/forecasting gates. They do not train
or activate a model, impute a missing modality, or create a ForecastRecord.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.config import PROJECT_ROOT
from app.models.entities import Case, Examination, MedicalMeasurement
from app.services.universal_evidence import build_graph
from app.services.research_baselines import evaluate


def paired_evidence(case: Case, db: Session, exam_id: int | None = None, confirmed_same_patient: bool = False) -> dict:
    if exam_id is not None and not db.query(Examination.id).filter(Examination.id == exam_id, Examination.case_id == case.id).first():
        raise HTTPException(404, "Examination is not available in this case.")
    graph = build_graph(case, db)
    uploads = [n for n in graph["nodes"] if n["kind"] == "upload" and n["details"].get("active_evidence")]
    groups = []
    for exam in [n for n in graph["nodes"] if n["kind"] == "examination" and (exam_id is None or n["examination_id"] == exam_id)][:32]:
        sources = [n for n in uploads if n.get("examination_id") == exam["examination_id"]]
        distinct = [n for n in sources if not n["details"].get("duplicate_of")]
        present = sorted({n["details"]["modality"] for n in distinct})
        missing = sorted({"IMAGE", "ECG", "REPORT"} - set(present))
        source_ids = {n["source_file_id"] for n in distinct}
        evidence = [n for n in graph["nodes"] if n.get("source_file_id") in source_ids and n["kind"] in {"statement", "measurement", "finding"}
                    and n["details"].get("active_evidence") and not n["details"].get("duplicate_of")]
        ids = {n["id"] for n in evidence}
        conflicts = [c for c in graph["conflicts"] if set(c["node_ids"]) <= ids]
        status = "SOURCE_MATCHED_EVIDENCE_SYNTHESIS_ONLY" if len(present) >= 2 and confirmed_same_patient else "IDENTITY_CONFIRMATION_REQUIRED" if len(present) >= 2 else "MISSING_MODALITIES"
        groups.append({"examination_id": exam["examination_id"], "exam_date": exam["timestamp"], "status": status,
            "identity_confirmed_by_request": confirmed_same_patient, "present_modalities": present, "missing_modalities": missing,
            "source_ids": sorted(source_ids), "duplicate_source_ids": [n["source_file_id"] for n in sources if n["details"].get("duplicate_of")],
            "source_hashes": {str(n["source_file_id"]): n["details"]["sha256"] for n in distinct},
            "evidence_node_ids": sorted(ids), "conflicts": conflicts, "learned_fusion_eligible": False,
            "fusion_reason": "No jointly evaluated source-matched image/report/ECG fusion model is activated by modality counts. Existing ECG-demographic model retains its independent input and research gates."})
    return {"schema_version": "medtwin.paired-evidence.v1", "case_id": case.id,
            "status": "SOURCE_MATCHED_EVIDENCE_AVAILABLE" if any(g["status"] == "SOURCE_MATCHED_EVIDENCE_SYNTHESIS_ONLY" for g in groups) else "INSUFFICIENT_CONFIRMED_MULTIMODAL_EVIDENCE",
            "groups": groups, "unlinked_source_ids": [n["source_file_id"] for n in uploads if n.get("examination_id") is None],
            "graph_data_version": graph["data_version"], "truncated": graph["truncated"] or len([n for n in graph["nodes"] if n["kind"] == "examination"]) > 32,
            "learned_fusion_eligible": False, "clinical_activation": False, "never_writes": True,
            "notice": "Only active distinct sources in the same selected case and examination are paired. Identity confirmation is explicit and is not stored as a review. Different examinations and unlinked sources are never fused; missing modalities remain missing."}


def backtest(case: Case, db: Session, metric: str, unit: str, horizon_days: int) -> dict:
    result = {"schema_version": "medtwin.baseline-backtest.v1", "case_id": case.id, "status": "INSUFFICIENT_EVIDENCE",
        "metric": metric, "unit": unit, "horizon_days": horizon_days, "models": {}, "matched_comparison": None,
        "reason": None, "clinical_activation": False, "never_writes": True,
        "notice": "Read-only expanding-window evaluation on reviewed source-linked observations. This is local descriptive baseline research, not prospective validation or a clinical disease prognosis. No prediction interval or treatment effect is inferred."}
    if db.query(MedicalMeasurement.id).filter(MedicalMeasurement.case_id == case.id).limit(513).count() > 512:
        return {**result, "reason": "CASE_MEASUREMENT_LIMIT_EXCEEDED_512"}
    outputs = {method: evaluate(case.id, db, metric, unit, horizon_days, method, persist=False) for method in ("persistence", "linear")}
    result["models"] = outputs
    folds = {method: {f["target_date"]: f for f in ((output.get("baseline_analysis") or {}).get("backtest") or {}).get("folds", [])}
             for method, output in outputs.items()}
    dates = sorted(set(folds["persistence"]) & set(folds["linear"]))
    if dates:
        errors = {method: np.asarray([folds[method][date]["error"] for date in dates]) for method in folds}
        mae = {method: float(np.abs(error).mean()) for method, error in errors.items()}
        result["matched_comparison"] = {"target_dates": dates, "n": len(dates), "persistence_mae": mae["persistence"],
            "linear_mae": mae["linear"], "linear_minus_persistence_mae": mae["linear"] - mae["persistence"],
            "interval": None, "significance": "NOT_ESTABLISHED_SINGLE_CASE_LOCAL_BACKTEST", "selection": "Same chronological targets; each fold fits earlier observations only."}
        result["status"] = "CHRONOLOGICAL_BASELINES_EVALUATED"
    elif any((output.get("baseline_analysis") or {}).get("backtest") for output in outputs.values()):
        result["status"] = "ONE_BASELINE_EVALUATED_NO_MATCHED_COMPARISON"
    else:
        result["reason"] = "CANONICAL_REVIEW_CONTEXT_DATE_MINIMUM_OR_HORIZON_GATE_NOT_MET"
    return result


def audit_summary() -> dict:
    """Public audit metadata only; no private case paths/content or arbitrary file reader."""
    directory = Path(PROJECT_ROOT) / "artifacts/completion-2026-11-13/research"
    entries = []
    for name in ("research-audit.json", "arena-measurements.json", "strict-parity-investigation.json", "development-experiment.json"):
        path = directory / name
        if path.is_file() and path.stat().st_size <= 4 * 1024 * 1024:
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
                entries.append({"artifact": name, "status": report.get("status"), "summary": report.get("summary"),
                                "clinical_activation": False})
            except (OSError, ValueError):
                entries.append({"artifact": name, "status": "UNREADABLE"})
    return {"schema_version": "medtwin.completion-research-audit.v1", "artifacts": entries, "clinical_activation": False,
            "notice": "Public-source engineering/research artifact summaries; no automatic model promotion, rights approval or clinical validation."}
