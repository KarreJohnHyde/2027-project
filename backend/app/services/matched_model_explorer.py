"""Same-input saved PTB-XL record comparison with strict source and rights gates.

No model execution, clinical decision or case linkage occurs. Raw publisher
record IDs, patient keys, dates, paths, ages and sex values never leave this module.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from app.services import universal_arena as arena
from app.schemas.matched_model_explorer import MatchedRecordsQuery

BASELINE = "ptbxl_ecg_baseline"
FUSION = "ptbxl_ecg_demographic_fusion"
LABELS = ["NORM", "MI", "STTC", "CD", "HYP"]
NOTICE = ("Saved public PTB-XL research predictions on matching publisher records, references and source bytes; no new inference. "
          "Reference annotations are ECG superclass labels, not adjudicated diagnoses. Probabilities are validation-calibrated model scores, not clinical certainty. "
          "Per-record errors and disagreements do not establish model superiority. Source-byte checks do not independently replay historical forward passes. "
          "Record pseudonyms identify public research samples only; no patient IDs or private case linkage are exposed.")


def _hash(item) -> str:
    return hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _pseudonym(identity: str) -> str:
    return "ptb-" + hashlib.sha256(f"medtwin.ptbxl.1.0.1.record:{identity}".encode()).hexdigest()[:20]


def _file_sha256(path: Path) -> str:
    # Deliberately independent of the Arena's stat-keyed digest cache. A file
    # changed with an unchanged size/mtime must invalidate the matched snapshot.
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publisher_data() -> dict:
    from ml_training.ptbxl import DATASET_DIR
    paths = [DATASET_DIR / name for name in ("ptbxl_database.csv", "scp_statements.csv", "SHA256SUMS.txt")]
    if any(not path.is_file() or path.stat().st_size > 32 * 1024 * 1024 for path in paths):
        raise ValueError("BOUNDED_PUBLISHER_METADATA_UNAVAILABLE")
    hashes = tuple(_file_sha256(path) for path in paths)
    return _publisher_cached(str(DATASET_DIR), hashes)


@lru_cache(maxsize=2)
def _publisher_cached(root_string: str, hashes: tuple[str, ...]) -> dict:
    from ml_training.ptbxl import load_metadata, publisher_checksums, dataset_version, verify_files, assert_patient_disjoint
    root = Path(root_string)
    records, _, _ = load_metadata(root)
    if len(records) > 30_000:
        raise ValueError("PUBLISHER_RECORD_LIMIT_EXCEEDED")
    sums = publisher_checksums(root)
    verify_files(["ptbxl_database.csv", "scp_statements.csv"], sums, root)
    assert_patient_disjoint(records)
    missingness = {}
    with (root / "ptbxl_database.csv").open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            missingness[row["ecg_id"]] = {"age_missing": not bool(row.get("age", "").strip()),
                "sex_missing": row.get("sex", "").strip() not in {"0", "0.0", "1", "1.0"}}
    return {"root": root, "records": {str(row["ecg_id"]): row for row in records if row["split"] == "test"},
            "sums": sums, "missingness": missingness, "dataset_version": dataset_version(records, sums),
            "metadata_sha256": hashes[0], "label_table_sha256": hashes[1], "checksum_manifest_sha256": hashes[2]}


def _source_bytes(identity: str, publisher: dict) -> dict:
    row = publisher["records"][identity]
    root = publisher["root"].resolve()
    proofs = {}
    for suffix, name in ((".hea", "header_sha256"), (".dat", "waveform_sha256")):
        relative = row["file"] + suffix
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("SELECTED_INPUT_BYTES_UNAVAILABLE")
        actual = _file_sha256(path)
        if actual != publisher["sums"].get(relative):
            raise ValueError("SELECTED_INPUT_PUBLISHER_HASH_MISMATCH")
        proofs[name] = actual
    return {"status": "MATCHED_PUBLISHER_RECORD_AND_CURRENT_SOURCE_BYTES", **proofs}


def _threshold(model: dict, report: dict, label: str, arm: str | None) -> tuple[float, str]:
    if arm == "ecg_only":
        entries = (report.get("arms", {}).get("ecg_only") or {}).get("per_class", [])
        threshold = next((entry.get("threshold_from_validation") for entry in entries if entry.get("class") == label), None)
        source = "SAME_RUN_ECG_ONLY_VALIDATION_THRESHOLD"
    else:
        threshold = ((model.get("artifact_bundle", {}).get("decision_thresholds") or {}).get("values") or {}).get(label)
        source = "REGISTERED_VALIDATION_THRESHOLD"
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("FROZEN_VALIDATION_THRESHOLD_UNAVAILABLE")
    return float(threshold), source


def query_records(request: MatchedRecordsQuery) -> dict:
    result = {"schema_version": "medtwin.matched-model-records.v1", "status": "UNAVAILABLE", "reason": None,
        "mode": request.mode, "label": request.label, "labels": LABELS, "order": request.order, "offset": request.offset,
        "limit": request.limit, "total": 0, "total_filtered": 0, "snapshot_id": None, "cohort": {}, "models": {},
        "rows": [], "never_writes": True, "clinical_activation": False, "notice": NOTICE}
    models = {m["model_id"]: m for m in arena.model_inference._load_registry()["models"] if m.get("research_inference")}
    left_id = BASELINE if request.mode == "global" else FUSION
    if left_id not in models or FUSION not in models:
        return {**result, "reason": "REQUIRED_RECORDED_MODELS_UNAVAILABLE"}
    left, right = models[left_id], models[FUSION]
    # No prediction, report, source-metadata or waveform read before both rights
    # decisions pass. Registry/rights evidence itself is not case data.
    if not all(arena._evaluation_rights(model).get("allowed") for model in (left, right)):
        return {**result, "status": "RIGHTS_BLOCKED", "reason": "COMMERCIAL_SOURCE_AND_MODEL_RIGHTS_GATE_NOT_PASSED"}
    try:
        bundles = [m.get("artifact_bundle") or {} for m in (left, right)]
        if any(m.get("task") != "multilabel_ecg_classification" or m.get("supported_classes") != LABELS for m in (left, right)):
            raise ValueError("TASK_OR_ORDERED_LABEL_DEFINITION_MISMATCH")
        if not bundles[0].get("dataset_version") or bundles[0].get("dataset_version") != bundles[1].get("dataset_version") or bundles[0].get("label_definition") != bundles[1].get("label_definition"):
            raise ValueError("DATASET_OR_TARGET_DEFINITION_MISMATCH")
        reports = [arena.model_inference._report(model) for model in (left, right)]
        for model, report in zip((left, right), reports):
            if arena._binding(model, report)["status"] != "VERIFIED_DECLARED_ARTIFACT_BINDING":
                raise ValueError("REPORT_REGISTRY_BINDING_UNVERIFIED")
            checkpoint = arena._resolve_artifact_path(model["artifact_bundle"]["checkpoint_path"])
            if _file_sha256(checkpoint) != model["artifact_bundle"]["checkpoint_sha256"]:
                raise ValueError("CHECKPOINT_BYTES_HASH_MISMATCH")
        arms = (None, None) if request.mode == "global" else ("ecg_only", "fusion")
        specs = [arena._prediction_spec(model, arm) for model, arm in zip((left, right), arms)]
        matrices = [arena._prediction_matrix(*spec) for spec in specs]
        a, b = matrices
        for spec, matrix in zip(specs, matrices):
            if _file_sha256(Path(spec[0])) != matrix["prediction_sha256"]:
                raise ValueError("PREDICTION_BYTES_CHANGED_DURING_READ_OR_CACHE")
        if a["ids"] != b["ids"] or a["patients"] != b["patients"] or not all(a["patients"]) or not np.array_equal(a["y"], b["y"]):
            raise ValueError("MATCHED_PATIENT_RECORD_OR_REFERENCE_LABEL_TUPLES_DIFFER")
        if any(report.get("test_n") != len(a["ids"]) for report in reports):
            raise ValueError("REPORT_COHORT_COUNT_MISMATCH")
        publisher = _publisher_data()
        if publisher["dataset_version"] != bundles[0]["dataset_version"]:
            raise ValueError("PUBLISHER_DATASET_VERSION_MISMATCH")
        for index, identity in enumerate(a["ids"]):
            reference = publisher["records"].get(identity)
            if (not reference or reference["patient_id"] != a["patients"][index]
                    or [int(label in reference["labels"]) for label in LABELS] != a["y"][index].tolist()):
                raise ValueError("PUBLISHER_HELD_OUT_RECORD_OR_REFERENCE_TUPLE_MISMATCH")
        column = LABELS.index(request.label)
        thresholds = [_threshold(model, report, request.label, arm) for model, report, arm in zip((left, right), reports, arms)]
        cohort_digest = _hash([[identity, patient, *truth.tolist()] for identity, patient, truth in zip(a["ids"], a["patients"], a["y"])])
        descriptors = {}
        for side, model, matrix, arm, threshold in zip(("left", "right"), (left, right), matrices, arms, thresholds):
            control_only = request.mode == "same_run" and arm == "ecg_only"
            descriptors[side] = {"model_id": model["model_id"], "arm": arm or ("fusion" if model["model_id"] == FUSION else "ecg_only"),
                "checkpoint_sha256": None if control_only else model["artifact_bundle"]["checkpoint_sha256"],
                "associated_run_checkpoint_sha256": model["artifact_bundle"]["checkpoint_sha256"],
                "checkpoint_binding_status": "CONTROL_ARM_CHECKPOINT_NOT_ARCHIVED" if control_only else "REGISTERED_CHECKPOINT_BYTES_VERIFIED",
                "prediction_sha256": matrix["prediction_sha256"],
                "probability_prefix": matrix["probability_prefix"], "threshold": threshold[0], "threshold_source": threshold[1],
                "decision_rule": "probability >= frozen validation threshold", "evaluation_url": f"/validation?model={model['model_id']}"}
        provenance = {key: publisher[key] for key in ("metadata_sha256", "label_table_sha256", "checksum_manifest_sha256")}
        snapshot_id = _hash({"mode": request.mode, "label": request.label, "models": descriptors, "cohort": cohort_digest, "publisher": provenance})
        result.update(snapshot_id=snapshot_id, models=descriptors, total=len(a["ids"]),
            cohort={"records": len(a["ids"]), "patients": len(set(a["patients"])), "tuple_sha256": cohort_digest,
                    "dataset_version": publisher["dataset_version"], **provenance})
        if request.expected_snapshot_id and request.expected_snapshot_id != snapshot_id:
            return {**result, "status": "SNAPSHOT_CHANGED", "reason": "Source bytes, cohort or decision policy changed; refresh before paging."}
        rows = []
        for index, identity in enumerate(a["ids"]):
            pseudonym = _pseudonym(identity)
            if request.search and request.search.casefold() not in pseudonym.casefold():
                continue
            truth = int(a["y"][index, column])
            decisions = []
            for matrix, (threshold, _) in zip(matrices, thresholds):
                probability = float(matrix["p"][index, column])
                predicted = int(probability >= threshold)
                error = ("TRUE_POSITIVE" if truth else "FALSE_POSITIVE") if predicted else ("FALSE_NEGATIVE" if truth else "TRUE_NEGATIVE")
                decisions.append({"probability": probability, "predicted_label": predicted, "error_type": error})
            errors = sum(decision["predicted_label"] != truth for decision in decisions)
            if request.errors_only and errors == 0:
                continue
            rows.append({"record_pseudonym": pseudonym, "reference_label": truth, "left": decisions[0], "right": decisions[1],
                "decision_disagreement": decisions[0]["predicted_label"] != decisions[1]["predicted_label"],
                "absolute_probability_gap": abs(decisions[1]["probability"] - decisions[0]["probability"]),
                "missingness": publisher["missingness"].get(identity, {"age_missing": True, "sex_missing": True}),
                "_identity": identity, "_errors": errors})
        def sort(row):
            gap, disagreement, errors = row["absolute_probability_gap"], int(row["decision_disagreement"]), row["_errors"]
            ranking = (-disagreement, -gap, -errors) if request.order == "disagreement" else (-errors, -disagreement, -gap) if request.order == "errors" else (-gap, -disagreement, -errors)
            return (*ranking, row["record_pseudonym"])
        rows.sort(key=sort)
        result["total_filtered"] = len(rows)
        page = rows[request.offset:request.offset + request.limit]
        for row in page:
            row["input_provenance"] = _source_bytes(row.pop("_identity"), publisher)
            row.pop("_errors")
        return {**result, "status": "MATCHED_RECORDS_AVAILABLE", "rows": page}
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        # Error strings are fixed codes only: never echo raw input rows or paths.
        reason = str(error) if isinstance(error, ValueError) and str(error).replace("_", "").isalnum() else "RECORDED_SOURCE_OR_PROVENANCE_UNAVAILABLE"
        return {**result, "status": "UNAVAILABLE", "reason": reason, "rows": []}
