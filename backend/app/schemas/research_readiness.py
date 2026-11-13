"""Allowlisted public engineering and private operator-evaluation aggregates."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SourceIdentity(BaseModel):
    source_id: str
    label: str
    sha256: str | None = None
    status: str


class MeasuredMetric(BaseModel):
    metric_id: str
    label: str
    value: int | float | None
    unit: str
    scope: str


class IndependentReportState(BaseModel):
    status: str
    visibility: Literal["PUBLIC_STATUS", "ADMIN_ONLY"]
    documents: int | None = None
    pages: int | None = None
    readable_pages: int | None = None
    unreadable_pages: int | None = None
    annotated_fields: int | None = None
    annotated_entities: int | None = None
    independent_real_documents: int | None = None
    independent_real_pages: int | None = None
    full_report_validation: str
    metrics: list[MeasuredMetric] = Field(default_factory=list)
    sources: list[SourceIdentity] = Field(default_factory=list)
    clinical_activation: Literal[False] = False
    notice: str


class ResearchReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["medtwin.research-readiness.v1"] = "medtwin.research-readiness.v1"
    status: str
    recorded_at: str | None
    metrics: list[MeasuredMetric]
    live_model_counts: dict[str, int | None]
    live_matched_cohort: dict[str, str | int | None]
    sources: list[SourceIdentity]
    limitations: list[str]
    independent_reports: IndependentReportState
    clinical_activation: Literal[False] = False
    new_inference: Literal[False] = False
    notice: str
