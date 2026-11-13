"""Stable response envelopes for bounded, read-only completion research tools."""
from typing import Any, Literal
from pydantic import BaseModel, Field


class PairedEvidenceResponse(BaseModel):
    schema_version: Literal["medtwin.paired-evidence.v1"] = "medtwin.paired-evidence.v1"
    case_id: int
    status: str
    groups: list[dict[str, Any]] = Field(default_factory=list)
    unlinked_source_ids: list[int] = Field(default_factory=list)
    graph_data_version: str
    truncated: bool
    learned_fusion_eligible: Literal[False] = False
    clinical_activation: Literal[False] = False
    never_writes: Literal[True] = True
    notice: str


class BacktestResponse(BaseModel):
    schema_version: Literal["medtwin.baseline-backtest.v1"] = "medtwin.baseline-backtest.v1"
    case_id: int
    status: str
    metric: str
    unit: str
    horizon_days: int
    models: dict[str, Any] = Field(default_factory=dict)
    matched_comparison: dict[str, Any] | None = None
    reason: str | None = None
    clinical_activation: Literal[False] = False
    never_writes: Literal[True] = True
    notice: str
