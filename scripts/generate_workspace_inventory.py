"""Generate a bounded, read-only MedTwin workspace inventory.

The scanner never extracts archives and never reads archive payloads. It reads ZIP
central directories, root-level metadata, and selected repository marker paths. It
writes only docs/integration/FILE_REGISTRY.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "integration" / "FILE_REGISTRY.json"
HASH_LIMIT_BYTES = 8 * 1024 * 1024

NAMED_REPOSITORIES = (
    "3d-anatomy-atlas-main",
    "anatomy-main",
    "cogstack-nlp-main",
    "CogStack-SemEHR-master",
    "health-assistant-main",
    "human-atlas-main",
    "MedCAT-main",
    "medical-main",
    "medvault-ai-main",
    "metriport-develop",
    "MONAI-dev",
    "radgraph-master",
    "scispacy-main",
    "SIH_26047-main",
    "TwinWeaver-main",
)

DATASET_DIRECTORIES = {
    "2d segmentation dataset",
    "BEHSOF",
    "Brain_Stroke_CT_Dataset",
    "cerebrovascular lesions",
    "data",
    "DATASET",
    "dyed-lifted-polyps",
    "dyed-resection-margins",
    "esophagitis",
    "External_test",
    "Gastrovision",
    "kvasir-dataset-v2",
    "LungcancerDataSet",
    "mri-tumor-detection-dataset(training and testing)",
    "normal-cecum",
    "normal-pylorus",
    "normal-z-line",
    "polyps",
    "segmentations",
    "split_data",
    "ST000001",
    "test",
    "Testing",
    "train",
    "Training",
    "ulcerative-colitis",
    "valid",
    "volume_pt1",
    "volume_pt2",
    "volume_pt3",
    "volume_pt4",
    "volume_pt5",
}

SKIP_REPOSITORY_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "node_modules",
}

MARKER_BASENAMES = {
    "dockerfile",
    "environment.yml",
    "environment.yaml",
    "license",
    "license.md",
    "license.txt",
    "license-apache",
    "package.json",
    "pyproject.toml",
    "requirements.in",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
}

WEIGHT_SUFFIXES = {".bin", ".ckpt", ".h5", ".onnx", ".pt", ".pth", ".safetensors"}
ENTRYPOINT_BASENAMES = {"app.py", "cli.py", "main.py", "manage.py", "run.py"}


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def sha256_if_bounded(path: Path) -> str | None:
    if path.stat().st_size > HASH_LIMIT_BYTES:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def category_for(path: Path) -> str:
    name = path.name
    lower = name.lower()
    if path.is_dir():
        if name in NAMED_REPOSITORIES:
            return "external_repository"
        if name in DATASET_DIRECTORIES:
            return "medical_dataset_or_split"
        if lower.startswith(".venv"):
            return "virtual_environment"
        if lower == "node_modules":
            return "dependency_cache"
        if lower in {"dist", ".pytest_cache"}:
            return "generated_output_or_cache"
        if name in {"backend", "src", "public", "scripts", "docs", ".github"}:
            return "medtwin_application"
        if name in {"dataset_registry", "model_registry"}:
            return "medtwin_registry"
        if name == "benchmarks":
            return "validation_output"
        if name == "MedTwin_2_Validation_Kit":
            return "validation_resource"
        if name in {".figma", ".vscode"}:
            return "development_tooling"
        if name == ".git":
            return "version_control_metadata"
        if name == "source":
            return "unclassified_source_tree"
        if name in {"heart blender", "textures"}:
            return "three_dimensional_source_asset"
        return "other_root_directory"
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "archive"
    if suffix == ".glb":
        return "three_dimensional_model"
    if suffix in {".docx", ".pdf", ".png"}:
        return "research_or_documentation_asset"
    if suffix in {".csv", ".yaml"} or lower.startswith("readme.dataset") or lower.startswith("readme.roboflow"):
        return "dataset_metadata"
    if suffix == ".py":
        return "utility_or_validation_source"
    if lower.startswith(".") or suffix in {".json", ".md", ".toml", ".ts", ".yml", ".ini", ".conf", ".html", ".txt"}:
        return "application_configuration_or_documentation"
    return "other_root_file"


def root_entry(path: Path) -> dict[str, object]:
    is_dir = path.is_dir()
    result: dict[str, object] = {
        "path": relative(path),
        "kind": "directory" if is_dir else "file",
        "category": category_for(path),
        "size_bytes": None if is_dir else path.stat().st_size,
        "sha256": None if is_dir else sha256_if_bounded(path),
    }
    if not is_dir and path.stat().st_size > HASH_LIMIT_BYTES:
        result["hash_status"] = f"not_computed_over_{HASH_LIMIT_BYTES}_bytes"
    return result


def unsafe_archive_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return True
    return ".." in PurePosixPath(normalized).parts


def inspect_archive(path: Path) -> dict[str, object]:
    record: dict[str, object] = {
        "path": relative(path),
        "size_bytes": path.stat().st_size,
        "inspection_mode": "zip_central_directory_only_no_extraction_no_crc_payload_scan",
        "central_directory_status": "unread",
        "member_count": None,
        "compressed_size_total": None,
        "uncompressed_size_total": None,
        "expansion_ratio": None,
        "unsafe_path_count": None,
        "encrypted_member_count": None,
        "symlink_member_count": None,
        "largest_member_uncompressed_bytes": None,
        "top_level_paths": [],
        "present_root_top_level_paths": [],
        "missing_root_top_level_paths": [],
        "central_directory_content_fingerprint_sha256": None,
        "potential_duplicate_archives": [],
        "matching_extracted_directory": None,
        "extraction_status": "not_extracted_by_inventory",
        "integration_status": "cataloged_only",
    }
    matching = ROOT / path.stem
    if matching.is_dir():
        record["matching_extracted_directory"] = relative(matching)
        record["extraction_status"] = "matching_root_directory_present_not_content_verified"
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            compressed = sum(item.compress_size for item in infos)
            uncompressed = sum(item.file_size for item in infos)
            top_level = sorted({item.filename.replace("\\", "/").split("/", 1)[0] for item in infos if item.filename})
            present_top_level = [name for name in top_level if (ROOT / name).exists()]
            missing_top_level = [name for name in top_level if not (ROOT / name).exists()]
            fingerprint = hashlib.sha256()
            for item in sorted(
                (item for item in infos if not item.is_dir()),
                key=lambda candidate: (candidate.CRC, candidate.file_size, candidate.compress_size),
            ):
                fingerprint.update(f"{item.CRC:08x}:{item.file_size}:{item.compress_size}\n".encode("ascii"))
            symlinks = sum(
                1
                for item in infos
                if stat.S_ISLNK((item.external_attr >> 16) & 0xFFFF)
            )
            record.update(
                {
                    "central_directory_status": "readable",
                    "member_count": len(infos),
                    "compressed_size_total": compressed,
                    "uncompressed_size_total": uncompressed,
                    "expansion_ratio": round(uncompressed / compressed, 3) if compressed else None,
                    "unsafe_path_count": sum(1 for item in infos if unsafe_archive_member(item.filename)),
                    "encrypted_member_count": sum(1 for item in infos if item.flag_bits & 0x1),
                    "symlink_member_count": symlinks,
                    "largest_member_uncompressed_bytes": max((item.file_size for item in infos), default=0),
                    "top_level_paths": top_level[:25],
                    "top_level_paths_truncated": len(top_level) > 25,
                    "present_root_top_level_paths": present_top_level[:25],
                    "missing_root_top_level_paths": missing_top_level[:25],
                    "central_directory_content_fingerprint_sha256": fingerprint.hexdigest(),
                }
            )
            if top_level and not missing_top_level:
                record["extraction_status"] = "all_root_top_level_paths_present_not_content_verified"
            elif present_top_level:
                record["extraction_status"] = "some_root_top_level_paths_present_not_content_verified"
            if record["unsafe_path_count"]:
                record["integration_status"] = "quarantined_path_review_required"
            elif record["expansion_ratio"] is not None and record["expansion_ratio"] > 100:
                record["integration_status"] = "cataloged_high_expansion_review_required"
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        record["central_directory_status"] = "error"
        record["inspection_error"] = f"{type(exc).__name__}: {exc}"
        record["integration_status"] = "disabled_unreadable_archive"
    return record


def inspect_dataset_directory(path: Path) -> dict[str, object]:
    extension_counts: dict[str, int] = {}
    total_size = 0
    file_count = 0
    marker_files: list[str] = []
    for current_root, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_REPOSITORY_DIRS)
        for filename in filenames:
            full = Path(current_root) / filename
            try:
                size = full.stat().st_size
            except OSError:
                continue
            file_count += 1
            total_size += size
            suffix = full.suffix.lower() or "[no_extension]"
            extension_counts[suffix] = extension_counts.get(suffix, 0) + 1
            lower = filename.lower()
            if (
                lower.startswith("readme")
                or lower in {"data.yaml", "dataset.yaml", "dataset.yml", "license", "license.txt", "license.md"}
                or suffix in {".csv", ".json", ".xml"}
            ) and len(marker_files) < 80:
                marker_files.append(full.relative_to(path).as_posix())
    return {
        "path": relative(path),
        "file_count": file_count,
        "total_size_bytes": total_size,
        "extension_counts": dict(sorted(extension_counts.items(), key=lambda item: (-item[1], item[0]))),
        "immediate_children": sorted(item.name for item in path.iterdir())[:100],
        "immediate_children_truncated": len(list(path.iterdir())) > 100,
        "metadata_candidates": sorted(marker_files),
        "inspection_status": "metadata_only_no_medical_payload_opened",
        "license_status": "requires_dataset_specific_review",
        "runtime_status": "not_integrated",
    }


def classify_repository_file(rel_path: str) -> str | None:
    path = Path(rel_path)
    lower_name = path.name.lower()
    lower_parts = {part.lower() for part in path.parts}
    if lower_name.startswith("readme"):
        return "readme"
    if lower_name in MARKER_BASENAMES or lower_name.startswith("license") or lower_name.startswith("copying"):
        return "license_or_dependency_manifest"
    if path.suffix.lower() in WEIGHT_SUFFIXES:
        return "weight_candidate"
    if lower_name in ENTRYPOINT_BASENAMES:
        return "entrypoint_candidate"
    if "test" in lower_parts or "tests" in lower_parts or lower_name.startswith("test_") or lower_name.endswith("_test.py"):
        return "test_candidate"
    if lower_name.startswith("docker-compose") or lower_name.startswith("dockerfile"):
        return "service_manifest"
    return None


def inspect_repository(path: Path) -> dict[str, object]:
    evidence: dict[str, list[str]] = {
        "readmes": [],
        "licenses_and_dependency_manifests": [],
        "entrypoint_candidates": [],
        "test_candidates": [],
        "weight_candidates": [],
        "service_manifests": [],
    }
    file_count = 0
    for current_root, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_REPOSITORY_DIRS)
        for filename in sorted(filenames):
            file_count += 1
            full = Path(current_root) / filename
            rel_path = full.relative_to(path).as_posix()
            kind = classify_repository_file(rel_path)
            if kind == "readme" and len(evidence["readmes"]) < 40:
                evidence["readmes"].append(rel_path)
            elif kind == "license_or_dependency_manifest" and len(evidence["licenses_and_dependency_manifests"]) < 80:
                evidence["licenses_and_dependency_manifests"].append(rel_path)
            elif kind == "entrypoint_candidate" and len(evidence["entrypoint_candidates"]) < 80:
                evidence["entrypoint_candidates"].append(rel_path)
            elif kind == "test_candidate" and len(evidence["test_candidates"]) < 80:
                evidence["test_candidates"].append(rel_path)
            elif kind == "weight_candidate" and len(evidence["weight_candidates"]) < 80:
                evidence["weight_candidates"].append(rel_path)
            elif kind == "service_manifest" and len(evidence["service_manifests"]) < 80:
                evidence["service_manifests"].append(rel_path)
    return {
        "path": relative(path),
        "present": path.is_dir(),
        "file_count_excluding_caches": file_count,
        "evidence": evidence,
        "evidence_lists_are_bounded": True,
        "runtime_status": "not_assessed_by_file_scanner",
    }


def main() -> None:
    root_paths = sorted(ROOT.iterdir(), key=lambda item: item.name.casefold())
    root_entries = [root_entry(path) for path in root_paths]
    archives = [inspect_archive(path) for path in root_paths if path.is_file() and path.suffix.lower() == ".zip"]
    fingerprints: dict[str, list[str]] = {}
    for archive in archives:
        fingerprint = archive.get("central_directory_content_fingerprint_sha256")
        if fingerprint:
            fingerprints.setdefault(str(fingerprint), []).append(str(archive["path"]))
    for archive in archives:
        fingerprint = archive.get("central_directory_content_fingerprint_sha256")
        duplicates = fingerprints.get(str(fingerprint), []) if fingerprint else []
        archive["potential_duplicate_archives"] = [item for item in duplicates if item != archive["path"]]
    repositories = [inspect_repository(ROOT / name) for name in NAMED_REPOSITORIES]
    datasets = [inspect_dataset_directory(ROOT / name) for name in sorted(DATASET_DIRECTORIES) if (ROOT / name).is_dir()]
    categories: dict[str, int] = {}
    for item in root_entries:
        category = str(item["category"])
        categories[category] = categories.get(category, 0) + 1
    readable = sum(item["central_directory_status"] == "readable" for item in archives)
    unsafe = sum(bool(item["unsafe_path_count"]) for item in archives if item["unsafe_path_count"] is not None)
    payload = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ROOT),
        "scope": {
            "root_entries": "all immediate files and directories",
            "archives": "all root ZIP central directories; no payload extraction or CRC payload scan",
            "repositories": "bounded marker-file discovery in the 15 extracted repositories named by the master prompt",
            "excluded_recursive_trees": sorted(SKIP_REPOSITORY_DIRS),
            "hash_policy": f"SHA-256 only for root files no larger than {HASH_LIMIT_BYTES} bytes",
        },
        "summary": {
            "root_entry_count": len(root_entries),
            "root_file_count": sum(item["kind"] == "file" for item in root_entries),
            "root_directory_count": sum(item["kind"] == "directory" for item in root_entries),
            "root_archive_count": len(archives),
            "readable_archive_count": readable,
            "archive_with_unsafe_path_count": unsafe,
            "named_extracted_repository_count": len(repositories),
            "dataset_directory_count": len(datasets),
            "dataset_file_count": sum(int(item["file_count"]) for item in datasets),
            "root_category_counts": dict(sorted(categories.items())),
        },
        "root_entries": root_entries,
        "archives": archives,
        "named_repository_file_evidence": repositories,
        "root_dataset_directory_evidence": datasets,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
