"""Regressions found by auditing a photographed head-CT case (report plus film photographs).

All inputs are synthetic: report wording in the glued form OCR produces from bold print, generated images
and fitted references. No patient document, image or identifier is used.
"""
import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.services import image_ood, model_inference, nlp_processor, ocr_text, scispacy_adapter
from app.services.nlp_processor import extract_clinical_statements, statements_to_source
from tests.conftest import get_auth_headers


def fracture(text: str) -> dict:
    return next(item for item in extract_clinical_statements(text) if item["entity"] == "Fracture")


def test_negated_fracture_takes_the_skeletal_site_of_the_sentence_before_it_on_the_same_line():
    text = "FINDINGS:\nBony cranium isunremarkable.No fractures noted.\n"
    item = fracture(text)
    assert item["negation"] == "NEGATED" and item["anatomical_site"] == "cranium"
    cue = next(cue for cue in item["cues"] if cue["type"] == "SITE_FROM_PRECEDING_SENTENCE")
    assert text[cue["start"]:cue["end"]] == cue["text"] == "cranium"


@pytest.mark.parametrize("text", [
    "FINDINGS:\nBony cranium is unremarkable.\nNo fractures noted.\n",          # another line
    "FINDINGS:\nThe liver is normal. No fractures noted.\n",                   # another anatomical system
    "FINDINGS:\nThe skull and the pelvis are unremarkable. No fractures noted.\n",  # two candidate sites
])
def test_a_site_is_not_borrowed_across_lines_systems_or_ambiguity(text):
    item = fracture(text)
    assert item["anatomical_site"] is None
    assert not any(cue["type"] == "SITE_FROM_PRECEDING_SENTENCE" for cue in item["cues"])


def test_required_head_ct_findings_with_laterality_and_severity():
    text = ("FINDINGS:\nRighthighparietalobeHemorrhagiccontusionwithmildperilesionaledema.\nNo midline shift.\n"
            "Bony cranium isunremarkable.No fractures noted.\nRight parietal region scalp soft tissue swelling.\n")
    found = {item["entity"]: item for item in extract_clinical_statements(text)}
    assert found["Cerebral contusion"]["negation"] == "AFFIRMED" and found["Cerebral contusion"]["laterality"] == "right"
    assert found["Cerebral contusion"]["atlas_structure_id"] == "nervous.parietal_lobe"
    assert found["Cerebral oedema"]["negation"] == "AFFIRMED"
    assert [cue["text"] for cue in found["Cerebral oedema"]["cues"] if cue["type"] == "SEVERITY"] == ["mild"]
    assert found["Midline shift"]["negation"] == "NEGATED"
    assert found["Scalp soft-tissue swelling"]["negation"] == "AFFIRMED" and found["Scalp soft-tissue swelling"]["laterality"] == "right"
    assert found["Fracture"]["negation"] == "NEGATED" and found["Fracture"]["anatomical_site"] == "cranium"


def test_model_entities_read_normalised_words_and_still_quote_the_source():
    source = "FINDINGS:\nBasalgangliaarenormal.\n"
    normalised, index = ocr_text.normalise(source)
    start = normalised.index("basal ganglia".capitalize())
    entity = {"start": start, "end": start + len("basal ganglia"), "text": normalised[start:start + len("basal ganglia")],
              "category": "MODEL_ENTITY", "cue": "fixture:ENTITY", "extractor_version": "fixture"}
    statements = statements_to_source(scispacy_adapter.entity_statements(normalised, [entity]), source, index)
    assert statements[0]["entity"] == "basal ganglia"
    assert statements[0]["entity_text"] == source[statements[0]["entity_start"]:statements[0]["entity_end"]] == "Basalganglia"
    assert statements[0]["source_span"] == source[statements[0]["source_span_start"]:statements[0]["source_span_end"]]


def test_garbled_model_entities_are_excluded_and_counted(tmp_path, monkeypatch):
    from app.services import clinical_nlp_adapter, radgraph_adapter

    report = tmp_path / "report.txt"
    report.write_text("FINDINGS:\nNoncontrastuelxiasenweeakemvettstuy study. Mild perilesional edema.\n", encoding="utf-8")
    seen = {}

    def model_statements(text):
        seen["text"] = text
        entities = [{"start": text.index(word), "end": text.index(word) + len(word), "text": word, "category": "MODEL_DISEASE",
                     "cue": "fixture:DISEASE", "extractor_version": "fixture"}
                    for word in ("Noncontrastuelxiasenweeakemvettstuy", "perilesional edema")]
        return scispacy_adapter.entity_statements(text, entities), [{"name": "fixture"}]

    monkeypatch.setattr(scispacy_adapter, "enabled", lambda: True)
    monkeypatch.setattr(scispacy_adapter, "model_statements", model_statements)
    monkeypatch.setattr(radgraph_adapter, "enabled", lambda: False)
    monkeypatch.setattr(clinical_nlp_adapter, "enabled", lambda: False)
    # The real hash: the derived-text cache is keyed by it, so a shared dummy hash would leak this text into other tests.
    result = nlp_processor.analyze_clinical_report(report, hashlib.sha256(report.read_bytes()).hexdigest())
    entities = [item["entity"] for item in result["statements"] if item["category"] == "MODEL_DISEASE"]
    assert entities == ["perilesional edema"]
    assert result["provenance"]["secondary_entities_excluded"] == {"UNREADABLE_OCR_RUN": 1}
    assert result["provenance"]["secondary_model_ner"]["input_text"] == "OCR_NORMALISED"


REPORT = (b"CT BRAIN REPORT\nStudy date: 2023-03-07\nFINDINGS:\nRighthighparietallobeHemorrhagiccontusionwithmildperilesionaledema.\n"
          b"No midline shift.\nBony cranium is unremarkable. No fractures noted.\n")


def test_reanalysis_supersedes_the_earlier_analysis_in_current_views(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-REANALYSIS"}).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                         files={"file": ("report.txt", REPORT, "text/plain")}).json()
    for _ in range(2):
        response = client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=headers)
        assert response.status_code == 201, response.text
    current = client.get(f"/api/v1/cases/{case_id}/statements", headers=headers).json()
    history = client.get(f"/api/v1/cases/{case_id}/statements?include_superseded=true", headers=headers).json()
    assert current and len(history) == 2 * len(current)
    assert not any(item["analysis_superseded"] for item in current)
    assert sum(item["analysis_superseded"] for item in history) == len(current)
    synthesis = client.get(f"/api/v1/cases/{case_id}/evidence-synthesis", headers=headers).json()
    assert len(synthesis["superseded_report_run_ids"]) == 1
    runs = {source["run_id"] for item in synthesis["report_findings"] for source in item["sources"]}
    assert len(runs) == 1 and runs.isdisjoint(synthesis["superseded_report_run_ids"])
    effective = client.get(f"/api/v1/cases/{case_id}/effective-evidence", headers=headers).json()
    assert len(effective["statements"]) == len(current)
    attributes = client.get(f"/api/v1/cases/{case_id}/attributes", headers=headers).json()
    all_attributes = client.get(f"/api/v1/cases/{case_id}/attributes?include_superseded=true", headers=headers).json()
    assert any(item["name"] == "study_date" for item in attributes) and len(all_attributes) == 2 * len(attributes)
    workflow = client.get(f"/api/v1/cases/{case_id}/workflow", headers=headers).json()
    review = next(stage for stage in workflow["stages"] if stage["id"] == "review")
    assert review["detail"].startswith("1 source findings"), "only the current analysis awaits review"


def test_secondary_nlp_readings_are_not_counted_as_report_findings(db_session, test_users, tmp_path):
    from app.models.entities import ClinicalReportStatement
    from app.services.evidence_synthesis import synthesize
    from tests.test_heterogeneous_evidence import case_and_upload

    case, _, finding = case_and_upload(db_session, test_users["clinician_a"], tmp_path)
    for entity, category, assertion in [("Fracture", "FINDING", "NEGATED"), ("fractures", "MODEL_DISEASE", "AFFIRMED"),
                                        ("mild", "MODEL_RADGRAPH_OBSERVATION", "AFFIRMED")]:
        db_session.add(ClinicalReportStatement(case_id=case.id, finding_id=finding.id, entity=entity, category=category,
                       negation=assertion, temporality="CURRENT", certainty="CERTAIN", source_span="No fractures noted.",
                       extractor_version="fixture"))
    db_session.commit()
    result = synthesize(case.id, db_session)
    assert [item["entity"] for item in result["report_findings"]] == ["Fracture"]
    assert sorted(item["entity"] for item in result["secondary_model_mentions"]) == ["fractures", "mild"]
    assert result["contradictions"] == [], "a secondary reading never contradicts the report's own assertion"


def two_stage_reference():
    rng = np.random.default_rng(7)
    fit = [rng.normal(size=(200, 6)), rng.normal(size=(200, 8))]
    calibration = [rng.normal(size=(100, 6)), rng.normal(size=(100, 8))]
    return image_ood.fit_reference(fit, calibration)


def fake_features(colour_offset: float, grey_offset: float):
    """Stage 0 moves with colour, stage 1 with content; a greyscale image has no colour."""
    def features(network, payload, device, image):
        rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
        coloured = bool(np.mean(rgb.max(axis=2) - rgb.min(axis=2) > model_inference.COLOUR_LEVELS) > .01)
        return [np.full(6, colour_offset if coloured else 0.), np.full(8, grey_offset)]
    return features


@pytest.mark.parametrize("colour,content,expected", [
    (30., 0., "Colour accounts for the refusal"),
    (30., 4., "the content itself differs"),
    (0., 30., "spread across the network's feature stages"),
])
def test_out_of_distribution_refusal_says_where_the_distance_comes_from(monkeypatch, colour, content, expected):
    reference = two_stage_reference()
    monkeypatch.setattr(model_inference, "image_features", fake_features(colour, content))
    image = Image.new("RGB", (64, 64), (200, 120, 60)) if colour else Image.new("RGB", (64, 64), (90, 90, 90))
    stages = image_ood.stage_scores(reference, [values[None] for values in model_inference.image_features(None, None, None, image)])[0]
    assert stages.mean() > reference["threshold"]
    assert expected in model_inference.refusal_explanation(reference, stages, image, None, None, None)


def test_a_greyscale_intensity_outlier_is_described_as_intensity():
    reference = two_stage_reference()
    stages = np.array([500., 1.])
    text = model_inference.refusal_explanation(reference, stages, Image.new("RGB", (32, 32), (250, 250, 250)), None, None, None)
    assert "overall intensity statistics" in text


RSNA = "brain_ct_rsna_ich_classifier"


def rsna_held_out_paths(n: int) -> list[Path]:
    import csv

    try:
        model = model_inference.get_model(RSNA)
        model_inference.ood_reference(model)
    except model_inference.InferenceNotPermitted:
        pytest.skip("RSNA checkpoint or applicability reference not available")
    root = Path(__file__).resolve().parents[2]
    manifest = root / model["artifact_bundle"]["ood_sample_manifest_path"]
    if not manifest.is_file():
        pytest.skip("RSNA held-out sample not available")
    with manifest.open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("split") == "test"][:n]
    paths = [Path(row["path"]) if Path(row["path"]).is_absolute() else root / row["path"] for row in rows]
    if len(paths) < n or not all(path.is_file() for path in paths):
        pytest.skip("RSNA held-out sample not available")
    return paths


def test_rsna_serving_path_accepts_its_own_held_out_slices_and_explains_a_colour_cast(tmp_path):
    """The threshold is not changed: held-out slices pass through the exact serving path, and the same slice
    with a 3-8 % colour cast (as a photograph adds) is refused with colour named as the cause."""
    paths = rsna_held_out_paths(10)
    model = model_inference.get_model(RSNA)
    for path in paths:
        assert model_inference.check_distribution(model, path)["status"] == "PASSED"
    grey = np.asarray(Image.open(paths[0]).convert("L"), dtype=np.float32)
    cast = tmp_path / "cast.png"
    Image.fromarray(np.stack([grey, grey * .97, grey * .92], axis=2).clip(0, 255).astype(np.uint8)).save(cast)
    with pytest.raises(model_inference.InferenceNotPermitted, match="Colour accounts for the refusal"):
        model_inference.check_distribution(model, cast)
