"""Optional local conversational copilot: off by default, loopback only, citations checked, deterministic fallback.
A stand-in replaces the local model; no model is downloaded or run, and no case data leave the test."""

import pytest

from app.services import copilot_local_llm as llm

ANSWERED = {"mode": "LOCAL_DETERMINISTIC_RESEARCH_ASSISTANT", "status": "ANSWERED", "answer": "[statement:3] Creatinine 1.4 mg/dL",
            "citations": [{"node_id": "statement:3"}], "actions": [], "never_writes": True, "reason": None, "tool": "search_case"}


class Request:
    query = "what does the report say about creatinine"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("MEDTWIN_COPILOT_LLM", "ollama")
    monkeypatch.setattr(llm, "query_case", lambda case, request, db: dict(ANSWERED))


def test_validation_rules():
    allowed = {"statement:3"}
    assert llm.validate("Creatinine was 1.4 mg/dL [statement:3].", allowed) is None
    assert llm.validate("Creatinine was 1.4 mg/dL.", allowed) == "NO_CITATION"
    assert llm.validate("Creatinine was high [statement:9].", allowed) == "CITATION_OUTSIDE_RETRIEVED_EVIDENCE"
    assert llm.validate("This means a diagnosis of kidney failure [statement:3].", allowed) == "CLINICAL_DECISION_LANGUAGE"


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MEDTWIN_COPILOT_LLM", raising=False)
    monkeypatch.setattr(llm, "query_case", lambda case, request, db: dict(ANSWERED))
    assert llm.converse(None, Request(), None)["llm"]["status"] == "DISABLED"


def test_a_remote_model_address_is_refused(enabled, monkeypatch):
    monkeypatch.setenv("MEDTWIN_COPILOT_LLM_URL", "https://example.com:11434")
    result = llm.converse(None, Request(), None)
    assert result["llm"]["status"] == "CONFIGURATION_REFUSED" and result["answer"] == ANSWERED["answer"]


def test_unavailable_or_rejected_answers_fall_back(enabled):
    def unavailable(*_):
        raise OSError("connection refused")
    assert llm.converse(None, Request(), None, ask=unavailable)["llm"]["status"] == "UNAVAILABLE_DETERMINISTIC_FALLBACK"
    rejected = llm.converse(None, Request(), None, ask=lambda *_: "Kidney disease is likely; start treatment [statement:3].")
    assert rejected["llm"]["status"] == "REJECTED_DETERMINISTIC_FALLBACK" and rejected["answer"] == ANSWERED["answer"]


def test_refusals_stay_deterministic(enabled, monkeypatch):
    monkeypatch.setattr(llm, "query_case", lambda case, request, db: {**ANSWERED, "status": "REFUSED", "citations": []})
    called = []
    result = llm.converse(None, Request(), None, ask=lambda *args: called.append(args) or "x")
    assert result["llm"]["status"] == "NOT_USED" and not called


def test_an_accepted_answer_keeps_the_deterministic_record(enabled):
    result = llm.converse(None, Request(), None, ask=lambda *_: "The report documents creatinine 1.4 mg/dL [statement:3].")
    assert result["llm"]["status"] == "ACCEPTED" and result["deterministic_answer"] == ANSWERED["answer"]
    assert result["citations"] == ANSWERED["citations"] and result["never_writes"] is True
