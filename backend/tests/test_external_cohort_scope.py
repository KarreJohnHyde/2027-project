import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("cq500_evaluator", Path(__file__).resolve().parents[2] / "scripts/evaluate_head_ct_cq500.py")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


def test_partial_download_never_becomes_a_full_external_cohort():
    reference = {"CQ500-CT-0": {}, "CQ500-CT-1": {}}
    archives = [Path("CQ500-CT-0.zip")]
    with pytest.raises(ValueError, match="Full external evaluation refused"):
        evaluator.cohort_scope(reference, archives, 0)
    pilot = evaluator.cohort_scope(reference, archives, 1)
    assert pilot["scope"] == "PILOT_SUBSET_NOT_FULL_COHORT"
    assert pilot["clinical_validation"] is False
    assert pilot["missing_reference_scans"] == ["CQ500-CT-1"]
