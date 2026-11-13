"""Versioned public catalogue contracts; no case or diagnostic data."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = str
CAPABILITY_STATES = ("CATALOGUE_ONLY", "EVIDENCE_SUPPORTED", "MODEL_AVAILABLE_RESEARCH_ONLY", "MODEL_BLOCKED")


class CodeMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    system: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=128)
    relation: Literal["EXACT", "BROADER", "NARROWER", "RELATED"]
    review_status: Literal["VERIFIED_SOURCE_MAPPING", "CURATED_UNVERIFIED"]
    source: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def exact_requires_reviewed_source(self):
        if self.relation == "EXACT" and self.review_status != "VERIFIED_SOURCE_MAPPING":
            raise ValueError("An exact mapping requires a verified source mapping")
        return self


class AnatomyLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structure_id: str = Field(min_length=1, max_length=256)
    relation: Literal["SCHEMATIC_ASSOCIATION", "REFERENCE_ATLAS_TERM"]


class TargetLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)


class CatalogueEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=256, pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    label: str = Field(min_length=1, max_length=256)
    kind: Literal["organ", "condition", "structure", "biomarker", "investigation", "classification"]
    system_ids: list[str] = Field(min_length=1, max_length=25)
    synonyms: list[str] = Field(default_factory=list, max_length=30)
    parent_id: str | None = None
    laterality: Literal["left", "right", "bilateral", "midline"] | None = None
    code_mappings: list[CodeMapping] = Field(default_factory=list, max_length=20)
    evidence_types: list[str] = Field(default_factory=list, max_length=20)
    anatomy_links: list[AnatomyLink] = Field(default_factory=list, max_length=30)
    model_targets: list[TargetLink] = Field(default_factory=list, max_length=20)
    source: str = Field(min_length=1, max_length=512)
    source_version: str = Field(min_length=1, max_length=128)
    licence: str = Field(min_length=1, max_length=256)
    review_status: Literal["CURATED_RESEARCH_CATALOGUE", "EXISTING_REFERENCE_TERMINOLOGY"] = "CURATED_RESEARCH_CATALOGUE"
    note: str = Field(default="", max_length=2048)


class AnatomicalSystem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")
    label: str = Field(min_length=1, max_length=128)
    synonyms: list[str] = Field(default_factory=list, max_length=20)
    organs: list[str] = Field(min_length=1, max_length=30)
    atlas_system: str | None = None
    evidence_types: list[str] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=15)


class CatalogueBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["medtwin.universal-catalogue.v1"]
    version: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=512)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    notice: str = Field(min_length=1, max_length=2048)
    systems: list[AnatomicalSystem] = Field(min_length=1, max_length=100)
    entries: list[CatalogueEntry] = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def check_references(self):
        system_ids = [s.id for s in self.systems]
        entry_ids = [e.id for e in self.entries]
        if len(set(system_ids)) != len(system_ids) or len(set(entry_ids)) != len(entry_ids):
            raise ValueError("Duplicate catalogue or system identifiers")
        known = set(system_ids)
        ids = set(entry_ids)
        for entry in self.entries:
            if len(set(entry.system_ids)) != len(entry.system_ids) or not set(entry.system_ids) <= known:
                raise ValueError(f"Unknown or repeated system reference: {entry.id}")
            if entry.parent_id and entry.parent_id not in ids:
                raise ValueError(f"Unknown parent: {entry.id}")
            if entry.parent_id == entry.id:
                raise ValueError("Self-parent catalogue entry")
        parents = {e.id: e.parent_id for e in self.entries}
        finished = set()
        for start in parents:
            if start in finished:
                continue
            seen, node = set(), start
            while node is not None and node not in finished:
                if node in seen:
                    raise ValueError("Catalogue parent cycle")
                seen.add(node)
                node = parents.get(node)
            finished.update(seen)
        return self
