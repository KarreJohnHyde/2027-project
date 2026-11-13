"""Public catalogue contracts, extension validation and live capability boundaries."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.routers.universal_catalogue import router
from app.schemas.universal_catalogue import CatalogueBundle
from app.services import universal_catalogue as catalogue

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("catalogue_importer", ROOT / "scripts" / "import_universal_catalogue.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        yield client


@pytest.fixture
def manifest():
    return catalogue.bundle()


def test_all_25_families_are_navigable_with_evidence_and_conditions(api):
    response = api.get("/api/v1/universal/systems")
    assert response.status_code == 200
    payload = response.json()
    systems = payload["systems"]
    assert len(systems) == len({s["id"] for s in systems}) == 25
    assert {s["id"] for s in systems} >= {"oral-dental", "mental-behavioural", "maternal-fetal", "genetic-metabolic", "breast"}
    assert all(s["condition_count"] > 0 and s["organs"] and s["evidence_types"] for s in systems)
    assert all(s["capability_state"] == "EVIDENCE_SUPPORTED" for s in systems)
    assert len(payload["data_version"]) == 64
    assert next(s for s in systems if s["id"] == "mental-behavioural")["atlas_system"] is None


@pytest.mark.parametrize("query,label", [
    ("renal calculus", "Kidney stone"),
    ("intracranial hemorrhage", "Intracranial haemorrhage"),
    ("COPD", "Chronic obstructive pulmonary disease"),
    ("fatty liver", "Hepatic steatosis"),
    ("acute lymphoblastic leukemia", "Acute lymphoblastic leukaemia"),
])
def test_synonyms_and_spelling_find_original_concept(query, label):
    result = catalogue.search(q=query, kind="condition")
    row = next(r for r in result["items"] if r["label"] == label)
    assert row["capability_state"] == "CATALOGUE_ONLY"
    assert row["code_mappings"] == []
    assert row["code_mapping_status"] == "NOT_MAPPED"


def test_conditions_without_models_have_usable_research_catalogue(api):
    response = api.get("/api/v1/universal/catalogue", params={"system": "mental-behavioural", "kind": "condition"})
    assert response.status_code == 200
    assert response.json()["items"]
    assert all(r["model_ids"] == [] and r["evidence_types"] for r in response.json()["items"])
    caps = api.get("/api/v1/universal/capabilities?system=mental-behavioural").json()
    assert caps["model_count"] == caps["clinical_activation_count"] == 0
    assert caps["items"] == []
    assert "not diagnostic" in response.json()["notice"]


def test_atlas_and_existing_biomarkers_are_reused_with_attribution():
    _, entries, _ = catalogue.catalogue_data()
    atlas = [r for r in entries if r["id"].startswith("atlas:")]
    assert len(atlas) == 4484
    assert all("CC BY-SA" in r["licence"] and r["model_targets"] == [] for r in atlas)
    term = next(r for r in atlas if r["synonyms"])
    found = catalogue.detail(term["id"])["item"]
    assert found["synonyms"] == term["synonyms"]
    assert found["anatomy_links"][0]["relation"] == "REFERENCE_ATLAS_TERM"
    creatinine = catalogue.detail("biomarker:creatinine")["item"]
    assert creatinine["evidence_types"] == ["LABORATORY", "DOCUMENT"]
    assert creatinine["code_mappings"]
    assert all(m["review_status"] == "CURATED_UNVERIFIED" and m["relation"] == "RELATED" for m in creatinine["code_mappings"])


def test_expanded_graph_validates_and_keeps_laterality(manifest):
    _, entries, _ = catalogue.catalogue_data()
    CatalogueBundle.model_validate({**manifest, "entries": entries})
    left = catalogue.detail("atlas:regions.eyelashes_l")["item"]
    right = catalogue.detail("atlas:regions.eyelashes_r")["item"]
    assert left["laterality"] == "left" and right["laterality"] == "right"
    assert left["label"] != right["label"]
    assert left["source"].endswith("/anatomy/derived/atlas/ATTRIBUTION.md")
    assert "atlas:regions.eyelashes_l" in {r["id"] for r in catalogue.search(q="eyelashes left")["items"]}


def test_pagination_has_stable_nonoverlapping_order_and_content_revision():
    first = catalogue.search(limit=17)
    second = catalogue.search(limit=17, offset=17)
    assert first["total"] > 4484 and first["data_version"] == second["data_version"]
    assert len(first["items"]) == len(second["items"]) == 17
    assert not ({r["id"] for r in first["items"]} & {r["id"] for r in second["items"]})


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"offset": 100001}, {"q": "x" * 201}, {"kind": "diagnosis"}, {"system": "not-a-system"}])
def test_api_refuses_invalid_or_unbounded_requests(api, params):
    assert api.get("/api/v1/universal/catalogue", params=params).status_code == 422


def test_detail_route_and_unknown_identifier(api):
    response = api.get("/api/v1/universal/catalogue/condition:urinary:kidney-stone")
    assert response.status_code == 200
    assert response.json()["item"]["label"] == "Kidney stone"
    assert api.get("/api/v1/universal/catalogue/../../private").status_code == 404
    assert api.get("/api/v1/universal/catalogue/unknown:item").status_code == 404
    assert api.get("/api/v1/universal/capabilities?system=unknown").status_code == 422


def test_model_links_require_registered_exact_target_not_string_similarity(monkeypatch):
    models = [{"model_id": "kidney_stone_detector", "supported_classes": ["kidney"]}]
    monkeypatch.setattr(catalogue, "_registry_models", lambda: models)
    item = catalogue.detail("condition:urinary:kidney-stone")["item"]
    assert item["model_ids"] == []
    assert catalogue.capabilities("urinary")["items"] == []


def test_capability_requires_real_gate_and_supported_input_and_never_activates(monkeypatch):
    from app.services import model_inference
    models = [
        {"model_id": "kidney_stone_detector", "supported_classes": ["kidney_stone"], "research_inference": True,
         "status": "READY_UNVALIDATED", "task": "object_detection", "artifact_bundle": {"checkpoint_sha256": "a" * 64}},
        {"model_id": "ct_kidney_tumour_segresnet", "supported_classes": ["renal_tumour"], "research_inference": True,
         "inference_input": "volume_nifti", "status": "FAILED", "task": "segmentation"},
        {"model_id": "ct_totalsegmentator_v2", "supported_classes": ["urinary_bladder"],
         "status": "READY_UNVALIDATED", "task": "segmentation"},
    ]
    called = []
    def gate(model):
        called.append(model["model_id"])
        return {"allowed": model["model_id"] != "ct_kidney_tumour_segresnet", "blockers": ["DECLARED_TARGET_FAILED_EVALUATION"] if model["status"] == "FAILED" else []}
    monkeypatch.setattr(catalogue, "_registry_models", lambda: models)
    monkeypatch.setattr(model_inference, "research_gate", gate)
    payload = catalogue.capabilities("urinary")
    by_id = {r["model_id"]: r for r in payload["items"]}
    assert set(called) == {m["model_id"] for m in models}
    assert by_id["kidney_stone_detector"]["capability_state"] == "MODEL_AVAILABLE_RESEARCH_ONLY"
    assert by_id["kidney_stone_detector"]["inference_input"] == "image_2d"
    assert by_id["ct_kidney_tumour_segresnet"]["capability_state"] == "MODEL_BLOCKED"
    assert by_id["ct_totalsegmentator_v2"]["capability_state"] == "MODEL_BLOCKED"
    assert all(row["clinical_activation"] == "CLINICAL_ACTIVATION_NOT_CLEARED" for row in by_id.values())
    assert payload["clinical_activation_count"] == 0


def test_gate_errors_fail_closed(monkeypatch):
    from app.services import model_inference
    monkeypatch.setattr(catalogue, "_registry_models", lambda: [{"model_id": "kidney_stone_detector", "supported_classes": ["kidney_stone"], "research_inference": True}])
    def unreadable(model): raise OSError("unreadable artifact")
    monkeypatch.setattr(model_inference, "research_gate", unreadable)
    row = catalogue.capabilities("urinary")["items"][0]
    assert row["capability_state"] == "MODEL_BLOCKED"
    assert row["research_gate"] == {"allowed": False, "blockers": ["GATE_UNAVAILABLE_OSError"]}


@pytest.mark.parametrize("mutation", ["duplicate", "unknown-system", "unknown-parent", "cycle", "exact-unverified-code", "extra-field"])
def test_schema_refuses_corrupt_or_overclaiming_manifest(manifest, mutation):
    if mutation == "duplicate": manifest["entries"].append(deepcopy(manifest["entries"][0]))
    elif mutation == "unknown-system": manifest["entries"][0]["system_ids"] = ["imaginary"]
    elif mutation == "unknown-parent": manifest["entries"][0]["parent_id"] = "absent:parent"
    elif mutation == "cycle":
        manifest["entries"][0]["parent_id"] = manifest["entries"][1]["id"]
        manifest["entries"][1]["parent_id"] = manifest["entries"][0]["id"]
    elif mutation == "exact-unverified-code":
        manifest["entries"][0]["code_mappings"] = [{"system": "test", "version": "1", "code": "code", "relation": "EXACT", "review_status": "CURATED_UNVERIFIED", "source": "unreviewed"}]
    else: manifest["entries"][0]["diagnostic_accuracy"] = 1.0
    with pytest.raises(ValidationError): CatalogueBundle.model_validate(manifest)


def test_hash_changes_when_system_metadata_or_entry_changes(manifest, monkeypatch):
    original = catalogue.catalogue_data()[2]
    manifest["systems"][0]["label"] = "Changed source label"
    monkeypatch.setattr(catalogue, "bundle", lambda: manifest)
    assert catalogue.catalogue_data()[2] != original


def write_payload(path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_explicit_import_is_idempotent_and_preserves_bytes_and_mtime(manifest, tmp_path):
    source, output = tmp_path / "incoming.json", tmp_path / "catalogue.json"
    write_payload(source, manifest)
    assert importer.import_catalogue(source, output)["changed"]
    before, stat = output.read_bytes(), output.stat()
    report = importer.import_catalogue(source, output)
    assert report["changed"] is False
    assert output.read_bytes() == before and output.stat().st_mtime_ns == stat.st_mtime_ns
    assert report["clinical_activation"] == "CLINICAL_ACTIVATION_NOT_CLEARED"
    assert list(tmp_path.glob("*.lock")) == []


def test_merge_adds_new_id_but_conflicting_id_cannot_overwrite(manifest, tmp_path):
    source, output = tmp_path / "extension.json", tmp_path / "catalogue.json"
    write_payload(output, manifest)
    extended = deepcopy(manifest)
    entry = deepcopy(manifest["entries"][0])
    entry.update(id="organ:neurological:extension-example", label="Authorized extension example", source="Local reviewed example source", source_version="1")
    extended["entries"].append(entry)
    write_payload(source, extended)
    before = output.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        importer.import_catalogue(source, output)
    assert output.read_bytes() == before
    assert importer.import_catalogue(source, output, merge=True)["entries"] == len(manifest["entries"]) + 1
    merged = output.read_bytes()
    extended["entries"][0]["label"] = "Conflicting replacement"
    write_payload(source, extended)
    with pytest.raises(ValueError, match="Conflicting existing"):
        importer.import_catalogue(source, output, merge=True)
    assert output.read_bytes() == merged
    assert list(tmp_path.glob(".catalogue-import-*.tmp")) == []


def test_invalid_import_cannot_touch_destination(manifest, tmp_path):
    source, output = tmp_path / "invalid.json", tmp_path / "catalogue.json"
    write_payload(output, manifest)
    before = output.read_bytes()
    manifest["entries"][0]["system_ids"] = ["absent"]
    write_payload(source, manifest)
    with pytest.raises(ValidationError): importer.import_catalogue(source, output, merge=True)
    assert output.read_bytes() == before
