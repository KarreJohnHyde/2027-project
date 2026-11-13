"""Read-only checkpoint/report reconciliation. Never loads models or grants eligibility.

This can run without Torch/CUDA and labels saved evaluation metrics as historical.
Only files named by the current registry are inspected; datasets are not crawled.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "model_id", "task", "registry_status", "validated_flag", "checkpoint_path",
    "checkpoint_sha256_expected", "checkpoint_sha256_actual", "checkpoint_integrity",
    "component_checkpoint_integrity_json",
    "dataset", "dataset_version", "permission_scope", "evaluation_unit",
    "sample_count", "patient_count", "split", "preprocessing_version", "metrics_json",
    "thresholds_json", "refusals_exclusions_json", "recorded_run_id", "recorded_evaluation_timestamp",
    "measurement_origin", "runtime", "eligibility", "report_path", "report_sha256",
    "binding_issues", "snapshot_issues", "limitations", "audit_timestamp", "code_revision",
    "working_tree_dirty", "registry_sha256",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Registry evidence path leaves the selected workspace.")
    return path


def json_file(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def git_state(root: Path) -> dict:
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return {"code_revision": "UNKNOWN", "working_tree_dirty": "UNKNOWN"}
    return {"code_revision": revision, "working_tree_dirty": dirty}


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False) if value is not None else ""


def _checkpoint_hash(report: dict):
    checkpoint = report.get("checkpoint")
    return report.get("checkpoint_sha256") or (checkpoint.get("sha256") if isinstance(checkpoint, dict) else None)


def _metrics(report: dict) -> dict:
    # Preserve metric names/units/intervals, rather than silently equating different tasks.
    result = {}
    for key in ("test", "metrics", "per_class", "clinical_indices", "test_serving_gate", "fusion_comparison", "operating_point", "dice_lungs", "volume_difference_ml", "summary"):
        if key in report:
            result[key] = report[key]
    return result


def _count(report: dict):
    test = report.get("test") or {}
    for source in (report, test):
        if isinstance(source, dict):
            for name in ("test_n", "n_images", "n_records", "n_patients", "n_videos", "scans", "n"):
                if name in source:
                    return source[name]
    return (report.get("split_counts") or {}).get("test", "")


def _patients(report: dict):
    if "test_patients" in report:
        return report["test_patients"]
    patients = report.get("patients") or {}
    if isinstance(patients, dict):
        return (patients.get("patients_per_split") or {}).get("test", "UNKNOWN")
    return "UNKNOWN"


def inspect_model(root: Path, model: dict, snapshot: dict | None) -> dict:
    bundle = model.get("artifact_bundle") or {}
    issues, snapshot_issues = [], []
    checkpoint_name = bundle.get("checkpoint_path") or model.get("weights_path")
    expected = bundle.get("checkpoint_sha256")
    actual, integrity = "", "NOT_DECLARED"
    if checkpoint_name:
        try:
            checkpoint = local_path(root, checkpoint_name)
            if checkpoint.is_dir():
                integrity = "DIRECTORY_ADAPTER_UNPINNED"
            elif not checkpoint.is_file():
                integrity = "MISSING"
            else:
                actual = sha256(checkpoint)
                integrity = "MATCH" if expected and actual == expected else "HASH_MISMATCH" if expected else "NO_EXPECTED_HASH"
        except (ValueError, OSError) as exc:
            integrity = "UNREADABLE_OR_OUTSIDE_WORKSPACE"
            issues.append(f"CHECKPOINT_READ:{type(exc).__name__}")
    components = []
    declared_components = bundle.get("component_checkpoints_sha256") or {}
    if declared_components and checkpoint_name:
        # Inspect exact named bundles only. Fast and full models can use different
        # trainer names; at most one immediate trainer/fold checkpoint is resolved.
        try:
            primary = local_path(root, checkpoint_name)
            anchors = [parent for parent in primary.parents if parent.name in declared_components]
            if not anchors:
                issues.append("COMPONENT_LAYOUT_NOT_RESOLVED")
            else:
                anchor = anchors[0]
                suffix = primary.relative_to(anchor)
                for name, expected_component in declared_components.items():
                    component = local_path(root, str(anchor.parent / name / suffix))
                    if not component.is_file():
                        component_root = local_path(root, str(anchor.parent / name))
                        candidates = list(component_root.glob(f"*/{primary.parent.name}/{primary.name}"))
                        if len(candidates) == 1:
                            component = local_path(root, str(candidates[0]))
                        elif len(candidates) > 1:
                            issues.append(f"AMBIGUOUS_COMPONENT_CHECKPOINT:{name}")
                    component_actual = sha256(component) if component.is_file() else ""
                    components.append({"name": name, "path": str(component.relative_to(root)),
                        "expected_sha256": expected_component, "actual_sha256": component_actual,
                        "integrity": "MATCH" if component_actual == expected_component else "HASH_MISMATCH" if component_actual else "MISSING"})
        except (ValueError, OSError):
            issues.append("COMPONENT_LAYOUT_OR_READ_FAILURE")
    report, report_hash = {}, ""
    report_name = bundle.get("evaluation_report_path")
    if report_name:
        try:
            report_path = local_path(root, report_name)
            report = json_file(report_path)
            report_hash = sha256(report_path)
        except (OSError, ValueError):
            issues.append("EVALUATION_REPORT_MISSING_OR_INVALID")
        if report:
            if report.get("model_id") != model["model_id"]:
                issues.append("REPORT_MODEL_ID_MISMATCH_OR_ABSENT")
            if bundle.get("dataset_version") and report.get("dataset_version") != bundle["dataset_version"]:
                issues.append("REPORT_DATASET_VERSION_MISMATCH_OR_ABSENT")
            report_checkpoint_hash = _checkpoint_hash(report)
            if expected and report_checkpoint_hash != expected:
                issues.append("REPORT_CHECKPOINT_HASH_MISMATCH_OR_ABSENT")
    if snapshot is None:
        snapshot_issues.append("MISSING_FROM_SAVED_SNAPSHOT")
    else:
        if snapshot.get("status") != model.get("status"):
            snapshot_issues.append("STATUS_DIFFERS")
        if expected and snapshot.get("checkpoint_sha256") != expected:
            snapshot_issues.append("CHECKPOINT_DIFFERS_OR_ABSENT")
    task = model.get("task", "")
    if report.get("scans") is not None:
        unit = "CT scans; limited reference-mask agreement, see original report"
    elif report.get("test_patients") is not None:
        unit = "patients (per-case volume metrics; see original report)"
    elif "ecg" in task:
        unit = "ECG records; patient count separately recorded"
    elif task == "object_detection":
        unit = "images/lesion boxes; see matching protocol"
    elif "survival" in task:
        unit = "patients"
    elif "echo" in task:
        unit = "videos; see report for patient identity"
    else:
        unit = "report-defined; do not infer patient independence"
    scope = bundle.get("dataset_license") or (report.get("dataset_license") or "UNKNOWN")
    eligibility = "NOT_RECOMPUTED: file integrity is not runtime, purpose or clinical eligibility"
    if model.get("status") == "FAILED" or (model.get("research_quality_assessment") or {}).get("status") == "FAILED_DECLARED_TARGET":
        eligibility = "BLOCKED_FAILED_TARGET; no activation or replacement performed"
    elif model.get("processor_only"):
        eligibility = "PROCESSOR_OR_FRAMEWORK_ONLY; not a validated predictive model"
    elif model.get("research_inference"):
        eligibility = "DECLARED_RESEARCH_ONLY; live purpose/input gates must still pass"
    refusals = {key: report[key] for key in ("excluded_records", "test_serving_gate", "refusals", "exclusions") if key in report}
    return {
        "model_id": model["model_id"], "task": task,
        "registry_status": model.get("status", "UNKNOWN"), "validated_flag": model.get("validated", False),
        "checkpoint_path": checkpoint_name or "", "checkpoint_sha256_expected": expected or "",
        "checkpoint_sha256_actual": actual, "checkpoint_integrity": integrity,
        "component_checkpoint_integrity_json": _compact(components),
        "dataset": report.get("dataset_id") or report.get("dataset") or report.get("reference") or "NOT_REPORTED",
        "dataset_version": bundle.get("dataset_version") or "", "permission_scope": scope if isinstance(scope, str) else _compact(scope),
        "evaluation_unit": unit, "sample_count": _count(report), "patient_count": _patients(report),
        "split": ("RECORDED_REFERENCE_EVALUATION" if report.get("reference") and not report.get("test") else "RECORDED_TEST") if report else "NO_BOUND_REPORT",
        "preprocessing_version": bundle.get("preprocessing_version") or "",
        "metrics_json": _compact(_metrics(report)) if report else "",
        "thresholds_json": _compact(bundle.get("decision_thresholds")), "refusals_exclusions_json": _compact(refusals),
        "recorded_run_id": report.get("run_id", ""),
        "recorded_evaluation_timestamp": report.get("evaluated_at") or report.get("evaluation_timestamp") or report.get("generated_at") or report.get("generated_on") or "NOT_RECORDED; run_id retained separately",
        "measurement_origin": "HISTORICAL_RECORDED_NOT_REPRODUCED" if report else "NO_BOUND_EVALUATION",
        "runtime": "UNVERIFIED_BY_READ_ONLY_AUDIT", "eligibility": eligibility,
        "report_path": report_name or "", "report_sha256": report_hash,
        "binding_issues": ";".join(issues), "snapshot_issues": ";".join(snapshot_issues),
        "limitations": " | ".join(dict.fromkeys(model.get("limitations", []) + report.get("limitations", []))),
    }


def audit(root: Path, registry_name="model_registry/models.json", snapshot_name="model_registry/validation_status.json") -> dict:
    root = root.resolve()
    registry_path = local_path(root, registry_name)
    registry = json_file(registry_path)
    models = registry.get("models")
    if not isinstance(models, list) or any(not isinstance(model, dict) or not model.get("model_id") for model in models):
        raise ValueError("Registry must contain a models list with identifiers.")
    if len({model["model_id"] for model in models}) != len(models):
        raise ValueError("Duplicate model identifiers in registry.")
    try:
        saved = json_file(local_path(root, snapshot_name))
    except (OSError, ValueError):
        saved = {}
    snapshots = {item["model_id"]: item for item in saved.get("models", [])}
    context = {"audit_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), **git_state(root), "registry_sha256": sha256(registry_path)}
    rows = [{**inspect_model(root, model, snapshots.get(model["model_id"])), **context} for model in models]
    return {
        "schema_version": "medtwin-review-model-evidence-1", **context,
        "scope": "Read-only local evidence and checkpoint hashes; no inference, training, gate approval or clinical validation.",
        "saved_snapshot_timestamp": saved.get("generated_at", "UNKNOWN"),
        "snapshot_only_model_ids": sorted(set(snapshots) - {model["model_id"] for model in models}),
        "summary": {
            "models": len(rows), "checkpoint_hash_matches": sum(row["checkpoint_integrity"] == "MATCH" for row in rows),
            "checkpoint_integrity_issues": sum(row["checkpoint_integrity"] not in ("MATCH", "NOT_DECLARED") for row in rows),
            "bound_report_issues": sum(bool(row["binding_issues"]) for row in rows),
            "snapshot_discrepancies": sum(bool(row["snapshot_issues"]) for row in rows),
            "component_checkpoint_hash_matches": sum(sum(item["integrity"] == "MATCH" for item in json.loads(row["component_checkpoint_integrity_json"])) for row in rows),
            "component_checkpoint_integrity_issues": sum(sum(item["integrity"] != "MATCH" for item in json.loads(row["component_checkpoint_integrity_json"])) for row in rows),
            "new_predictive_evaluations": 0,
        }, "models": rows,
    }


def write_outputs(payload: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "MEDTWIN_MODEL_RESULTS_2026-11-13.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(payload["models"])
    (output / "MEDTWIN_MODEL_EVIDENCE_2026-11-13.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/review-2026-11-13")
    parser.add_argument("--require-integrity", action="store_true", help="Exit nonzero for named checkpoint integrity or report binding failures; processors without checkpoints are not failures.")
    args = parser.parse_args(argv)
    payload = audit(args.root)
    write_outputs(payload, args.out)
    print(json.dumps(payload["summary"]))
    return int(args.require_integrity and bool(payload["summary"]["checkpoint_integrity_issues"] or payload["summary"]["component_checkpoint_integrity_issues"] or payload["summary"]["bound_report_issues"]))


if __name__ == "__main__":
    raise SystemExit(main())
