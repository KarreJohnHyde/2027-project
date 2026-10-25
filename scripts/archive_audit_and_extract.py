"""Audit, deduplicate and safely extract the MedTwin source archives.

Read-only audit first: SHA-256, entry table, expansion size, compression ratios,
encryption, multipart and unsafe paths. An archive whose every file already
exists in the project (same name, size and CRC-32) is registered at that location
instead of being extracted again. The rest are extracted, one directory per
archive, through a staging directory and an atomic rename, with a completion
marker. Nothing extracted is executed. Original archives are never modified.

Statuses: EXTRACTED_VERIFIED, ALREADY_PRESENT_VERIFIED, EXTRACTION_FAILED,
SOURCE_MISSING, CORRUPT, UNSAFE, DISK_BLOCKED, UNSUPPORTED_MULTIPART
(AUDITED_ONLY for additional discoveries, which are never extracted).

The supplementary batch (archives 23-60, downloaded and extracted into the workspace
root by the user on 2026-10-25) is audited and gets per-entry manifests like the named
archives, but is never extracted: PARTIALLY_PRESENT or NOT_PRESENT report entries
whose on-disk copy is missing or differs.

Versioned outputs hold counts, histograms and top-level folder names only; full
entry lists stay under the git-ignored import directory.

Usage:
    python scripts/archive_audit_and_extract.py --extract
    python scripts/archive_audit_and_extract.py --only "archive (4).zip" --extract
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import zipfile
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
NAMED_ARCHIVES = ["anatomy-of-the-airways.zip", "archive.zip"] + [f"archive ({index}).zip" for index in range(1, 23)]
SUPPLEMENTARY_ARCHIVES = [f"archive ({index}).zip" for index in range(23, 61)]
MANIFESTED_ROLES = {"NAMED", "SUPPLEMENTARY"}
DEFAULT_SOURCE = Path(r"C:\Users\johnn\Downloads")
DEFAULT_DEST = ROOT / "_imports" / "archives"
MARKER = "_MEDTWIN_IMPORT.json"
INDEX_EXCLUDE = {".git", "node_modules", "dist", "logs", "_imports", "_derived", "__pycache__", ".pytest_cache", ".vite", ".figma"}
MAX_TOTAL_EXPANSION = 60 * 1024**3
MAX_OVERALL_RATIO = 100.0
MAX_ENTRY_RATIO = 1000.0
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
RESERVED_WINDOWS = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)
SUPPORTED_METHODS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA}

CATEGORY_BY_EXTENSION = {
    "tabular": {".csv", ".tsv", ".xlsx", ".xls", ".parquet"},
    "structured_annotation": {".json", ".xml", ".yaml", ".yml"},
    "raster_image": {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"},
    "dicom": {".dcm", ".dicom"},
    "volume": {".nii", ".nrrd", ".mha", ".mhd", ".raw", ".hdr", ".img"},
    "document": {".pdf", ".docx", ".doc", ".rtf", ".md"},
    "text": {".txt"},
    "waveform": {".edf", ".bdf", ".hea", ".dat", ".atr", ".wfdb"},
    "checkpoint": {".pt", ".pth", ".ckpt", ".onnx", ".h5", ".hdf5", ".pb", ".safetensors", ".pkl", ".pickle", ".keras", ".tflite"},
    "anatomy_3d": {".glb", ".gltf", ".blend", ".fbx", ".obj", ".stl", ".ply", ".mtl", ".usdz", ".3ds", ".dae"},
    "code": {".py", ".ipynb", ".js", ".ts", ".tsx", ".jsx", ".java", ".r", ".m", ".sh", ".cpp", ".c", ".h", ".go", ".rs", ".php", ".rb", ".cs", ".html", ".css"},
}
MASK_HINT = re.compile(r"(^|[/_\-. ])(mask|masks|seg|segmentation|label|labels|annotation|annotations|gt|ground[_ ]?truth)([/_\-. ]|$)", re.IGNORECASE)
LICENSE_FILES = re.compile(r"(^|/)(license|licence|copying|readme|dataset-metadata|citation|terms)[^/]*$", re.IGNORECASE)
LICENSE_TERMS = [
    ("CC-BY-4.0", re.compile(r"CC[\s-]?BY[\s-]?4\.0|Creative Commons Attribution 4\.0", re.IGNORECASE)),
    ("CC-BY-NC", re.compile(r"CC[\s-]?BY[\s-]?NC|Non[\s-]?Commercial", re.IGNORECASE)),
    ("CC-BY-SA", re.compile(r"CC[\s-]?BY[\s-]?SA|ShareAlike", re.IGNORECASE)),
    ("CC0", re.compile(r"\bCC0\b|Public Domain Dedication", re.IGNORECASE)),
    ("MIT", re.compile(r"\bMIT License\b", re.IGNORECASE)),
    ("Apache-2.0", re.compile(r"Apache License,? Version 2\.0", re.IGNORECASE)),
    ("ODbL", re.compile(r"Open Database License|\bODbL\b", re.IGNORECASE)),
    ("RESEARCH_ONLY_TERMS", re.compile(r"research (and educational )?purposes only|for research purposes|educational purposes", re.IGNORECASE)),
    ("CITATION_REQUIRED", re.compile(r"please cite|must cite|cite the following|citation", re.IGNORECASE)),
]


@dataclass
class ArchiveResult:
    listed_name: str
    listed_path: str
    role: str  # NAMED or ADDITIONAL
    status: str = ""
    sha256: str = ""
    size_bytes: int = 0
    entries: int = 0
    files: int = 0
    directories: int = 0
    uncompressed_bytes: int = 0
    overall_ratio: float = 0.0
    max_entry_ratio: float = 0.0
    project_copy: str = ""
    project_copy_identical: bool | None = None
    duplicate_of_listed: str = ""
    already_present_roots: list[str] = field(default_factory=list)
    extracted_to: str = ""
    skipped_entries: int = 0
    unsafe_reasons: list[str] = field(default_factory=list)
    categories: dict[str, int] = field(default_factory=dict)
    extensions: dict[str, int] = field(default_factory=dict)
    top_level: dict[str, int] = field(default_factory=dict)
    second_level: dict[str, int] = field(default_factory=dict)
    entry_manifest: str = ""
    mask_like_files: int = 0
    coco_like_json: int = 0
    yolo_like_label_files: int = 0
    license_evidence: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


class Log:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a", encoding="utf-8")

    def __call__(self, message: str) -> None:
        line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {message}"
        print(line, flush=True)
        self.handle.write(line + "\n")
        self.handle.flush()


def long_path(path: Path) -> str:
    text = str(path.resolve())
    return text if os.name != "nt" or text.startswith("\\\\?\\") else "\\\\?\\" + text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(long_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crc32_file(path: Path) -> int:
    value = 0
    with open(long_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            value = zlib.crc32(chunk, value)
    return value & 0xFFFFFFFF


def count_files(path: Path) -> int:
    """Files under path, excluding the completion marker; long-path safe."""
    total = 0
    for _directory, _subdirs, files in os.walk(long_path(path)):
        total += len(files)
    return total - (1 if (path / MARKER).exists() else 0)


def slug_for(name: str) -> str:
    match = re.fullmatch(r"archive(?: \((\d+)\))?\.zip", name, re.IGNORECASE)
    if match:
        return f"archive_{int(match.group(1)):02d}" if match.group(1) else "archive_00"
    return re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-")


def classify(name: str) -> str:
    lower = name.lower()
    suffix = ".nii.gz" if lower.endswith(".nii.gz") else PurePosixPath(lower).suffix
    if suffix == ".nii.gz":
        return "volume"
    for category, suffixes in CATEGORY_BY_EXTENSION.items():
        if suffix in suffixes:
            return category
    return "no_extension" if not suffix else "other"


def check_entry_name(name: str) -> tuple[str | None, str | None]:
    """Returns (fatal_reason, skip_reason). Fatal reasons refuse the whole archive."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or normalized.startswith("//"):
        return "ABSOLUTE_OR_DRIVE_PATH", None
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return "PATH_TRAVERSAL", None
    for part in parts:
        if INVALID_WINDOWS_CHARS.search(part) or RESERVED_WINDOWS.match(part) or part.endswith((" ", ".")):
            return None, "INVALID_WINDOWS_NAME"
    return None, None


def audit_archive(path: Path, result: ArchiveResult) -> tuple[zipfile.ZipFile | None, list[zipfile.ZipInfo]]:
    try:
        bundle = zipfile.ZipFile(long_path(path))
    except zipfile.BadZipFile as exc:
        text = str(exc).lower()
        if "multiple disks" in text or "span" in text:
            result.status = "UNSUPPORTED_MULTIPART"
        else:
            result.status = "CORRUPT"
        result.notes.append(f"Archive could not be opened: {exc}")
        return None, []
    infos = bundle.infolist()
    result.entries = len(infos)
    files = [info for info in infos if not info.is_dir()]
    result.files = len(files)
    result.directories = result.entries - result.files
    result.uncompressed_bytes = sum(info.file_size for info in files)
    compressed = sum(info.compress_size for info in files) or 1
    result.overall_ratio = round(result.uncompressed_bytes / compressed, 2)
    result.max_entry_ratio = round(max((info.file_size / info.compress_size for info in files if info.compress_size), default=0.0), 1)
    extensions, categories, top, second = Counter(), Counter(), Counter(), Counter()
    seen_lower: set[str] = set()
    for info in infos:
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            result.unsafe_reasons.append("SYMLINK_ENTRY")
        if info.flag_bits & 0x1:
            result.unsafe_reasons.append("ENCRYPTED_ENTRY")
        if info.compress_type not in SUPPORTED_METHODS:
            result.unsafe_reasons.append(f"UNSUPPORTED_COMPRESSION_METHOD_{info.compress_type}")
        fatal, _skip = check_entry_name(info.filename)
        if fatal:
            result.unsafe_reasons.append(fatal)
        name = info.filename.replace("\\", "/")
        first = name.strip("/").split("/", 1)[0]
        top[first + ("/" if "/" in name.strip("/") or info.is_dir() else "")] += 0 if info.is_dir() else 1
        if info.is_dir():
            continue
        parts = name.strip("/").split("/")
        if len(parts) >= 3:
            second["/".join(parts[:2]) + "/"] += 1
        if name.lower() in seen_lower:
            result.notes.append("Case-insensitive duplicate entry names present.")
        seen_lower.add(name.lower())
        lower = name.lower()
        suffix = ".nii.gz" if lower.endswith(".nii.gz") else PurePosixPath(lower).suffix or "<none>"
        extensions[suffix] += 1
        category = classify(name)
        categories[category] += 1
        if category in {"raster_image", "volume", "dicom"} and MASK_HINT.search(name):
            result.mask_like_files += 1
        if suffix == ".txt" and re.search(r"(^|/)labels?/", lower):
            result.yolo_like_label_files += 1
        if info.compress_size and info.file_size > 100 * 1024**2 and info.file_size / info.compress_size > MAX_ENTRY_RATIO:
            result.unsafe_reasons.append("ENTRY_COMPRESSION_RATIO_EXCESSIVE")
    if result.uncompressed_bytes > MAX_TOTAL_EXPANSION or (result.uncompressed_bytes > 1024**3 and result.overall_ratio > MAX_OVERALL_RATIO):
        result.unsafe_reasons.append("DECOMPRESSION_BOMB_SUSPECTED")
    result.unsafe_reasons = sorted(set(result.unsafe_reasons))
    result.extensions = dict(extensions.most_common(20))
    result.categories = dict(categories.most_common())
    result.top_level = dict(top.most_common(25))
    result.second_level = dict(second.most_common(60))
    for info in files:
        lower = info.filename.lower()
        if lower.endswith(".json") and info.file_size < 64 * 1024**2 and result.coco_like_json < 50:
            try:
                head = bundle.open(info).read(65536).decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001 - classification only
                continue
            if '"annotations"' in head and '"images"' in head:
                result.coco_like_json += 1
        if LICENSE_FILES.search(info.filename) and info.file_size < 512 * 1024:
            try:
                text = bundle.open(info).read().decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            for term, pattern in LICENSE_TERMS:
                if pattern.search(text):
                    result.license_evidence.append(f"{term} in {PurePosixPath(info.filename).name}")
    result.license_evidence = sorted(set(result.license_evidence))
    return bundle, files


def build_index(root: Path, log: Log) -> dict[int, list[Path]]:
    index: dict[int, list[Path]] = defaultdict(list)
    count = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(long_path(directory)))
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if entry.is_dir(follow_symlinks=False):
                if name in INDEX_EXCLUDE or name.startswith(".venv"):
                    continue
                stack.append(Path(directory) / name)
            elif entry.is_file(follow_symlinks=False):
                if directory == root and name.lower().endswith(".zip"):
                    continue
                try:
                    index[entry.stat().st_size].append(Path(directory) / name)
                except OSError:
                    continue
                count += 1
    log(f"index: {count} existing project files by size")
    return index


def find_existing(files: list[zipfile.ZipInfo], index: dict[int, list[Path]], crc_cache: dict[str, int], locations: dict[str, str] | None = None,
                  exhaustive: bool = False) -> tuple[int, Counter]:
    """Number of archive files present in the project with identical content, and the roots holding them.
    When `locations` is given it receives entry name -> matched on-disk path. By default the first
    missing entry ends the search (the question is whether the whole archive is present);
    `exhaustive` counts every matching entry, for archives expected to be partly present."""
    candidates_for = []
    for info in files:
        relative = info.filename.replace("\\", "/").strip("/")
        base = relative.rsplit("/", 1)[-1].lower()
        candidates = [path for path in index.get(info.file_size, []) if path.name.lower() == base]
        if not candidates:
            if exhaustive:
                continue
            return 0, Counter()
        candidates_for.append((info, relative, candidates))
    matched, roots = 0, Counter()
    for info, relative, candidates in candidates_for:
        suffix = relative.lower()
        candidates.sort(key=lambda path: not str(path).replace("\\", "/").lower().endswith(suffix))
        for path in candidates:
            key = str(path)
            if key not in crc_cache:
                try:
                    crc_cache[key] = crc32_file(path)
                except OSError:
                    crc_cache[key] = -1
            if crc_cache[key] == info.CRC:
                normalized = str(path).replace("\\", "/")
                root = normalized[: -len(relative)].rstrip("/") if normalized.lower().endswith(suffix) else f"<other layout> {path.parent}"
                roots[root] += 1
                matched += 1
                if locations is not None:
                    locations[info.filename] = str(path)
                break
        else:
            if not exhaustive:
                return matched, roots
    return matched, roots


def extract(bundle: zipfile.ZipFile, files: list[zipfile.ZipInfo], result: ArchiveResult, dest_root: Path, log: Log) -> None:
    slug = slug_for(result.listed_name)
    final = dest_root / slug
    if final.exists():
        marker = final / MARKER
        if marker.exists() and json.loads(marker.read_text(encoding="utf-8")).get("archive_sha256") == result.sha256:
            present = count_files(final)
            expected = json.loads(marker.read_text(encoding="utf-8"))["files_written"]
            result.extracted_to = str(final)
            result.status = "EXTRACTED_VERIFIED" if present == expected else "EXTRACTION_FAILED"
            result.notes.append(f"Existing extraction re-verified: {present} of {expected} files present.")
            return
        final = dest_root / f"{slug}-{result.sha256[:8]}"
        result.notes.append("Destination existed with different content; extracted beside it instead of overwriting.")
    staging = dest_root / ".staging" / f"{slug}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(long_path(staging))
    os.makedirs(long_path(staging), exist_ok=True)
    staging_real = os.path.realpath(long_path(staging))
    written, skipped, seen = 0, Counter(), set()
    started = time.monotonic()
    for number, info in enumerate(files, start=1):
        fatal, skip = check_entry_name(info.filename)
        relative = info.filename.replace("\\", "/").strip("/")
        if fatal or skip:
            skipped[skip or fatal] += 1
            continue
        if relative.lower() in seen:
            skipped["CASE_INSENSITIVE_COLLISION"] += 1
            continue
        seen.add(relative.lower())
        target = staging.joinpath(*relative.split("/"))
        target_real = os.path.realpath(long_path(target))
        if os.path.commonpath([staging_real, target_real]) != staging_real:
            raise RuntimeError("Entry resolved outside the staging directory")
        os.makedirs(os.path.dirname(target_real), exist_ok=True)
        with bundle.open(info) as source, open(target_real, "wb") as sink:
            shutil.copyfileobj(source, sink, 4 * 1024 * 1024)
        if os.path.getsize(target_real) != info.file_size:
            raise RuntimeError("Extracted size differs from the archive entry")
        try:
            stamp = time.mktime(info.date_time + (0, 0, -1))
            os.utime(target_real, (stamp, stamp))
        except (OverflowError, ValueError, OSError):
            pass  # an invalid archive timestamp leaves the extraction time
        written += 1
        if number % 5000 == 0:
            log(f"  {result.listed_name}: {number}/{len(files)} entries ({time.monotonic() - started:.0f}s)")
    marker = {
        "archive": result.listed_name, "archive_sha256": result.sha256, "files_written": written,
        "skipped": dict(skipped), "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "scripts/archive_audit_and_extract.py",
    }
    with open(os.path.join(staging_real, MARKER), "w", encoding="utf-8") as handle:
        json.dump(marker, handle, indent=2)
    os.makedirs(long_path(final.parent), exist_ok=True)
    os.replace(staging_real, long_path(final))
    result.extracted_to = str(final)
    result.skipped_entries = sum(skipped.values())
    if skipped:
        result.notes.append(f"Skipped entries: {dict(skipped)}")
    present = count_files(final)
    result.status = "EXTRACTED_VERIFIED" if present == written else "EXTRACTION_FAILED"


def write_entry_manifest(result: ArchiveResult, files: list[zipfile.ZipInfo], locations: dict[str, str], args) -> None:
    """Per-entry manifest (git-ignored): which on-disk file holds each archive entry.
    This keeps archives separable where several were unpacked into the same folder."""
    if result.role not in MANIFESTED_ROLES:
        return
    target = args.dest / "_manifests" / f"{slug_for(result.listed_name)}.entries.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entry", "size", "crc32", "location"])
        for info in files:
            writer.writerow([info.filename, info.file_size, f"{info.CRC:08x}", locations.get(info.filename, "")])
    result.entry_manifest = str(target)


def process(path: Path, role: str, args, index, crc_cache, project_copies: dict[str, Path], listed_hashes: dict[str, str], log: Log) -> ArchiveResult:
    result = ArchiveResult(listed_name=path.name, listed_path=str(path), role=role)
    started = time.monotonic()
    if not path.exists():
        result.status = "SOURCE_MISSING"
        return result
    result.size_bytes = path.stat().st_size
    log(f"{role} {path.name}: hashing {result.size_bytes / 1024**2:.1f} MB")
    result.sha256 = sha256_file(path)
    copy = project_copies.get(path.name.lower())
    if copy and copy.resolve() != path.resolve():
        result.project_copy = str(copy)
        result.project_copy_identical = copy.stat().st_size == result.size_bytes and sha256_file(copy) == result.sha256
    duplicate = next((name for name, digest in listed_hashes.items() if digest == result.sha256 and name != path.name), "")
    listed_hashes[path.name] = result.sha256
    bundle, files = audit_archive(path, result)
    if bundle is None:
        result.duration_seconds = round(time.monotonic() - started, 1)
        return result
    try:
        if result.unsafe_reasons:
            if role == "SUPPLEMENTARY":
                # Never extracted by this tool, so extraction-risk findings stay on record
                # but do not prevent auditing what the user's own extraction put on disk.
                result.notes.append(f"Unsafe for automatic extraction ({', '.join(result.unsafe_reasons)}); audited for presence only.")
            else:
                fatal = [reason for reason in result.unsafe_reasons if reason not in {"ENCRYPTED_ENTRY"} and not reason.startswith("UNSUPPORTED_COMPRESSION")]
                result.status = "UNSAFE" if fatal else "EXTRACTION_FAILED"
                return result
        locations: dict[str, str] = {}
        matched, roots = find_existing(files, index, crc_cache, locations, exhaustive=role == "SUPPLEMENTARY")
        if duplicate:
            result.duplicate_of_listed = duplicate
            result.status = "ALREADY_PRESENT_VERIFIED"
            result.notes.append(f"Byte-identical to {duplicate} (same SHA-256); not extracted twice.")
            write_entry_manifest(result, files, locations, args)
            return result
        if files and matched == len(files):
            result.status = "ALREADY_PRESENT_VERIFIED"
            result.already_present_roots = [f"{root} ({count} files)" for root, count in roots.most_common(5)]
            write_entry_manifest(result, files, locations, args)
            return result
        if role == "SUPPLEMENTARY":
            # Extracted by the user, not by this tool: record what is on disk, never extract.
            result.status = "PARTIALLY_PRESENT" if matched else "NOT_PRESENT"
            result.already_present_roots = [f"{root} ({count} files)" for root, count in roots.most_common(5)]
            missing = [info.filename for info in files if info.filename not in locations]
            listed = f" ({', '.join(missing)})" if len(missing) <= 10 else ""
            result.notes.append(f"{matched} of {len(files)} files present with identical name, size and CRC-32; "
                                f"{len(files) - matched} missing or different on disk{listed}.")
            write_entry_manifest(result, files, locations, args)
            return result
        if role == "NAMED" and not args.extract:
            # Audit mode must still recognise this tool's own earlier extraction (git-ignored
            # _imports is not part of the project index): marker, archive hash and file count.
            final = args.dest / slug_for(result.listed_name)
            marker = final / MARKER
            if marker.exists() and json.loads(marker.read_text(encoding="utf-8")).get("archive_sha256") == result.sha256:
                expected = json.loads(marker.read_text(encoding="utf-8"))["files_written"]
                present = count_files(final)
                result.extracted_to = str(final)
                result.status = "EXTRACTED_VERIFIED" if present == expected else "EXTRACTION_FAILED"
                result.notes.append(f"Existing extraction re-verified in audit mode: {present} of {expected} files present.")
                write_entry_manifest(result, files, {info.filename: str(final.joinpath(*info.filename.replace("\\", "/").strip("/").split("/"))) for info in files}, args)
                return result
        if matched:
            result.notes.append(f"{matched} of {len(files)} files already present with identical content; extracting the complete archive.")
        if role != "NAMED" or not args.extract:
            result.status = "AUDITED_ONLY" if role != "NAMED" else "NOT_EXTRACTED_AUDIT_MODE"
            return result
        free = shutil.disk_usage(args.dest.anchor).free
        if free - result.uncompressed_bytes < args.min_free_gb * 1024**3:
            result.status = "DISK_BLOCKED"
            result.notes.append(f"Needs {result.uncompressed_bytes / 1024**3:.2f} GB; {free / 1024**3:.2f} GB free; margin {args.min_free_gb} GB.")
            return result
        try:
            extract(bundle, files, result, args.dest, log)
            if result.status == "EXTRACTED_VERIFIED":
                base = Path(result.extracted_to)
                write_entry_manifest(result, files, {info.filename: str(base.joinpath(*info.filename.replace("\\", "/").strip("/").split("/"))) for info in files}, args)
        except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
            result.status = "CORRUPT"
            result.notes.append(f"Extraction stopped: {exc}")
        except (OSError, RuntimeError) as exc:
            result.status = "EXTRACTION_FAILED"
            result.notes.append(f"Extraction stopped: {exc}")
        return result
    finally:
        bundle.close()
        result.duration_seconds = round(time.monotonic() - started, 1)
        log(f"{role} {path.name}: {result.status} ({result.duration_seconds}s)")


def write_outputs(results: list[ArchiveResult], args, started_at: str) -> None:
    docs = ROOT / "docs" / "import"
    (docs / "inventories").mkdir(parents=True, exist_ok=True)
    columns = ["role", "listed_name", "listed_path", "status", "sha256", "size_bytes", "entries", "files", "uncompressed_bytes", "overall_ratio",
               "project_copy", "project_copy_identical", "duplicate_of_listed", "already_present_roots", "extracted_to", "skipped_entries",
               "unsafe_reasons", "categories", "license_evidence", "notes"]
    with (docs / "ARCHIVE_MANIFEST.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in results:
            row = {column: getattr(item, column) for column in columns}
            for key in ("already_present_roots", "unsafe_reasons", "license_evidence", "notes"):
                row[key] = "; ".join(row[key])
            row["categories"] = json.dumps(item.categories, sort_keys=True)
            writer.writerow(row)
    for item in results:
        if item.role in MANIFESTED_ROLES and item.sha256:
            payload = {key: value for key, value in item.__dict__.items()}
            (docs / "inventories" / f"{slug_for(item.listed_name)}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    registry = ROOT / "dataset_registry" / "imported.json"
    records = []
    for item in results:
        if item.role not in MANIFESTED_ROLES:
            continue
        location = item.extracted_to or (item.already_present_roots[0].rsplit(" (", 1)[0] if item.already_present_roots else "")
        records.append({
            "archive_id": slug_for(item.listed_name), "source_archive": item.listed_name, "source_sha256": item.sha256,
            "batch": "NAMED_24" if item.role == "NAMED" else "SUPPLEMENTARY_2026_10_25_USER_EXTRACTED",
            "status": item.status, "location": location, "duplicate_of": item.duplicate_of_listed or None,
            "files": item.files, "uncompressed_bytes": item.uncompressed_bytes, "content_categories": item.categories,
            "mask_like_files": item.mask_like_files, "coco_like_json": item.coco_like_json, "yolo_like_label_files": item.yolo_like_label_files,
            "license_evidence": item.license_evidence or ["NO_LICENSE_FILE_IN_ARCHIVE"],
            "training_eligibility": "NOT_DETERMINED_SEE_TASK_REGISTRY",
        })
    registry.write_text(json.dumps({"generated_at": started_at, "tool": "scripts/archive_audit_and_extract.py", "archives": records}, indent=2) + "\n", encoding="utf-8")
    named = [item for item in results if item.role == "NAMED"]
    supplementary = [item for item in results if item.role == "SUPPLEMENTARY"]
    extra = [item for item in results if item.role == "ADDITIONAL"]
    counts = Counter(item.status for item in named)
    lines = [
        "# Archive import report", "",
        f"Generated {started_at} by `scripts/archive_audit_and_extract.py` (source `{args.source}`, destination `{args.dest}`).",
        "Counts and folder names only; full entry lists stay in the git-ignored import directory.", "",
        f"**Named archives accounted for: {len(named)} of {len(NAMED_ARCHIVES)}.** " + ", ".join(f"{status} {count}" for status, count in sorted(counts.items())),
        f"Additional archives discovered (audited, not extracted): {len(extra)}.", "",
        "| Archive | Status | Files | Expanded | Location | Content | Licence evidence |",
        "| --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for item in named:
        location = item.extracted_to or "; ".join(item.already_present_roots) or (f"same as {item.duplicate_of_listed}" if item.duplicate_of_listed else "—")
        content = ", ".join(f"{key} {value}" for key, value in list(item.categories.items())[:4])
        lines.append(f"| `{item.listed_name}` | {item.status} | {item.files} | {item.uncompressed_bytes / 1024**3:.2f} GB | {location.replace(str(ROOT), '.')} | {content} | {', '.join(item.license_evidence) or 'none in archive'} |")
    lines += ["", "## Notes", ""]
    for item in named:
        for note in item.notes + [f"Unsafe: {reason}" for reason in item.unsafe_reasons]:
            lines.append(f"- `{item.listed_name}`: {note}")
    if supplementary:
        batch_counts = Counter(item.status for item in supplementary)
        lines += ["", "## Supplementary batch (2026-10-25)", "",
                  "Archives the user downloaded and extracted into the workspace root on 2026-10-25. They are audited and "
                  "manifested here but never extracted by this tool; a dataset enters training only through "
                  "`scripts/dataset_task_audit.py`. " + ", ".join(f"{status} {count}" for status, count in sorted(batch_counts.items())) + ".", "",
                  "| Archive | Status | Files | Expanded | On-disk location (matching files) | Content | Licence evidence |",
                  "| --- | --- | ---: | ---: | --- | --- | --- |"]
        for item in supplementary:
            location = "; ".join(item.already_present_roots) or (f"same as {item.duplicate_of_listed}" if item.duplicate_of_listed else "—")
            content = ", ".join(f"{key} {value}" for key, value in list(item.categories.items())[:4])
            lines.append(f"| `{item.listed_name}` | {item.status} | {item.files} | {item.uncompressed_bytes / 1024**3:.2f} GB | {location.replace(str(ROOT), '.')} | "
                         f"{content} | {', '.join(item.license_evidence) or 'none in archive'} |")
        lines.append("")
        for item in supplementary:
            # A supplementary archive's notes already name its unsafe reasons.
            for note in item.notes:
                lines.append(f"- `{item.listed_name}`: {note}")
    lines += ["", "## Additional discoveries", "", "| Archive | Status | Files | Same content as / reason |", "| --- | --- | ---: | --- |"]
    for item in extra:
        same = "; ".join(item.already_present_roots) or item.duplicate_of_listed or "; ".join(item.unsafe_reasons) or "-"
        lines.append(f"| `{item.listed_path.replace(str(ROOT), '.')}` | {item.status} | {item.files} | {same.replace(str(ROOT), '.')} |")
    (docs / "ARCHIVE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--extract", action="store_true", help="Extract named archives not already present (default: audit only).")
    parser.add_argument("--only", nargs="*", help="Limit to these named archives.")
    parser.add_argument("--min-free-gb", type=float, default=15.0)
    parser.add_argument("--no-discover", action="store_true", help="Skip auditing additional archives.")
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log = Log(ROOT / "logs" / "archive_import_redacted.log")
    log(f"start source={args.source} dest={args.dest} extract={args.extract}")
    if not args.source.exists():
        log("SOURCE_NOT_MOUNTED: the source directory is not accessible from this runtime")
        return 2
    args.dest.mkdir(parents=True, exist_ok=True)
    index = build_index(ROOT, log)
    project_copies = {path.name.lower(): path for path in ROOT.glob("*.zip")}
    crc_cache: dict[str, int] = {}
    listed_hashes: dict[str, str] = {}
    names = args.only or NAMED_ARCHIVES
    results = [process(args.source / name, "NAMED", args, index, crc_cache, project_copies, listed_hashes, log) for name in names]
    if not args.only:
        results += [process(args.source / name, "SUPPLEMENTARY", args, index, crc_cache, project_copies, listed_hashes, log)
                    for name in SUPPLEMENTARY_ARCHIVES if (args.source / name).exists()]
    if not args.no_discover and not args.only:
        known = set(NAMED_ARCHIVES) | set(SUPPLEMENTARY_ARCHIVES)
        extras = sorted({path for root in (args.source, ROOT) for path in root.glob("*.zip") if path.name not in known}, key=lambda p: (p.parent != args.source, p.name.lower()))
        seen_hash: dict[str, str] = {}
        for path in extras:
            item = process(path, "ADDITIONAL", args, index, crc_cache, {}, seen_hash, log)
            results.append(item)
    write_outputs(results, args, started_at)
    log(f"done: {Counter(item.status for item in results if item.role == 'NAMED')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
