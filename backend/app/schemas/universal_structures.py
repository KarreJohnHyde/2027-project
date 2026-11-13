"""Reference-only hierarchy; source ancestry differs from application context."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StructureNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    kind: Literal["system", "organ", "atlas_structure", "asset", "asset_structure", "model_task", "segmentation_label"]
    parent_id: str | None = None
    parent_relation: Literal["APPLICATION_SYSTEM_CONTEXT", "SOURCE_EXPLICIT_PARENT", "SOURCE_ASSET_COMPONENT", "REGISTERED_TASK_CLASS", "NONE"]
    system_ids: list[str] = Field(default_factory=list)
    laterality: str | None = None
    laterality_source: str | None = None
    source_id: str
    source: str
    review_state: str
    asset_ids: list[str] = Field(default_factory=list)
    model_ids: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    child_count: int = 0
    capability_state: str = "EVIDENCE_SUPPORTED"
