"""Actual source hierarchy invariants and credential-free WHO adapter contracts."""
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.database import get_db
from app.models.entities import Case
from app.routers.universal_structures import router
from app.services import universal_structures as structures, icd11_source_adapter as who
from conftest import get_auth_headers


def test_all_25_families_have_source_navigation_and_no_invented_side():
    data = structures.registry()
    assert len(structures.systems()["systems"]) == 25
    assert len([n for n in data["nodes"].values() if n["kind"] == "atlas_structure"]) == 4484
    for node in data["nodes"].values():
        if node["parent_id"]: assert node["parent_id"] in data["nodes"]
        if node["kind"] != "atlas_structure": assert node["laterality"] is None
    left = data["nodes"]["atlas:regions.eyelashes_l"]
    assert left["laterality"] == "left" and left["laterality_source"] == "atlas.side"
    assert left["parent_id"] == "atlas:regions.hairs" and left["parent_relation"] == "SOURCE_EXPLICIT_PARENT"
    assert all(row["items"] for row in [structures.browse(system=s["id"]) for s in structures.systems()["systems"]])


def test_segmentation_labels_remain_registered_classes_not_atlas_mappings():
    rows = [n for n in structures.registry()["nodes"].values() if n["kind"] == "segmentation_label"]
    renal = next(n for n in rows if n["label"] == "kidney_right")
    assert renal["parent_relation"] == "REGISTERED_TASK_CLASS" and renal["laterality"] is None
    assert renal["asset_ids"] == [] and renal["capability_state"] == "CATALOGUE_ONLY"


def test_missing_atlas_geometry_uses_terms_without_inventing_asset(tmp_path, monkeypatch):
    monkeypatch.setattr(structures, "ATLAS", tmp_path / "missing-index.json")
    monkeypatch.setattr(structures, "MANIFEST", tmp_path / "missing-manifest.json")
    data = structures.registry()
    assert not data["sources"]["atlas_geometry_index_available"] and not data["sources"]["manifest_available"]
    assert data["nodes"]["atlas:regions.eyelashes_l"]["asset_ids"] == []


def test_asset_size_availability_and_unknown_rights_are_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(structures, "PUBLIC", tmp_path)
    p = tmp_path / "asset.glb"; p.write_bytes(b"123")
    asset = {"tiers": {"standard": {"url":"/asset.glb","bytes":3}}, "licence": {}}
    state = structures.asset_status(asset)
    assert state["local_available"] and not state["commercial_use_declared"]
    p.unlink(); assert not structures.asset_status(asset)["local_available"]
    assert structures.asset_status({"tiers":{"bad":{"url":"/../outside.glb"}}})["tiers"][0]["url"] is None


def test_mixed_atlas_source_licences_never_automatically_clear_chunk_rights():
    data = structures.registry()
    chunks = [a for k, a in data["assets"].items() if k.startswith("chunk:")]
    assert chunks and all(a["licence"]["commercial_use"] is None for a in chunks)


def test_unknown_parent_and_bounds_refuse():
    with pytest.raises(KeyError): structures.browse(parent_id="not:source")
    with pytest.raises(ValueError): structures.browse(limit=201)


def test_who_missing_credentials_does_not_make_network_requests(monkeypatch):
    for key in ["WHO_ICD_CLIENT_ID", "WHO_ICD_CLIENT_SECRET", "WHO_ICD_RELEASE", "MEDTWIN_WHO_ICD_TERMS_ACCEPTED"]: monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(who, "_json", lambda request: pytest.fail("Missing credentials must not make network requests"))
    result = who.lookup("257068234")
    assert result["status"] == "UNAVAILABLE" and not result["source_status"]["local_icd10cm_is_icd11"]
    assert not result["source_status"]["crosswalk_mapping_available"]
    assert "SECTION_1_2_4" in result["source_status"]["crosswalk_blocker"]
    with pytest.raises(ValueError): who.lookup("https://private.invalid/")


def test_who_native_adapter_preserves_code_title_uri_without_crosswalk(monkeypatch):
    for key, value in {"WHO_ICD_CLIENT_ID":"id", "WHO_ICD_CLIENT_SECRET":"secret", "WHO_ICD_RELEASE":"2026-01", "MEDTWIN_WHO_ICD_TERMS_ACCEPTED":"true"}.items(): monkeypatch.setenv(key, value)
    requests = []
    def response(request):
        requests.append(request)
        return {"access_token":"token"} if len(requests)==1 else {"@id":"http://id.who.int/icd/release/11/2026-01/mms/257068234", "code":"1A00", "title":{"@value":"Cholera"}}
    monkeypatch.setattr(who, "_json", response)
    result = who.lookup("257068234")
    assert result["entity"] == {"code":"1A00", "title":"Cholera", "uri":"http://id.who.int/icd/release/11/2026-01/mms/257068234", "release":"2026-01", "classification":"ICD-11 MMS"}
    assert result["local_crosswalk"] is None and result["case_data_transmitted"] is False
    assert requests[0].data == b"grant_type=client_credentials&scope=icdapi_access"
    assert requests[1].get_header("Api-version") == "v2"


@pytest.fixture
def client(db_session):
    app=FastAPI(); app.include_router(router,prefix="/api/v1"); app.dependency_overrides[get_db]=lambda:db_session
    with TestClient(app) as client: yield client


@pytest.mark.private_workspace
def test_reference_auth_and_optional_private_case_boundary(client,db_session,test_users):
    path="/api/v1/universal/structures/atlas:regions.eyelashes_l/detail"
    assert client.get("/api/v1/universal/structures/systems").status_code==401
    owner=test_users["clinician_a"]; other=test_users["clinician_b"]
    case=Case(pseudonymous_id="hierarchy-"+uuid4().hex,created_by_id=owner.id); db_session.add(case); db_session.commit()
    assert client.get(path+f"?case_id={case.id}",headers=get_auth_headers(other)).status_code==403
    result=client.get(path+f"?case_id={case.id}",headers=get_auth_headers(owner))
    assert result.status_code==200 and result.json()["case_associations"]["diagnosis_inferred"] is False
