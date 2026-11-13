"""Bounded public research-record exploration, without patient identifiers."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class MatchedRecordsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["global", "same_run"] = "global"
    label: Literal["NORM", "MI", "STTC", "CD", "HYP"] = "NORM"
    order: Literal["disagreement", "errors", "probability_gap"] = "disagreement"
    errors_only: bool = False
    search: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_-]*$")
    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=20, ge=1, le=50)
    expected_snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class RecordDecision(BaseModel):
    probability: float
    predicted_label: int
    error_type: Literal["TRUE_POSITIVE", "TRUE_NEGATIVE", "FALSE_POSITIVE", "FALSE_NEGATIVE"]


class MatchedRecord(BaseModel):
    record_pseudonym: str
    reference_label: int
    left: RecordDecision
    right: RecordDecision
    decision_disagreement: bool
    absolute_probability_gap: float
    missingness: dict[str, bool]
    input_provenance: dict[str, str]


class MatchedRecordsResponse(BaseModel):
    schema_version: Literal["medtwin.matched-model-records.v1"] = "medtwin.matched-model-records.v1"
    status: Literal["MATCHED_RECORDS_AVAILABLE", "RIGHTS_BLOCKED", "UNAVAILABLE", "SNAPSHOT_CHANGED"]
    reason: str | None = None
    mode: str
    label: str
    labels: list[str]
    order: str
    offset: int
    limit: int
    total: int = 0
    total_filtered: int = 0
    snapshot_id: str | None = None
    cohort: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, Any] = Field(default_factory=dict)
    rows: list[MatchedRecord] = Field(default_factory=list)
    never_writes: Literal[True] = True
    clinical_activation: Literal[False] = False
    notice: str
