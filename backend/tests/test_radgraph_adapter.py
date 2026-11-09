"""RadGraph-XL observations: imaging pages only, presence labels, located_at anatomy, offsets, failure isolation.

Graphs in the fake-runner tests are fixtures shaped like RadGraph's output; the live test (MEDTWIN_TEST_RADGRAPH=1)
runs the real model on the synthetic demo CT report."""

import hashlib
import os
from pathlib import Path

import pytest

from app.services import nlp_processor, radgraph_adapter

SENTENCE = "No pleural effusion."
IMAGING = [{"document_type": {"document_type": "IMAGING_REPORT"}}]


def _graph(sentences):
    """RadGraph's shape for the sentence (the rule splitter's bounds end before the full stop): its tokens
    joined by spaces, entities indexing them."""
    assert sentences == ["No pleural effusion"]
    return {"0": {"text": "No pleural effusion", "entities": {
        "1": {"tokens": "pleural", "label": "Anatomy::definitely present", "start_ix": 1, "end_ix": 1, "relations": []},
        "2": {"tokens": "effusion", "label": "Observation::definitely absent", "start_ix": 2, "end_ix": 2, "relations": [["located_at", "1"]]},
    }}}


def test_observation_gets_presence_site_and_offsets():
    statements, provenance = radgraph_adapter.observation_statements(SENTENCE, [0], IMAGING, runner=_graph)
    [statement] = statements
    assert (statement["entity"], statement["negation"], statement["certainty"], statement["anatomical_site"]) == ("effusion", "NEGATED", "CERTAIN", "pleural")
    assert SENTENCE[statement["entity_start"]:statement["entity_end"]] == "effusion"
    assert statement["category"] == "MODEL_RADGRAPH_OBSERVATION" and statement["cues"][1]["text"] == "located_at:pleural"
    assert provenance["status"] == "COMPLETED" and provenance["observations"] == 1


def test_only_imaging_report_pages_are_read():
    def must_not_run(sentences):
        raise AssertionError("RadGraph must not run on a laboratory page")

    statements, provenance = radgraph_adapter.observation_statements(SENTENCE, [0], [{"document_type": {"document_type": "LAB_REPORT"}}], runner=must_not_run)
    assert statements == [] and provenance["status"] == "NOT_APPLICABLE"


def test_a_token_missing_from_the_text_skips_that_graph():
    def shifted(sentences):
        graph = _graph(sentences)
        graph["0"]["text"] = "No pleural effusions"
        return graph

    statements, _ = radgraph_adapter.observation_statements(SENTENCE, [0], IMAGING, runner=shifted)
    assert statements == []


DEMO_CT = Path(__file__).resolve().parents[1] / "app" / "data" / "demo" / "demo_ct_abdomen_report.txt"


def test_pipeline_adds_observations_and_keeps_rule_statements(monkeypatch):
    monkeypatch.setenv("MEDTWIN_RADGRAPH", "on")

    def broken(sentences):
        raise radgraph_adapter.RadGraphUnavailable("RadGraph failed: RuntimeError")

    monkeypatch.setattr(radgraph_adapter, "run_model", broken)
    digest = hashlib.sha256(DEMO_CT.read_bytes()).hexdigest()
    result = nlp_processor.analyze_clinical_report(DEMO_CT, digest)
    assert result["provenance"]["secondary_radgraph"]["status"] == "UNAVAILABLE"
    assert not any(item["category"] == "MODEL_RADGRAPH_OBSERVATION" for item in result["statements"])
    assert any(item["entity_text"].lower() == "hydronephrosis" and item["negation"] == "NEGATED" for item in result["statements"])


def test_switched_off_in_tests():
    assert radgraph_adapter.enabled() is False


@pytest.mark.skipif(os.getenv("MEDTWIN_TEST_RADGRAPH") != "1", reason="set MEDTWIN_TEST_RADGRAPH=1 to run the RadGraph-XL model")
def test_real_radgraph_on_the_demo_ct_report(monkeypatch):
    monkeypatch.setenv("MEDTWIN_RADGRAPH", "on")
    digest = hashlib.sha256(DEMO_CT.read_bytes()).hexdigest()
    result = nlp_processor.analyze_clinical_report(DEMO_CT, digest)
    observations = [item for item in result["statements"] if item["category"] == "MODEL_RADGRAPH_OBSERVATION"]
    assert result["provenance"]["secondary_radgraph"]["status"] == "COMPLETED" and observations
    by_entity = {item["entity"]: item for item in observations}
    assert by_entity["hydronephrosis"]["negation"] == "NEGATED"
    assert any(item["negation"] == "AFFIRMED" and "calculus" in item["entity"] for item in observations)
    text = nlp_processor.prepare_report_text(DEMO_CT)[0]
    assert all(text[item["entity_start"]:item["entity_end"]] == item["entity_text"] for item in observations)
