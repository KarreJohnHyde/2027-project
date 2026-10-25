"""Research analytics over real workspace artifacts only.

Each chart payload carries the provenance the dashboard must display: source,
sample count and its semantics, analysis population, time frame, model
version, metric definition, calculation status and limitations. Charts whose
data do not exist are returned with status NOT_AVAILABLE and no data.
"""

from __future__ import annotations

from collections import Counter
import glob
import json
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import ANATOMY_MANIFEST_PATH, PROJECT_ROOT
from app.models.entities import Case, CaseMembership, ClinicalReportStatement, EvaluationRun, MedicalMeasurement, UploadedFile, User, UserRole
from app.services.dataset_registry import load_dataset_registry
from app.services.model_registry import list_models

BENCHMARK_GLOB = str(PROJECT_ROOT / "benchmarks" / "results" / "*.json")
DERIVATIVES_PATH = PROJECT_ROOT / "docs" / "anatomy" / "derivatives.json"
TEST_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "validation" / "test-evidence.json"


def chart(chart_id: str, title: str, data: Optional[list[dict[str, Any]]], *, source: str, sample_count: Optional[int], sample_semantics: str,
          population: str, time_frame: Optional[str], metric: str, model_version: Optional[str] = None, limitations: list[str] = (),
          status: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": chart_id,
        "title": title,
        "status": status or ("COMPUTED" if data else "NOT_AVAILABLE"),
        "data": data or [],
        "provenance": {
            "source": source,
            "sample_count": sample_count,
            "sample_count_semantics": sample_semantics,
            "analysis_population": population,
            "time_frame": time_frame,
            "model_version": model_version,
            "metric_definition": metric,
            "limitations": list(limitations),
        },
    }


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def dataset_charts() -> list[dict[str, Any]]:
    registry = load_dataset_registry()
    datasets = [item for item in registry.get("datasets", []) if item.get("registry_kind") != "engineering_artifact_not_medical_dataset"]
    generated = registry.get("generated_at_utc")
    by_size = sorted(({"dataset": item["dataset_id"], "files": item.get("sample_count", 0)} for item in datasets), key=lambda row: -row["files"])
    extensions: Counter = Counter()
    for item in datasets:
        for extension, count in ((item.get("file_inventory") or {}).get("extension_counts") or {}).items():
            extensions[extension] += count
    readiness = Counter(
        "TRAINING_ELIGIBLE" if item.get("training_eligible") else "VALIDATION_ELIGIBLE" if item.get("validation_eligible") else "NOT_ELIGIBLE"
        for item in datasets
    )
    licenses = Counter(item.get("license_status", "unknown") for item in datasets)
    pairing = []
    for item in datasets:
        pairs = (item.get("annotation_evidence") or {}).get("image_mask_pairing")
        if isinstance(pairs, dict) and pairs.get("image_files"):
            pairing.append({"dataset": item["dataset_id"], "image_files": pairs.get("image_files"), "mask_files": pairs.get("mask_files"), "matching_stems": pairs.get("matching_stems")})
    common = dict(source="dataset_registry/datasets.json (scripts/audit_datasets.py)", time_frame=f"Audit generated {generated}", population="Workspace dataset directories")
    file_limit = ["File counts are media files, not patients, studies or independent samples.", "Overlapping roots are not deduplicated."]
    return [
        chart("dataset_file_counts", "Media files per dataset directory", by_size, sample_count=len(by_size), sample_semantics="dataset directories", metric="Exact media-file count per directory", limitations=file_limit, **common),
        chart("dataset_extensions", "File formats across datasets", [{"extension": key, "files": value} for key, value in extensions.most_common()], sample_count=sum(extensions.values()), sample_semantics="files", metric="Files per extension", limitations=file_limit, **common),
        chart("dataset_readiness", "Training/validation eligibility", [{"state": key, "datasets": value} for key, value in readiness.items()], sample_count=len(datasets), sample_semantics="dataset directories", metric="Registry eligibility flag", limitations=["Eligibility requires licence, provenance, label validation and leakage-safe splits."], **common),
        chart("dataset_licenses", "Licence status", [{"license_status": key, "datasets": value} for key, value in licenses.items()], sample_count=len(datasets), sample_semantics="dataset directories", metric="Registry licence status", **common),
        chart("annotation_pairing", "Image/mask pairing completeness", pairing, sample_count=len(pairing), sample_semantics="datasets with image/mask evidence", metric="Images, masks and filename-stem matches", limitations=["Filename pairing is structural evidence, not label validation."], **common),
        chart("class_distribution", "Verified class distribution", None, status="NOT_AVAILABLE", sample_count=None, sample_semantics="—", metric="Counts of verified labels per class",
              limitations=["No dataset has verified label files; directory names are not treated as ground truth."], **common),
    ]


def benchmark_charts() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(glob.glob(BENCHMARK_GLOB)):
        payload = _read_json(Path(path))
        if not payload or payload.get("status") != "completed":
            continue
        kind = payload.get("benchmark_kind", "unknown")
        for profile in payload.get("profiles", []):
            aggregate = profile.get("aggregate", {})
            rows.append({
                "artifact": Path(path).name,
                "kind": kind,
                "concurrency": profile.get("concurrency"),
                "p50_ms": aggregate.get("p50_latency_ms_median_across_repeats"),
                "p95_ms": aggregate.get("p95_latency_ms_median_across_repeats"),
                "throughput": aggregate.get("successful_throughput_rps_median_across_repeats", aggregate.get("successful_throughput_median_across_repeats")),
                "attempted": aggregate.get("total_attempted", aggregate.get("total_attempted_workflows")),
                "failed": aggregate.get("total_failed", aggregate.get("total_failed_workflows")),
                "peak_rss_mb": round((aggregate.get("max_peak_rss_bytes") or aggregate.get("maximum_process_tree_peak_rss_bytes") or 0) / 2 ** 20, 1),
                "generated_at": payload.get("generated_at_utc"),
            })
    return [chart(
        "software_benchmarks", "Software latency and throughput (median across repeats)", rows,
        source="benchmarks/results/*.json", sample_count=sum(row["attempted"] or 0 for row in rows), sample_semantics="HTTP requests or synthetic workflows",
        population="Same-host loopback; one Uvicorn worker; synthetic de-identified fixtures", time_frame=", ".join(sorted({row["generated_at"] or "" for row in rows})) or None,
        metric="p50/p95 latency (ms) and successful throughput per concurrency level",
        limitations=["Software behaviour only; no clinical or model performance is measured.", "The RTX 5060 GPU was not used by these workloads."],
    )]


def anatomy_charts() -> list[dict[str, Any]]:
    manifest = _read_json(ANATOMY_MANIFEST_PATH)
    derivatives = _read_json(DERIVATIVES_PATH)
    if not manifest or not derivatives:
        return [chart("anatomy_assets", "Anatomy asset pipeline", None, source="public/anatomy/manifest.json", sample_count=None, sample_semantics="—", population="—", time_frame=None, metric="—", limitations=["Run tools/asset-pipeline first."])]
    rows, licenses = [], Counter()
    for variant in manifest["variants"].values():
        if variant["kind"] != "STANDALONE_ASSET":
            continue
        tiers = variant.get("tiers", {})
        rows.append({
            "variant": variant["id"],
            "system": variant["system_id"],
            "source_mb": round(variant["source"]["bytes"] / 2 ** 20, 2),
            "standard_mb": round(tiers.get("standard", {}).get("bytes", 0) / 2 ** 20, 2),
            "preview_mb": round(tiers.get("preview", {}).get("bytes", 0) / 2 ** 20, 2) if "preview" in tiers else None,
            "triangles": variant["statistics"]["triangles"],
            "labelled_structures": variant["labelled_structures"],
            "structures": len(variant["structures"]),
            "bounds_deviation": tiers.get("standard", {}).get("bounds_relative_deviation"),
        })
        licenses[variant["license"]["class"]] += 1
    common = dict(source="public/anatomy/manifest.json + docs/anatomy/derivatives.json", time_frame=f"Manifest generated {manifest['generated_at_utc']}", population="Curated standalone anatomy assets")
    return [
        chart("anatomy_compression", "Original versus derived asset size", rows, sample_count=len(rows), sample_semantics="assets", metric="MB per tier; standard tier preserves triangle count", limitations=["Preview tiers reduce geometry and are labelled as such."], **common),
        chart("anatomy_licenses", "Asset licence classes", [{"license_class": key, "assets": value} for key, value in licenses.items()], sample_count=sum(licenses.values()), sample_semantics="assets", metric="Licence class from embedded asset metadata", **common),
    ]


def model_charts(db: Session) -> list[dict[str, Any]]:
    registry = list_models()
    statuses = Counter(model["status"] for model in registry["models"])
    runs = db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(50).all()
    run_rows = [{
        "run_id": run.id, "task_type": run.task_type, "model_id": run.model_id, "dataset": run.dataset_label, "n": run.n_samples,
        "headline": {key: value for key, value in (run.metrics.get("metrics") or {}).items() if isinstance(value, (int, float))},
        "input_sha256": run.input_sha256, "created_at": run.created_at.isoformat(),
    } for run in runs]
    return [
        chart("model_status", "Model registry states", [{"status": key, "models": value} for key, value in statuses.items()], source="model_registry/models.json",
              sample_count=registry["model_count"], sample_semantics="registered models", population="Registered model records", time_frame=None,
              metric="Registry status; activation requires a complete artifact bundle", limitations=[f"{registry['activatable_count']} of {registry['model_count']} models are activation-eligible."]),
        chart("evaluation_runs", "Evaluation runs on uploaded held-out predictions", run_rows, source="evaluation_runs table", sample_count=len(run_rows), sample_semantics="evaluation runs",
              population="Prediction files uploaded through the Validation Center", time_frame=None, metric="Task-appropriate metrics; see each run",
              limitations=["Metrics describe the uploaded predictions; they do not validate a model unless the predictions are genuinely held-out."]),
    ]


def _documented_position(item: MedicalMeasurement) -> str:
    if item.reference_low is None and item.reference_high is None:
        return "NO_DOCUMENTED_INTERVAL"
    if item.reference_low is not None and item.value < item.reference_low:
        return "BELOW"
    if item.reference_high is not None and item.value > item.reference_high:
        return "ABOVE"
    return "WITHIN"


def case_charts(db: Session, user: User) -> list[dict[str, Any]]:
    if user.role == UserRole.ADMIN:
        case_ids = [row.id for row in db.query(Case.id).all()]
    else:
        shared = {row.case_id for row in db.query(CaseMembership.case_id).filter(CaseMembership.user_id == user.id)}
        case_ids = [row.id for row in db.query(Case.id).filter(Case.created_by_id == user.id).all()] + list(shared)
    uploads = db.query(UploadedFile).filter(UploadedFile.case_id.in_(case_ids)).all() if case_ids else []
    statements = db.query(ClinicalReportStatement).filter(ClinicalReportStatement.case_id.in_(case_ids)).all() if case_ids else []
    measurements = db.query(MedicalMeasurement).filter(MedicalMeasurement.case_id.in_(case_ids)).all() if case_ids else []
    common = dict(source="Authorised case records", time_frame="All records to date", population=f"{len(case_ids)} authorised case(s)", model_version="rules-v1/v2 transparent extractor")
    assertion = Counter(f"{item.negation} / {item.certainty or 'NOT_ASSESSED_V1'}" for item in statements)
    analytes = Counter(item.display_name for item in measurements)
    positions = Counter(_documented_position(item) for item in measurements)
    return [
        chart("case_uploads", "Uploads by modality", [{"modality": key.value, "uploads": value} for key, value in Counter(item.modality for item in uploads).items()], sample_count=len(uploads), sample_semantics="uploaded files", metric="File count", **common),
        chart("case_statements", "Extracted statements by assertion and certainty", [{"assertion": key, "statements": value} for key, value in assertion.most_common()], sample_count=len(statements), sample_semantics="source-linked statements", metric="Statement count",
              limitations=["Rule extraction is unvalidated on an annotated corpus; counts describe outputs, not truth."], **common),
        chart("case_analytes", "Extracted measurements by analyte", [{"analyte": key, "measurements": value} for key, value in analytes.most_common(20)], sample_count=len(measurements), sample_semantics="source-linked measurements", metric="Measurement count", **common),
        chart("case_reference_positions", "Position against documented reference interval", [{"position": key, "measurements": value} for key, value in positions.items()], sample_count=len(measurements), sample_semantics="source-linked measurements",
              metric="Arithmetic comparison with the interval printed in the same source", limitations=["No population reference ranges are applied."], **common),
    ]


def test_evidence() -> dict[str, Any]:
    payload = _read_json(TEST_EVIDENCE_PATH)
    return payload or {"status": "NOT_AVAILABLE", "reason": "Run scripts/record_test_evidence.py to record the latest test run."}


def research_overview(db: Session, user: User) -> dict[str, Any]:
    return {
        "schema_version": "medtwin-research-analytics-1.0.0",
        "sections": {
            "datasets": dataset_charts(),
            "software": benchmark_charts(),
            "anatomy": anatomy_charts(),
            "models": model_charts(db),
            "cases": case_charts(db, user),
        },
        "unavailable_by_design": [
            {"chart": "ROC / PR curves of a deployed model", "reason": "No validated model has held-out predictions in this workspace; upload predictions in the Validation Center to compute them."},
            {"chart": "Risk trajectories and time-to-event plots", "reason": "No validated prognostic model or outcome cohort is registered."},
            {"chart": "Model-versus-model comparison", "reason": "Requires at least two evaluation runs on the same held-out dataset."},
            {"chart": "Data and model drift", "reason": "Requires a deployed model with production inputs over time."},
        ],
        "test_evidence": test_evidence(),
    }
