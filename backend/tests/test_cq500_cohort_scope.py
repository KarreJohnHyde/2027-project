"""The CQ500 external evaluation refuses a "full" cohort with unexplained missing scans, and excludes a missing scan only
when a repair record documents that its public source copy is defective. Synthetic records only."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_head_ct_cq500.py"


@pytest.fixture(scope="module")
def evaluation():
    spec = importlib.util.spec_from_file_location("evaluate_head_ct_cq500", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archives(*names):
    return [Path(f"{name}.zip") for name in names]


def test_unexplained_missing_scans_refuse_a_full_evaluation(evaluation):
    truth = {"CQ500-CT-0": {}, "CQ500-CT-1": {}}
    with pytest.raises(ValueError, match="without a documented source defect"):
        evaluation.cohort_scope(truth, archives("CQ500-CT-0"), 0, {})


def test_a_documented_source_defect_is_excluded_and_named(evaluation, tmp_path):
    record = {"source": {"problem": "no central directory; the file ends in zero bytes", "sha256": "ab" * 32},
              "entries_recovered": 2, "local_headers_found": 3,
              "series": [{"description": "Thin Plain", "slices": 2, "missing_inside_range": [5]}]}
    (tmp_path / "CQ500-CT-1.zip.repaired.json").write_text(json.dumps(record), encoding="utf-8")
    defects = evaluation.source_defects(tmp_path)
    scope = evaluation.cohort_scope({"CQ500-CT-0": {}, "CQ500-CT-1": {}}, archives("CQ500-CT-0"), 0, defects)
    assert scope["scope"] == "FULL_REFERENCED_COHORT_EXCEPT_DOCUMENTED_SOURCE_DEFECTS"
    assert list(scope["excluded_source_defects"]) == ["CQ500-CT-1"]
    assert scope["excluded_source_defects"]["CQ500-CT-1"]["series"][0]["missing_inside_range"] == 1
    assert scope["clinical_validation"] is False


def test_complete_and_pilot_cohorts_keep_their_labels(evaluation):
    truth = {"CQ500-CT-0": {}}
    assert evaluation.cohort_scope(truth, archives("CQ500-CT-0"), 0, {})["scope"] == "FULL_REFERENCED_COHORT"
    assert evaluation.cohort_scope({"CQ500-CT-0": {}, "CQ500-CT-1": {}}, archives("CQ500-CT-0"), 1, {})["scope"] == "PILOT_SUBSET_NOT_FULL_COHORT"
