"""Strict source-bound research comparison requests; client quality labels are forbidden."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TemporalSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: int = Field(ge=1)
    frame_index: int | None = Field(default=None, ge=0, le=4095)
    frame_kind: Literal["channel", "time"] | None = None


class BoundSource(TemporalSource):
    sha256: str = Field(pattern="^[0-9a-f]{64}$")


class ProvidedRigid(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    previous: BoundSource
    current: BoundSource
    previous_to_current_ras_mm: list[list[float]]


class TemporalComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    previous: BoundSource
    current: BoundSource
    previous_region: str = Field(min_length=2, max_length=80)
    current_region: str = Field(min_length=2, max_length=80)
    same_subject_attested: bool = False
    same_region_attested: bool = False
    comparable_intensity_attested: bool = False
    alignment: Literal["compute_rigid", "shared_physical_space", "provided_rigid"] = "compute_rigid"
    shared_physical_space_attested: bool = False
    provided_rigid: ProvidedRigid | None = None
    metric: Literal["mattes", "mean_squares"] = "mattes"


class TemporalRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    axis: Literal["axial", "coronal", "sagittal"] = "axial"
    index: int | None = Field(default=None, ge=0, le=1023)
    mode: Literal["previous", "current", "blend", "checkerboard", "difference"] = "blend"
    center: float | None = None
    width: float | None = Field(default=None, gt=0, le=1e12)
    blend: float = Field(default=.5, ge=0, le=1)
    difference_scale: float | None = Field(default=None, gt=0, le=1e12)
