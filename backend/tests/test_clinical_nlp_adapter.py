"""Secondary clinical NLP: medSpaCy context agreement and MedCAT concept statements, failure isolation.

The fake-runner payloads are fixtures; the WSL test (MEDTWIN_TEST_WSL=1) runs real medSpaCy and MedCAT
(the example pack) on a synthetic sentence."""

import hashlib
import os

import pytest

from app.services import clinical_nlp_adapter, nlp_processor

TEXT = "IMPRESSION: No evidence of pneumonia. Known kidney failure. Family history of diabetes mellitus."


def _rule_statements():
    return nlp_processor.extract_clinical_statements(TEXT)


def _fake(text, spans, pack):
    """medSpaCy agrees on everything except the first span; MedCAT links 'kidney failure'."""
    context = [{"id": span["id"], "is_negated": "pneumonia" in text[span["start"]:span["end"]].lower(), "is_uncertain": False,
                "is_historical": False, "is_hypothetical": False, "is_family": "diabetes" in text[span["start"]:span["end"]].lower(),
                "section": "impression", "modifiers": [{"category": "NEGATED_EXISTENCE", "text": "No evidence of"}]} for span in spans]
    if context:
        context[0]["is_negated"] = not context[0]["is_negated"]
    start = text.index("kidney failure")
    return {"tools": {"medspacy": {"name": "medspacy", "version": "1.3.1"}, "medcat": {"name": "medcat", "version": "2.3.0"}},
            "context": context,
            "medcat": {"pack": {"file": pack.name if pack else None, "model_id": "7d3918d28e973efa", "concepts": 2, "names": 6},
                       "entities": [{"cui": "C0035078", "name": "Kidney Failure", "start": start, "end": start + 14, "text": "kidney failure",
                                     "similarity": 1.0, "types": []}]}}


def test_context_comparison_and_concept_statements():
    rules = _rule_statements()
    concepts, provenance = clinical_nlp_adapter.analyse(TEXT, rules, runner=_fake)
    assert provenance["status"] == "COMPLETED"
    comparison = provenance["medspacy_context"]
    assert comparison["statements_compared"] == len(rules) > 0
    assert len(comparison["disagreements"]) >= 1, "the deliberately flipped first span is reported"
    assert comparison["agreement"]["negation=NEGATED"]["of"] == len(rules)
    assert [(item["entity"], item["category"], item["negation"]) for item in concepts] == [("kidney failure", "MODEL_CONCEPT", "AFFIRMED")]
    assert concepts[0]["cues"][0]["text"] == "medcat:C0035078:Kidney Failure"
    assert TEXT[concepts[0]["entity_start"]:concepts[0]["entity_end"]] == "kidney failure"


def test_the_example_pack_is_labelled_as_a_demonstration(monkeypatch):
    monkeypatch.delenv("MEDTWIN_MEDCAT_MODEL_PACK", raising=False)
    if not clinical_nlp_adapter.EXAMPLE_PACK.exists():
        pytest.skip("MedCAT example pack not present in this checkout")
    _, provenance = clinical_nlp_adapter.analyse(TEXT, _rule_statements(), runner=_fake)
    assert provenance["medcat"]["pack"]["example_pack"] is True
    assert "not a clinical vocabulary" in provenance["medcat"]["vocabulary_note"]


def _report(tmp_path):
    path = tmp_path / "synthetic.txt"
    path.write_text(f"Synthetic fixture. {TEXT}", encoding="utf-8")
    return path


def _digest(tmp_path):
    # The prepared-text cache is keyed by file hash, so each fixture needs its own.
    return hashlib.sha256(_report(tmp_path).read_bytes()).hexdigest()


def test_pipeline_keeps_rule_statements_and_records_the_comparison(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDTWIN_CLINICAL_NLP", "wsl")
    monkeypatch.setattr(clinical_nlp_adapter, "run_worker", _fake)
    baseline = nlp_processor.extract_clinical_statements(nlp_processor.prepare_report_text(_report(tmp_path))[0])
    result = nlp_processor.analyze_clinical_report(_report(tmp_path), _digest(tmp_path))
    assert result["provenance"]["secondary_clinical_nlp"]["status"] == "COMPLETED"
    rules = [item for item in result["statements"] if not item["category"].startswith("MODEL_")]
    assert len(rules) == len(baseline) and result["label"] == nlp_processor.summarise_statements(baseline)
    assert [item["entity"] for item in result["statements"] if item["category"] == "MODEL_CONCEPT"] == ["kidney failure"]


def test_worker_failure_keeps_rule_statements(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDTWIN_CLINICAL_NLP", "wsl")

    def broken(text, spans, pack):
        raise clinical_nlp_adapter.ClinicalNlpUnavailable("worker exited with 1")

    monkeypatch.setattr(clinical_nlp_adapter, "run_worker", broken)
    result = nlp_processor.analyze_clinical_report(_report(tmp_path), _digest(tmp_path))
    assert result["provenance"]["secondary_clinical_nlp"]["status"] == "UNAVAILABLE"
    assert not any(item["category"] == "MODEL_CONCEPT" for item in result["statements"])


def test_spans_expanding_to_one_token_go_to_different_layers():
    """OCR-glued 'masslesion': two character spans expand to the same token and must not share a Doc."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("clinical_nlp_worker", Path(__file__).resolve().parents[1] / "nlp_worker" / "clinical_nlp_worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    layers = worker.layers([(0, 4, 5), (1, 4, 5), (2, 6, 8), (3, 7, 9)])
    assert all(not (a[1] < b[2] and b[1] < a[2]) for layer in layers for a in layer for b in layer if a is not b)
    assert sorted(span[0] for layer in layers for span in layer) == [0, 1, 2, 3]


def test_any_secondary_failure_keeps_the_rule_extraction(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDTWIN_CLINICAL_NLP", "wsl")

    def broken(text, statements, runner=None):
        raise KeyError("pleural effusion")

    monkeypatch.setattr(clinical_nlp_adapter, "analyse", broken)
    result = nlp_processor.analyze_clinical_report(_report(tmp_path), _digest(tmp_path))
    assert result["provenance"]["secondary_clinical_nlp"] == {"status": "UNAVAILABLE", "reason": "KeyError in clinical_pass"}
    assert result["statements"], "rule statements survive"


def test_switched_off_by_default_in_tests():
    assert clinical_nlp_adapter.enabled() is False


@pytest.mark.skipif(os.getenv("MEDTWIN_TEST_WSL") != "1", reason="set MEDTWIN_TEST_WSL=1 to run medSpaCy and MedCAT in WSL")
def test_real_medspacy_and_medcat_in_wsl(monkeypatch):
    monkeypatch.delenv("MEDTWIN_MEDCAT_MODEL_PACK", raising=False)
    text = "No evidence of pneumonia. The patient has kidney failure."
    rules = nlp_processor.extract_clinical_statements(text)
    concepts, provenance = clinical_nlp_adapter.analyse(text, rules)
    assert provenance["tools"]["medspacy"]["version"] and provenance["tools"]["medcat"]["version"]
    assert [(item["entity_text"], item["negation"]) for item in rules] == [("pneumonia", "NEGATED")]
    comparison = provenance["medspacy_context"]
    assert comparison["statements_compared"] == 1 and comparison["agreement"]["negation=NEGATED"] == {"agree": 1, "of": 1}
    assert [(item["entity"], item["negation"]) for item in concepts] == [("kidney failure", "AFFIRMED")]
    assert provenance["medcat"]["pack"]["concepts"] == 2 and provenance["medcat"]["pack"]["example_pack"] is True
