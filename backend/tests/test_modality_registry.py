"""Reader availability reflects installed dependencies, not model validation."""

import pytest

from app.services import modality_registry


@pytest.mark.parametrize("installed", [True, False])
def test_series_and_wfdb_use_the_implemented_reader_dependencies(monkeypatch, installed):
    checked = []

    def available(module):
        checked.append(module)
        return installed

    monkeypatch.setattr(modality_registry, "_available", available)
    readers = modality_registry._readers()
    assert readers["DICOM_SERIES"]["available"] is installed
    assert readers["DICOM_SERIES"]["upload_accepted"] is True
    assert readers["WFDB"]["available"] is installed
    assert readers["WFDB"]["library"] == "numpy"
    assert "numpy" in checked and "wfdb" not in checked
    assert "Other formats and multi-segment records are refused" in readers["WFDB"]["note"]
    assert "proof that all acquired slices are present" in readers["DICOM_SERIES"]["note"]


def test_reader_support_never_fabricates_validated_tasks(monkeypatch):
    monkeypatch.setattr(modality_registry, "_available", lambda _: True)
    monkeypatch.setattr(modality_registry, "list_models", lambda: {"models": [{
        "model_id": "research-only", "display_name": "Research fixture",
        "status": "READY_UNVALIDATED", "supported_modalities": ["MRI", "ECG"],
        "activation": {"eligible": False}, "research_gate": {"allowed": True},
    }]})
    payload = modality_registry.modality_registry()
    modalities = {item["id"]: item for item in payload["modalities"]}
    for name in ("MRI", "ECG"):
        assert modalities[name]["file_support_status"] == "SUPPORTED"
        assert modalities[name]["available_ai_models"][0]["research_inference"] is True
        assert modalities[name]["validated_tasks"] == []
        assert all(item["status"] == "MODEL_NOT_VALIDATED" for item in modalities[name]["unsupported_tasks"])
