"""A stable bounded projection of persisted case evidence; never a diagnostic graph.

Source occurrences, rejected findings and earlier analyses remain visible as history.
Only current eligible effective records participate in conflict checks and summaries.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Case, Examination, UploadedFile, InferenceRun, Finding, ClinicalReportStatement, MedicalMeasurement, HumanReview, ConcordanceRecord
from app.schemas.universal_intelligence import EvidenceNode
from app.services.effective_evidence import correction_index, effective_record, MEASUREMENT_FIELDS, STATEMENT_FIELDS
from app.services.evidence_synthesis import eligible_upload
from app.services.measurement_identity import duplicate_map
from app.services.report_runs import superseded_report_run_ids
from app.services.anatomy_evidence import SYSTEM_LABELS
from app.services.terminology import convert

NOTICE = "Research evidence navigation only. Source mentions and model outputs are not diagnoses or independently confirmed disease probabilities. Anatomy links are schematic lexical associations, not patient registration. Conflicts require human review."
LIMITS = {"nodes": 1600, "edges": 3200, "rows_per_kind": 256, "conflicts": 40}


def value(item):
    return item.value if hasattr(item, "value") else item


def stamp(item):
    return item.isoformat() if item else None


def build_graph(case: Case, db: Session) -> dict:
    nodes, edges, truncated = {}, [], False
    cap = LIMITS["rows_per_kind"]

    def rows(model):
        nonlocal truncated
        result = db.query(model).filter(model.case_id == case.id).order_by(model.id).limit(cap + 1).all()
        truncated |= len(result) > cap
        return result[:cap]

    def add(kind, row_id, label, **fields):
        nonlocal truncated
        key = f"{kind}:{row_id}"
        if len(nodes) >= LIMITS["nodes"] and key not in nodes:
            truncated = True
            return key
        nodes[key] = {"id": key, "kind": kind, "label": str(label)[:300], **fields}
        return key

    def edge(source, target, relation):
        nonlocal truncated
        if source not in nodes or target not in nodes:
            return
        if len(edges) >= LIMITS["edges"]:
            truncated = True
            return
        edges.append({"id": f"{source}|{relation}|{target}", "source": source, "target": target, "relation": relation})

    case_node = add("case", case.id, case.pseudonymous_id, timestamp=stamp(case.updated_at))
    exams = {r.id: r for r in rows(Examination)}
    for row in exams.values():
        key = add("examination", row.id, f"{value(row.modality)} examination", examination_id=row.id,
                  timestamp=stamp(row.exam_date), details={"modality": value(row.modality)})
        edge(case_node, key, "HAS_EXAMINATION")
    dated_exams = sorted(exams.values(), key=lambda row: (row.exam_date, row.id))
    for earlier, later in zip(dated_exams, dated_exams[1:]):
        if earlier.exam_date < later.exam_date:
            edge(f"examination:{earlier.id}", f"examination:{later.id}", "PRECEDES_IN_CASE_TIME")
    uploads = {r.id: r for r in rows(UploadedFile)}
    first_hash = {}
    for row in uploads.values():
        active = eligible_upload(row, case.id)
        duplicate = first_hash.get(row.file_hash) if active else None
        if active:
            first_hash.setdefault(row.file_hash, row.id)
        key = add("upload", row.id, f"Source #{row.id} · {value(row.modality)}", source_file_id=row.id,
                  examination_id=row.examination_id if row.examination_id in exams else None,
                  timestamp=stamp(row.created_at), details={"active_evidence": active, "sha256": row.file_hash,
                      "modality": value(row.modality), "is_associated": row.is_associated,
                      "withdrawn": row.withdrawn_at is not None, "superseded": row.superseded_by_file_id is not None,
                      "version": row.version_number, "duplicate_of": f"upload:{duplicate}" if duplicate else None})
        edge(case_node, key, "HAS_SOURCE")
        edge(f"examination:{row.examination_id}", key, "HAS_SOURCE")
        if duplicate:
            edge(key, f"upload:{duplicate}", "DUPLICATE_SOURCE_OF")
        # Never reference an unrelated case's linked identifier.
    for row in uploads.values():
        if row.superseded_by_file_id in uploads:
            edge(f"upload:{row.id}", f"upload:{row.superseded_by_file_id}", "SUPERSEDED_BY")
    superseded = superseded_report_run_ids(db, [case.id])
    runs = {r.id: r for r in rows(InferenceRun) if r.file_id in uploads}
    for row in runs.values():
        key = add("model_run", row.id, row.model_name, source_file_id=row.file_id,
                  examination_id=uploads[row.file_id].examination_id if uploads[row.file_id].examination_id in exams else None,
                  timestamp=stamp(row.completed_at or row.started_at), details={"model_id": row.model_name,
                      "model_version": row.model_version, "preprocessing_version": row.preprocessing_version,
                      "status": value(row.status), "current_analysis": row.id not in superseded,
                      "active_evidence": eligible_upload(uploads[row.file_id], case.id) and row.id not in superseded})
        edge(f"upload:{row.file_id}", key, "ANALYZED_BY")
    findings = {r.id: r for r in rows(Finding) if r.inference_run_id in runs}
    reviews, latest = [], {}
    if findings:
        # A busy finding must not crowd another finding's latest rejection out
        # of the bounded history and accidentally reactivate rejected evidence.
        ranking = db.query(HumanReview.id.label("review_id"), func.row_number().over(
            partition_by=HumanReview.finding_id, order_by=(HumanReview.reviewed_at.desc(), HumanReview.id.desc())
        ).label("position")).filter(HumanReview.finding_id.in_(findings)).subquery()
        latest_rows = db.query(HumanReview).join(ranking, ranking.c.review_id == HumanReview.id).filter(ranking.c.position == 1).order_by(HumanReview.id).all()
        latest = {row.finding_id: row for row in latest_rows}
        history = (db.query(HumanReview).filter(HumanReview.finding_id.in_(findings))
                   .order_by(HumanReview.reviewed_at.desc(), HumanReview.id.desc()).limit(cap + 1).all())
        retained = {row.id: row for row in latest_rows}
        retained.update({row.id: row for row in history})
        truncated |= len(retained) > cap
        reviews = list(retained.values())[:cap]
    for row in findings.values():
        run = runs[row.inference_run_id]
        provenance = row.evidence_provenance if isinstance(row.evidence_provenance, dict) else {}
        review = latest.get(row.id)
        status = value(review.review_status if review else row.review_status)
        active = (nodes[f"model_run:{run.id}"]["details"]["active_evidence"] and not row.failure_reason
                  and status not in {"REJECTED", "REJECT", "ERROR", "ABSTAIN", "NOT_ELIGIBLE"})
        key = add("finding", row.id, row.label, source_file_id=run.file_id, finding_id=row.id,
                  examination_id=uploads[run.file_id].examination_id if uploads[run.file_id].examination_id in exams else None,
                  timestamp=stamp(row.created_at), review_status=status,
                  details={"active_evidence": bool(active), "category": row.category,
                      "failure_reason": row.failure_reason, "source_file_sha256": uploads[run.file_id].file_hash,
                      "representation_level": value(row.representation_level), "mapping_status": row.mapping_status,
                      "raw_confidence": row.raw_confidence, "calibrated_confidence": row.calibrated_confidence,
                      "calibration_status": row.calibration_status, "is_demo": row.is_demo,
                      "model_provenance": {key: provenance[key] for key in ("source", "output_status", "model_id", "checkpoint_sha256", "dataset_version", "dataset_license", "held_out_evaluation", "declared_input_type", "anatomy_system_of_model") if key in provenance}})
        edge(f"model_run:{run.id}", key, "PRODUCED")
    for row in reviews[:cap]:
        key = add("review", row.id, f"Review · {value(row.review_status)}", finding_id=row.finding_id,
                  review_status=value(row.review_status), timestamp=stamp(row.reviewed_at),
                  details={"scope": "FINDING", "original_output_preserved": row.original_output_preserved,
                           "has_correction_proposal": bool(row.correction_payload)})
        edge(f"finding:{row.finding_id}", key, "REVIEWED_BY")
    measurement_corrections, statement_corrections = correction_index(db, case.id)
    assertions = []

    def anatomy(node, system, site_unchanged=True):
        if system in SYSTEM_LABELS and site_unchanged:
            key = add("anatomy", system, SYSTEM_LABELS[system], details={"system_id": system,
                      "association": "LEXICAL_SCHEMATIC_ONLY", "patient_registered": False})
            edge(node, key, "LEXICALLY_ASSOCIATED_WITH")

    for row in rows(ClinicalReportStatement):
        if row.finding_id not in findings or f"finding:{row.finding_id}" not in nodes:
            continue
        finding = nodes[f"finding:{row.finding_id}"]
        upload = uploads[finding["source_file_id"]]
        original = {name: getattr(row, name) for name in STATEMENT_FIELDS.values()}
        overlay = effective_record(original, statement_corrections.get(row.id, []), STATEMENT_FIELDS)
        effective = overlay["effective"]
        active = finding["details"]["active_evidence"] and overlay["correction_state"] != "REMOVED_IN_EFFECTIVE_VIEW" and row.experiencer == "PATIENT"
        key = add("statement", row.id, effective["entity"], source_file_id=upload.id, finding_id=row.finding_id,
                  examination_id=upload.examination_id if upload.examination_id in exams else None,
                  source_span=row.source_span, source_page=row.source_page, source_start=row.source_span_start,
                  source_end=row.source_span_end, assertion=effective["negation"], review_status=finding["review_status"],
                  timestamp=stamp(row.created_at), details={"active_evidence": bool(active), **effective,
                      "experiencer": row.experiencer, "category": row.category, "original": original,
                      "correction_state": overlay["correction_state"], "applied_review_id": overlay["applied_review_id"]})
        edge(finding["id"], key, "EXTRACTED_STATEMENT")
        edge(key, f"upload:{upload.id}", "QUOTED_FROM")
        anatomy(key, row.anatomy_system, effective["anatomical_site"] == row.anatomical_site and effective["laterality"] == row.laterality)
        # Historical/uncertain/non-patient mentions cannot directly contradict current claims.
        if active and str(effective.get("temporality", "")).upper() == "CURRENT" and str(effective.get("certainty", "")).upper() in {"CERTAIN", "DEFINITE"} and not str(row.category).startswith("MODEL_"):
            scope = ("exam", upload.examination_id) if upload.examination_id in exams else ("source", upload.file_hash)
            assertions.append((scope, key, effective, upload.file_hash))
    measurements = [r for r in rows(MedicalMeasurement) if r.finding_id in findings and r.source_file_id in uploads
                    and runs[findings[r.finding_id].inference_run_id].file_id == r.source_file_id
                    and (r.examination_id is None or r.examination_id in exams)]
    duplicates = duplicate_map(measurements)
    for row in measurements:
        finding = nodes.get(f"finding:{row.finding_id}")
        if not finding:
            continue
        original = {name: getattr(row, name) for name in MEASUREMENT_FIELDS.values()}
        overlay = effective_record(original, measurement_corrections.get(row.id, []), MEASUREMENT_FIELDS)
        effective = overlay["effective"]
        active = finding["details"]["active_evidence"] and overlay["correction_state"] != "REMOVED_IN_EFFECTIVE_VIEW" and value(row.review_status) not in {"REJECT", "REJECTED", "ERROR"}
        key = add("measurement", row.id, f"{effective['display_name']}: {effective.get('result_operator') or '='}{effective['value']} {effective['unit']}",
                  source_file_id=row.source_file_id, finding_id=row.finding_id, examination_id=row.examination_id,
                  source_span=row.source_span, source_page=row.source_page, source_start=row.source_span_start,
                  source_end=row.source_span_end, source_bbox=row.source_bbox, review_status=finding["review_status"], timestamp=stamp(row.created_at),
                  details={"active_evidence": bool(active), "name": row.name, **effective, "documented_date": row.documented_date,
                      "specimen": effective.get("specimen"), "laboratory_method": effective.get("laboratory_method"),
                      "source_bbox_coordinate_space": row.source_bbox_coordinate_space,
                      "original": original, "correction_state": overlay["correction_state"],
                      "applied_review_id": overlay["applied_review_id"], "duplicate_of": f"measurement:{duplicates[row.id]}" if row.id in duplicates else None})
        edge(finding["id"], key, "EXTRACTED_MEASUREMENT")
        edge(key, f"upload:{row.source_file_id}", "QUOTED_FROM")
        if row.id in duplicates:
            edge(key, f"measurement:{duplicates[row.id]}", "DUPLICATE_OCCURRENCE_OF")
        anatomy(key, row.anatomy_system)
    conflicts, grouped = [], defaultdict(list)
    for scope, node, effective, source_hash in assertions:
        grouped[(scope, str(effective["entity"]).casefold(), str(effective.get("anatomical_site") or "").casefold())].append((node, effective, source_hash))
    for claims in grouped.values():
        for index, (left, a, ahash) in enumerate(claims):
            for right, b, bhash in claims[index + 1:]:
                # Repeated output or duplicate bytes are one source, not corroboration/conflict.
                if ahash == bhash:
                    continue
                polarity = {str(a["negation"]).upper(), str(b["negation"]).upper()} == {"AFFIRMED", "NEGATED"}
                sides = {str(a.get("laterality") or "").upper(), str(b.get("laterality") or "").upper()}
                laterality = sides == {"LEFT", "RIGHT"}
                kind = "POSSIBLE_POLARITY_CONFLICT" if polarity and not laterality else "POSSIBLE_LATERALITY_DISCREPANCY" if laterality else None
                if kind and len(conflicts) < LIMITS["conflicts"]:
                    conflicts.append({"id": f"{kind}:{left}:{right}", "kind": kind, "node_ids": [left, right], "status": "HUMAN_REVIEW_REQUIRED", "resolved": False})
                elif kind:
                    truncated = True
    def conflict(kind, left, right, **details):
        nonlocal truncated
        if len(conflicts) >= LIMITS["conflicts"]:
            truncated = True
            return
        conflicts.append({"id": f"{kind}:{left}:{right}", "kind": kind, "node_ids": [left, right],
                          "status": "HUMAN_REVIEW_REQUIRED", "resolved": False, **details})
    comparable = defaultdict(list)
    for node in nodes.values():
        detail = node.get("details", {})
        if node["kind"] != "measurement" or not detail.get("active_evidence") or detail.get("duplicate_of"):
            continue
        # Same analyte, examination and documented collection date; no pooling of
        # unknown specimens or laboratory methods. Different dates are history.
        if node.get("examination_id") and detail.get("documented_date") and detail.get("specimen") and detail.get("laboratory_method"):
            identity = (node["examination_id"], detail["name"], detail["documented_date"], str(detail["specimen"]).casefold(), str(detail["laboratory_method"]).casefold())
            comparable[identity].append(node)
    for measurements_in_context in comparable.values():
        for index, left in enumerate(measurements_in_context):
            for right in measurements_in_context[index + 1:]:
                a, b = left["details"], right["details"]
                if a["unit"] != b["unit"] and convert(a["name"], 0, a["unit"], b["unit"]) is None:
                    conflict("INCOMPATIBLE_UNITS_REVIEW_REQUIRED", left["id"], right["id"], reason="No registered conversion; numeric values were not compared or corrected.")
    for row in rows(ConcordanceRecord):
        left, right = nodes.get(f"statement:{row.report_statement_id}"), nodes.get(f"finding:{row.model_finding_id}")
        if (not row.is_discordant or row.review_flag == "UNCOMPARABLE" or not left or not right
                or not left["details"].get("active_evidence") or not right["details"].get("active_evidence")
                or not left.get("examination_id") or left.get("examination_id") != right.get("examination_id")
                or str(left["details"].get("temporality") or "").upper() != "CURRENT"):
            continue
        conflict("RECORDED_REPORT_MODEL_DISCORDANCE", left["id"], right["id"], concordance_record_id=row.id,
                 review_flag=row.review_flag, reason="Existing recorded comparison; neither source is resolved or overwritten.")
    present = {value(row.modality) for row in uploads.values() if eligible_upload(row, case.id)}
    graph = {"schema_version": "medtwin.evidence-graph.v1", "case_id": case.id,
             "nodes": [EvidenceNode.model_validate(node).model_dump() for node in sorted(nodes.values(), key=lambda n: n["id"])], "edges": sorted({e["id"]: e for e in edges}.values(), key=lambda e: e["id"]),
             "conflicts": conflicts, "missing_modalities": sorted({"IMAGE", "ECG", "REPORT"} - present),
             "limits": LIMITS.copy(), "truncated": bool(truncated), "notice": NOTICE}
    graph["data_version"] = sha256(json.dumps(graph, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return graph
