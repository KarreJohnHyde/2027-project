"""Bounded, read-only audit of registered and prepared MedTwin datasets.

No model imports, training, recursive disk discovery, registry writes or rights
approval occur. Full manifest grouping checks and bounded NEW byte checks are
reported separately from historical recorded hashes and near-duplicate claims.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GROUP_FIELDS = ("patient_id", "patient", "subject_id", "group_id")
PATH_FIELDS = ("path", "image_path", "video_path", "record_path", "entry")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def first(row: dict, fields: tuple[str, ...]) -> tuple[str | None, str]:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return field, str(value).strip()
    return None, ""


def split_name(value: Any) -> str:
    name = str(value or "UNSPECIFIED").strip().lower()
    return {"valid": "val", "validation": "val", "training": "train", "testing": "test"}.get(name, name)


def grouping_summary(rows: list[dict]) -> dict:
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    paths: dict[str, set[str]] = defaultdict(set)
    recorded_hashes: dict[str, set[str]] = defaultdict(set)
    exact_dhash: dict[str, set[str]] = defaultdict(set)
    fields = Counter()
    missing = 0
    for row in rows:
        split = split_name(row.get("split"))
        field, group = first(row, GROUP_FIELDS)
        if field is None:
            missing += 1
        else:
            # Keep patient and study-derived image groups distinguishable.
            groups[(field, group)].add(split)
            fields[field] += 1
        _, path = first(row, PATH_FIELDS)
        if path:
            paths[path.replace("\\", "/").casefold()].add(split)
        sha = row.get("image_sha256") or row.get("sha256")
        if sha:
            recorded_hashes[str(sha)].add(split)
        if row.get("dhash"):
            exact_dhash[str(row["dhash"])].add(split)
    def crossed(mapping):
        return [token(str(key)) for key, splits in mapping.items() if len(splits) > 1]
    group_crossings = crossed(groups)
    return {
        "rows": len(rows), "split_counts": dict(Counter(split_name(row.get("split")) for row in rows)),
        "group_fields": dict(fields), "rows_without_group": missing,
        "group_count": len(groups), "groups_crossing_splits": len(group_crossings),
        "crossing_group_tokens": group_crossings[:20],
        "paths_crossing_splits": len(crossed(paths)),
        "recorded_image_sha256_crossing_splits": len(crossed(recorded_hashes)),
        "recorded_image_sha256_rows": sum(bool(row.get("image_sha256") or row.get("sha256")) for row in rows),
        "identical_dhash_candidates_crossing_splits": len(crossed(exact_dhash)),
        "dhash_notice": "Appearance candidates only; identical dHash is not proof of identical pixels or patients.",
        "patient_independence": "GROUPING_ONLY_PATIENT_IDENTITY_NOT_ESTABLISHED" if not any(field in fields for field in ("patient_id", "patient", "subject_id")) else "PATIENT_KEYS_CHECKED_NOT_IDENTITY_ADJUDICATED",
    }


def read_rows(path: Path, max_rows: int) -> tuple[list[dict], dict, bool]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = payload.get("cases", payload.get("samples", []))
        if not isinstance(rows, list):
            raise ValueError("Manifest cases/samples must be a list")
        return rows[:max_rows], payload, len(rows) > max_rows
    payload = {}
    publisher_sums = {}
    if path.name == "ptbxl_database.csv":
        sums_path = path.parent / "SHA256SUMS.txt"
        if sums_path.is_file():
            for line in sums_path.read_text(encoding="ascii").splitlines():
                sha, _, name = line.partition(" ")
                publisher_sums[name.strip().lstrip("*")] = sha
        payload = {"dataset_id": "ptb-xl-1.0.1-full-metadata", "dataset_root": str(path.parent),
                   "scope": "All publisher metadata rows, not only the previously evaluated diagnostic-superclass subset",
                   "publisher_checksum_manifest_sha256": digest(sums_path) if sums_path.is_file() else None}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        rows = []
        for row in reader:
            if len(rows) == max_rows:
                return rows, payload, True
            if path.name == "ptbxl_database.csv":
                fold = int(row["strat_fold"])
                member = row["filename_lr"] + ".dat"
                row = {"patient_id": row["patient_id"], "entry": member, "path": member,
                       "split": "train" if fold <= 8 else "val" if fold == 9 else "test",
                       "sha256": publisher_sums.get(member)}
            rows.append(row)
    return rows, payload, False


def resolve_image(row: dict, payload: dict, root: Path) -> Path | None:
    _, value = first(row, PATH_FIELDS)
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    data_root = payload.get("dataset_root")
    return (Path(data_root) if data_root else root) / path


def check_bytes(rows: list[dict], payload: dict, *, root: Path, sample_per_split: int, byte_budget: int, max_file_bytes: int) -> dict:
    """Deterministic stratified sampling; never imply a sampled audit is complete."""
    selected: list[dict] = []
    for split in sorted({split_name(row.get("split")) for row in rows}):
        candidates = [row for row in rows if split_name(row.get("split")) == split]
        candidates.sort(key=lambda row: token(first(row, PATH_FIELDS)[1]))
        selected.extend(candidates[:sample_per_split])
    checked, missing, deferred, changed, archive_deferred = [], 0, 0, 0, 0
    used = 0
    for row in selected:
        path = resolve_image(row, payload, root)
        if path is None or not path.is_file():
            if payload.get("source_archive") and Path(payload["source_archive"]).is_file():
                # A stored ZIP member is not a missing loose file. Do not unpack
                # or imply individual members were newly verified in this audit.
                archive_deferred += 1
                continue
            missing += 1
            continue
        size = path.stat().st_size
        if size > max_file_bytes or used + size > byte_budget:
            deferred += 1
            continue
        actual = digest(path)
        expected = row.get("image_sha256") or row.get("sha256")
        matches = actual == expected if expected else None
        changed += matches is False
        used += size
        checked.append({"split": split_name(row.get("split")), "path_token": token(str(path)), "sha256": actual,
                        "bytes": size, "matches_recorded_sha256": matches})
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for item in checked:
        by_hash[item["sha256"]].append(item)
    return {
        "scope": "NEW_DETERMINISTIC_STRATIFIED_BYTE_SAMPLE_NOT_FULL_DATASET_VERIFICATION",
        "selected": len(selected), "checked": len(checked), "missing_selected": missing,
        "archive_members_not_opened": archive_deferred,
        "deferred_by_budget": deferred, "bytes_read": used, "hash_mismatches": changed,
        "sampled_sha256_cross_split_duplicates": sum(len({item["split"] for item in group}) > 1 for group in by_hash.values()),
        "records": checked,
    }


def dhash_candidates(rows: list[dict], *, limit: int, threshold: int = 4) -> dict:
    """Bounded fresh Hamming check of recorded dHashes; no invented confirmation."""
    candidates = sorted((row for row in rows if row.get("dhash")), key=lambda row: token(first(row, PATH_FIELDS)[1]))[:limit]
    pairs, compared = 0, 0
    for index, a in enumerate(candidates):
        for b in candidates[index + 1:]:
            if split_name(a.get("split")) == split_name(b.get("split")):
                continue
            try:
                distance = (int(str(a["dhash"]), 16) ^ int(str(b["dhash"]), 16)).bit_count()
            except ValueError:
                continue
            compared += 1
            pairs += distance <= threshold
    return {"sampled_rows": len(candidates), "cross_split_pairs_compared": compared, "hamming_threshold": threshold,
            "candidate_pairs": pairs, "pixel_confirmed": False,
            "scope": "BOUNDED_RECORDED_DHASH_CANDIDATES_ONLY_NOT_A_NEW_FULL_PIXEL_AUDIT"}


def audit(root: Path, *, sample_per_split: int = 3, byte_budget: int = 512 * 1024**2, max_file_bytes: int = 256 * 1024**2,
          max_rows: int = 1_000_000, near_limit: int = 256) -> dict:
    registry_path = root / "dataset_registry/tasks.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    entries = registry.get("datasets", [])
    # Shallow, documented preparation directory only; never scan patient folders.
    prepared = root / "_derived/datasets"
    manifest_paths = sorted({*prepared.glob("*/samples.csv"), *prepared.glob("*/manifest.json")})
    ecg_metadata = root / "ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.1/ptbxl_database.csv"
    if ecg_metadata.is_file():
        manifest_paths.insert(0, ecg_metadata)
    reports = []
    remaining = byte_budget
    for path in manifest_paths:
        try:
            rows, payload, truncated = read_rows(path, max_rows)
            if path.parent.name == "rsna-ich":
                payload.update(source_archive=str(root / "RSNA_PNG/rsna-ich-png.zip"),
                               source_representation="Archive entries declared by ml_training/rsna_ich.py; members not unpacked or rehashed here")
            result = {"manifest": path.relative_to(root).as_posix(), "manifest_sha256": digest(path),
                      "dataset_id": payload.get("dataset_id"), "dataset_version": payload.get("dataset_version"),
                      "source_scope": payload.get("scope"), "source_representation": payload.get("source_representation"),
                      "source_archive_present": Path(payload["source_archive"]).is_file() if payload.get("source_archive") else None,
                      "recorded_volume_shapes": dict(Counter("x".join(map(str, row["shape"])) for row in rows if isinstance(row.get("shape"), list))),
                      "manifest_truncated": truncated, "grouping": grouping_summary(rows)}
            result["bytes"] = check_bytes(rows, payload, root=root, sample_per_split=sample_per_split,
                                          byte_budget=remaining, max_file_bytes=max_file_bytes)
            remaining -= result["bytes"]["bytes_read"]
            result["near_duplicates"] = dhash_candidates(rows, limit=near_limit)
            reports.append(result)
        except (OSError, ValueError, TypeError) as exc:
            reports.append({"manifest": path.relative_to(root).as_posix(), "error": f"{type(exc).__name__}: {exc}"})
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for result in reports:
        for item in result.get("bytes", {}).get("records", []):
            by_hash[item["sha256"]].append({"manifest": result["manifest"], "split": item["split"]})
    cross_manifest = [{"sha256": sha, "occurrences": items} for sha, items in by_hash.items()
                      if len({item["manifest"] for item in items}) > 1]
    return {
        "schema_version": "medtwin-bounded-dataset-audit-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_sha256": digest(registry_path), "registry_datasets": len(entries),
        "registry_inventory": [{"dataset_id": item.get("id"), "modality": item.get("modality"), "patient_ids": item.get("patient_ids"),
                                "license": item.get("license"), "tasks": [{"task_id": task.get("task_id"),
                                "training_eligible_recorded": task.get("training_eligible"), "flags_recorded": task.get("flags"),
                                "historical_preparation": task.get("preparation")} for task in item.get("tasks", [])]}
                               for item in entries],
        "limits": {"sample_per_split": sample_per_split, "global_byte_budget": byte_budget, "max_file_bytes": max_file_bytes,
                   "max_rows_per_manifest": max_rows, "near_duplicate_rows_per_manifest": near_limit},
        "manifests": reports, "cross_manifest_sampled_sha256_overlap": cross_manifest,
        "summary": {"manifests": len(reports), "rows_inspected": sum(r.get("grouping", {}).get("rows", 0) for r in reports),
                    "new_files_hashed": sum(r.get("bytes", {}).get("checked", 0) for r in reports),
                    "new_bytes_hashed": byte_budget - remaining,
                    "hash_mismatches": sum(r.get("bytes", {}).get("hash_mismatches", 0) for r in reports),
                    "manifests_with_crossing_groups": sum(r.get("grouping", {}).get("groups_crossing_splits", 0) > 0 for r in reports),
                    "errors": sum("error" in r for r in reports)},
        "notice": "Read-only technical inspection. Registry rights and historical readiness are not re-approved. Group/content overlap is not patient-identity adjudication. Sampled byte checks do not certify whole datasets. No predictions, labels or thresholds were tuned.",
        "not_covered": ["No recursive image, patient-folder or archive extraction audit", "No new independent human annotation",
                        "MIT-BIH tabular files do not establish patient grouping or permission scope and were not treated as a new eligible signal dataset",
                        "Unregistered GRAZPEDWRI-DX/pneumonia/other requested datasets were not inferred present from names alone",
                        "Paired masks/geometry retain prior manifest evidence; this fresh byte sample rehashes input files only"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/review-2026-11-13/data-audit.json")
    parser.add_argument("--sample-per-split", type=int, default=3)
    parser.add_argument("--byte-budget-mib", type=int, default=512)
    parser.add_argument("--max-file-mib", type=int, default=256)
    parser.add_argument("--max-rows", type=int, default=1_000_000)
    parser.add_argument("--near-limit", type=int, default=256)
    args = parser.parse_args()
    if min(args.sample_per_split, args.byte_budget_mib, args.max_file_mib, args.max_rows, args.near_limit) < 0 or args.max_rows == 0:
        parser.error("Audit limits must be nonnegative and max rows positive")
    result = audit(args.root.resolve(), sample_per_split=args.sample_per_split, byte_budget=args.byte_budget_mib * 1024**2,
                   max_file_bytes=args.max_file_mib * 1024**2, max_rows=args.max_rows, near_limit=args.near_limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **result["summary"]}, indent=2))
    return int(result["summary"]["errors"] > 0 or result["summary"]["hash_mismatches"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
