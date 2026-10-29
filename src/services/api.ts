import type {
  HealthPackage,
  IeeeValidationResponse,
  ImagingServiceCategory,
  LabReportRecord,
  LabTestReference,
  LongitudinalComparisonResponse as LegacyLongitudinalComparisonResponse,
  OrderedPackageRecord,
  OrderStatus,
} from '../types/medtwin';

export type {
  HealthPackage,
  ImagingServiceCategory,
  LabReportRecord,
  LabTestReference,
  LabTestResult,
  OrderedPackageRecord,
  OrderStatus,
} from '../types/medtwin';

const TOKEN_STORAGE_KEY = 'medtwin_token';
const configuredOrigin = (import.meta.env.VITE_MEDTWIN_API_URL as string | undefined)
  ?.trim()
  .replace(/\/+$/, '');

/**
 * VITE_MEDTWIN_API_URL is an optional origin, for example
 * "https://medtwin.example.org". The versioned path is deliberately owned by
 * this client so frontend calls cannot drift between /api and /api/v1.
 */
export const API_V1_BASE = configuredOrigin ? `${configuredOrigin}/api/v1` : '/api/v1';

export type ResourceId = number | string;
export type UserRole = 'public' | 'admin' | 'clinician' | 'researcher';
export type VerificationStatus = 'UNVERIFIED' | 'PENDING' | 'VERIFIED' | 'SUSPENDED';
export type Modality = 'IMAGE' | 'ECG' | 'REPORT' | 'SIGNAL' | 'MULTIMODAL';

export interface SignalChannel {
  index: number;
  label: string;
  transducer: string;
  physical_dimension: string;
  physical_min: number;
  physical_max: number;
  prefiltering: string;
  samples_per_record: number;
  sampling_rate_hz: number;
}

export interface SignalHeader {
  upload_id: number;
  format: string;
  records: number;
  record_duration_s: number;
  duration_s: number;
  start: string | null;
  patient_identification_field: 'EMPTY' | 'ANONYMISED' | 'FILLED_NOT_SHOWN';
  recording_identification_field: 'EMPTY' | 'ANONYMISED' | 'FILLED_NOT_SHOWN';
  signals: SignalChannel[];
  annotations: Array<{ onset_s: number; duration_s: number | null; text: string }>;
  warnings: string[];
  model: string;
}

export interface SignalPreview {
  start_s: number;
  duration_s: number;
  recording_duration_s: number;
  reduction: string;
  channels: Array<{ index: number; label: string; unit: string; sampling_rate_hz: number; points: number; seconds_per_point: number | null;
    min: number[]; max: number[]; window_min: number | null; window_max: number | null }>;
}
export type EvidenceStatus =
  | 'COMPLETED'
  | 'PENDING_HUMAN_REVIEW'
  | 'ERROR'
  | 'REJECT'
  | 'ABSTAIN'
  | 'UNASSOCIATED'
  | 'NOT_RUN'
  | 'NOT_ELIGIBLE'
  | 'MAPPING_UNSUPPORTED';
export type RepresentationLevel = 'L1' | 'L2' | 'L3';

export interface AuthToken {
  access_token: string;
  token_type: 'bearer' | string;
  user_id: number;
  username: string;
  role: UserRole;
  verification_status: VerificationStatus;
}

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  verification_status: VerificationStatus;
  is_active: boolean;
  created_at: string;
}

export interface AuthenticatedSession extends AuthToken {
  user: User;
}

export interface RegisterUserInput {
  username: string;
  email: string;
  password: string;
  full_name?: string;
  requested_role: RequestedRole;
  requested_department?: RequestedDepartment;
  requested_department_other?: string;
}

export interface RegisterUserResult {
  user: User;
  profileRequestSaved: boolean;
}

export type RequestedRole =
  | 'standard_user'
  | 'patient'
  | 'medical_staff'
  | 'nurse'
  | 'lab_expert'
  | 'doctor'
  | 'surgeon'
  | 'department_expert'
  | 'researcher';

export type RequestedDepartment =
  | 'anesthesiology'
  | 'cardiology'
  | 'cardiothoracic_surgery'
  | 'dermatology'
  | 'emergency_medicine'
  | 'endocrinology'
  | 'family_medicine'
  | 'gastroenterology'
  | 'general_surgery'
  | 'hematology'
  | 'infectious_disease'
  | 'internal_medicine'
  | 'laboratory_medicine'
  | 'nephrology'
  | 'neurology'
  | 'neurosurgery'
  | 'obstetrics_gynecology'
  | 'oncology'
  | 'ophthalmology'
  | 'orthopedic_surgery'
  | 'otolaryngology'
  | 'pediatrics'
  | 'psychiatry'
  | 'pulmonology'
  | 'radiology'
  | 'rehabilitation_medicine'
  | 'urology'
  | 'other';

export interface Examination {
  id: number;
  case_id: number;
  exam_date: string;
  modality: Modality;
  clinical_indication: string | null;
  created_at: string;
}

export interface Case {
  id: number;
  pseudonymous_id: string;
  patient_ref: string | null;
  description: string | null;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
  examinations: Examination[];
}

export interface CreateCaseInput {
  pseudonymous_id: string;
  patient_ref?: string | null;
  description?: string | null;
  examinations?: CreateExaminationInput[];
}

export interface CreateExaminationInput {
  exam_date: string;
  modality: Exclude<Modality, 'MULTIMODAL'>;
  clinical_indication?: string | null;
}

export interface UploadedFile {
  id: number;
  case_id: number;
  examination_id: number | null;
  filename: string;
  file_hash: string;
  file_size_bytes: number;
  mime_type: string;
  modality: Exclude<Modality, 'MULTIMODAL'>;
  is_associated: boolean;
  association_notes: string | null;
  version_number?: number;
  supersedes_file_id?: number | null;
  superseded_by_file_id?: number | null;
  withdrawn_at?: string | null;
  withdrawal_reason?: string | null;
  created_at: string;
}

export interface UploadOptions {
  /** Explicit user attestation required by the backend ingestion gate. */
  deidentified: true;
  examinationId?: ResourceId;
  isAssociated?: boolean;
  associationNotes?: string;
}

export interface AnalysisJobFinding {
  id: number;
  modality: Modality;
  category: string;
  label: string;
  raw_confidence: number | null;
  calibrated_confidence: number | null;
  review_status: EvidenceStatus;
  failure_reason: string | null;
}

export interface AnalysisJob {
  id: number;
  case_id: number;
  upload_id: number;
  status: EvidenceStatus;
  modality: Modality;
  model_name: string;
  model_version: string;
  preprocessing_version: string;
  execution_time_ms: number | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  findings: AnalysisJobFinding[];
}

export type QueuedJobStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';

export interface QueuedJob {
  id: number;
  kind: string;
  status: QueuedJobStatus;
  resource: 'CPU' | 'GPU';
  case_id: number | null;
  file_id: number | null;
  attempts: number;
  max_attempts: number;
  progress: number | null;
  message: string | null;
  last_error: string | null;
  result_ref: { inference_run_id?: number; run_status?: string } | null;
  cancel_requested: boolean;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  execution_mode: 'inline' | 'worker';
}

export interface DetectionBox {
  bbox_xyxy: [number, number, number, number];
  score: number;
  above_display_threshold: boolean;
}

export type ResearchOutput =
  | {
      type: 'classification';
      classes: Array<{ class: string; probability: number }>;
      top_class: string;
      top_probability: number;
      probability_semantics: string;
    }
  | {
      type: 'detection';
      class: string;
      coordinate_space: string;
      image_size: [number, number];
      display_score_threshold: number;
      boxes: DetectionBox[];
      score_semantics: string;
    }
  | {
      type: 'segmentation';
      coordinate_space: string;
      image_size: [number, number];
      segments: Array<{ class_index: number; segment: string; area_px: number; rle: { size: [number, number]; counts: string } }>;
      vessel_area_px: number;
      foreground_label?: string;
      encoding: string;
    }
  | {
      type: 'ecg_multilabel';
      classes: Array<{ class: string; probability: number; threshold: number; at_or_above_threshold: boolean }>;
      positive_classes: string[];
      probability_semantics: string;
      threshold_semantics: string;
      numeric_precision: string;
      input: { format: string; sampling_rate_hz: number; samples: number; duration_s: number; leads: string[]; peak_abs_amplitude_mv: number; notes: string[]; processing: string };
    }
  | {
      type: 'volume_segmentation';
      structures: Array<{ class_index: number; structure: string; voxels: number; volume_ml: number }>;
      slices: Array<{ slice_index: number; segments: Array<{ class_index: number; area_px: number; rle: { size: [number, number]; counts: string } }> }>;
      volume_shape_ijk: [number, number, number];
      voxel_spacing_mm: [number, number, number];
      voxel_volume_ml: number;
      coordinate_space: string;
      encoding: string;
      numeric_precision: string;
      volume_semantics: string;
      held_out_volume_agreement: Record<string, { n_patients: number | null; bias_ml: number; limits_of_agreement_ml: [number, number] | null }>;
      input_warnings: string[];
    };

/** Inputs some research models need besides the upload itself. */
export interface ResearchRunOptions {
  /** WFDB signal file (.dat) uploaded alongside a .hea header. */
  companionUploadId?: ResourceId;
  /** CSV ECG records carry no amplitude unit. */
  amplitudeUnit?: 'mV' | 'uV';
}

export interface ResearchRun extends AnalysisJob {
  research_output: ResearchOutput | null;
  research_provenance: Record<string, unknown>;
}

export interface ResearchModel {
  model_id: string;
  display_name: string;
  task: 'image_classification' | 'object_detection' | 'semantic_segmentation' | 'multilabel_ecg_classification' | 'survival_prediction' | 'volumetric_semantic_segmentation';
  anatomy: string | null;
  supported_modalities: string[];
  supported_classes: string[];
  status: string;
  validated: boolean;
  gate: { allowed: boolean; blockers: string[] };
  inference_input?: 'image_2d' | 'ecg_12lead' | 'tabular_survival' | 'volume_nifti';
  run_scope?: 'RESEARCH' | 'EXPLORATORY_ONLY';
  dataset_license: string | null;
  model_card_path: string | null;
  evaluation_report_path: string | null;
  checkpoint_sha256: string | null;
  output_status: string;
  held_out_evaluation?: Record<string, unknown>;
}

export interface ResearchModelListing {
  notice: string;
  input_types: Record<string, string>;
  models: ResearchModel[];
}

export interface StatementCue {
  type: string;
  text: string;
  start: number | null;
  end: number | null;
}

export interface ReportStatement {
  id: string;
  case_id: string;
  finding_id: string;
  source_file_id: string | null;
  entity: string;
  entity_text: string;
  entity_start: number | null;
  entity_end: number | null;
  category: string | null;
  negation: string;
  is_negated: boolean;
  certainty: string;
  temporality: string;
  experiencer: string;
  comparison: string | null;
  section: string | null;
  anatomical_site: string | null;
  laterality: string | null;
  anatomy_system: string | null;
  atlas_structure_id: string | null;
  cues: StatementCue[];
  source_span: string;
  source_span_start: number | null;
  source_span_end: number | null;
  char_start: number;
  char_end: number;
  confidence: null;
  extraction_method: 'TRANSPARENT_RULE_BASELINE';
  extractor_version: string;
  created_at: string;
}

/** "~" marks a value the report prints as approximate; it is never treated as exact. */
export type ResultOperator = '=' | '<' | '>' | '<=' | '>=' | '~';

export interface MedicalMeasurement {
  id: number;
  case_id: number;
  examination_id: number | null;
  source_file_id: number;
  finding_id: number;
  name: string;
  display_name: string;
  value: number;
  result_operator: ResultOperator;
  unit: string;
  raw_value: string;
  raw_unit: string;
  source_span: string;
  source_span_start: number;
  source_span_end: number;
  source_page: number | null;
  source_bbox: [number, number, number, number] | null;
  source_bbox_coordinate_space: string | null;
  source_image_width: number | null;
  source_image_height: number | null;
  extraction_method: string;
  review_status: EvidenceStatus;
  canonical_code: string | null;
  code_system: string | null;
  code_mapping_status: string | null;
  reference_low: number | null;
  reference_high: number | null;
  reference_low_inclusive: boolean | null;
  reference_high_inclusive: boolean | null;
  reference_text: string | null;
  reference_source: string | null;
  documented_flag: string | null;
  /** Every stratum printed in the reference column; one is selected only from documented sex/age. */
  reference_options?: ReferenceOption[];
  reference_selection?: string | null;
  /** Category band printed by the laboratory that contains the value, e.g. "Fair Control". */
  documented_category?: string | null;
  /** Set when this row reprints an earlier occurrence of the same measurement. */
  duplicate_of_measurement_id?: number | null;
  source_occurrences?: { measurement_id: number; source_file_id: number; source_page: number | null }[];
  documented_range_position: string;
  conversion_status: string;
  documented_date: string | null;
  anatomy_system: string | null;
  association: string | null;
  specimen: string;
  laboratory_method: string;
  laboratory_name: string;
  extractor_version: string | null;
  source_hash: string | null;
  extraction_uncertainty: string;
  created_at: string;
}

export interface ReferenceOption {
  label: string | null;
  text: string;
  low: number | null;
  high: number | null;
  low_inclusive: boolean | null;
  high_inclusive: boolean | null;
  sex: string | null;
  pregnancy: boolean;
  category_band: boolean;
  age_years: [number, number | null] | null;
}

export interface DocumentedAttribute {
  id: number;
  source_file_id: number;
  finding_id: number;
  name: string;
  value_text: string | null;
  value_number: number | null;
  unit: string | null;
  parse_status: string;
  raw_text: string;
  source_span: string;
  source_span_start: number;
  source_span_end: number;
  created_at: string;
}

export type ObservationSource = "DOCUMENT_EXTRACTION" | "MANUAL_TRANSCRIPTION";

export interface TrendPoint {
  observation_id: string;
  source_type: ObservationSource;
  /** Set for document-extracted points. */
  measurement_id: number | null;
  /** Set for clinician-transcribed laboratory results. */
  lab_report_id: number | null;
  date: string;
  date_source: string;
  value: number;
  documented_value: number;
  result_operator: '=' | '<' | '>' | '<=' | '>=';
  documented_unit: string;
  unit_converted: boolean;
  source_file_id: number | null;
  examination_id: number | null;
  source_span: string;
  reference_low: number | null;
  reference_high: number | null;
  documented_flag: string | null;
  specimen: string;
  laboratory_method: string;
}

export interface TrendStatistic {
  status: string;
  slope_per_year?: number;
  slope_95ci_per_year?: [number, number];
  r_squared?: number;
  p_value_slope_zero?: number;
  p_value_two_sided?: number;
  kendall_tau?: number;
  assumptions?: string;
  required?: number;
}

export interface TrendAnalysis {
  status: string;
  n: number;
  distinct_dates: number;
  reason?: string;
  first?: { date: string; value: number };
  last?: { date: string; value: number };
  absolute_change?: number;
  percent_change?: number | null;
  percent_change_status?: string;
  interval_days?: number;
  rate_per_day?: number | null;
  rate_per_year?: number | null;
  ols?: TrendStatistic;
  theil_sen?: TrendStatistic;
  mann_kendall?: TrendStatistic;
  interpretation: null;
}

export interface BiomarkerSeries {
  name: string;
  display_name: string;
  unit: string;
  anatomy_system: string | null;
  association: string | null;
  canonical_code: string | null;
  source_types: ObservationSource[];
  points: TrendPoint[];
  excluded: Array<{ observation_id: string; measurement_id: number | null; lab_report_id: number | null; reason: string }>;
  conversions: string[];
  conversion_source: string | null;
  identity_review_required: boolean;
  comparability_blockers: string[];
  analysis: TrendAnalysis;
}

export interface EgfrResult {
  creatinine_measurement_id: number;
  source_file_id: number;
  documented_creatinine: { value: number; unit: string; source_span: string };
  documented_date: string | null;
  status: string;
  value: number | null;
  unit?: string;
  missing_or_invalid_inputs?: string[];
  inputs?: { creatinine_mg_dl: number; age_years: number; sex: string; age_source: { source_file_id: number; source_span: string; same_source_as_creatinine: boolean } };
}

export interface EgfrResponse {
  equation: { equation_id: string; display: string; citation: string; unit: string; population: string; caveats: string[] };
  status: string;
  results: EgfrResult[];
  notice: string;
}

export type MappingCategory = 'SPATIALLY_REGISTERED' | 'VERIFIED_ANATOMICAL_REGION' | 'SCHEMATIC_ORGAN_ASSOCIATION' | 'UNSUPPORTED_MAPPING';
export type MappingState = 'SPATIALLY_REGISTERED' | 'REGION_VERIFIED' | 'SCHEMATIC_ORGAN_ONLY' | 'NOT_MAPPABLE';

export interface AnatomyEvidenceItem {
  kind: 'REPORT_STATEMENT' | 'MEASUREMENT' | 'IMAGING_STUDY' | 'MODEL_FINDING';
  id: number;
  source_file_id: number | null;
  label: string;
  system: string | null;
  mapping_state: MappingState;
  /** Transitional alias retained for older API clients. */
  mapping_category: MappingCategory;
  reason: string;
  atlas_structure_id: string | null;
  candidate_atlas_structure_id?: string | null;
  candidate_atlas_structure_ids?: string[];
  assertion?: string;
  certainty?: string;
  temporality?: string;
  comparison?: string | null;
  documented_region?: string | null;
  review_status?: string;
  source_span?: string;
  value?: number;
  unit?: string;
  documented_date?: string | null;
  documented_flag?: string | null;
  association?: string | null;
  body_part?: string | null;
  container?: string | null;
  source_hash?: string | null;
  extractor_version?: string | null;
  clinician_confirmation?: { review_id: number; reviewer_id: number | null; scope: 'FINDING_LEVEL'; status: string; reviewed_at: string | null; original_output_preserved: boolean } | null;
  evidence_status?: string | null;
  model_id?: string | null;
  checkpoint_sha256?: string | null;
  dataset_version?: string | null;
  evaluation_report_path?: string | null;
  output_type?: string | null;
  source_coordinate_space?: string | null;
}

export interface AnatomySystemEvidence {
  system_id: string;
  label: string;
  items: AnatomyEvidenceItem[];
  counts: Record<MappingCategory, number>;
  state_counts: Record<MappingState, number>;
  highlight: { organ_schematic: boolean; verified_structures: string[]; spatially_registered: string[]; documented_structures?: string[] };
}

export interface AnatomyEvidenceResponse {
  case_id: number;
  mapping_states: MappingState[];
  mapping_categories: MappingCategory[];
  spatial_registration: { status: string; reason: string };
  systems: Record<string, AnatomySystemEvidence>;
  unsupported: AnatomyEvidenceItem[];
  excluded: Array<{ kind: string; id: number; label: string; reason: string }>;
}

export interface ModalityFormat {
  format: string;
  library: string | null;
  available: boolean;
  extensions: string[];
  upload_accepted: boolean;
  note?: string;
}

export interface ModalityEntry {
  id: string;
  label: string;
  group: string;
  dicom_modality_codes: string[];
  supported_file_formats: ModalityFormat[];
  file_support_status: string;
  supported_preprocessing: string[];
  available_ai_models: Array<{ model_id: string; display_name: string; status: string; activation_eligible: boolean; research_inference?: boolean }>;
  validated_tasks: string[];
  unsupported_tasks: Array<{ task: string; status: string }>;
  extraction_status: string | null;
  notes: string[];
}

export interface ModalityRegistryResponse {
  schema_version: string;
  notice: string;
  modalities: ModalityEntry[];
}

export interface ImagingMetadata {
  upload_id: number;
  filename: string;
  sha256: string;
  container: string;
  dimensions: Array<number | null>;
  slices: number;
  spacing_mm: number[] | null;
  spatial_metadata: string;
  modality_tag: string | null;
  body_part: string | null;
  body_part_systems?: string[];
  orientation?: string;
  technical_tags?: Record<string, unknown>;
  deidentification_warnings: string[];
  inference: { status: string; detections: unknown[]; segmentations: unknown[]; reason: string };
  [key: string]: unknown;
}

/** PATIENT and CAREGIVER open only the read-only portal of a personal account. */
export type CaseMemberRole = 'VIEWER' | 'EDITOR' | 'PATIENT' | 'CAREGIVER';

export interface PortalCase {
  case_id: number;
  record: string;
  relationship: 'PATIENT' | 'CAREGIVER';
}

export interface PortalRecord {
  case_id: number;
  relationship: 'PATIENT' | 'CAREGIVER';
  notice: string;
  documents: Array<{ id: number; filename: string; kind: string; size_bytes: number | null; uploaded_at: string | null }>;
  results: Array<{ name: string; value: number; comparator: string; unit: string; reference_low: number | null; reference_high: number | null;
    reference_source: string; documented_flag: string | null; documented_date: string | null; source_document_id: number | null; corrected_by_review: boolean }>;
}

export interface DicomSeriesReport {
  status: 'ASSEMBLED' | 'REJECTED';
  issues: string[];
  warnings: string[];
  series: Array<{ series_reference: string; slice_count: number }>;
  series_reference?: string | null;
  shape_slices_rows_columns?: [number, number, number];
  spacing_mm?: { row: number; column: number; slice: number };
  ordered_upload_ids?: number[];
  identifying_tags_present?: string[];
  slice_steps_mm?: number[];
}

export interface SeriesRenderInfo {
  axis: 'axial' | 'coronal' | 'sagittal';
  index: number;
  count: number;
  shape: [number, number];
  pixel_spacing_mm: { vertical: number; horizontal: number };
  window: { low: number; high: number; source: string };
  plane: string;
  warnings: string[];
}

export interface RenderInfo {
  container: string;
  slice_index: number;
  slice_count: number;
  axis?: string;
  window: { low: number; high: number; source: string };
  display_dimensions: [number, number];
  pixel_spacing_mm?: number[] | null;
  spacing_xyz_mm?: Array<number | null>;
  rescale?: { slope: number; intercept: number; units: string };
  display_to_source: string;
  plane_definition?: string;
}

export interface ReportPageType {
  document_type: 'LABORATORY_REPORT' | 'IMAGING_REPORT' | 'PROCEDURE_REPORT' | 'PATHOLOGY_REPORT' | 'DISCHARGE_SUMMARY' | 'CONSULTATION_NOTE' | 'PRESCRIPTION' | 'BILLING' | 'UNCLASSIFIED';
  imaging_modality: string | null;
  cues: string[];
  scores: Record<string, number>;
  method: string;
  validation_status: string;
  /** The page continues the numbered page (it ended "P.T.O") and took its type. */
  continued_from_page?: number;
}

export interface ReportPageLine {
  text_start: number;
  text_end: number;
  confidence: number | null;
  bbox_xyxy: [number, number, number, number];
  identifiers_masked: boolean;
}

export interface ReportPage {
  page: number;
  method: string;
  engine?: string;
  mean_confidence?: number | null;
  line_count?: number;
  image_width?: number;
  image_height?: number;
  rotation_degrees?: number;
  lines?: ReportPageLine[];
  identifiers_masked?: Record<string, number>;
  document_type?: ReportPageType;
}

export interface ReportTextResponse {
  upload_id: number;
  filename: string;
  source_sha256: string;
  text: string;
  text_sha256: string;
  page_starts: number[];
  pages?: ReportPage[];
  extractor_version: string;
  privacy_screen?: { status: string; identifiers_masked: Record<string, number>; pages_with_identifiers: number[]; verification: string; notice: string };
  date_conflicts?: Array<{ page: number; dates: string[] }>;
}

/** Output of the third-party chest-radiograph research model (backend app.services.cxr_research). */
export interface ChestRadiographOutput {
  type: 'chest_radiograph_findings';
  coordinate_space: 'SOURCE_IMAGE_PIXELS';
  image_size: [number, number];
  /** The centre square the models read: left, top, side (source pixels). */
  analysis_square: [number, number, number];
  operating_point: number;
  weak_margin: number;
  findings: Array<{ finding: string; score: number; above_operating_point: boolean; weak: boolean }>;
  attention: Array<{ finding: string; zones: Record<string, number>; outside_lungs: number; top_zone: string | null; grid: number[][] }>;
  anatomy: Array<{ name: string; fraction: number; contours: number[][][] }>;
  input_checks: {
    status: string; right_lung_fraction: number; left_lung_fraction: number; heart_fraction: number; lungs_on_expected_sides: boolean;
    autoencoder_reconstruction_error: number; autoencoder_note: string; rule: string;
    printed_document?: { printed_text_lines: number | null; document_text_line_limit: number; status: string } | null;
  };
  report_comparison: Array<{ finding: string; score: number; report_status: 'AFFIRMED' | 'NEGATED'; status: 'AGREES' | 'DIFFERS' | 'MODEL_INDETERMINATE'; report_entities: string[]; report_quote: string; report_statement_ids: number[] }>;
  summary: string;
}

export interface ChestRadiographModelCard {
  model_id: string;
  display_name: string;
  output_status: string;
  available: boolean;
  status: string;
  reason?: string;
  publisher: { library: string; citation: string; training_data: string; anatomy_model: string; local_evaluation: string };
  operating_point: number;
  weak_margin: number;
  weights_sha256: Record<string, string>;
}

/** A report page rendered for side-by-side checking, with its identifier lines painted out. */
export interface ReportPageImage {
  url: string;
  page: number;
  width: number;
  height: number;
  masking: 'APPLIED' | 'NO_IDENTIFIER_LINES' | 'UNAVAILABLE_EMBEDDED_TEXT';
  masked_lines: number;
  source_image_width: number | null;
  source_image_height: number | null;
}

export interface PrognosisCapability {
  organ_system: string;
  label: string;
  outcome_variables: Array<{ name: string; type: string }>;
  suitable_data: string;
  candidate_models: string[];
  trained_model_status: string;
  model_validation_status: string;
  applicable_population: string | null;
  required_inputs: string[];
  forecast_horizon: string | null;
  uncertainty_method: string | null;
  treatment_comparison: { status: string; reason: string };
  forecast_2d: { status: string; reason: string };
  forecast_3d: { status: string; reason: string };
  observed_analytes: string[];
  workspace_data_status: string;
  interventions: Array<{ id: string; label: string }>;
}

export interface PrognosisCapabilitiesResponse {
  schema_version: string;
  target_trial_fields: Array<{ id: string; label: string }>;
  status_vocabulary: string[];
  capabilities: PrognosisCapability[];
  notice: string;
}

export interface ScenarioBlock {
  label: string;
  status: string;
  reason_codes: string[];
  forecast: null;
  uncertainty: null;
  forecast_2d: { status: string; reason: string };
  forecast_3d: { status: string; reason: string };
}

export interface PrognosisEvaluation {
  status: string;
  case_id: number;
  organ_system: string;
  horizon_days: number;
  intervention_id: string | null;
  capability: PrognosisCapability;
  observed: {
    status: string;
    biomarker_series: BiomarkerSeries[];
    imaging_studies: Array<{ upload_id: number; filename: string; examination_id: number | null; date: string | null; status: string }>;
  };
  scenarios: { A: ScenarioBlock; B: ScenarioBlock };
  treatment_effect: { status: string; reason_codes: string[]; target_trial_specification: Record<string, null>; estimate: null };
  guideline_information: { status: string; reason: string };
  notice: string;
  evaluation_id: number;
  evaluated_at: string;
}

export interface RiskRegistryResponse {
  schema_version: string;
  models: Array<{
    organ_system: string;
    instrument: string;
    risk_target: string;
    risk_horizon: string | null;
    required_inputs: string[];
    derivation_population: string;
    calibration_status: string;
    validation_status: string;
    status: string;
    blockers: string[];
    output: null;
  }>;
  explainability_methods: Array<{ method: string; applies_to: string; status: string; limits: string }>;
  explanation_provenance_fields: string[];
  distinctions: Array<{ term: string; meaning: string }>;
  notice: string;
}

export interface ChartProvenance {
  source: string;
  sample_count: number | null;
  sample_count_semantics: string;
  analysis_population: string;
  time_frame: string | null;
  model_version: string | null;
  metric_definition: string;
  limitations: string[];
}

export interface AnalyticsChart {
  id: string;
  title: string;
  status: string;
  data: Array<Record<string, unknown>>;
  provenance: ChartProvenance;
}

export interface ResearchAnalyticsResponse {
  schema_version: string;
  sections: Record<'datasets' | 'software' | 'anatomy' | 'models' | 'cases', AnalyticsChart[]>;
  unavailable_by_design: Array<{ chart: string; reason: string }>;
  test_evidence: Record<string, unknown>;
}

export type EvaluationTask = 'classification' | 'multiclass' | 'regression' | 'survival' | 'forecast' | 'lab_extraction';
export type EvaluationSplit = 'test' | 'external_test' | 'validation' | 'development';

/** The validation kit's binding of a score to its dataset, split and frozen checkpoint. */
export interface EvaluationContextInput {
  modelId?: string;
  /** Stable datasets[].id from dataset_registry/tasks.json. */
  datasetId?: string;
  /** @deprecated Use datasetId. Retained for API compatibility. */
  datasetLabel?: string;
  datasetVersion?: string;
  split?: EvaluationSplit;
  checkpoint?: string;
}

export interface EvaluationContext {
  model_id: string | null;
  dataset: string | null;
  dataset_version: string | null;
  split: EvaluationSplit | null;
  checkpoint: string | null;
  evaluation_input_sha256: string | null;
  evaluation_input_digest_scheme: string | null;
  reporting_status: 'ELIGIBLE_FOR_REPORTING' | 'EXPLORATORY';
  reporting_blockers: string[];
  reporting_scope?: 'RESEARCH_EVIDENCE_ONLY_NOT_CLINICAL_ACTIVATION';
  registry_resolution?: {
    model_id: string | null;
    checkpoint_sha256: string | null;
    checkpoint_artifact_verified: boolean;
    evaluation_input_sha256: string | null;
    evaluation_input_artifact_verified: boolean;
    evaluation_input_format: string | null;
    evaluation_input_digest_scheme: string | null;
    dataset_id: string | null;
    dataset_version: string | null;
    task_id: string | null;
    task_type: string | null;
    split: EvaluationSplit | null;
    split_n: number | null;
    exact_match: boolean;
  };
  code_revision?: { commit: string | null; source: string; working_tree_clean: boolean | null };
  reproducibility_warnings?: string[];
}

export type PixelSpacing = { x: number; y: number; unit: string };

function evaluationForm(context: EvaluationContextInput, spacing?: PixelSpacing): FormData {
  const form = new FormData();
  const fields: Array<[string, string | undefined]> = [
    ['model_id', context.modelId], ['dataset_label', context.datasetId ?? context.datasetLabel], ['dataset_version', context.datasetVersion],
    ['split', context.split], ['checkpoint', context.checkpoint],
  ];
  for (const [name, value] of fields) if (value?.trim()) form.append(name, value.trim());
  if (spacing) {
    form.append('spacing_x', String(spacing.x));
    form.append('spacing_y', String(spacing.y));
    form.append('unit', spacing.unit);
  }
  return form;
}

export interface EvaluationResult {
  run_id: number;
  input_sha256: string;
  created_at: string;
  task_type: string;
  n: number;
  n_groups?: number | null;
  metrics: Record<string, number | null | undefined>;
  confidence_intervals_95?: Record<string, unknown>;
  confusion_matrix?: Record<string, number> | number[][];
  curves?: { roc: Array<{ fpr: number; tpr: number; threshold: number | null }>; pr: Array<{ recall: number; precision: number; threshold: number }> };
  calibration?: { bins?: Array<{ bin_low: number; bin_high: number; count: number; mean_predicted: number; observed_fraction: number }>; expected_calibration_error?: number; status?: string };
  evaluation_context?: EvaluationContext;
  [key: string]: unknown;
}

export interface EvaluationRunSummary {
  run_id: number;
  task_type: string;
  model_id: string | null;
  dataset_label: string | null;
  input_filename: string;
  input_sha256: string;
  n_samples: number;
  created_at: string;
  reporting_status: EvaluationContext['reporting_status'];
  metrics: Record<string, number | null> | null;
}

export interface TraceabilityClaim {
  id: string;
  section: string;
  claim: string;
  module: string;
  status: 'IMPLEMENTED_AND_TESTED' | 'IMPLEMENTED_NOT_VALIDATED' | 'PARTIALLY_IMPLEMENTED' | 'PROPOSED_ONLY' | 'UNSUPPORTED';
  evidence: string[];
  gap: string | null;
}

export interface TraceabilityResponse {
  status?: string;
  schema_version?: string;
  manuscript?: string;
  generated_at?: string;
  claims: TraceabilityClaim[];
  status_counts?: Record<string, number>;
}

export interface ReadinessResponse {
  ready: boolean;
  checks: Record<string, { ready: boolean; [key: string]: unknown }>;
}

export interface GpuTelemetry {
  cuda_available: boolean;
  torch_version: string;
  cuda_build: string | null;
  host_memory: { total_bytes: number; available_bytes: number; process_rss_bytes: number };
  loaded_models: string[];
  inference_concurrency_limit: number;
  device?: { name: string; capability: number[]; memory_total_bytes: number; memory_free_bytes: number; memory_allocated_by_process_bytes: number };
}

export interface FusionRecord {
  id?: number | null;
  case_id: number;
  modality_mask: Record<string, number>;
  active_modalities_count: number;
  gated_weights: Record<string, number> | null;
  fused_status: string;
  fused_prediction: Record<string, unknown> | null;
  paired_data_validated: boolean;
  abstention_reason: string | null;
  notice: string;
}

export interface ConcordanceSummary {
  case_id: number;
  total_comparisons: number;
  discordant_count: number;
  items: Array<{ finding_category: string; report_entity: string; report_status: string; model_label: string; is_discordant: boolean; review_flag: string; notes: string | null }>;
  notice: string;
}

export interface CaseMember {
  user_id: number;
  username: string;
  full_name: string | null;
  role: CaseMemberRole;
  created_at: string;
}

export interface LongitudinalSourceSnapshot {
  measurement_id: number;
  value: number;
  source_file_id: number;
  source_span: string;
}

export interface LongitudinalNumericDelta {
  name: string;
  display_name: string;
  unit: string;
  prior: LongitudinalSourceSnapshot;
  current: LongitudinalSourceSnapshot;
  absolute_delta: number;
  percent_change: number | null;
  interpretation: null;
  review_status: EvidenceStatus;
}

export interface LongitudinalStatementSnapshot {
  statement_id: number;
  assertion: string;
  temporality: string;
  certainty: string | null;
  comparison: string | null;
  source_span: string;
  source_file_id: number;
}

export interface LongitudinalStatementIdentity {
  entity: string;
  category: string | null;
  anatomical_site: string | null;
  laterality: string | null;
  anatomy_system: string | null;
  atlas_structure_id: string | null;
  experiencer: string | null;
  section: string | null;
}

export interface LongitudinalComparisonResponse {
  status: string;
  reason: string;
  case_id: number;
  case_pseudonym?: string;
  examinations_count?: number;
  prior_examination?: {
    id: number;
    date: string;
    modality: Modality;
  };
  current_examination?: {
    id: number;
    date: string;
    modality: Modality;
  };
  interval_days?: number;
  numeric_deltas?: LongitudinalNumericDelta[];
  numeric_comparison_blockers?: Array<{
    name: string;
    unit: string;
    prior_measurement_ids: number[];
    current_measurement_ids: number[];
    reason: string;
    prior?: string;
    current?: string;
  }>;
  semantic_report_diff?: Array<{
    entity: string;
    identity: LongitudinalStatementIdentity;
    change_type: string;
    prior: LongitudinalStatementSnapshot | null;
    current: LongitudinalStatementSnapshot | null;
    interpretation: null;
  }>;
  semantic_comparison_blockers?: Array<{
    entity: string;
    identity: LongitudinalStatementIdentity;
    reason: string;
    prior: LongitudinalStatementSnapshot[];
    current: LongitudinalStatementSnapshot[];
  }>;
  image_comparison?: {
    status: string;
    is_comparable: boolean;
    prior_associated_image_count: number;
    current_associated_image_count: number;
    reason: string;
  };
  twin_state_delta?: {
    status: string;
    representation_level: RepresentationLevel;
    reason: string;
  };
  notice?: string;
}

export interface Finding {
  id: number;
  inference_run_id: number | null;
  case_id: number;
  modality: Modality;
  category: string;
  label: string;
  raw_confidence: number | null;
  calibrated_confidence: number | null;
  calibration_status: string;
  visual_explanation_path: string | null;
  explanation_type: string | null;
  representation_level: RepresentationLevel;
  anatomical_region: string | null;
  mapping_status: string;
  tre_score: number | null;
  tre_threshold: number | null;
  evidence_provenance: Record<string, unknown> | null;
  review_status: EvidenceStatus;
  failure_reason: string | null;
  is_demo: boolean;
  created_at: string;
  report_statements: Array<{
    id: number;
    entity: string;
    negation: string;
    temporality: string;
    source_span: string;
  }>;
}

export type HumanReviewDecision = 'CONFIRMED' | 'REJECTED' | 'MODIFIED' | 'REQUIRES_FURTHER_WORKUP';

export interface EntityCorrection {
  target_statement_id: number;
  action: 'AMEND' | 'REMOVE';
  corrected_entity?: string;
  corrected_assertion?: 'AFFIRMED' | 'NEGATED';
  corrected_temporality?: 'CURRENT' | 'HISTORICAL' | 'FUTURE' | 'UNSPECIFIED';
  corrected_certainty?: 'CERTAIN' | 'UNCERTAIN' | 'HYPOTHETICAL' | 'UNSPECIFIED';
  corrected_anatomical_site?: string;
  corrected_laterality?: 'LEFT' | 'RIGHT' | 'BILATERAL' | 'MIDLINE' | 'UNSPECIFIED';
}

export interface MeasurementCorrection {
  target_measurement_id: number;
  action: 'AMEND' | 'REMOVE';
  corrected_display_name?: string;
  corrected_value?: number;
  corrected_result_operator?: '=' | '<' | '>' | '<=' | '>=';
  corrected_unit?: string;
  corrected_reference_low?: number;
  corrected_reference_high?: number;
  corrected_specimen?: string;
  corrected_laboratory_method?: string;
}

export interface HumanReviewCorrectionPayload {
  schema_version: '1.0';
  status: 'PROPOSED_NOT_APPLIED';
  entity_corrections: EntityCorrection[];
  measurement_corrections: MeasurementCorrection[];
}

export interface HumanReview {
  id: number;
  finding_id: number;
  reviewer_id: number | null;
  review_status: HumanReviewDecision;
  reviewer_comments: string | null;
  correction_payload: HumanReviewCorrectionPayload | null;
  original_output_preserved: boolean;
  reviewed_at: string;
  /** Independent second-reviewer decision; only APPROVED changes the effective (reviewed) view. */
  decision?: CorrectionDecision | null;
}

export interface CorrectionDecision {
  id: number;
  review_id: number;
  decided_by_id: number | null;
  decision: 'APPROVED' | 'REJECTED';
  rationale: string;
  decided_at: string;
}

export type EffectiveCorrectionState = 'ORIGINAL_IMMUTABLE' | 'CORRECTION_PROPOSED' | 'CORRECTION_REJECTED'
  | 'CORRECTION_APPLIED_TO_EFFECTIVE_VIEW' | 'REMOVED_IN_EFFECTIVE_VIEW';

export interface EvidenceCorrection<T> {
  review_id: number;
  proposed_by_id: number | null;
  proposed_at: string;
  state: 'CORRECTION_PROPOSED' | 'CORRECTION_APPROVED' | 'CORRECTION_REJECTED';
  decided_by_id: number | null;
  decided_at: string | null;
  correction: T;
}

export interface EffectiveEvidenceRecord<T, C> {
  correction_state: EffectiveCorrectionState;
  original: T;
  effective: T;
  applied_review_id: number | null;
  corrections: EvidenceCorrection<C>[];
}

export type EffectiveStatementFields = Pick<ReportStatement, 'entity' | 'negation' | 'temporality' | 'certainty' | 'anatomical_site' | 'laterality'>;
export type EffectiveMeasurementFields = Pick<MedicalMeasurement, 'display_name' | 'value' | 'result_operator' | 'unit' | 'reference_low' | 'reference_high' | 'specimen' | 'laboratory_method'>;

export interface EffectiveEvidenceResponse {
  case_id: number;
  statements: Array<EffectiveEvidenceRecord<EffectiveStatementFields, EntityCorrection> & { statement_id: number }>;
  measurements: Array<EffectiveEvidenceRecord<EffectiveMeasurementFields, MeasurementCorrection> & { measurement_id: number }>;
  notice: string;
}

export interface ReviewedDemographics {
  id: number;
  case_id: number;
  revision: number;
  sex: 'M' | 'F' | 'UNKNOWN';
  date_of_birth: string | null;
  source_file_id: number | null;
  source_reference_id: number | null;
  reason: string;
  reviewed_by_id: number | null;
  created_at: string;
  source_state: 'ACTIVE' | 'WITHDRAWN_OR_UNASSOCIATED' | 'SOURCE_DELETED' | 'PROVENANCE_UNAVAILABLE' | 'REVIEWER_ATTESTATION';
  provenance: 'REVIEWER_ENTERED_NOT_SOURCE_EXTRACTED';
}

export interface ReviewedDemographicsResponse {
  case_id: number;
  current: ReviewedDemographics | null;
  history: ReviewedDemographics[];
  notice: string;
  can_record: boolean;
}

export type ReviewedDemographicsInput = Pick<ReviewedDemographics, 'sex' | 'date_of_birth' | 'source_file_id' | 'reason'> & { expected_revision: number };

export interface ProvenanceEvent {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  timestamp: string;
}

export interface AnatomyAsset {
  id: number;
  name: string;
  system_name: string;
  asset_path: string;
  format: string;
  representation_level: RepresentationLevel;
  is_available: boolean;
  notes: string | null;
}

export interface SystemHealth {
  status: string;
  project: string;
  version: string;
  cuda_available: boolean;
  gpu_name: string | null;
  research_notice: string;
  database_status: string;
  /** Data is kept only in a serverless instance's temp directory and is lost when it stops. */
  temporary_storage?: boolean;
  active_cases: number;
  total_findings: number;
  health_scope: string;
  models_status: Record<string, string>;
}

export type ModelRegistryStatus =
  | 'DISCOVERED'
  | 'NOT_INSTALLED'
  | 'DEPENDENCY_MISSING'
  | 'WEIGHTS_MISSING'
  | 'READY_UNVALIDATED'
  | 'VALIDATED'
  | 'FAILED'
  | 'UNSUPPORTED';

export interface ModelActivationGate {
  eligible: boolean;
  blockers: string[];
  missing_fields: string[];
  missing_artifacts: string[];
  required_status: 'VALIDATED';
  current_status: ModelRegistryStatus;
  validated: boolean;
  checkpoint_hash_matches: boolean;
}

export interface ModelRegistryRecord {
  model_id: string;
  display_name: string;
  domain: string;
  task: string;
  anatomy: string;
  framework: string;
  adapter: string;
  source_repository: string;
  dependency_environment: string;
  weights_path: string | null;
  device: string;
  supported_inputs: string[];
  supported_classes: string[];
  status: ModelRegistryStatus;
  registry_state: string;
  validated: boolean;
  processor_only: boolean;
  limitations: string[];
  artifact_bundle: Record<string, unknown>;
  activation: ModelActivationGate;
  research_inference?: boolean;
  research_gate?: { allowed: boolean; blockers: string[] };
  held_out_evaluation?: Record<string, unknown>;
}

export interface ModelRegistryResponse {
  schema_version: string;
  generated_from: string;
  model_count: number;
  activatable_count: number;
  models: ModelRegistryRecord[];
}

export interface CapabilityRecord {
  capability_id: string;
  label: string;
  operational: boolean;
  verification_status: string;
  inference_operational?: boolean;
  model_status?: ModelRegistryStatus;
  supports?: string[];
  limitations: string[];
}

export interface CapabilityRegistryResponse {
  schema_version: string;
  capability_count: number;
  operational_count: number;
  capabilities: CapabilityRecord[];
}

export interface DatasetRegistryRecord {
  dataset_id: string;
  source_path: string;
  path_exists: boolean;
  registry_kind: string;
  medical_domain: string;
  modality: string;
  task: string;
  annotation_format: string;
  classes: string[];
  sample_count: number;
  sample_count_semantics: string;
  split_status: string;
  license_status: string;
  supported_models: string[];
  integration_status: string;
  training_eligible: boolean;
  validation_eligible: boolean;
  limitations: string[];
}

export interface DatasetRegistryResponse {
  schema_version: string;
  generated_at_utc: string;
  global_readiness: string;
  global_blockers: string[];
  datasets: DatasetRegistryRecord[];
}

export interface DatasetTaskAuditLicense {
  status: string;
  name: string;
  source?: string;
  verified_on?: string;
  citation?: string;
}

export interface DatasetTaskAuditPreparation {
  samples?: number;
  labels?: string[];
  per_split?: Record<string, number>;
  split_method?: string;
  dataset_version?: string;
}

export interface DatasetTaskAuditTask {
  task_id: string;
  type: string;
  target: string;
  flags: string[];
  training_eligible: boolean;
  validation_ready?: boolean;
  minimum_samples_per_class?: number;
  readiness: string;
  preparation?: DatasetTaskAuditPreparation;
}

export interface DatasetTaskAuditDataset {
  id: string;
  title: string;
  modality: string;
  system: string | null;
  identity: string;
  labels: string;
  official_splits: boolean;
  patient_ids: string;
  files: number;
  license: DatasetTaskAuditLicense;
  privacy: string;
  notes: string[];
  tasks: DatasetTaskAuditTask[];
}

export interface DatasetTaskAuditResponse {
  generated_at: string;
  tool: string;
  split_seed: number;
  dhash_threshold: number;
  datasets: DatasetTaskAuditDataset[];
}

export interface CaseStats {
  case_id: string;
  pseudonym: string;
  total_files: number;
  images_count: number;
  ecg_count: number;
  reports_count: number;
  findings_count: number;
  pending_reviews_count: number;
  completed_count: number;
  rejected_count: number;
  fusion_status: string;
  concordance_flags_count: number;
  orders_count: number;
  lab_reports_count: number;
  is_demo_data: boolean;
}

// Descriptive aliases make imports self-documenting in the application shell.
export type CaseRecord = Case;
export type ExaminationRecord = Examination;
export type UploadRecord = UploadedFile;
export type FindingRecord = Finding;
export type ClinicalStatement = ReportStatement;
export type AuditEvent = ProvenanceEvent;
export type AnatomicalAsset = AnatomyAsset;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly requestId: string | null;

  constructor(status: number, message: string, detail?: unknown, requestId: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }
}

function resourcePath(id: ResourceId): string {
  return encodeURIComponent(String(id));
}

function formatValidationDetail(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null;

  const issues = detail.flatMap((entry): string[] => {
    if (!entry || typeof entry !== 'object') return [];
    const location =
      'loc' in entry && Array.isArray(entry.loc)
        ? entry.loc
            .filter((part: unknown): part is string | number => typeof part === 'string' || typeof part === 'number')
            .slice(1)
            .join('.')
        : '';
    const message = 'msg' in entry && typeof entry.msg === 'string' ? entry.msg : '';
    return message ? [`${location || 'Request'}: ${message}`] : [];
  });

  return issues.length > 0 ? issues.join('; ') : null;
}

function rejectsRegistrationProfileFields(error: unknown): error is ApiError {
  if (!(error instanceof ApiError) || error.status !== 422 || !Array.isArray(error.detail)) return false;
  const profileFields = new Set([
    'requested_role',
    'requested_department',
    'requested_department_other',
  ]);
  const errors = error.detail.filter((entry) => entry && typeof entry === 'object');

  return (
    errors.length > 0 &&
    errors.every(
      (entry) =>
        'loc' in entry &&
        Array.isArray(entry.loc) &&
        entry.loc[0] === 'body' &&
        typeof entry.loc[1] === 'string' &&
        profileFields.has(entry.loc[1]) &&
        'msg' in entry &&
        entry.msg === 'Extra inputs are not permitted',
    )
  );
}

class ApiClient {
  private token: string | null =
    typeof window === 'undefined' ? null : window.localStorage.getItem(TOKEN_STORAGE_KEY);

  setToken(token: string | null): void {
    this.token = token;
    if (typeof window === 'undefined') return;
    if (token) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  }

  getToken(): string | null {
    return this.token;
  }

  private async request<T>(
    endpoint: `/${string}`,
    options: RequestInit = {},
    authenticated = true,
  ): Promise<T> {
    const headers = new Headers(options.headers);
    if (authenticated && this.token) headers.set('Authorization', `Bearer ${this.token}`);
    if (options.body !== undefined && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    const response = await fetch(`${API_V1_BASE}${endpoint}`, { ...options, headers });
    const rawBody = response.status === 204 ? '' : await response.text();
    let body: unknown;
    if (rawBody) {
      try {
        body = JSON.parse(rawBody) as unknown;
      } catch {
        body = rawBody;
      }
    }

    if (!response.ok) {
      if (response.status === 401 && endpoint !== '/auth/login') this.setToken(null);
      const detail =
        body && typeof body === 'object' && 'detail' in body
          ? (body as { detail: unknown }).detail
          : body;
      // A 413 without the API's JSON detail came from the hosting platform or proxy (Vercel
      // accepts at most 4.5 MB per request), whose error page is not a useful message.
      const rejectedBeforeApi = response.status === 413 && !(body && typeof body === 'object');
      const message = rejectedBeforeApi
        ? 'The file is larger than this server accepts, so it was rejected before reaching MedTwin (HTTP 413).'
        : typeof detail === 'string'
          ? detail
          : (formatValidationDetail(detail) ??
            `Request failed (${response.status} ${response.statusText})`);
      throw new ApiError(response.status, message, detail, response.headers.get('X-Request-ID'));
    }

    return body as T;
  }

  /** Authenticated binary fetch (images, rendered slices) returning the blob and headers. */
  async requestBlob(endpoint: `/${string}`, body?: unknown): Promise<{ blob: Blob; headers: Headers }> {
    const headers = new Headers();
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`);
    if (body !== undefined) headers.set('Content-Type', 'application/json');
    const response = await fetch(`${API_V1_BASE}${endpoint}`, body === undefined ? { headers } : { method: 'POST', headers, body: JSON.stringify(body) });
    if (!response.ok) {
      let message = `Request failed (${response.status} ${response.statusText})`;
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === 'string') message = body.detail;
      } catch {
        // Non-JSON error body; keep the status message.
      }
      if (response.status === 401) this.setToken(null);
      throw new ApiError(response.status, message, undefined, response.headers.get('X-Request-ID'));
    }
    return { blob: await response.blob(), headers: response.headers };
  }

  /** Authenticate against the flat token response, then hydrate the user via /auth/me. */
  async login(username: string, password: string): Promise<AuthenticatedSession> {
    const token = await this.request<AuthToken>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ username, password }) },
      false,
    );
    this.setToken(token.access_token);
    try {
      const user = await this.getMe();
      return { ...token, user };
    } catch (error) {
      this.setToken(null);
      throw error;
    }
  }

  async register(input: RegisterUserInput): Promise<RegisterUserResult> {
    try {
      const user = await this.request<User>(
        '/auth/register',
        { method: 'POST', body: JSON.stringify(input) },
        false,
      );
      return { user, profileRequestSaved: true };
    } catch (error) {
      if (!rejectsRegistrationProfileFields(error)) throw error;

      const { username, email, password, full_name } = input;
      const user = await this.request<User>(
        '/auth/register',
        { method: 'POST', body: JSON.stringify({ username, email, password, full_name }) },
        false,
      );
      return { user, profileRequestSaved: false };
    }
  }

  logout(): void {
    this.setToken(null);
  }

  getMe(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  getSystemHealth(): Promise<SystemHealth> {
    return this.request<SystemHealth>('/system/health');
  }

  getSystemStatus(): Promise<SystemHealth> {
    return this.getSystemHealth();
  }

  getModels(): Promise<ModelRegistryResponse> {
    return this.request<ModelRegistryResponse>('/models');
  }

  getModel(modelId: ResourceId): Promise<ModelRegistryRecord> {
    return this.request<ModelRegistryRecord>(`/models/${resourcePath(modelId)}`);
  }

  getCapabilities(): Promise<CapabilityRegistryResponse> {
    return this.request<CapabilityRegistryResponse>('/capabilities');
  }

  getDatasets(): Promise<DatasetRegistryResponse> {
    return this.request<DatasetRegistryResponse>('/datasets');
  }

  getDatasetTaskAudit(): Promise<DatasetTaskAuditResponse> {
    return this.request<DatasetTaskAuditResponse>('/datasets/task-audit');
  }

  getDataset(datasetId: ResourceId): Promise<DatasetRegistryRecord> {
    return this.request<DatasetRegistryRecord>(`/datasets/${resourcePath(datasetId)}`);
  }

  getCases(): Promise<Case[]> {
    return this.request<Case[]>('/cases');
  }

  getCase(caseId: ResourceId): Promise<Case> {
    return this.request<Case>(`/cases/${resourcePath(caseId)}`);
  }

  getCaseStats(caseId: ResourceId): Promise<CaseStats> {
    return this.request<CaseStats>(`/cases/${resourcePath(caseId)}/stats`);
  }

  createCase(input: CreateCaseInput): Promise<Case>;
  createCase(pseudonymousId: string, description?: string): Promise<Case>;
  createCase(input: CreateCaseInput | string, description?: string): Promise<Case> {
    const payload: CreateCaseInput =
      typeof input === 'string'
        ? { pseudonymous_id: input, description: description ?? null }
        : input;
    return this.request<Case>('/cases', { method: 'POST', body: JSON.stringify(payload) });
  }

  getExaminations(caseId: ResourceId): Promise<Examination[]> {
    return this.request<Examination[]>(`/cases/${resourcePath(caseId)}/examinations`);
  }

  createExamination(caseId: ResourceId, input: CreateExaminationInput): Promise<Examination>;
  createExamination(
    caseId: ResourceId,
    modality: Exclude<Modality, 'MULTIMODAL'>,
    examDate?: string,
    clinicalIndication?: string,
  ): Promise<Examination>;
  createExamination(
    caseId: ResourceId,
    input: CreateExaminationInput | Exclude<Modality, 'MULTIMODAL'>,
    examDate?: string,
    clinicalIndication?: string,
  ): Promise<Examination> {
    const payload: CreateExaminationInput =
      typeof input === 'string'
        ? {
            modality: input,
            exam_date: examDate ?? new Date().toISOString(),
            clinical_indication: clinicalIndication ?? null,
          }
        : input;
    return this.request<Examination>(`/cases/${resourcePath(caseId)}/examinations`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  getCaseUploads(caseId: ResourceId): Promise<UploadedFile[]> {
    return this.request<UploadedFile[]>(`/cases/${resourcePath(caseId)}/uploads`);
  }

  getCaseFiles(caseId: ResourceId): Promise<UploadedFile[]> {
    return this.getCaseUploads(caseId);
  }

  getUpload(uploadId: ResourceId): Promise<UploadedFile> {
    return this.request<UploadedFile>(`/uploads/${resourcePath(uploadId)}`);
  }

  getUploadContentUrl(uploadId: ResourceId): string {
    return `${API_V1_BASE}/uploads/${resourcePath(uploadId)}/content`;
  }

  /** Replace a file with a new version; the earlier version keeps its bytes and is marked superseded. */
  uploadFileVersion(uploadId: ResourceId, file: File, reason: string): Promise<UploadedFile> {
    const form = new FormData();
    form.append('file', file);
    form.append('reason', reason);
    form.append('deidentified', 'true');
    return this.request<UploadedFile>(`/uploads/${resourcePath(uploadId)}/versions`, { method: 'POST', body: form });
  }

  /** Withdraw a file with a reason: an audited tombstone; bytes are kept for retention. */
  withdrawFile(uploadId: ResourceId, reason: string): Promise<UploadedFile> {
    return this.request<UploadedFile>(`/uploads/${resourcePath(uploadId)}`, {
      method: 'DELETE',
      body: JSON.stringify({ reason }),
    });
  }

  uploadFile(caseId: ResourceId, file: File, options: UploadOptions): Promise<UploadedFile> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('deidentified', String(options.deidentified));
    formData.append('is_associated', String(options.isAssociated ?? true));
    if (options.examinationId !== undefined) {
      formData.append('examination_id', String(options.examinationId));
    }
    if (options.associationNotes) formData.append('association_notes', options.associationNotes);

    return this.request<UploadedFile>(`/cases/${resourcePath(caseId)}/uploads`, {
      method: 'POST',
      body: formData,
    });
  }

  /** Upload with byte-level progress (fetch cannot report upload progress). */
  uploadFileWithProgress(caseId: ResourceId, file: File, options: UploadOptions, onProgress: (fraction: number) => void): Promise<UploadedFile> {
    return this.uploadWithProgress(`/cases/${resourcePath(caseId)}/uploads`, file, options, onProgress);
  }

  uploadPortalDocumentWithProgress(caseId: ResourceId, file: File, onProgress: (fraction: number) => void): Promise<UploadedFile> {
    return this.uploadWithProgress(`/portal/cases/${resourcePath(caseId)}/documents`, file, { deidentified: true }, onProgress);
  }

  private uploadWithProgress(endpoint: string, file: File, options: UploadOptions, onProgress: (fraction: number) => void): Promise<UploadedFile> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('deidentified', String(options.deidentified));
    formData.append('is_associated', String(options.isAssociated ?? true));
    if (options.examinationId !== undefined) formData.append('examination_id', String(options.examinationId));
    if (options.associationNotes) formData.append('association_notes', options.associationNotes);
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open('POST', `${API_V1_BASE}${endpoint}`);
      if (this.token) request.setRequestHeader('Authorization', `Bearer ${this.token}`);
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded / event.total);
      };
      request.onerror = () => reject(new ApiError(0, 'Network error during upload.'));
      request.onload = () => {
        let body: unknown = null;
        try {
          body = JSON.parse(request.responseText) as unknown;
        } catch {
          body = request.responseText;
        }
        if (request.status >= 200 && request.status < 300) {
          resolve(body as UploadedFile);
          return;
        }
        if (request.status === 401) this.setToken(null);
        const detail = body && typeof body === 'object' && 'detail' in body ? (body as { detail: unknown }).detail : body;
        reject(new ApiError(request.status, typeof detail === 'string' ? detail : `Upload failed (${request.status})`, detail));
      };
      request.send(formData);
    });
  }

  updateFileAssociation(
    uploadId: ResourceId,
    isAssociated: boolean,
    associationNotes?: string,
  ): Promise<UploadedFile> {
    return this.request<UploadedFile>(`/uploads/${resourcePath(uploadId)}/association`, {
      method: 'PATCH',
      body: JSON.stringify({
        is_associated: isAssociated,
        association_notes: associationNotes ?? null,
      }),
    });
  }

  /** Runs (inline mode) or queues (worker mode) an analysis; a queued job is polled to completion. */
  async createAnalysisJob(uploadId: ResourceId, onQueued?: (job: QueuedJob) => void): Promise<AnalysisJob> {
    const response = await this.request<AnalysisJob | { queued_job: QueuedJob }>(`/uploads/${resourcePath(uploadId)}/analysis-jobs`, {
      method: 'POST',
    });
    if (!('queued_job' in response)) return response;
    const runId = await this.waitForJob(response.queued_job, onQueued);
    return this.getAnalysisJob(runId);
  }

  getQueuedJob(jobId: ResourceId): Promise<QueuedJob> {
    return this.request<QueuedJob>(`/jobs/${resourcePath(jobId)}`);
  }

  cancelQueuedJob(jobId: ResourceId): Promise<QueuedJob> {
    return this.request<QueuedJob>(`/jobs/${resourcePath(jobId)}/cancel`, { method: 'POST' });
  }

  /** Polls a durable job until it is terminal; resolves with the analysis-run id it produced. */
  async waitForJob(job: QueuedJob, onUpdate?: (job: QueuedJob) => void, intervalMs = 1500): Promise<number> {
    let current = job;
    while (current.status === 'QUEUED' || current.status === 'RUNNING') {
      onUpdate?.(current);
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      current = await this.getQueuedJob(current.id);
    }
    onUpdate?.(current);
    const runId = current.result_ref?.inference_run_id;
    if (current.status !== 'SUCCEEDED' || runId === undefined) {
      throw new ApiError(500, current.status === 'CANCELLED' ? 'The job was cancelled.' : `The job failed: ${current.last_error ?? 'no detail recorded'}`);
    }
    return runId;
  }

  getResearchModels(): Promise<ResearchModelListing> {
    return this.request<ResearchModelListing>('/research-models');
  }

  getResearchModelEvaluation(modelId: string): Promise<{ model_id: string; task: string; gate: { allowed: boolean; blockers: string[] }; report: Record<string, unknown> }> {
    return this.request(`/research-models/${encodeURIComponent(modelId)}/evaluation`);
  }

  async runResearchModel(uploadId: ResourceId, modelId: string, declaredInputType: string, onQueued?: (job: QueuedJob) => void, options: ResearchRunOptions = {}): Promise<ResearchRun> {
    const response = await this.request<ResearchRun | { queued_job: QueuedJob }>(`/uploads/${resourcePath(uploadId)}/research-inference`, {
      method: 'POST',
      body: JSON.stringify({
        model_id: modelId,
        declared_input_type: declaredInputType,
        ...(options.companionUploadId !== undefined ? { companion_upload_id: options.companionUploadId } : {}),
        ...(options.amplitudeUnit ? { amplitude_unit: options.amplitudeUnit } : {}),
      }),
    });
    if (!('queued_job' in response)) return response;
    return this.getResearchRun(await this.waitForJob(response.queued_job, onQueued));
  }

  getPortalCases(): Promise<PortalCase[]> {
    return this.request<PortalCase[]>('/portal/cases');
  }

  createPersonalPortalRecord(): Promise<PortalCase> {
    return this.request<PortalCase>('/portal/cases', { method: 'POST' });
  }

  getPortalRecord(caseId: ResourceId): Promise<PortalRecord> {
    return this.request<PortalRecord>(`/portal/cases/${resourcePath(caseId)}`);
  }

  async downloadPortalDocument(caseId: ResourceId, documentId: ResourceId): Promise<string> {
    const { blob } = await this.requestBlob(`/portal/cases/${resourcePath(caseId)}/documents/${resourcePath(documentId)}`);
    return URL.createObjectURL(blob);
  }

  getPortalCaregivers(caseId: ResourceId): Promise<Array<{ user_id: number; username: string; since: string }>> {
    return this.request(`/portal/cases/${resourcePath(caseId)}/caregivers`);
  }

  addPortalCaregiver(caseId: ResourceId, username: string): Promise<{ user_id: number; username: string }> {
    return this.request(`/portal/cases/${resourcePath(caseId)}/caregivers`, { method: 'POST', body: JSON.stringify({ username }) });
  }

  removePortalCaregiver(caseId: ResourceId, userId: ResourceId): Promise<void> {
    return this.request<void>(`/portal/cases/${resourcePath(caseId)}/caregivers/${resourcePath(userId)}`, { method: 'DELETE' });
  }

  assembleDicomSeries(caseId: ResourceId, uploadIds: number[]): Promise<DicomSeriesReport> {
    return this.request<DicomSeriesReport>(`/cases/${resourcePath(caseId)}/dicom-series/assemble`, { method: 'POST', body: JSON.stringify({ upload_ids: uploadIds }) });
  }

  async renderDicomSeries(caseId: ResourceId, uploadIds: number[], plane: { axis: 'axial' | 'coronal' | 'sagittal'; index: number | null; center?: number; width?: number }): Promise<{ url: string; info: SeriesRenderInfo }> {
    const { blob, headers } = await this.requestBlob(`/cases/${resourcePath(caseId)}/dicom-series/render`, {
      upload_ids: uploadIds, axis: plane.axis, ...(plane.index !== null ? { index: plane.index } : {}),
      ...(plane.center !== undefined && plane.width !== undefined ? { center: plane.center, width: plane.width } : {}),
    });
    return { url: URL.createObjectURL(blob), info: JSON.parse(headers.get('X-MedTwin-Render') ?? '{}') as SeriesRenderInfo };
  }

  async runSeriesResearchModel(caseId: ResourceId, uploadIds: number[], modelId: string, onQueued?: (job: QueuedJob) => void): Promise<ResearchRun> {
    const response = await this.request<ResearchRun | { queued_job: QueuedJob }>(`/cases/${resourcePath(caseId)}/dicom-series/research-inference`, {
      method: 'POST', body: JSON.stringify({ upload_ids: uploadIds, model_id: modelId, declared_input_type: 'MRI' }),
    });
    if (!('queued_job' in response)) return response;
    return this.getResearchRun(await this.waitForJob(response.queued_job, onQueued));
  }

  getResearchRun(runId: ResourceId): Promise<ResearchRun> {
    return this.request<ResearchRun>(`/research-inference/${resourcePath(runId)}`);
  }

  getAnalysisJob(jobId: ResourceId): Promise<AnalysisJob> {
    return this.request<AnalysisJob>(`/analysis-jobs/${resourcePath(jobId)}`);
  }

  getJobStatus(jobId: ResourceId): Promise<AnalysisJob> {
    return this.getAnalysisJob(jobId);
  }

  getCaseAnalysisJobs(caseId: ResourceId, limit = 100): Promise<AnalysisJob[]> {
    const query = new URLSearchParams({ limit: String(limit) });
    return this.request<AnalysisJob[]>(`/cases/${resourcePath(caseId)}/analysis-jobs?${query}`);
  }

  getCaseFindings(caseId: ResourceId): Promise<Finding[]> {
    return this.request<Finding[]>(`/cases/${resourcePath(caseId)}/findings`);
  }

  getFinding(findingId: ResourceId): Promise<Finding> {
    return this.request<Finding>(`/findings/${resourcePath(findingId)}`);
  }

  getFindingReviews(findingId: ResourceId): Promise<HumanReview[]> {
    return this.request<HumanReview[]>(`/reviews/${resourcePath(findingId)}`);
  }

  /** Approve or reject another reviewer's proposed correction (four-eyes rule). */
  decideCorrection(reviewId: number, decision: 'APPROVED' | 'REJECTED', rationale: string): Promise<CorrectionDecision> {
    return this.request<CorrectionDecision>(`/reviews/corrections/${reviewId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, rationale }),
    });
  }

  submitFindingReview(
    findingId: ResourceId,
    reviewStatus: HumanReviewDecision,
    reviewerComments?: string,
    correctionPayload?: HumanReviewCorrectionPayload,
  ): Promise<HumanReview> {
    return this.request<HumanReview>(`/reviews/${resourcePath(findingId)}`, {
      method: 'POST',
      body: JSON.stringify({
        review_status: reviewStatus,
        reviewer_comments: reviewerComments?.trim() || null,
        correction_payload: correctionPayload ?? null,
      }),
    });
  }

  getReportStatements(caseId: ResourceId): Promise<ReportStatement[]> {
    return this.request<ReportStatement[]>(`/cases/${resourcePath(caseId)}/statements`);
  }

  getCaseMeasurements(caseId: ResourceId): Promise<MedicalMeasurement[]> {
    return this.request<MedicalMeasurement[]>(`/cases/${resourcePath(caseId)}/measurements`);
  }

  getCaseProvenance(caseId: ResourceId, limit = 100): Promise<ProvenanceEvent[]> {
    const query = new URLSearchParams({ limit: String(limit) });
    return this.request<ProvenanceEvent[]>(`/cases/${resourcePath(caseId)}/provenance?${query}`);
  }

  getAnatomyAssets(): Promise<AnatomyAsset[]> {
    return this.request<AnatomyAsset[]>('/assets/anatomy');
  }

  getAnatomicalAssets(): Promise<AnatomyAsset[]> {
    return this.getAnatomyAssets();
  }

  getAuditLogs(limit = 50): Promise<ProvenanceEvent[]> {
    const query = new URLSearchParams({ limit: String(limit) });
    return this.request<ProvenanceEvent[]>(`/system/audit?${query}`);
  }

  // Existing secondary screens use these current backend routes. They still
  // share the same authenticated /api/v1 transport defined above.
  getHealthPackages(): Promise<HealthPackage[]> {
    return this.request<HealthPackage[]>('/catalog/packages');
  }

  getHealthPackage(packageId: ResourceId): Promise<HealthPackage> {
    return this.request<HealthPackage>(`/catalog/packages/${resourcePath(packageId)}`);
  }

  getImagingServices(): Promise<ImagingServiceCategory[]> {
    return this.request<ImagingServiceCategory[]>('/catalog/imaging');
  }

  getLabTestCatalog(): Promise<{
    panels: Record<string, string>;
    tests: LabTestReference[];
    notice: string;
  }> {
    return this.request('/catalog/lab-tests');
  }

  createCaseOrder(
    caseId: ResourceId,
    itemId: string,
    clinicalNotes?: string,
  ): Promise<OrderedPackageRecord> {
    return this.request<OrderedPackageRecord>(`/cases/${resourcePath(caseId)}/orders`, {
      method: 'POST',
      body: JSON.stringify({ item_id: itemId, clinical_notes: clinicalNotes }),
    });
  }

  updateCaseOrderStatus(
    caseId: ResourceId,
    orderId: ResourceId,
    status: OrderStatus,
  ): Promise<OrderedPackageRecord> {
    return this.request<OrderedPackageRecord>(
      `/cases/${resourcePath(caseId)}/orders/${resourcePath(orderId)}`,
      { method: 'PATCH', body: JSON.stringify({ status }) },
    );
  }

  getCaseOrders(caseId: ResourceId): Promise<OrderedPackageRecord[]> {
    return this.request<OrderedPackageRecord[]>(`/cases/${resourcePath(caseId)}/orders`);
  }

  getCaseLabReports(caseId: ResourceId): Promise<LabReportRecord[]> {
    return this.request<LabReportRecord[]>(`/cases/${resourcePath(caseId)}/lab-reports`);
  }

  createCaseLabReport(
    caseId: ResourceId,
    data: {
      ordered_package_id?: number;
      source_file_id?: number;
      report_title?: string;
      lab_name?: string;
      sample_type?: string;
      laboratory_method?: string;
      patient_sex?: 'M' | 'F';
      collection_date?: string;
      collection_time?: string;
      reporting_time?: string;
      clinical_summary?: string;
      results: Array<{
        code: string;
        value: string | number;
        result_operator?: '=' | '<' | '>' | '<=' | '>=';
        ref_low?: number;
        ref_high?: number;
      }>;
    },
  ): Promise<LabReportRecord> {
    return this.request<LabReportRecord>(`/cases/${resourcePath(caseId)}/lab-reports`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  compareExaminations<TResponse = LegacyLongitudinalComparisonResponse>(
    caseId: ResourceId,
    priorExamId?: number,
    currentExamId?: number,
  ): Promise<TResponse> {
    return this.request<TResponse>(`/cases/${resourcePath(caseId)}/compare`, {
      method: 'POST',
      body: JSON.stringify({
        prior_exam_id: priorExamId,
        current_exam_id: currentExamId,
      }),
    });
  }

  getIeeeValidationMetrics(): Promise<IeeeValidationResponse> {
    return this.request<IeeeValidationResponse>('/metrics/ieee-validation');
  }

  getDocumentedAttributes(caseId: ResourceId): Promise<DocumentedAttribute[]> {
    return this.request<DocumentedAttribute[]>(`/cases/${resourcePath(caseId)}/attributes`);
  }

  getEffectiveEvidence(caseId: ResourceId): Promise<EffectiveEvidenceResponse> {
    return this.request<EffectiveEvidenceResponse>(`/cases/${resourcePath(caseId)}/effective-evidence`);
  }

  getReviewedDemographics(caseId: ResourceId): Promise<ReviewedDemographicsResponse> {
    return this.request<ReviewedDemographicsResponse>(`/cases/${resourcePath(caseId)}/demographics`);
  }

  recordReviewedDemographics(caseId: ResourceId, input: ReviewedDemographicsInput): Promise<ReviewedDemographics> {
    return this.request<ReviewedDemographics>(`/cases/${resourcePath(caseId)}/demographics`, { method: 'POST', body: JSON.stringify(input) });
  }

  getBiomarkerTrends(caseId: ResourceId): Promise<{ case_id: number; series: BiomarkerSeries[] }> {
    return this.request(`/cases/${resourcePath(caseId)}/biomarker-trends`);
  }

  getEgfr(caseId: ResourceId): Promise<EgfrResponse> {
    return this.request<EgfrResponse>(`/cases/${resourcePath(caseId)}/calculations/egfr`);
  }

  getAnatomyEvidence(caseId: ResourceId): Promise<AnatomyEvidenceResponse> {
    return this.request<AnatomyEvidenceResponse>(`/cases/${resourcePath(caseId)}/anatomy-evidence`);
  }

  getModalities(): Promise<ModalityRegistryResponse> {
    return this.request<ModalityRegistryResponse>('/modalities');
  }

  getSignalHeader(uploadId: ResourceId): Promise<SignalHeader> {
    return this.request<SignalHeader>(`/uploads/${resourcePath(uploadId)}/signal`);
  }

  getSignalPreview(uploadId: ResourceId, start: number, duration: number, channels: number[], maxPoints = 1200): Promise<SignalPreview> {
    const query = new URLSearchParams({ start: String(start), duration: String(duration), max_points: String(maxPoints), channels: channels.join(",") });
    return this.request<SignalPreview>(`/uploads/${resourcePath(uploadId)}/signal/preview?${query.toString()}`);
  }

  getImagingMetadata(uploadId: ResourceId): Promise<ImagingMetadata> {
    return this.request<ImagingMetadata>(`/uploads/${resourcePath(uploadId)}/imaging/metadata`);
  }

  async renderImagingSlice(
    uploadId: ResourceId,
    options: { index?: number; axis?: 'axial' | 'coronal' | 'sagittal'; center?: number; width?: number },
  ): Promise<{ url: string; info: RenderInfo }> {
    const query = new URLSearchParams();
    if (options.index !== undefined) query.set('index', String(options.index));
    if (options.axis) query.set('axis', options.axis);
    if (options.center !== undefined && options.width !== undefined) {
      query.set('center', String(options.center));
      query.set('width', String(options.width));
    }
    const { blob, headers } = await this.requestBlob(`/uploads/${resourcePath(uploadId)}/imaging/render?${query}`);
    return { url: URL.createObjectURL(blob), info: JSON.parse(headers.get('X-MedTwin-Render') ?? '{}') as RenderInfo };
  }

  async getUploadObjectUrl(uploadId: ResourceId): Promise<string> {
    const { blob } = await this.requestBlob(`/uploads/${resourcePath(uploadId)}/content`);
    return URL.createObjectURL(blob);
  }

  getReportText(uploadId: ResourceId): Promise<ReportTextResponse> {
    return this.request<ReportTextResponse>(`/uploads/${resourcePath(uploadId)}/text`);
  }

  getChestRadiographModel(): Promise<ChestRadiographModelCard> {
    return this.request<ChestRadiographModelCard>('/chest-radiograph-model');
  }

  /** Runs the third-party chest-radiograph research model; the result is a finding pending review. */
  runChestRadiographAnalysis(uploadId: ResourceId): Promise<{ id: number; research_output: ChestRadiographOutput; research_provenance: Record<string, unknown> }> {
    return this.request(`/uploads/${resourcePath(uploadId)}/chest-radiograph-analysis`, {
      method: 'POST',
      body: JSON.stringify({ attest_frontal_chest_radiograph: true }),
    });
  }

  /** One PDF report page as an image with its identifier lines painted out (verification). */
  async getReportPageImage(uploadId: ResourceId, page: number): Promise<ReportPageImage> {
    const { blob, headers } = await this.requestBlob(`/uploads/${resourcePath(uploadId)}/pages/${page}/image`);
    const info = JSON.parse(headers.get('X-MedTwin-Page') ?? '{}') as Omit<ReportPageImage, 'url'>;
    return { ...info, url: URL.createObjectURL(blob) };
  }

  getPrognosisCapabilities(): Promise<PrognosisCapabilitiesResponse> {
    return this.request<PrognosisCapabilitiesResponse>('/prognosis/capabilities');
  }

  evaluatePrognosis(input: { case_id: number; organ_system: string; intervention_id?: string | null; horizon_days: number }): Promise<PrognosisEvaluation> {
    return this.request<PrognosisEvaluation>('/prognosis/evaluate', { method: 'POST', body: JSON.stringify(input) });
  }

  getFusion(caseId: ResourceId): Promise<FusionRecord | null> {
    return this.request<FusionRecord | null>(`/cases/${resourcePath(caseId)}/fusion`);
  }

  runFusion(caseId: ResourceId): Promise<FusionRecord> {
    return this.request<FusionRecord>(`/cases/${resourcePath(caseId)}/fusion`, { method: 'POST' });
  }

  getConcordance(caseId: ResourceId): Promise<ConcordanceSummary> {
    return this.request<ConcordanceSummary>(`/cases/${resourcePath(caseId)}/concordance`);
  }

  getPrognosisEvaluations(caseId: ResourceId): Promise<Array<{ id: number; organ_system: string; intervention_id: string | null; horizon_days: number; status: string; created_at: string }>> {
    return this.request(`/cases/${resourcePath(caseId)}/prognosis-evaluations`);
  }

  getRiskRegistry(): Promise<RiskRegistryResponse> {
    return this.request<RiskRegistryResponse>('/risk/registry');
  }

  getResearchAnalytics(): Promise<ResearchAnalyticsResponse> {
    return this.request<ResearchAnalyticsResponse>('/analytics/research');
  }

  getTraceability(): Promise<TraceabilityResponse> {
    return this.request<TraceabilityResponse>('/research/traceability');
  }

  runEvaluation(task: EvaluationTask, file: File, options: EvaluationContextInput & { threshold?: number; alpha?: number; absTolerance?: number }): Promise<EvaluationResult> {
    const form = evaluationForm(options);
    form.append('file', file);
    if (options.threshold !== undefined) form.append('threshold', String(options.threshold));
    if (options.alpha !== undefined) form.append('alpha', String(options.alpha));
    if (options.absTolerance !== undefined) form.append('abs_tolerance', String(options.absTolerance));
    return this.request<EvaluationResult>(`/evaluation/${task}`, { method: 'POST', body: form });
  }

  runSegmentationEvaluation(reference: File, prediction: File, spacing: PixelSpacing, context: EvaluationContextInput = {}): Promise<EvaluationResult> {
    const form = evaluationForm(context, spacing);
    form.append('reference', reference);
    form.append('prediction', prediction);
    return this.request<EvaluationResult>('/evaluation/segmentation/masks', { method: 'POST', body: form });
  }

  runSegmentationBatchEvaluation(archive: File, spacing: PixelSpacing, context: EvaluationContextInput = {}): Promise<EvaluationResult> {
    const form = evaluationForm(context, spacing);
    form.append('archive', archive);
    return this.request<EvaluationResult>('/evaluation/segmentation/batch', { method: 'POST', body: form });
  }

  runDetectionEvaluation(predictions: File, annotations: File, context: EvaluationContextInput = {}): Promise<EvaluationResult> {
    const form = evaluationForm(context);
    form.append('predictions', predictions);
    form.append('annotations', annotations);
    return this.request<EvaluationResult>('/evaluation/detection/coco', { method: 'POST', body: form });
  }

  runClinicalNlpEvaluation(
    gold: File,
    predictions: File,
    context: EvaluationContextInput = {},
    attestations: { deidentified: boolean; independentlyAnnotated: boolean },
  ): Promise<EvaluationResult> {
    const form = evaluationForm(context);
    form.append('gold', gold);
    form.append('predictions', predictions);
    form.append('deidentified', String(attestations.deidentified));
    form.append('independently_annotated', String(attestations.independentlyAnnotated));
    return this.request<EvaluationResult>('/evaluation/clinical_nlp', { method: 'POST', body: form });
  }

  runOcrEvaluation(
    gold: File,
    predictions: File,
    context: EvaluationContextInput = {},
    attestations: { deidentified: boolean; independentlyTranscribed: boolean },
  ): Promise<EvaluationResult> {
    const form = evaluationForm(context);
    form.append('gold', gold);
    form.append('predictions', predictions);
    form.append('deidentified', String(attestations.deidentified));
    form.append('independently_transcribed', String(attestations.independentlyTranscribed));
    return this.request<EvaluationResult>('/evaluation/ocr', { method: 'POST', body: form });
  }

  getEvaluationRuns(): Promise<EvaluationRunSummary[]> {
    return this.request<EvaluationRunSummary[]>('/evaluation/runs');
  }

  getEvaluationRun(runId: ResourceId): Promise<EvaluationResult> {
    return this.request<EvaluationResult>(`/evaluation/runs/${resourcePath(runId)}`);
  }

  getReadiness(): Promise<ReadinessResponse> {
    return this.request<ReadinessResponse>('/system/readiness', {}, false);
  }

  getGpuTelemetry(): Promise<GpuTelemetry> {
    return this.request<GpuTelemetry>('/system/gpu');
  }

  getCaseMembers(caseId: ResourceId): Promise<CaseMember[]> {
    return this.request<CaseMember[]>(`/cases/${resourcePath(caseId)}/members`);
  }

  addCaseMember(caseId: ResourceId, username: string, role: CaseMemberRole): Promise<CaseMember> {
    return this.request<CaseMember>(`/cases/${resourcePath(caseId)}/members`, { method: 'POST', body: JSON.stringify({ username, role }) });
  }

  removeCaseMember(caseId: ResourceId, userId: number): Promise<void> {
    return this.request<void>(`/cases/${resourcePath(caseId)}/members/${resourcePath(userId)}`, { method: 'DELETE' });
  }

  submitRegistrationReview(layerId: string, decision: 'ACCEPTED_FOR_EDUCATIONAL_DISPLAY' | 'REJECTED' | 'NEEDS_LANDMARKS', comments?: string): Promise<Record<string, unknown>> {
    return this.request('/anatomy/registration-reviews', { method: 'POST', body: JSON.stringify({ layer_id: layerId, decision, comments: comments || null }) });
  }

  getRegistrationReviews(layerId?: string): Promise<Array<Record<string, unknown>>> {
    const query = layerId ? `?${new URLSearchParams({ layer_id: layerId })}` : '';
    return this.request(`/anatomy/registration-reviews${query}`);
  }
}

export const api = new ApiClient();
