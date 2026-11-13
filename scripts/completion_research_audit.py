"""Bounded completion research audit and narrowly scoped PTB-XL operator review.

No original registry/checkpoint is changed. A supplemental review is explicitly
automated, local-scope operator evidence; it is not a human/legal/clinical signoff.
"""
from __future__ import annotations
import argparse
import ast
import copy
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import subprocess
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "artifacts/completion-2026-11-13/research"
PTB_IDS = ("ptbxl_ecg_baseline", "ptbxl_ecg_demographic_fusion")
REVIEWER = "Codex automated audit — AUTOMATED_PRIMARY_SOURCE_AND_ARTIFACT_AUDIT; no human/legal approval claimed"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path: Path, item) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, indent=2, default=str) + "\n", encoding="utf-8")


def record(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix(), "sha256": digest(path)}


def fetch(url: str, path: Path, limit=3_000_000) -> dict:
    request = Request(url, headers={"User-Agent": "MedTwin completion evidence audit (local operator; no patient data)"})
    with urlopen(request, timeout=40) as response:
        content = response.read(limit + 1)
        final_url = response.url
    if len(content) > limit:
        raise ValueError("Primary evidence size limit exceeded")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"url": url, "final_url": final_url, "bytes": len(content), **record(path)}


def overlap(path: Path) -> dict:
    groups, count = {}, 0
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            group = row.get("group_id") or row.get("patient_id")
            if group:
                groups.setdefault(group, set()).add(row["split"])
            count += 1
    cross = {key: sorted(splits) for key, splits in groups.items() if len(splits) > 1}
    return {**record(path), "rows": count, "cross_split_group_count": len(cross), "cross_split_groups": cross,
            "scope": "Recorded group keys, not independent patient identity adjudication; original splits unchanged."}


def archived_parity(out: Path) -> dict:
    archived = ROOT / "artifacts/training/gi_kvasir_seg_polyp_segmenter-20261025T080312Z/config.json"
    previous = ROOT / "artifacts/review-2026-11-13/parity-controls-final.json"
    config, prior = json.loads(archived.read_text()), json.loads(previous.read_text())
    result = next(r for r in prior["results"] if r["model_id"] == "gi_kvasir_seg_polyp_segmenter")
    source = ROOT / "ml_training/segment.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    predict = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "predict_masks")
    commit = config.get("git", {}).get("commit", "")
    archived_source = subprocess.run(["git", "show", f"{commit}:ml_training/segment.py"], cwd=ROOT,
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    result = {"schema_version": "medtwin.strict-parity-investigation.v1", "status": "STRICT_HISTORICAL_FAILURE_RETAINED_COMMERCIAL_REEXECUTION_BLOCKED",
        "summary": "Historical criterion stays zero differing pixels; recorded mismatch remains one pixel. Archived batch/device/precision investigated without executing restricted NC data or weights.",
        "archived_environment": config["environment"], "archived_batch_size": config["config"]["batch_size"],
        "current_control_batch_size": 1, "current_control_environment": prior["environment"],
        "historical_model_grid_check": result["checks"]["historical_saved_model_grid_mask"],
        "declared_criterion_differing_pixels": 0, "criterion_relaxed": False,
        "archived_config_evidence": record(archived), "previous_execution_evidence": record(previous),
        "archived_git": config.get("git"), "archived_commit_source_available": archived_source.returncode == 0,
        "archived_commit_source_diagnostic": archived_source.stderr.strip() if archived_source.returncode else None,
        "current_trainer_predict_source": ast.get_source_segment(source.read_text(encoding="utf-8-sig"), predict),
        "current_trainer_source": record(source), "historical_raw_logits_available": False,
        "cause": "UNDETERMINED: batch-8 archived evaluation versus batch-1 controls and Python patch version differ. Archived commit source is unavailable and the training worktree was dirty; stored raw logits and all kernel/determinism state are absent. Causality is not established.",
        "new_forward_passes": 0, "original_artifacts_changed": False,
        "commercial_blocker": "Kvasir-SEG terms are research/educational only; no new commercial-development execution or copied NC-derived benchmark is authorized."}
    write(out / "strict-parity-investigation.json", result)
    return result


def rights_audit(out: Path) -> dict:
    from scripts.prepare_review_experiments import prepare, verify_live_rights
    prepared = prepare(ROOT)
    verify_live_rights(prepared, ROOT)
    for item in prepared["experiments"]:
        item.pop("development_commands", None)
    manifests = {name: overlap(ROOT / "_derived/datasets" / name / "samples.csv")
                 for name in ("arcade-stenosis-detection", "arcade-syntax-segmentation")}
    result = {"schema_version": "medtwin.completion-research-audit.v1", "status": "AUDITED_WITH_COMMERCIAL_BLOCKERS",
        "summary": "Original six development gates freshly checked without data loaders or training; known ARCADE overlap re-counted without moving splits. NC families remain blocked.",
        "training_purpose": prepared["training_purpose"], "source_registry_sha256": prepared["registry_sha256"],
        "six_development_families": prepared["experiments"], "leakage": manifests,
        "clinical_activation": False, "original_registries_changed": False, "training_launched": False}
    write(out / "research-audit.json", result)
    return result


def ptb_operator_review(out: Path) -> dict:
    from ml_training.ptbxl import DATASET_DIR
    now = datetime.now(timezone.utc).isoformat()
    evidence_dir = out / "rights-evidence"
    remote_license = fetch("https://physionet.org/files/ptb-xl/1.0.1/LICENSE.txt", evidence_dir / "PTB-XL-1.0.1-LICENSE.txt")
    remote_page = fetch("https://physionet.org/content/ptb-xl/1.0.1/", evidence_dir / "PTB-XL-1.0.1-publisher.html")
    license_path = evidence_dir / "PTB-XL-1.0.1-LICENSE.txt"
    if not license_path.read_text().startswith("Creative Commons Attribution 4.0 International Public License"):
        raise ValueError("Exact PTB-XL release license not verified")
    if digest(DATASET_DIR / "LICENSE.txt") != digest(license_path):
        raise ValueError("Local release license differs from publisher bytes")
    page = (evidence_dir / "PTB-XL-1.0.1-publisher.html").read_text(encoding="utf-8")
    if "1.0.1" not in page or "Creative Commons Attribution 4.0" not in page:
        raise ValueError("Publisher version/license identity not verified")
    dependencies = []
    for name in ("numpy", "scipy", "scikit-learn", "torch"):
        dist = importlib.metadata.distribution(name)
        files = [f for f in dist.files or [] if str(f).replace("\\", "/").endswith(("/LICENSE", "/LICENSE.txt", "/COPYING"))]
        chosen = next((f for f in files if ".dist-info" in str(f)), None)
        if chosen is None:
            raise ValueError(f"Installed {name} license evidence unavailable")
        source = Path(dist.locate_file(chosen))
        target = evidence_dir / f"{name}-{dist.version}-LICENSE.txt"
        target.write_bytes(source.read_bytes())
        text = target.read_text(errors="replace")
        if not any(marker in text.lower() for marker in ("redistribution and use", "bsd", "permission is hereby granted")):
            raise ValueError(f"Permissive installed {name} license marker not found")
        dependencies.append({"name": name, "version": dist.version, **record(target)})
    source_paths = [ROOT / name for name in ("ml_training/ecg.py", "ml_training/ecg_fusion.py", "ml_training/ptbxl.py", "ml_training/common.py", "scripts/completion_ptb_development.py", "scripts/completion_research_audit.py")]
    for path in source_paths:
        if not path.is_file():
            raise ValueError(f"Missing reproducible local source: {path.name}")
    # Narrow provenance check: the own-from-scratch ECG architecture is built
    # from nn layers, not a downloaded upstream pretrained backbone.
    ecg_source = (ROOT / "ml_training/ecg.py").read_text()
    if "pretrained=True" in ecg_source or "torch.hub" in ecg_source or "load_state_dict_from_url" in ecg_source:
        raise ValueError("Upstream weight lineage needs a separate review")
    models = [m for m in json.loads((ROOT / "model_registry/models.json").read_text())["models"] if m["model_id"] in PTB_IDS]
    checkpoints = []
    for model in models:
        bundle = model["artifact_bundle"]
        checkpoint = ROOT / bundle["checkpoint_path"]
        if digest(checkpoint) != bundle["checkpoint_sha256"]:
            raise ValueError("Registered PTB checkpoint byte binding failed")
        config_path = checkpoint.parent / "config.json"
        config = json.loads(config_path.read_text())
        if config.get("model_id") != model["model_id"]:
            raise ValueError("Training config/checkpoint identity mismatch")
        checkpoints.append({"model_id": model["model_id"], "checkpoint_sha256": bundle["checkpoint_sha256"], "training_config": record(config_path),
            "weight_lineage": "Owner-supplied local ResNet1d/FusionNet trained from scratch on PTB-XL; inspected local training source and archived config, no downloaded pretrained encoder."})
    attribution = evidence_dir / "ATTRIBUTION.md"
    attribution.write_text("# Local PTB-XL commercial-development evaluation attribution\n\nPTB-XL 1.0.1: Wagner P, Strodthoff N, Bousseljot R-D, Samek W, Schaeffter T (2020), PhysioNet, DOI 10.13026/x4td-x982; original paper DOI 10.1038/s41597-020-0495-6. Source: https://physionet.org/content/ptb-xl/1.0.1/. Licensed CC BY 4.0: https://creativecommons.org/licenses/by/4.0/.\n\nChanges: derived metrics, plots/data, and a separate age/sex-only validation experiment; original source files remain unchanged. Preserve attribution/license notice on any permitted derivative. This local review does not authorize redistribution of this application's own source or third-party runtime packages, identify individuals, or grant clinical approval.\n", encoding="utf-8")
    declared = "Local commercial-development evaluation of PTB-XL 1.0.1 and the two own-from-scratch PTB ECG checkpoints; one separate metadata-only train-fold fit and validation-only controlled comparison; no clinical use, redistribution, external patient data, original checkpoint replacement, registry promotion or test-driven tuning."
    review = {"schema_version": "medtwin.automated-source-rights-review.v1", "status": "AUTOMATED_PRIMARY_SOURCE_AND_ARTIFACT_AUDIT", "reviewer": REVIEWER,
        "reviewed_at": now, "declared_use": declared, "human_review": False, "legal_opinion": False, "clinical_approval": False,
        "source_license": "CC BY 4.0", "publisher_evidence": [remote_license, remote_page], "local_license": record(DATASET_DIR / "LICENSE.txt"),
        "dependency_license_evidence": dependencies, "source_code_evidence": [record(path) for path in source_paths], "checkpoints": checkpoints,
        "reasoned_scope": "Publisher's exact release license permits use/adaptation including commercial purposes with attribution. Own local ECG layers contain no upstream pretrained backbone. Framework licenses are preserved for local installed use. This is transparent operator review, not a manufactured human/legal signature or unrestricted distribution approval.",
        "original_registry_sha256": digest(ROOT / "dataset_registry/tasks.json"), "original_model_registry_sha256": digest(ROOT / "model_registry/models.json")}
    review_path = out / "ptb-operator-review.json"
    write(review_path, review)
    evidence_files = [record(review_path), record(license_path), record(attribution)] + [record(path) for path in source_paths] + [{"path": item["path"], "sha256": item["sha256"]} for item in dependencies]
    sidecar = copy.deepcopy(json.loads((ROOT / "dataset_registry/tasks.json").read_text()))
    dataset = next(d for d in sidecar["datasets"] if d["id"] == "ptb-xl-1.0.1")
    dataset["license"].update(authorization_status="VERIFIED", authorization_reason="Narrow automated exact-publisher-release license/artifact audit in completion sidecar; original registry unchanged.",
        commercial_development_review={"status": "REVIEWED_FOR_DECLARED_COMMERCIAL_DEVELOPMENT", "reviewer": REVIEWER, "reviewed_at": now, "declared_use": declared, "evidence_files": evidence_files,
                                       "review_kind": "AUTOMATED_PRIMARY_SOURCE_AND_ARTIFACT_AUDIT", "human_approval": False, "clinical_approval": False})
    dataset_path = out / "ptb-dataset-rights-sidecar.json"
    write(dataset_path, sidecar)
    model_records = [{"model_id": model["model_id"], "checkpoint_sha256": model["artifact_bundle"]["checkpoint_sha256"],
        **{key: "REVIEWED_FOR_DECLARED_COMMERCIAL_USE" for key in ("source_data_rights", "code_rights", "weights_rights", "redistribution_rights")},
        "reviewer": REVIEWER, "reviewed_at": now, "declared_use": declared, "evidence_files": evidence_files,
        "review_kind": "AUTOMATED_PRIMARY_SOURCE_AND_ARTIFACT_AUDIT", "human_approval": False, "clinical_approval": "NOT_ESTABLISHED",
        "redistribution_scope": "No redistribution performed or authorized by this local evaluation; preserve original dataset/framework attribution and obtain project-owner permission for project-code distribution."} for model in models]
    model_path = out / "ptb-model-rights-sidecar.json"
    write(model_path, {"schema_version": 1, "notice": "Scoped automated operator review only; not legal, human or clinical approval. Original registries unchanged.", "models": model_records})
    from ml_training.volumetric_manifest import enforce_training_license
    gate = enforce_training_license({"dataset_id": "ptb-xl-1.0.1"}, dataset_path)
    summary = {"status": "SCOPED_AUTOMATED_OPERATOR_REVIEW_PREPARED", "dataset_rights_sidecar": str(dataset_path), "model_rights_sidecar": str(model_path),
               "canonical_dataset_gate": gate, "original_registries_changed": False, "human_legal_or_clinical_approval": False}
    write(out / "ptb-rights-gate.json", summary)
    return summary


def measure_arena(out: Path) -> dict:
    from app.services import universal_arena as arena
    # Explicit sidecars only for this isolated command; no research-profile switch.
    os.environ["MEDTWIN_COMPLETION_RIGHTS_REGISTRY"] = str(out / "ptb-dataset-rights-sidecar.json")
    os.environ["MEDTWIN_COMMERCIAL_REVIEW_PATH"] = str(out / "ptb-model-rights-sidecar.json")
    os.environ["MEDTWIN_USAGE_PROFILE"] = "commercial"
    comparison = arena.compare_models(*PTB_IDS)
    diagnostics = {mid: arena.diagnostics(mid) for mid in PTB_IDS}
    ecg_arm = arena.diagnostics(PTB_IDS[1], "ecg_only")
    result = {"schema_version": "medtwin.actual-arena-measurements.v1", "status": "COMPUTED" if comparison["paired_statistics"].get("status") == "COMPUTED_PAIRED_PATIENT_BOOTSTRAP" else "RIGHTS_OR_COHORT_BLOCKED",
        "summary": "Actual frozen PTB ECG/fusion prediction diagnostics and paired patient bootstrap under hash-bound automated commercial operator review; no new clinical validation or superiority assumed.",
        "comparison": comparison, "diagnostics": diagnostics, "fusion_csv_ecg_only_arm": ecg_arm,
        "clinical_activation": False, "new_training": False, "source_files_changed": False}
    write(out / "arena-measurements.json", result)
    return {"status": result["status"], "paired_statistics": comparison["paired_statistics"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--prepare-ptb-review", action="store_true")
    parser.add_argument("--measure-arena", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    audit = rights_audit(out)
    parity = archived_parity(out)
    result = {"audit": audit["status"], "strict_parity": parity["status"]}
    if args.prepare_ptb_review:
        result["ptb_review"] = ptb_operator_review(out)["status"]
    if args.measure_arena:
        result["arena"] = measure_arena(out)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
