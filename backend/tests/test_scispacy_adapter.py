"""Secondary scispaCy NER: context rules on model spans, provenance, failure isolation.

Entities in the fake-runner tests are fixtures; the WSL test (MEDTWIN_TEST_WSL=1) runs
the real model on a synthetic sentence."""

import os

import pytest

from app.services import nlp_processor, scispacy_adapter

TEXT = "IMPRESSION: No evidence of pneumonia. Possible pleural effusion. History of diabetes mellitus."


def _fake(text, names):
    def span(surface, label):
        start = text.index(surface)
        return {"model": "en_ner_bc5cdr_md", "label": label, "start": start, "end": start + len(surface), "text": surface}

    misaligned = {"model": "en_ner_bc5cdr_md", "label": "DISEASE", "start": 0, "end": 5, "text": "wrong"}
    return {"models": [{"name": "en_ner_bc5cdr_md", "version": "0.5.4", "spacy_version": "3.7.5"}],
            "entities": [span("pneumonia", "DISEASE"), span("pleural effusion", "DISEASE"), span("diabetes mellitus", "DISEASE"), misaligned]}


def test_model_spans_get_rule_context_and_their_own_version():
    statements, models = scispacy_adapter.model_statements(TEXT, runner=_fake)
    by_entity = {item["entity"]: item for item in statements}
    assert set(by_entity) == {"pneumonia", "pleural effusion", "diabetes mellitus"}, "a span whose offsets do not match the text is dropped"
    assert by_entity["pneumonia"]["negation"] == "NEGATED"
    assert by_entity["pleural effusion"]["certainty"] == "UNCERTAIN"
    assert by_entity["diabetes mellitus"]["temporality"] == "HISTORICAL"
    assert all(item["category"] == "MODEL_DISEASE" and item["extractor_version"] == "scispacy:en_ner_bc5cdr_md-0.5.4" for item in statements)
    assert all(item["cues"][0]["type"] == "MODEL_INFERENCE" for item in statements)
    assert all(TEXT[item["entity_start"]:item["entity_end"]] == item["entity_text"] for item in statements)
    assert models[0]["version"] == "0.5.4"


def _report(tmp_path):
    path = tmp_path / "synthetic.txt"
    path.write_text(f"Synthetic fixture. {TEXT}", encoding="utf-8")
    return path


def test_disabled_by_default_and_rule_output_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDTWIN_SCISPACY", raising=False)
    result = nlp_processor.analyze_clinical_report(_report(tmp_path), "0" * 64)
    assert result["provenance"]["secondary_model_ner"] == {"status": "DISABLED"}
    assert not any(item["category"].startswith("MODEL_") for item in result["statements"])


def test_worker_failure_keeps_rule_statements(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDTWIN_SCISPACY", "wsl")
    baseline = nlp_processor.extract_clinical_statements(nlp_processor.prepare_report_text(_report(tmp_path))[0])

    def broken(text, names):
        raise scispacy_adapter.ScispacyUnavailable("worker exited with 1")

    monkeypatch.setattr(scispacy_adapter, "run_worker", broken)
    result = nlp_processor.analyze_clinical_report(_report(tmp_path), "0" * 64)
    assert result["provenance"]["secondary_model_ner"]["status"] == "UNAVAILABLE"
    assert len(result["statements"]) == len(baseline) and result["label"] == nlp_processor.summarise_statements(baseline)


@pytest.mark.skipif(os.getenv("MEDTWIN_TEST_WSL") != "1", reason="set MEDTWIN_TEST_WSL=1 to run scispaCy in WSL")
def test_real_scispacy_in_wsl_negates_a_denied_disease():
    statements, models = scispacy_adapter.model_statements("No evidence of pneumonia.")
    assert models[0]["name"] == "en_ner_bc5cdr_md"
    assert [(item["entity"], item["negation"]) for item in statements] == [("pneumonia", "NEGATED")]
