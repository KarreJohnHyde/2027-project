"""Measured public evidence plus fail-closed admin-only independent-report state.

This is not an arbitrary artifact reader. No configured pathname, report text,
per-document identity/hash or private error string is ever included in the API.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re

from app.config import PROJECT_ROOT
from app.services import model_registry

EVIDENCE_PATH = Path(PROJECT_ROOT)/"docs/universal/evidence/finalization-2026-11-13.json"
PROOF_LABELS = {"control-room/proof.json": "Unified control room", "catalogue/browser-proof.json": "Source catalogue", "research/ui-proof.json": "Research explorer UI", "research/api-proof.json": "Research explorer API", "imaging/browser/proof.json": "Temporal comparison", "operations/proof.json": "Operations", "container-acceptance/proof.json": "Container acceptance", "readiness/proof.json": "Measured readiness", "independent-report-tools/proof.json": "Independent report tooling"}
LIMITATIONS = [
    "Engineering checks and saved internal research evaluations do not establish clinical validation or model superiority.",
    "Independent full real-report accuracy is pending import and verification of the permitted reports and independently checked references; missing evaluation is not zero accuracy.",
    "Commercial data/code/weight rights, task validation and clinical/regulatory approval are separate gates; original weak-model restrictions remain enforced.",
    "Known leakage groups, uncertain patient identities and exact historical one-pixel Kvasir parity remain scientific limitations.",
    "Temporal and registration controls are synthetic engineering evidence; patient-to-atlas localization and clinical progression remain unvalidated.",
    "Broad paired multimodal and longitudinal outcomes, ICD-11 configuration/crosswalk permissions, off-host recovery and clinical release still require their own evidence.",
]
INDEPENDENT_METRICS = {
    "ocr": {"character_error_rate": "OCR character error rate", "word_error_rate": "OCR word error rate", "exact_page_rate": "OCR exact-page rate"},
    "lab": {"precision": "Laboratory extraction precision", "recall": "Laboratory extraction recall", "f1": "Laboratory extraction F1", "value_and_unit_exact_match_rate_at_tolerance": "Laboratory value/unit match rate"},
    "nlp_given_human_text": {"exact_span_precision": "NLP precision given human text", "exact_span_recall": "NLP recall given human text", "exact_span_f1": "NLP F1 given human text"},
    "nlp_end_to_end_source_regions": {"precision": "End-to-end NLP precision", "recall": "End-to-end NLP recall", "f1": "End-to-end NLP F1"},
}


def _sha(value):
    return value.lower() if isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value) else None


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1_000_000_000 else None


def _json(path: Path, maximum=2*1024*1024):
    if not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("BOUNDED_AGGREGATE_UNAVAILABLE")
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict): raise ValueError("AGGREGATE_OBJECT_REQUIRED")
    return payload, hashlib.sha256(raw).hexdigest()


def _metric(identifier, label, value, unit, scope):
    return {"metric_id": identifier, "label": label, "value": value, "unit": unit, "scope": scope}


def _public_evidence():
    payload, sha = _json(EVIDENCE_PATH)
    if payload.get("schema_version") != "medtwin.public-expansion-evidence.v1":
        raise ValueError("PUBLIC_EVIDENCE_SCHEMA_UNSUPPORTED")
    backend = payload.get("backend") or {}; matched = payload.get("matched_records") or {}; anatomy = payload.get("source_hierarchy") or {}
    metrics = [
        _metric("backend_passed", "Backend checks passed", _count(backend.get("passed")), "checks", "RECORDED_COMMITTED_RUN"),
        _metric("backend_skipped", "Backend checks skipped", _count(backend.get("skipped")), "checks", "RECORDED_COMMITTED_RUN"),
        _metric("matched_records", "Saved matched research records", _count(matched.get("records")), "records", "RECORDED_COMMITTED_COHORT"),
        _metric("matched_patients", "Recorded research cohort size", _count(matched.get("patients")), "patients", "RECORDED_COMMITTED_COHORT"),
        _metric("anatomy_families", "Source anatomy families", _count(anatomy.get("families")), "families", "RECORDED_SOURCE_HIERARCHY"),
        _metric("anatomy_nodes", "Source hierarchy entries", _count(anatomy.get("nodes")), "entries", "RECORDED_SOURCE_HIERARCHY"),
    ]
    sources = [{"source_id": "committed_engineering_evidence", "label": "Latest committed public engineering evidence", "sha256": sha, "status": "BYTES_HASHED_CURRENT_SUMMARY"}]
    if _sha(backend.get("log_sha256")):
        sources.append({"source_id": "recorded_backend_log", "label": "Recorded backend-run log identity", "sha256": _sha(backend["log_sha256"]), "status": "RECORDED_HASH_NOT_REPLAYED"})
    proofs = payload.get("proofs") if isinstance(payload.get("proofs"), list) else []
    for proof in proofs[:32]:
        if not isinstance(proof, dict) or proof.get("name") not in PROOF_LABELS: continue
        label = PROOF_LABELS[proof["name"]]
        metrics.append(_metric("proof_"+re.sub(r"[^a-z]+", "_", label.lower()), label+" checks", _count(proof.get("checks_passed")), "checks", "RECORDED_COMMITTED_PROOF"))
        sources.append({"source_id": "proof_"+re.sub(r"[^a-z]+", "_", label.lower()), "label": label+" proof", "sha256": _sha(proof.get("artifact_sha256")), "status": "RECORDED_HASH_NOT_REPLAYED"})
    timestamp = None
    try: timestamp = datetime.fromisoformat(payload["generated_at"]).isoformat()
    except (ValueError, KeyError, TypeError): pass
    return metrics, sources, timestamp, _sha(payload.get("registry_sha256_preserved"))


def _live_counts():
    from app.services.model_inference import research_gate
    payload, sha = _json(model_registry.REGISTRY_PATH, 8*1024*1024)
    models = model_registry._validate_registry(payload)["models"]
    gates = [research_gate(model) for model in models]
    supported = {"image_2d", "ecg_12lead", "volume_nifti", "echo_video", "head_ct_series"}
    counts = {"registry_models": len(models), "research_allowed": sum(g.get("allowed") is True for g in gates),
              "research_blocked": sum(g.get("allowed") is not True for g in gates),
              "upload_runnable": sum(g.get("allowed") is True and model.get("inference_input", "image_2d" if model.get("research_inference") else None) in supported for model, g in zip(models, gates)),
              "clinical_activated": 0}
    states = Counter(model["status"] for model in models)
    counts.update({"status_"+status.lower(): count for status, count in states.items()})
    return counts, sha


def _matched_cohort():
    from app.schemas.matched_model_explorer import MatchedRecordsQuery
    from app.services.matched_model_explorer import query_records
    result = query_records(MatchedRecordsQuery(limit=1))
    if result.get("status") != "MATCHED_RECORDS_AVAILABLE":
        return {"status": "CURRENT_SOURCE_BINDING_UNAVAILABLE", "records": None, "patients": None, "snapshot_sha256": None}
    cohort = result.get("cohort") or {}
    return {"status": "SOURCE_BOUND_CURRENT_COHORT", "records": _count(cohort.get("records")), "patients": _count(cohort.get("patients")), "snapshot_sha256": _sha(result.get("snapshot_id"))}


def _independent_state(status, notice, *, visibility="PUBLIC_STATUS"):
    return {"status": status, "visibility": visibility, "documents": None, "pages": None, "readable_pages": None, "unreadable_pages": None, "annotated_fields": None, "annotated_entities": None, "independent_real_documents": None, "independent_real_pages": None, "full_report_validation": "NOT_VERIFIED", "metrics": [], "sources": [], "clinical_activation": False, "notice": notice}


def independent_reports(admin: bool):
    configured = os.getenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", "").strip()
    if not configured:
        return _independent_state("PENDING_REFERENCE_IMPORT", "Source reports have been offered; independent full-page references and allowed-use/source bindings have not yet been verified here. Manuscript checks and unreviewed model outputs are not independent gold annotations.")
    if not admin:
        return _independent_state("PRIVATE_OPERATOR_EVALUATION", "Independent operator evaluation is private. An administrator can inspect its verified aggregate; no report data or metrics are disclosed here.", visibility="ADMIN_ONLY")
    try:
        payload, artifact_sha = _json(Path(configured))
        if payload.get("schema_version") != "medtwin.independent-report-evaluation.v1":
            raise ValueError("UNSUPPORTED_SCHEMA")
        if payload.get("status") == "REFUSED":
            return _independent_state("EVALUATION_REFUSED", "Configured evaluation refused source/reference checks; no accuracy estimate is available.", visibility="ADMIN_ONLY")
        if payload.get("status") not in {"EVALUATED_INDEPENDENT_REPORTS", "SYNTHETIC_SOFTWARE_CONTROL"} or payload.get("clinical_activation") is not False:
            raise ValueError("INVALID_STATE")
        counts = payload.get("counts") or {}; provenance = payload.get("provenance") or {}
        required_hashes = ["inventory_sha256", "annotations_sha256", "permissions_sha256", "source_manifest_sha256", "predictions_sha256", "pipeline_sha256"]
        if any(_sha(provenance.get(key)) is None for key in required_hashes): raise ValueError("BINDING_HASHES_MISSING")
        selected_counts = {key: _count(counts.get(key)) for key in ["documents", "readable_pages", "independent_real_documents", "independent_real_pages"]}
        if any(value is None for value in selected_counts.values()): raise ValueError("COUNTS_MISSING")
        synthetic = payload.get("status") == "SYNTHETIC_SOFTWARE_CONTROL"
        if provenance.get("verified_source_bindings") is not True: raise ValueError("SOURCE_BINDINGS_NOT_VERIFIED")
        if provenance.get("raw_text_persisted") is not False or provenance.get("raw_identifiers_persisted") is not False:
            raise ValueError("PRIVATE_AGGREGATE_PRIVACY_STATE_UNVERIFIED")
        pages, readable, unreadable = [_count(counts.get(key)) for key in ["pages", "readable_pages", "unreadable_pages"]]
        if pages is None or readable is None or unreadable is None or readable+unreadable != pages or selected_counts["independent_real_documents"] > selected_counts["documents"] or selected_counts["independent_real_pages"] > pages:
            raise ValueError("PAGE_OR_DOCUMENT_COUNTS_INVALID")
        if synthetic and payload.get("evidence_type") != "SYNTHETIC": raise ValueError("SYNTHETIC_TYPE_MISMATCH")
        if synthetic and (selected_counts["independent_real_documents"] != 0 or selected_counts["independent_real_pages"] != 0): raise ValueError("SYNTHETIC_INDEPENDENCE_CLAIM")
        if not synthetic and (payload.get("evidence_type") != "REAL_PERMITTED" or selected_counts["independent_real_documents"] <= 0 or selected_counts["independent_real_pages"] <= 0): raise ValueError("REAL_REFERENCE_COUNTS_UNVERIFIED")
        if not synthetic:
            if selected_counts["documents"] != selected_counts["independent_real_documents"] or pages != selected_counts["independent_real_pages"]:
                raise ValueError("MIXED_REFERENCE_DENOMINATOR")
            references = payload.get("references") or {}
            if any(references.get(key) is not True for key in ["all_readable_pages_independently_checked", "full_page_text_available", "permissions_verified", "full_report_page_coverage_verified", "unexposed_reference_attested"]):
                raise ValueError("FULL_REFERENCE_COVERAGE_NOT_VERIFIED")
            if _count(counts.get("independent_real_readable_pages")) != readable:
                raise ValueError("READABLE_REFERENCE_DENOMINATOR_MISMATCH")
        metrics = []
        for group, fields in INDEPENDENT_METRICS.items():
            values = (payload.get("metrics") or {}).get(group) or {}
            for key, label in fields.items():
                if key not in values: continue
                value = values[key]
                if value is None: continue  # Undefined denominators are not zero accuracy.
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or ("error_rate" not in key and value > 1): raise ValueError("NONFINITE_OR_INVALID_METRIC")
                metrics.append(_metric(group+"."+key, label, float(value), "ratio", "SYNTHETIC_CONTROL" if synthetic else "RECORDED_INDEPENDENT_REPORT_RUN"))
        if not metrics: raise ValueError("METRICS_MISSING")
        result = _independent_state("SYNTHETIC_SOFTWARE_CONTROL" if synthetic else "RECORDED_INDEPENDENT_EVALUATION", "Operator-run aggregate only. Synthetic controls do not measure independent real-report accuracy." if synthetic else "Permitted independent-report evaluation recorded; source/reference completeness and clinical generalization remain separate checks.", visibility="ADMIN_ONLY")
        result.update(selected_counts, pages=pages, unreadable_pages=unreadable, annotated_fields=_count(counts.get("annotated_fields")), annotated_entities=_count(counts.get("annotated_entities")), metrics=metrics, full_report_validation="SYNTHETIC_ONLY" if synthetic else "RECORDED_FULL_REFERENCE_COVERAGE_RESEARCH_ONLY")
        result["sources"] = [{"source_id": "private_operator_aggregate", "label": "Private operator aggregate identity", "sha256": artifact_sha, "status": "ADMIN_ONLY_AGGREGATE_HASH"}] + [{"source_id": key, "label": key.removesuffix("_sha256").replace("_", " ").capitalize()+" aggregate binding", "sha256": _sha(provenance[key]), "status": "RECORDED_AGGREGATE_BINDING"} for key in required_hashes]
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return _independent_state("EVALUATION_UNVERIFIED", "Configured operator evaluation is missing, unreadable or failed the bounded aggregate/schema/source checks. No accuracy is inferred.", visibility="ADMIN_ONLY")


def readiness_summary(*, independent_admin=False):
    sources, metrics, timestamp = [], [], None
    status = "MEASURED_ENGINEERING_EVIDENCE"
    recorded_registry = None
    try: metrics, sources, timestamp, recorded_registry = _public_evidence()
    except (OSError, ValueError, TypeError, KeyError): status = "PUBLIC_EVIDENCE_UNAVAILABLE"
    try:
        counts, registry_sha = _live_counts()
        sources.append({"source_id": "current_original_model_registry", "label": "Current original model registry", "sha256": registry_sha, "status": "MATCHES_RECORDED_REGISTRY" if registry_sha == recorded_registry else "CURRENT_HASH_DIFFERS_FROM_RECORDED_BASELINE"})
    except (OSError, ValueError, TypeError, KeyError, model_registry.RegistryConfigurationError):
        counts = {"registry_models": None, "research_allowed": None, "research_blocked": None, "upload_runnable": None, "clinical_activated": 0}
    try: cohort = _matched_cohort()
    except (OSError, ValueError, TypeError, KeyError): cohort = {"status": "CURRENT_SOURCE_BINDING_UNAVAILABLE", "records": None, "patients": None, "snapshot_sha256": None}
    if cohort.get("snapshot_sha256"):
        sources.append({"source_id": "current_matched_cohort", "label": "Current rights/source-bound matched cohort", "sha256": cohort["snapshot_sha256"], "status": "CURRENT_SOURCE_BINDING_VERIFIED"})
    independent = independent_reports(independent_admin)
    limitations = list(LIMITATIONS)
    if independent["status"] == "RECORDED_INDEPENDENT_EVALUATION": limitations[1] = "An independent-report research run is recorded; its source/reference coverage does not establish external clinical generalization or approval."
    elif independent["status"] == "PRIVATE_OPERATOR_EVALUATION": limitations[1] = "Independent operator report evaluation is private; this view makes no public independent-accuracy claim."
    return {"schema_version": "medtwin.research-readiness.v1", "status": status, "recorded_at": timestamp, "metrics": metrics, "live_model_counts": counts, "live_matched_cohort": cohort,
            "sources": sources, "limitations": limitations, "independent_reports": independent, "clinical_activation": False, "new_inference": False,
            "notice": "Recorded engineering results and live capability/source checks are shown separately. No diagnostic accuracy, clinical release or model improvement is inferred."}
