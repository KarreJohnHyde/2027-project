"""U-013 integrity audit: cross-split groups and exact duplicates are quarantined; patient independence and rights are
classified conservatively. Synthetic rows and files generated in the test only."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "remediation_dataset_integrity.py"


@pytest.fixture(scope="module")
def audit():
    spec = importlib.util.spec_from_file_location("remediation_dataset_integrity", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_crossing_groups_and_duplicate_files_are_quarantined(audit, tmp_path):
    same = b"identical image bytes"
    (tmp_path / "a.png").write_bytes(same)
    (tmp_path / "b.png").write_bytes(same)
    (tmp_path / "c.png").write_bytes(b"other")
    (tmp_path / "d.png").write_bytes(b"another")
    rows = [
        {"entry": "a", "path": str(tmp_path / "a.png"), "split": "train", "group_id": "g1"},
        {"entry": "b", "path": str(tmp_path / "b.png"), "split": "test", "group_id": "g2"},
        {"entry": "c", "path": str(tmp_path / "c.png"), "split": "train", "group_id": "g3"},
        {"entry": "d", "path": str(tmp_path / "d.png"), "split": "val", "group_id": "g3"},
    ]
    summary, quarantine = audit.audit_rows("fixture", rows, [10**6])
    assert summary["groups_crossing_splits"] == 1 and summary["crossing_group_examples"] == ["g3"]
    assert summary["exact_hash"]["duplicate_sets_across_splits"] == 1 and summary["exact_hash"]["status"] == "COMPLETE"
    assert {(item["reason"], item["entry"]) for item in quarantine} == {("GROUP_CROSSES_SPLITS", "d"), ("EXACT_DUPLICATE_ACROSS_SPLITS", "b")}
    assert summary["patient_independence"] == "PATIENT_INDEPENDENCE_UNVERIFIED_GROUPED_BY_CONTENT_ONLY"


def test_budget_exhaustion_is_reported_as_deferred_not_clean(audit, tmp_path):
    (tmp_path / "a.png").write_bytes(b"x" * 100)
    rows = [{"entry": "a", "path": str(tmp_path / "a.png"), "split": "test", "patient_id": "p1"}]
    summary, _ = audit.audit_rows("fixture", rows, [10])
    assert summary["exact_hash"]["status"] == "NOT_RUN_ARCHIVE_OR_PATHS" and summary["exact_hash"]["files_deferred_budget_or_unresolved"] == 1
    assert summary["patient_independence"] == "PATIENT_SEPARATION_RECORDED"


def test_rights_classification_never_assumes_commercial_use(audit):
    rights = audit.rights_by_task()
    classes = {record["usage_class"] for record in rights.values()}
    assert classes <= {"UNKNOWN_LICENCE_BLOCKED", "NON_COMMERCIAL_RESEARCH_ONLY", "COMMERCIAL_USE_PERMITTED_BY_TERMS_WITH_ATTRIBUTION",
                       "TERMS_UNCLEAR_REVIEW_REQUIRED"}
    kits = rights.get("kits19-labels")
    if kits:
        assert kits["usage_class"] == "NON_COMMERCIAL_RESEARCH_ONLY"
    assert all(record["clinical_use"] == "NOT_APPROVED" for record in rights.values())
