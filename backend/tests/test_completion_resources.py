"""Offline miniature source fixtures; no internet/model execution in these tests."""
from contextlib import closing
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile

import pytest
from app.services import universal_catalogue as catalogue
from app.services import universal_terminology as terminology

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


builder = script("build_official_terminology")
downloader = script("fetch_external_resources")
benchmark = script("benchmark_external_ocr")


@pytest.fixture
def index(tmp_path, monkeypatch):
    codes, tabular, output = [tmp_path / name for name in ("codes.zip", "tabular.zip", "index.sqlite3")]
    labels = [("A00", 0, "Cholera"), ("A000", 1, "Cholera due to Vibrio cholerae 01, biovar cholerae"),
              ("S0000", 0, "Unspecified superficial injury of scalp"), ("S0000XA", 1, "Unspecified superficial injury of scalp, initial encounter")]
    with ZipFile(codes, "w") as archive:
        archive.writestr("icd10cm-order-2027.txt", "\n".join(f"{n:05} {code:<7} {valid} {label[:60]:<60} {label}" for n, (code, valid, label) in enumerate(labels, 1)))
    with ZipFile(tabular, "w") as archive:
        archive.writestr("icd10cm-tabular_-2027.xml", '<ICD10CM.tabular><chapter><name>1</name><desc>Infections</desc><section><diag><name>A00</name><diag><name>A00.0</name></diag></diag></section></chapter><chapter><name>19</name><desc>Injury</desc><section><diag><name>S00.00</name></diag></section></chapter></ICD10CM.tabular>')
    monkeypatch.setattr(builder, "EXPECTED", {"codes": hashlib.sha256(codes.read_bytes()).hexdigest(), "tabular": hashlib.sha256(tabular.read_bytes()).hexdigest()})
    report = builder.build(codes, tabular, output)
    monkeypatch.setattr(terminology, "DB_PATH", output)
    terminology._metadata.cache_clear()
    return codes, tabular, output, report


def test_official_index_preserves_exact_source_code_and_broad_scope(index):
    state = terminology.status()
    assert state["available"] and state["entry_count"] == 4
    assert state["valid_code_count"] == state["header_count"] == 2
    result = terminology.search("A00.0", "infectious", limit=5)
    item = result["items"][0]
    assert item["classification"]["code"] == "A000"  # Exact dotless source representation.
    assert item["code_mappings"][0]["relation"] == "EXACT"
    assert item["code_mappings"][0]["review_status"] == "VERIFIED_SOURCE_MAPPING"
    assert item["classification"]["curated_condition_crosswalk"] is False
    assert item["classification"]["system_link_semantics"] == "BROAD_CHAPTER_OR_CODE_RANGE_CONTEXT_ONLY"
    assert item["capability_state"] == "CATALOGUE_ONLY" and item["model_ids"] == []
    assert "No CDC/HHS/US Government endorsement" in state["notice"]


def test_seventh_character_source_codes_link_to_existing_tabular_ancestor(index):
    item = terminology.detail("icd10cm:fy2027:s0000xa")
    assert item["parent_id"] == "icd10cm:fy2027:s0000"
    assert item["classification"]["code"] == "S0000XA"


def test_import_is_idempotent_and_never_replaces_different_existing_index(index):
    codes, tabular, output, report = index
    before, modified = output.read_bytes(), output.stat().st_mtime_ns
    assert builder.build(codes, tabular, output)["changed"] is False
    assert output.read_bytes() == before and output.stat().st_mtime_ns == modified
    with closing(sqlite3.connect(output)) as db:
        manifest = json.loads(db.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0])
        manifest["data_sha256"] = "changed"
        db.execute("UPDATE metadata SET value=? WHERE key='manifest'", (json.dumps(manifest),)); db.commit()
    with pytest.raises(ValueError, match="differs"): builder.build(codes, tabular, output)


def test_modified_release_checksum_is_refused_before_output(index, tmp_path):
    codes, tabular, _, _ = index
    codes.write_bytes(codes.read_bytes() + b"different")
    output = tmp_path / "unwritten.sqlite3"
    with pytest.raises(ValueError, match="SHA-256"): builder.build(codes, tabular, output)
    assert not output.exists()


def test_custom_xml_entities_are_refused(index):
    codes, tabular, _, _ = index
    with ZipFile(tabular, "w") as archive:
        archive.writestr("icd10cm-tabular_-2027.xml", '<!DOCTYPE x [<!ENTITY a "expanded">]><ICD10CM.tabular>&a;</ICD10CM.tabular>')
    with pytest.raises(ValueError, match="entities"): builder.parse_release(codes, tabular)


@pytest.mark.parametrize("mode", ["missing", "corrupt", "wrong-schema"])
def test_missing_or_invalid_deployment_index_is_explicit_and_core_still_works(tmp_path, monkeypatch, mode):
    path = tmp_path / "index.sqlite3"
    if mode == "corrupt": path.write_bytes(b"not a database")
    elif mode == "wrong-schema":
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE metadata(key TEXT,value TEXT)")
            db.execute("INSERT INTO metadata VALUES('manifest',?)", ('{"schema_version":"unknown"}',)); db.commit()
    monkeypatch.setattr(terminology, "DB_PATH", path)
    state = terminology.status()
    assert state["available"] is False and state["state"] == "OFFICIAL_REFERENCE_INDEX_UNAVAILABLE"
    assert catalogue.search(q="renal calculus")["items"][0]["label"] == "Kidney stone"
    assert terminology.search("cholera", None, limit=1)["total"] == 0


def test_integrated_search_pagination_keeps_source_groups_and_original_mapping(index):
    result = catalogue.search(q="cholera", limit=1)
    next_page = catalogue.search(q="cholera", limit=1, offset=1)
    assert result["total"] == 2
    assert result["items"][0]["id"] != next_page["items"][0]["id"]
    assert catalogue.search(q="cholera", kind="condition")["total"] == 0
    assert catalogue.search(q="cholera", kind="classification")["total"] == 2
    assert catalogue.detail("icd10cm:fy2027:a000")["item"]["kind"] == "classification"
    assert catalogue.detail("condition:urinary:kidney-stone")["item"]["code_mappings"] == []


def test_index_mutation_changes_runtime_revision_and_invalid_count_fails_closed(index):
    _, _, output, _ = index
    before = catalogue.catalogue_data()[2]
    with closing(sqlite3.connect(output)) as db:
        db.execute("UPDATE terms SET short_label='changed' WHERE code='A000'"); db.commit()
    assert catalogue.catalogue_data()[2] != before
    with closing(sqlite3.connect(output)) as db:
        db.execute("DELETE FROM terms WHERE code='A000'"); db.commit()
    assert not terminology.status()["available"]


def test_commercial_only_downloader_and_runner_refuse_research_only_dataset(tmp_path):
    with pytest.raises(ValueError, match="commercial-use"):
        downloader.fetch_resource("kaggle-rx-words-v1", tmp_path)
    with pytest.raises(ValueError, match="commercially eligible"):
        benchmark.run(tmp_path / "unused.zip", "prescription_words", 1)
    assert list(tmp_path.iterdir()) == []


def test_bounded_downloader_receipt_hash_and_idempotence(tmp_path, monkeypatch):
    blob = io.BytesIO()
    with ZipFile(blob, "w") as archive: archive.writestr("example.txt", "source")
    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(blob.getvalue()))}
        def geturl(self): return "https://ftp.cdc.gov/approved.zip"
    calls = []
    def open_resource(request, timeout):
        calls.append(request.full_url)
        assert "Authorization" not in request.headers
        return Response(blob.getvalue())
    monkeypatch.setattr(downloader.urllib.request, "urlopen", open_resource)
    first = downloader.fetch_resource("icd10cm-2027-codes", tmp_path)
    second = downloader.fetch_resource("icd10cm-2027-codes", tmp_path)
    assert first["sha256"] == second["sha256"] == hashlib.sha256(blob.getvalue()).hexdigest()
    assert len(calls) == 1 and second["downloaded_now"] is False


def test_empty_nonzip_and_oversize_downloads_are_not_installed(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        headers = {"Content-Length": "999999999"}
        def geturl(self): return "https://ftp.cdc.gov/approved.zip"
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda *a, **k: Response(b"html error"))
    with pytest.raises(ValueError, match="budget"): downloader.fetch_resource("icd10cm-2027-codes", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_external_ocr_metric_uses_reference_denominators_and_no_clinical_repair():
    assert benchmark.score("  A B\n", "a b")["exact"]
    result = benchmark.score("mg", "mcg")
    assert result["character_edits"] == 1 and result["cer"] == .5
    assert result["wer"] == 1 and result["exact"] is False
    empty = benchmark.score("word", "")
    assert empty["cer"] == empty["wer"] == 1 and empty["empty_prediction"]


def test_external_clinocr_plan_excludes_all_exemplars():
    content = io.BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr("oneshot_lookup.csv", "subset,template,sample,role\nnormal,1,1,exemplar\nnormal,1,2,eval\nnormal,2,2,eval\n")
        for template in (1, 2):
            archive.writestr(f"ClinOCR-Bench/scans/normal/template_{template}_sample_2_normal.jpg", b"image")
            archive.writestr(f"ClinOCR-Bench/ground_truth/normal/template_{template}_sample_2_normal.txt", "external gold")
    with ZipFile(content) as archive: rows = benchmark.clinocr_rows(archive, 1)
    assert len(rows) == 1 and rows[0]["id"] == "clinocr-normal-t1-s2"
    assert rows[0]["split"] == "upstream_eval_not_exemplar"
