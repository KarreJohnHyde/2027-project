"""Safety tests for scripts/archive_audit_and_extract.py, using small synthetic ZIPs."""

import importlib.util
import json
import sys
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "archive_audit_and_extract.py"
spec = importlib.util.spec_from_file_location("archive_import", SCRIPT)
archive_import = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = archive_import
spec.loader.exec_module(archive_import)


class SilentLog:
    def __call__(self, message):
        pass


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in entries.items():
            bundle.writestr(name, data)
    return path


def run(path: Path, dest: Path, project: Path, hashes=None, extract=True):
    args = Namespace(extract=extract, dest=dest, min_free_gb=0.0)
    index = archive_import.build_index(project, SilentLog())
    return archive_import.process(path, "NAMED", args, index, {}, {}, {} if hashes is None else hashes, SilentLog())


@pytest.fixture
def layout(tmp_path):
    source, dest, project = tmp_path / "downloads", tmp_path / "imports", tmp_path / "project"
    for directory in (source, dest, project):
        directory.mkdir()
    return source, dest, project


def test_traversal_and_absolute_entries_refuse_the_archive(layout, tmp_path):
    source, dest, project = layout
    for name in ("../escape.txt", "C:/escape.txt", "/escape.txt"):
        archive = make_zip(source / "archive (1).zip", {"ok/data.csv": b"a,b\n", name: b"x"})
        result = run(archive, dest, project)
        assert result.status == "UNSAFE", name
        assert result.extracted_to == ""
    assert not (tmp_path / "escape.txt").exists()
    assert not any(dest.rglob("escape.txt"))


def test_extraction_is_complete_atomic_and_marked(layout):
    source, dest, project = layout
    archive = make_zip(source / "archive (2).zip", {"images/a.png": b"\x89PNG fixture", "labels/a.txt": b"0 0.5 0.5 0.1 0.1\n"})
    result = run(archive, dest, project)
    assert result.status == "EXTRACTED_VERIFIED"
    final = Path(result.extracted_to)
    assert final.name == "archive_02"
    assert (final / "images" / "a.png").read_bytes() == b"\x89PNG fixture"
    marker = json.loads((final / archive_import.MARKER).read_text(encoding="utf-8"))
    assert marker["archive_sha256"] == result.sha256 and marker["files_written"] == 2
    assert not list((dest / ".staging").iterdir())
    assert result.categories == {"raster_image": 1, "text": 1} and result.yolo_like_label_files == 1


def test_rerun_is_idempotent_and_never_overwrites_different_content(layout):
    source, dest, project = layout
    archive = make_zip(source / "archive (3).zip", {"a.csv": b"1\n"})
    first = run(archive, dest, project)
    again = run(archive, dest, project)
    assert first.status == again.status == "EXTRACTED_VERIFIED" and again.extracted_to == first.extracted_to
    # A different archive with the same name must not replace the existing extraction.
    original = (Path(first.extracted_to) / "a.csv").read_bytes()
    changed = make_zip(source / "archive (3).zip", {"a.csv": b"2\n"})
    other = run(changed, dest, project)
    assert other.extracted_to != first.extracted_to
    assert (Path(first.extracted_to) / "a.csv").read_bytes() == original


def test_identical_archives_are_not_extracted_twice(layout):
    source, dest, project = layout
    payload = {"x/y.json": b'{"k": 1}'}
    hashes: dict[str, str] = {}
    first = run(make_zip(source / "archive (4).zip", payload), dest, project, hashes)
    second = run(make_zip(source / "archive (5).zip", payload), dest, project, hashes)
    assert first.status == "EXTRACTED_VERIFIED"
    assert second.status == "ALREADY_PRESENT_VERIFIED" and second.duplicate_of_listed == "archive (4).zip"
    assert not (dest / "archive_05").exists()


def test_content_already_in_the_project_is_registered_not_copied(layout):
    source, dest, project = layout
    (project / "dataset" / "class_a").mkdir(parents=True)
    (project / "dataset" / "class_a" / "img1.jpg").write_bytes(b"jpeg fixture one")
    archive = make_zip(source / "archive (6).zip", {"dataset/class_a/img1.jpg": b"jpeg fixture one"})
    result = run(archive, dest, project)
    assert result.status == "ALREADY_PRESENT_VERIFIED"
    assert result.already_present_roots and result.already_present_roots[0].startswith(str(project).replace("\\", "/"))
    # Same name and size but different bytes is not the same content.
    (project / "dataset" / "class_a" / "img1.jpg").write_bytes(b"jpeg fixture two")
    assert run(archive, dest, project).status == "EXTRACTED_VERIFIED"


def test_supplementary_archives_are_counted_exhaustively_and_never_extracted(layout):
    source, dest, project = layout
    (project / "Dataset-SEG" / "images").mkdir(parents=True)
    (project / "Dataset-SEG" / "images" / "a.jpg").write_bytes(b"jpeg fixture a")
    # The archive's root README was replaced on disk (as when an extraction overwrote a project file).
    archive = make_zip(source / "archive (25).zip", {"README.md": b"upstream readme", "Dataset-SEG/images/a.jpg": b"jpeg fixture a"})
    args = Namespace(extract=True, dest=dest, min_free_gb=0.0)
    result = archive_import.process(archive, "SUPPLEMENTARY", args, archive_import.build_index(project, SilentLog()), {}, {}, {}, SilentLog())
    assert result.status == "PARTIALLY_PRESENT" and "1 of 2 files present" in result.notes[-1]
    assert not (dest / "archive_25").exists(), "supplementary archives are never extracted"
    manifest = (dest / "_manifests" / "archive_25.entries.csv").read_text(encoding="utf-8")
    assert "Dataset-SEG/images/a.jpg" in manifest and str(project / "Dataset-SEG" / "images" / "a.jpg") in manifest


def test_invalid_windows_names_are_skipped_and_reported(layout):
    source, dest, project = layout
    archive = make_zip(source / "archive (7).zip", {"good.txt": b"ok", "bad|name.txt": b"x", "CON.txt": b"x"})
    result = run(archive, dest, project)
    assert result.status == "EXTRACTED_VERIFIED" and result.skipped_entries == 2
    assert (Path(result.extracted_to) / "good.txt").exists()


def test_missing_and_corrupt_sources_are_typed(layout):
    source, dest, project = layout
    assert run(source / "archive (8).zip", dest, project).status == "SOURCE_MISSING"
    (source / "archive (9).zip").write_bytes(b"not a zip at all")
    assert run(source / "archive (9).zip", dest, project).status == "CORRUPT"


def test_audit_mode_extracts_nothing(layout):
    source, dest, project = layout
    archive = make_zip(source / "archive (10).zip", {"a.txt": b"a"})
    result = run(archive, dest, project, extract=False)
    assert result.status == "NOT_EXTRACTED_AUDIT_MODE" and not (dest / "archive_10").exists()
