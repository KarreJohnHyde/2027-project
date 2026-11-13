"""Bounded, typed read-only research assistant interface."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

Tool = Literal["search_case", "get_source", "get_examination", "get_model_provenance", "get_anatomy", "get_biomarker_history", "get_evaluation", "navigate_view", "draft_report"]


class CopilotQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tool: Tool
    query: str = Field(default="", max_length=1000)
    source_id: int | None = Field(default=None, gt=0)
    finding_id: int | None = Field(default=None, gt=0)
    exam_id: int | None = Field(default=None, gt=0)
    model_id: str | None = Field(default=None, max_length=128)
    system_id: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=10, ge=1, le=20)


class Citation(BaseModel):
    node_id: str
    upload_id: int | None = None
    page: int | None = None
    span: str | None = None


class NavigateAction(BaseModel):
    type: Literal["NAVIGATE"] = "NAVIGATE"
    path: str
    source_id: int | None = None
    finding_id: int | None = None


class CopilotResponse(BaseModel):
    mode: Literal["LOCAL_DETERMINISTIC_RESEARCH_ASSISTANT"] = "LOCAL_DETERMINISTIC_RESEARCH_ASSISTANT"
    tool: Tool
    status: Literal["ANSWERED", "INSUFFICIENT_EVIDENCE", "REFUSED"]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    actions: list[NavigateAction] = Field(default_factory=list)
    never_writes: Literal[True] = True
    reason: str | None = None


class EvidenceNode(BaseModel):
    id: str
    kind: Literal["case", "examination", "upload", "finding", "statement", "measurement", "anatomy", "model_run", "review"]
    label: str
    source_file_id: int | None = None
    finding_id: int | None = None
    examination_id: int | None = None
    source_span: str | None = None
    source_page: int | None = None
    source_start: int | None = None
    source_end: int | None = None
    source_bbox: list[float] | None = None
    assertion: str | None = None
    review_status: str | None = None
    timestamp: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class EvidenceEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str


class EvidenceGraph(BaseModel):
    schema_version: Literal["medtwin.evidence-graph.v1"] = "medtwin.evidence-graph.v1"
    case_id: int
    data_version: str
    nodes: list[EvidenceNode]
    edges: list[EvidenceEdge]
    conflicts: list[dict[str, Any]]
    missing_modalities: list[str]
    limits: dict[str, int]
    truncated: bool
    notice: str
