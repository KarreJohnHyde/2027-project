"""
SQLAlchemy database models for MedTwin Research Framework.
Implements the entity-relationship schema defined in Section IX (Fig. 5) of the IEEE manuscript.
"""

from datetime import datetime, timezone
import enum
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SQLEnum, JSON, Index
)
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    PUBLIC = "public"
    ADMIN = "admin"
    CLINICIAN = "clinician"
    RESEARCHER = "researcher"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    SUSPENDED = "SUSPENDED"


class EvidenceStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    ERROR = "ERROR"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"
    UNASSOCIATED = "UNASSOCIATED"
    NOT_RUN = "NOT_RUN"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    MAPPING_UNSUPPORTED = "MAPPING_UNSUPPORTED"


class RepresentationLevel(str, enum.Enum):
    L1_GENERIC = "L1"
    L2_FINDING_ASSOCIATED = "L2"
    L3_PATIENT_SPECIFIC = "L3"


class ModalityType(str, enum.Enum):
    IMAGE = "IMAGE"
    ECG = "ECG"
    REPORT = "REPORT"
    MULTIMODAL = "MULTIMODAL"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    full_name = Column(String(128), nullable=True)
    role = Column(SQLEnum(UserRole), default=UserRole.PUBLIC, nullable=False)
    verification_status = Column(
        SQLEnum(VerificationStatus),
        default=VerificationStatus.UNVERIFIED,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    cases = relationship("Case", back_populates="creator")
    reviews = relationship("HumanReview", back_populates="reviewer")
    audit_events = relationship("AuditEvent", back_populates="user")


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    pseudonymous_id = Column(String(64), unique=True, index=True, nullable=False)
    patient_ref = Column(String(128), nullable=True) # Pseudonymized reference, no PHI
    description = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    creator = relationship("User", back_populates="cases")
    examinations = relationship("Examination", back_populates="case", cascade="all, delete-orphan")
    files = relationship("UploadedFile", back_populates="case", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="case", cascade="all, delete-orphan")
    fusion_records = relationship("MultimodalFusionRecord", back_populates="case", cascade="all, delete-orphan")
    concordance_records = relationship("ConcordanceRecord", back_populates="case", cascade="all, delete-orphan")
    forecast_records = relationship("ForecastRecord", back_populates="case", cascade="all, delete-orphan")
    ordered_packages = relationship("OrderedPackage", back_populates="case", cascade="all, delete-orphan")
    lab_reports = relationship("LabInvestigationReport", back_populates="case", cascade="all, delete-orphan")
    measurements = relationship("MedicalMeasurement", back_populates="case", cascade="all, delete-orphan")


class Examination(Base):
    __tablename__ = "examinations"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_date = Column(DateTime, nullable=False, index=True)
    modality = Column(SQLEnum(ModalityType), nullable=False)
    clinical_indication = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="examinations")
    files = relationship("UploadedFile", back_populates="examination")
    measurements = relationship("MedicalMeasurement", back_populates="examination")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    examination_id = Column(Integer, ForeignKey("examinations.id", ondelete="SET NULL"), nullable=True, index=True)
    filename = Column(String(256), nullable=False)
    stored_filename = Column(String(256), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True) # SHA-256 for idempotency & integrity
    file_size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String(64), nullable=False)
    modality = Column(SQLEnum(ModalityType), nullable=False)
    is_associated = Column(Boolean, default=True, nullable=False)
    association_notes = Column(String(256), nullable=True)
    # Versioning and withdrawal change metadata only; stored bytes are never altered or erased
    # here (permanent erasure is the case retention workflow).
    version_number = Column(Integer, default=1, nullable=False)
    supersedes_file_id = Column(Integer, ForeignKey("uploaded_files.id", ondelete="SET NULL"), nullable=True)
    superseded_by_file_id = Column(Integer, ForeignKey("uploaded_files.id", ondelete="SET NULL"), nullable=True)
    withdrawn_at = Column(DateTime, nullable=True)
    withdrawn_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    withdrawal_reason = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="files")
    examination = relationship("Examination", back_populates="files")
    inference_runs = relationship("InferenceRun", back_populates="file", cascade="all, delete-orphan")
    measurements = relationship("MedicalMeasurement", back_populates="source_file", cascade="all, delete-orphan")


class InferenceRun(Base):
    __tablename__ = "inference_runs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, index=True)
    modality = Column(SQLEnum(ModalityType), nullable=False)
    model_name = Column(String(128), nullable=False)
    model_version = Column(String(64), nullable=False)
    preprocessing_version = Column(String(64), nullable=False)
    status = Column(SQLEnum(EvidenceStatus), default=EvidenceStatus.PENDING_HUMAN_REVIEW, nullable=False)
    execution_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=utc_now, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    file = relationship("UploadedFile", back_populates="inference_runs")
    findings = relationship("Finding", back_populates="inference_run", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)
    inference_run_id = Column(Integer, ForeignKey("inference_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    modality = Column(SQLEnum(ModalityType), nullable=False)
    category = Column(String(128), nullable=False) # e.g. Musculoskeletal Radiograph, Cardiac Rhythm, Clinical Impression
    label = Column(String(128), nullable=False) # e.g. Fracture, Normal, Arrhythmia, Cardiomegaly
    raw_confidence = Column(Float, nullable=True)
    calibrated_confidence = Column(Float, nullable=True)
    calibration_status = Column(String(32), default="UNCALIBRATED", nullable=False)
    visual_explanation_path = Column(String(512), nullable=True) # Grad-CAM explanation path
    explanation_type = Column(String(64), nullable=True) # e.g. "Grad-CAM (Visual Explanation Only; Not 3D Localization)"
    representation_level = Column(SQLEnum(RepresentationLevel), default=RepresentationLevel.L1_GENERIC, nullable=False)
    anatomical_region = Column(String(128), nullable=True) # Null unless passed L2 gate
    mapping_status = Column(String(256), nullable=False)
    tre_score = Column(Float, nullable=True)
    tre_threshold = Column(Float, nullable=True)
    evidence_provenance = Column(JSON, nullable=True)
    review_status = Column(SQLEnum(EvidenceStatus), default=EvidenceStatus.PENDING_HUMAN_REVIEW, nullable=False)
    failure_reason = Column(String(256), nullable=True)
    is_demo = Column(Boolean, default=True, nullable=False) # Explicit demo / research flag
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="findings")
    inference_run = relationship("InferenceRun", back_populates="findings")
    report_statements = relationship("ClinicalReportStatement", back_populates="finding", cascade="all, delete-orphan")
    reviews = relationship("HumanReview", back_populates="finding", cascade="all, delete-orphan")
    anatomical_mapping = relationship("AnatomicalMapping", back_populates="finding", uselist=False, cascade="all, delete-orphan")
    measurements = relationship("MedicalMeasurement", back_populates="finding", cascade="all, delete-orphan")


class ClinicalReportStatement(Base):
    __tablename__ = "clinical_report_statements"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(Integer, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    entity = Column(String(128), nullable=False) # Extracted finding/entity
    negation = Column(String(32), nullable=False) # "AFFIRMED" or "NEGATED"
    temporality = Column(String(32), nullable=False) # "CURRENT" or "HISTORICAL"
    source_span = Column(String(256), nullable=False) # Exact text excerpt
    source_span_start = Column(Integer, nullable=True)
    source_span_end = Column(Integer, nullable=True)
    # Context attributes from the rules-v2 extractor (nullable for v1 rows).
    entity_text = Column(String(128), nullable=True) # Surface form in the source
    entity_start = Column(Integer, nullable=True)
    entity_end = Column(Integer, nullable=True)
    category = Column(String(32), nullable=True) # FINDING, CONDITION, PROCEDURE, MEDICATION, ...
    certainty = Column(String(32), nullable=True) # CERTAIN, UNCERTAIN, HYPOTHETICAL
    experiencer = Column(String(16), nullable=True) # PATIENT or FAMILY
    comparison = Column(String(32), nullable=True) # STABLE, INCREASED, DECREASED, NEW, RESOLVED, PERSISTENT
    section = Column(String(48), nullable=True)
    anatomical_site = Column(String(128), nullable=True) # Documented site text
    laterality = Column(String(8), nullable=True)
    anatomy_system = Column(String(32), nullable=True) # One of the ten studio systems
    atlas_structure_id = Column(String(160), nullable=True) # Lexical match to the atlas index
    cues = Column(JSON, nullable=True) # Cue type, text and offsets
    extractor_version = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    finding = relationship("Finding", back_populates="report_statements")


class MedicalMeasurement(Base):
    """A numeric value extracted from an exact source span; never an inferred value."""

    __tablename__ = "medical_measurements"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    examination_id = Column(Integer, ForeignKey("examinations.id", ondelete="SET NULL"), nullable=True, index=True)
    source_file_id = Column(Integer, ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id = Column(Integer, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    value = Column(Float, nullable=False)
    result_operator = Column(String(2), default="=", nullable=True) # =, <, >, <=, >= as documented
    unit = Column(String(32), nullable=False)
    raw_value = Column(String(64), nullable=False)
    raw_unit = Column(String(32), nullable=False)
    source_span = Column(String(256), nullable=False)
    source_span_start = Column(Integer, nullable=False)
    source_span_end = Column(Integer, nullable=False)
    extraction_method = Column(String(64), default="TRANSPARENT_RULE_BASELINE", nullable=False)
    review_status = Column(SQLEnum(EvidenceStatus), default=EvidenceStatus.PENDING_HUMAN_REVIEW, nullable=False)
    # Terminology, documented reference interval and context (nullable for v1 rows).
    canonical_code = Column(String(32), nullable=True)
    code_system = Column(String(64), nullable=True)
    code_mapping_status = Column(String(64), nullable=True)
    reference_low = Column(Float, nullable=True)
    reference_high = Column(Float, nullable=True)
    reference_text = Column(String(64), nullable=True)
    reference_source = Column(String(32), nullable=True) # DOCUMENTED_IN_SOURCE only
    documented_flag = Column(String(16), nullable=True) # Flag printed in the source, e.g. HIGH
    conversion_status = Column(String(48), nullable=True)
    documented_date = Column(String(10), nullable=True) # ISO date documented in the source
    anatomy_system = Column(String(32), nullable=True)
    association = Column(String(48), nullable=True)
    source_page = Column(Integer, nullable=True)
    source_bbox = Column(JSON, nullable=True) # [x1, y1, x2, y2] in rendered page pixels
    source_bbox_coordinate_space = Column(String(64), nullable=True)
    source_image_width = Column(Integer, nullable=True)
    source_image_height = Column(Integer, nullable=True)
    specimen = Column(String(64), nullable=True)
    laboratory_method = Column(String(128), nullable=True)
    laboratory_name = Column(String(128), nullable=True)
    reference_low_inclusive = Column(Boolean, nullable=True)
    reference_high_inclusive = Column(Boolean, nullable=True)
    reference_options = Column(JSON, nullable=True) # every printed stratum: label, bounds, sex, age band
    reference_selection = Column(String(48), nullable=True) # how one stratum was selected, or why none applies
    documented_category = Column(String(64), nullable=True) # band printed by the laboratory, e.g. "Fair Control"
    extractor_version = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="measurements")
    examination = relationship("Examination", back_populates="measurements")
    source_file = relationship("UploadedFile", back_populates="measurements")
    finding = relationship("Finding", back_populates="measurements")


class MultimodalFusionRecord(Base):
    __tablename__ = "multimodal_fusion_records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    modality_mask = Column(JSON, nullable=False) # e.g. {"IMAGE": 1, "ECG": 1, "REPORT": 0}
    active_modalities_count = Column(Integer, nullable=False)
    gated_weights = Column(JSON, nullable=True) # Normalized attention weights alpha_k
    fused_status = Column(SQLEnum(EvidenceStatus), nullable=False)
    fused_prediction = Column(JSON, nullable=True)
    paired_data_validated = Column(Boolean, default=False, nullable=False)
    abstention_reason = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="fusion_records")


class ConcordanceRecord(Base):
    __tablename__ = "concordance_records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_category = Column(String(128), nullable=False)
    report_statement_id = Column(Integer, ForeignKey("clinical_report_statements.id", ondelete="SET NULL"), nullable=True)
    model_finding_id = Column(Integer, ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    report_entity = Column(String(128), nullable=False)
    report_status = Column(String(32), nullable=False) # e.g. "AFFIRMED", "NEGATED"
    model_label = Column(String(128), nullable=False)
    is_discordant = Column(Boolean, nullable=False)
    review_flag = Column(String(64), nullable=False) # "CONCORDANT", "REVIEW_DISCORDANCE", "UNCOMPARABLE"
    notes = Column(Text, nullable=True)
    neither_source_overwritten = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="concordance_records")


class AnatomicalAsset(Base):
    __tablename__ = "anatomical_assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    system_name = Column(String(64), nullable=False) # e.g. "Musculoskeletal", "Cardiovascular", "Generic Reference"
    asset_path = Column(String(512), nullable=False)
    format = Column(String(16), default="glb", nullable=False)
    representation_level = Column(SQLEnum(RepresentationLevel), default=RepresentationLevel.L1_GENERIC, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    notes = Column(String(256), nullable=True)


class AnatomicalMapping(Base):
    __tablename__ = "anatomical_mappings"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(Integer, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, unique=True)
    coordinate_frame = Column(String(64), nullable=False)
    projection_metadata_valid = Column(Boolean, nullable=False)
    transform_matrix = Column(JSON, nullable=True) # 4x4 rigid registration matrix
    held_out_landmarks_count = Column(Integer, nullable=False)
    tre_error = Column(Float, nullable=True)
    tre_threshold = Column(Float, nullable=False)
    passed_gate = Column(Boolean, nullable=False)
    assigned_region = Column(String(128), nullable=True)
    mapping_status = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    finding = relationship("Finding", back_populates="anatomical_mapping")


class ForecastRecord(Base):
    __tablename__ = "forecast_records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    target_metric = Column(String(128), nullable=False) # e.g. "Joint Space Width", "Cardiothoracic Ratio"
    unit = Column(String(32), nullable=False) # e.g. "mm", "%"
    horizon_days = Column(Integer, nullable=False)
    observations_count = Column(Integer, nullable=False)
    predicted_value = Column(Float, nullable=True)
    baseline_persistence = Column(Float, nullable=True)
    baseline_linear = Column(Float, nullable=True)
    mae_estimate = Column(Float, nullable=True)
    rmse_estimate = Column(Float, nullable=True)
    eligibility_status = Column(SQLEnum(EvidenceStatus), nullable=False)
    ineligibility_reason = Column(String(256), nullable=True)
    notice = Column(String(256), default="EXPERIMENTAL ESTIMATE ONLY. NOT A MEDICAL PREDICTION.", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="forecast_records")


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(Integer, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_status = Column(String(32), nullable=False) # "CONFIRMED", "REJECTED", "MODIFIED", "REQUIRES_FURTHER_WORKUP"
    reviewer_comments = Column(Text, nullable=True)
    # Typed, size-bounded proposed corrections. The referenced source statement
    # or measurement remains immutable and this payload is never promoted to
    # ground truth automatically.
    correction_payload = Column(JSON, nullable=True)
    original_output_preserved = Column(Boolean, default=True, nullable=False)
    reviewed_at = Column(DateTime, default=utc_now, nullable=False)

    finding = relationship("Finding", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews")
    decision = relationship("CorrectionDecision", back_populates="review", uselist=False, cascade="all, delete-orphan")


class CorrectionDecision(Base):
    """A second, independent reviewer's decision on a proposed correction.

    Only an APPROVED decision makes a correction part of the effective (reviewed) view;
    the extracted statement or measurement row itself is never modified. One decision per
    proposal: a different correction needs a new proposal."""
    __tablename__ = "correction_decisions"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("human_reviews.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    decided_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision = Column(String(16), nullable=False) # APPROVED or REJECTED
    rationale = Column(Text, nullable=False)
    decided_at = Column(DateTime, default=utc_now, nullable=False)

    review = relationship("HumanReview", back_populates="decision")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(64), nullable=False) # e.g. "AUTH_LOGIN", "FILE_UPLOAD", "FUSION_EVALUATED", "CASE_ACCESS"
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=True)
    details = Column(JSON, nullable=True) # Sensitive text omitted; metadata only
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)

    user = relationship("User", back_populates="audit_events")


class OrderedPackage(Base):
    __tablename__ = "ordered_packages"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id = Column(String(64), nullable=False) # e.g. "PKG-GEN-01", "CT-KUB", "CARDIAC-CT-STRUCTURAL"
    package_name = Column(String(128), nullable=False)
    category = Column(String(64), nullable=False)
    status = Column(String(32), default="ORDERED", nullable=False) # "ORDERED", "IN_PROGRESS", "COMPLETED"
    ordered_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    clinical_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="ordered_packages")


class LabInvestigationReport(Base):
    __tablename__ = "lab_reports"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    lab_name = Column(String(128), nullable=False) # e.g. "Max Lab", "1mg Labs"
    report_title = Column(String(128), nullable=False) # e.g. "Wellwise Essential Profile (Hematology / CBC)"
    sample_type = Column(String(64), nullable=False) # "NOT_DOCUMENTED" when the report does not state it
    patient_name = Column(String(128), nullable=True)
    collection_time = Column(String(64), nullable=True)
    reporting_time = Column(String(64), nullable=True)
    clinical_summary = Column(Text, nullable=True)
    test_results_json = Column(JSON, nullable=False) # Complete biomarker list with values, units, ref intervals, flags
    created_at = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case", back_populates="lab_reports")


class DocumentedAttribute(Base):
    """A non-numeric or contextual value documented in a source (date, age, sex)."""

    __tablename__ = "documented_attributes"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    source_file_id = Column(Integer, ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id = Column(Integer, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False, index=True) # sampling_date, report_date, age_years, sex
    value_text = Column(String(64), nullable=True) # None when the raw text could not be parsed safely
    value_number = Column(Float, nullable=True)
    unit = Column(String(16), nullable=True)
    parse_status = Column(String(48), nullable=False)
    raw_text = Column(String(64), nullable=False)
    source_span = Column(String(256), nullable=False)
    source_span_start = Column(Integer, nullable=False)
    source_span_end = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class CaseMembership(Base):
    """Explicit case sharing. Creators and admins keep implicit access."""

    __tablename__ = "case_memberships"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(16), nullable=False) # VIEWER or EDITOR
    granted_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class AnatomyRegistrationReview(Base):
    """Reviewer decision on how an unregistered anatomy asset is placed in a shared frame."""

    __tablename__ = "anatomy_registration_reviews"

    id = Column(Integer, primary_key=True, index=True)
    layer_id = Column(String(96), nullable=False, index=True)
    variant_id = Column(String(96), nullable=False)
    target_frame = Column(String(96), nullable=False)
    method = Column(String(64), nullable=False)
    transform = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=True)
    decision = Column(String(48), nullable=False) # ACCEPTED_FOR_EDUCATIONAL_DISPLAY, REJECTED, NEEDS_LANDMARKS
    comments = Column(Text, nullable=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class PrognosisEvaluation(Base):
    """Every prognosis or scenario request and the machine-readable outcome returned."""

    __tablename__ = "prognosis_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    organ_system = Column(String(32), nullable=False)
    intervention_id = Column(String(64), nullable=True)
    horizon_days = Column(Integer, nullable=False)
    status = Column(String(48), nullable=False)
    result = Column(JSON, nullable=False)
    requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class EvaluationRun(Base):
    """A reproducible metric computation over uploaded held-out predictions."""

    __tablename__ = "evaluation_runs"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String(32), nullable=False) # classification, regression, segmentation, survival
    model_id = Column(String(96), nullable=True)
    dataset_label = Column(String(128), nullable=True)
    input_filename = Column(String(256), nullable=False)
    input_sha256 = Column(String(64), nullable=False, index=True)
    n_samples = Column(Integer, nullable=False)
    n_groups = Column(Integer, nullable=True)
    config = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class QueuedJob(Base):
    """A durable unit of background work (app/services/job_queue.py, app/worker.py).

    Status moves QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED. A running job
    holds a time-limited lease; a job whose worker dies is reclaimed when the lease
    expires, up to max_attempts. All state is in the database, so it survives
    restarts of both the API and the worker."""

    __tablename__ = "queued_jobs"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(48), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="QUEUED", index=True)
    resource = Column(String(8), nullable=False, default="CPU")  # CPU or GPU, for concurrency quotas
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    file_id = Column(Integer, ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=True, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(128), nullable=True, unique=True)
    requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    lease_owner = Column(String(96), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    not_before = Column(DateTime, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    progress = Column(Integer, nullable=False, default=0)
    message = Column(String(256), nullable=True)
    last_error = Column(Text, nullable=True)
    result_ref = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


# Ensure indexes for performance
Index("idx_queued_jobs_claim", QueuedJob.status, QueuedJob.id)
Index("idx_audit_timestamp", AuditEvent.timestamp)
Index("uq_case_membership", CaseMembership.case_id, CaseMembership.user_id, unique=True)
Index("idx_findings_case_modality", Finding.case_id, Finding.modality)
Index("idx_files_case_hash", UploadedFile.case_id, UploadedFile.file_hash)
Index("idx_measurements_case_name_exam", MedicalMeasurement.case_id, MedicalMeasurement.name, MedicalMeasurement.examination_id)
