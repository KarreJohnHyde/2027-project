"""
Pydantic schemas for request validation and response serialization.
Strict type validation, safety guarantees, and complete metadata.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from app.models.entities import UserRole, EvidenceStatus, RepresentationLevel, ModalityType


# ---------------- Auth Schemas ----------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: UserRole


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=128, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None

    # Role assignment is deliberately absent from public self-registration.
    # Reject unexpected fields instead of silently suggesting they are honored.
    model_config = ConfigDict(extra="forbid")


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------- Case & Examination Schemas ----------------
class ExaminationCreate(BaseModel):
    exam_date: datetime
    modality: ModalityType
    clinical_indication: Optional[str] = None


class ExaminationResponse(BaseModel):
    id: int
    case_id: int
    exam_date: datetime
    modality: ModalityType
    clinical_indication: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseCreate(BaseModel):
    pseudonymous_id: str = Field(..., min_length=3, max_length=64)
    patient_ref: Optional[str] = None
    description: Optional[str] = None
    examinations: Optional[List[ExaminationCreate]] = None


class CaseResponse(BaseModel):
    id: int
    pseudonymous_id: str
    patient_ref: Optional[str]
    description: Optional[str]
    created_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    examinations: List[ExaminationResponse] = []

    model_config = ConfigDict(from_attributes=True)


# ---------------- Uploaded File Schemas ----------------
class FileUploadResponse(BaseModel):
    id: int
    case_id: int
    examination_id: Optional[int]
    filename: str
    file_hash: str
    file_size_bytes: int
    mime_type: str
    modality: ModalityType
    is_associated: bool
    association_notes: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------- Finding & Report Statements ----------------
class ClinicalStatementResponse(BaseModel):
    id: int
    entity: str
    negation: str
    temporality: str
    source_span: str

    model_config = ConfigDict(from_attributes=True)


class FindingResponse(BaseModel):
    id: int
    inference_run_id: Optional[int]
    case_id: int
    modality: ModalityType
    category: str
    label: str
    raw_confidence: Optional[float]
    calibrated_confidence: Optional[float]
    calibration_status: str
    visual_explanation_path: Optional[str]
    explanation_type: Optional[str]
    representation_level: RepresentationLevel
    anatomical_region: Optional[str]
    mapping_status: str
    tre_score: Optional[float]
    tre_threshold: Optional[float]
    evidence_provenance: Optional[Dict[str, Any]]
    review_status: EvidenceStatus
    failure_reason: Optional[str]
    is_demo: bool
    created_at: datetime
    report_statements: List[ClinicalStatementResponse] = []

    model_config = ConfigDict(from_attributes=True)


class AnalysisJobFindingSummary(BaseModel):
    id: int
    modality: ModalityType
    category: str
    label: str
    raw_confidence: Optional[float]
    calibrated_confidence: Optional[float]
    review_status: EvidenceStatus
    failure_reason: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class AnalysisJobResponse(BaseModel):
    id: int
    case_id: int
    upload_id: int
    status: EvidenceStatus
    modality: ModalityType
    model_name: str
    model_version: str
    preprocessing_version: str
    execution_time_ms: Optional[float]
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    findings: List[AnalysisJobFindingSummary] = Field(default_factory=list)



# ---------------- Fusion Schemas ----------------
class FusionRequest(BaseModel):
    case_id: int


class FusionResponse(BaseModel):
    id: Optional[int] = None
    case_id: int
    modality_mask: Dict[str, int]
    active_modalities_count: int
    gated_weights: Optional[Dict[str, float]] = None
    fused_status: EvidenceStatus
    fused_prediction: Optional[Dict[str, Any]] = None
    paired_data_validated: bool
    abstention_reason: Optional[str] = None
    notice: str = "RESEARCH ONLY. NOT A DIAGNOSTIC PREDICTION."


# ---------------- Concordance Schemas ----------------
class ConcordanceCheckRequest(BaseModel):
    case_id: int


class ConcordanceItemResponse(BaseModel):
    id: int
    finding_category: str
    report_entity: str
    report_status: str
    model_label: str
    is_discordant: bool
    review_flag: str
    notes: Optional[str]
    neither_source_overwritten: bool

    model_config = ConfigDict(from_attributes=True)


class ConcordanceResponse(BaseModel):
    case_id: int
    total_comparisons: int
    discordant_count: int
    items: List[ConcordanceItemResponse] = []
    notice: str = "Report concordance flags disagreements for human review. Neither source is overwritten."


# ---------------- Anatomical Mapping Schemas ----------------
class RegistrationGateCheck(BaseModel):
    finding_id: int
    coordinate_frame: str = "Blender_Model_M_To_Anatomy_A"
    landmarks_source: List[List[float]] = [] # [ [x, y, z], ... ]
    landmarks_target: List[List[float]] = [] # [ [x, y, z], ... ]
    threshold_mm: Optional[float] = 5.0


class AnatomicalAssetResponse(BaseModel):
    id: int
    name: str
    system_name: str
    asset_path: str
    format: str
    representation_level: RepresentationLevel
    is_available: bool
    notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class RegistrationResponse(BaseModel):
    finding_id: int
    coordinate_frame: str
    transform_matrix: Optional[List[List[float]]]
    held_out_landmarks_count: int
    tre_error: Optional[float]
    tre_threshold: float
    passed_gate: bool
    representation_level: RepresentationLevel
    assigned_region: Optional[str]
    mapping_status: str
    explanatory_reason: str


# ---------------- Forecasting Schemas ----------------
class ForecastRequest(BaseModel):
    case_id: int
    target_metric: str = "Joint Space Width"
    unit: str = "mm"
    horizon_days: int = 180


class ForecastResponse(BaseModel):
    id: Optional[int] = None
    case_id: int
    target_metric: str
    unit: str
    horizon_days: int
    observations_count: int
    predicted_value: Optional[float]
    baseline_persistence: Optional[float]
    baseline_linear: Optional[float]
    mae_estimate: Optional[float]
    rmse_estimate: Optional[float]
    eligibility_status: EvidenceStatus
    ineligibility_reason: Optional[str]
    chronological_series: List[Dict[str, Any]] = []
    notice: str = "EXPERIMENTAL ESTIMATE ONLY. NOT A MEDICAL PREDICTION."


# ---------------- Review & Audit Schemas ----------------
class EntityCorrection(BaseModel):
    """A proposed amendment to one extracted statement; source text is immutable."""

    target_statement_id: int = Field(..., gt=0, strict=True)
    action: Literal["AMEND", "REMOVE"]
    corrected_entity: Optional[str] = Field(default=None, min_length=1, max_length=128)
    corrected_assertion: Optional[Literal["AFFIRMED", "NEGATED"]] = None
    corrected_temporality: Optional[Literal["CURRENT", "HISTORICAL", "FUTURE", "UNSPECIFIED"]] = None
    corrected_certainty: Optional[Literal["CERTAIN", "UNCERTAIN", "HYPOTHETICAL", "UNSPECIFIED"]] = None
    corrected_anatomical_site: Optional[str] = Field(default=None, min_length=1, max_length=128)
    corrected_laterality: Optional[Literal["LEFT", "RIGHT", "BILATERAL", "MIDLINE", "UNSPECIFIED"]] = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)

    @model_validator(mode="after")
    def validate_change(self):
        amended_values = (
            self.corrected_entity,
            self.corrected_assertion,
            self.corrected_temporality,
            self.corrected_certainty,
            self.corrected_anatomical_site,
            self.corrected_laterality,
        )
        if self.action == "AMEND" and not any(value is not None for value in amended_values):
            raise ValueError("AMEND requires at least one corrected entity field.")
        if self.action == "REMOVE" and any(value is not None for value in amended_values):
            raise ValueError("REMOVE cannot include corrected entity fields.")
        return self


class MeasurementCorrection(BaseModel):
    """A proposed amendment to one extracted measurement; it is never applied automatically."""

    target_measurement_id: int = Field(..., gt=0, strict=True)
    action: Literal["AMEND", "REMOVE"]
    corrected_display_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    corrected_value: Optional[float] = Field(default=None, ge=-1e15, le=1e15)
    corrected_result_operator: Optional[Literal["=", "<", ">", "<=", ">="]] = None
    corrected_unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    corrected_reference_low: Optional[float] = Field(default=None, ge=-1e15, le=1e15)
    corrected_reference_high: Optional[float] = Field(default=None, ge=-1e15, le=1e15)
    corrected_specimen: Optional[str] = Field(default=None, min_length=1, max_length=64)
    corrected_laboratory_method: Optional[str] = Field(default=None, min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_change(self):
        amended_values = (
            self.corrected_display_name,
            self.corrected_value,
            self.corrected_result_operator,
            self.corrected_unit,
            self.corrected_reference_low,
            self.corrected_reference_high,
            self.corrected_specimen,
            self.corrected_laboratory_method,
        )
        if self.action == "AMEND" and not any(value is not None for value in amended_values):
            raise ValueError("AMEND requires at least one corrected measurement field.")
        if self.action == "REMOVE" and any(value is not None for value in amended_values):
            raise ValueError("REMOVE cannot include corrected measurement fields.")
        if (
            self.corrected_reference_low is not None
            and self.corrected_reference_high is not None
            and self.corrected_reference_low > self.corrected_reference_high
        ):
            raise ValueError("Corrected reference_low cannot exceed corrected reference_high.")
        return self


class HumanReviewCorrectionPayload(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["PROPOSED_NOT_APPLIED"] = "PROPOSED_NOT_APPLIED"
    entity_corrections: List[EntityCorrection] = Field(default_factory=list, max_length=20)
    measurement_corrections: List[MeasurementCorrection] = Field(default_factory=list, max_length=20)

    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="after")
    def validate_payload(self):
        total = len(self.entity_corrections) + len(self.measurement_corrections)
        if total == 0:
            raise ValueError("At least one typed correction is required.")
        if total > 20:
            raise ValueError("At most 20 corrections are allowed per review.")
        statement_ids = [item.target_statement_id for item in self.entity_corrections]
        measurement_ids = [item.target_measurement_id for item in self.measurement_corrections]
        if len(statement_ids) != len(set(statement_ids)):
            raise ValueError("A statement may be corrected only once per review.")
        if len(measurement_ids) != len(set(measurement_ids)):
            raise ValueError("A measurement may be corrected only once per review.")
        if len(self.model_dump_json().encode("utf-8")) > 8192:
            raise ValueError("Correction payload exceeds the 8192-byte limit.")
        return self


class HumanReviewCreate(BaseModel):
    review_status: str = Field(..., pattern="^(CONFIRMED|REJECTED|MODIFIED|REQUIRES_FURTHER_WORKUP)$")
    reviewer_comments: Optional[str] = Field(default=None, max_length=2000)
    correction_payload: Optional[HumanReviewCorrectionPayload] = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("reviewer_comments")
    @classmethod
    def normalize_comments(cls, value: Optional[str]) -> Optional[str]:
        return value or None

    @model_validator(mode="after")
    def validate_decision_payload(self):
        if self.review_status == "MODIFIED":
            if not self.reviewer_comments:
                raise ValueError("MODIFIED reviews require a reviewer rationale.")
            if self.correction_payload is None:
                raise ValueError("MODIFIED reviews require a typed correction_payload.")
        elif self.correction_payload is not None:
            raise ValueError("correction_payload is allowed only for MODIFIED reviews.")
        return self


class HumanReviewResponse(BaseModel):
    id: int
    finding_id: int
    reviewer_id: Optional[int]
    review_status: str
    reviewer_comments: Optional[str]
    correction_payload: Optional[HumanReviewCorrectionPayload]
    original_output_preserved: bool
    reviewed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditEventResponse(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    resource_type: str
    resource_id: Optional[str]
    details: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------- System Telemetry ----------------
class SystemHealthResponse(BaseModel):
    status: str
    project: str
    version: str
    cuda_available: bool
    gpu_name: Optional[str]
    research_notice: str
    database_status: str
    active_cases: int
    total_findings: int
    health_scope: str
    models_status: Dict[str, str]
