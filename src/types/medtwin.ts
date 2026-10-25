export type UserRole = 'ADMIN' | 'CLINICIAN' | 'RESEARCHER' | 'REVIEWER';

export type ModalityType = 'IMAGE' | 'ECG' | 'REPORT';

export type EvidenceStatus = 
  | 'PENDING'
  | 'COMPLETED'
  | 'ABSTAIN'
  | 'REJECT'
  | 'ERROR'
  | 'NOT_RUN'
  | 'UNASSOCIATED'
  | 'NOT_ELIGIBLE'
  | 'MAPPING_UNSUPPORTED';

export type AnatomicalLevel = 'L1_GENERIC' | 'L2_FINDING_ASSOCIATED' | 'L3_PATIENT_SPECIFIC';

export type ReviewStatus = 'PENDING_HUMAN_REVIEW' | 'CONFIRMED' | 'REJECTED' | 'AMENDED';

export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  full_name: string;
  is_active: boolean;
}

export interface Case {
  id: string;
  pseudonym: string;
  created_at: string;
  updated_at: string;
  created_by_user_id: string;
  notes?: string;
  metadata_json?: Record<string, unknown>;
}

export interface Examination {
  id: string;
  case_id: string;
  timestamp: string;
  examination_type: string;
  clinician_notes?: string;
  created_at: string;
}

export interface UploadedFile {
  id: string;
  case_id: string;
  examination_id?: string;
  file_name: string;
  storage_path: string;
  modality: ModalityType;
  mime_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  is_associated: boolean;
  association_reason?: string;
  created_at: string;
}

export interface Finding {
  id: string;
  case_id: string;
  source_file_id?: string;
  modality: ModalityType;
  task_name: string;
  finding_category: string;
  finding_label: string;
  raw_confidence: number;
  calibrated_confidence?: number;
  is_calibrated: boolean;
  model_name: string;
  model_version: string;
  evidence_status: EvidenceStatus;
  abstention_reason?: string;
  anatomical_level: AnatomicalLevel;
  anatomical_region?: string;
  mapping_status?: string;
  review_status: ReviewStatus;
  review_comments?: string;
  details_json?: Record<string, unknown>;
  created_at: string;
}

export interface ClinicalReportStatement {
  id: string;
  case_id: string;
  source_file_id: string;
  entity_text: string;
  category: string;
  is_negated: boolean;
  temporality: string;
  char_start: number;
  char_end: number;
  confidence: number;
  created_at: string;
}

export interface MultimodalFusionRecord {
  id: string;
  case_id: string;
  image_present: boolean;
  ecg_present: boolean;
  report_present: boolean;
  fusion_status: EvidenceStatus;
  abstention_reason?: string;
  alpha_image?: number;
  alpha_ecg?: number;
  alpha_report?: number;
  fused_prediction_label?: string;
  fused_confidence?: number;
  paired_data_validated: boolean;
  fusion_model_version: string;
  created_at: string;
}

export interface ConcordanceRecord {
  id: string;
  case_id: string;
  finding_category: string;
  model_label: string;
  model_modality: ModalityType;
  model_confidence: number;
  report_statement_text: string;
  report_negated: boolean;
  is_concordant: boolean;
  review_flag: boolean;
  review_note?: string;
  created_at: string;
}

export interface RegistrationEvaluation {
  status: string;
  message: string;
  held_out_tre: number | null;
  tau_tre_threshold: number;
  is_gate_passed: boolean;
  fitting_error_rms: number | null;
  anatomical_level: AnatomicalLevel;
  assigned_region: string | null;
  held_out_count: number;
}

export interface ForecastRecord {
  id: string;
  case_id: string;
  target_metric: string;
  unit: string;
  horizon_days: number;
  history_length: number;
  status: EvidenceStatus;
  forecast_value?: number;
  baseline_persistence_value?: number;
  baseline_linear_value?: number;
  mae_estimate?: number;
  rmse_estimate?: number;
  ineligibility_reason?: string;
  is_experimental: boolean;
  created_at: string;
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
  fusion_status?: string;
  concordance_flags_count: number;
  orders_count?: number;
  lab_reports_count?: number;
}

export type ComponentType = 'LAB' | 'IMAGING' | 'CARDIAC' | 'PROCEDURE' | 'CONSULTATION' | 'PACKAGE';

export interface PackageComponent {
  name: string;
  type: ComponentType;
  lab_codes: string[];
  note?: string;
  includes_package?: string;
  included_components?: PackageComponent[];
}

export interface HealthPackage {
  id: string;
  name: string;
  kind: 'COMPREHENSIVE' | 'TOP_UP';
  category: string;
  description: string;
  components: PackageComponent[];
  lab_test_codes?: string[];
}

export interface ImagingModality {
  code: string;
  name: string;
  details?: string;
}

export interface ImagingServiceCategory {
  id: string;
  category: string;
  description: string;
  modalities: ImagingModality[];
}

export interface LabTestReference {
  code: string;
  name: string;
  unit: string;
  panel: string;
  kind: 'QUANTITATIVE' | 'QUALITATIVE' | 'INFORMATIONAL';
  ref_low?: number | null;
  ref_high?: number | null;
  ref_male?: [number, number] | null;
  ref_female?: [number, number] | null;
  organ_system?: string;
  options?: string[];
  expected?: string;
}

export type OrderStatus = 'ORDERED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';

export interface OrderedPackageRecord {
  id: number;
  case_id: number;
  package_id: string;
  package_name: string;
  category: string;
  status: OrderStatus;
  clinical_notes?: string | null;
  created_at: string;
}

export interface LabTestResult {
  code: string;
  test_name: string;
  unit: string;
  panel: string;
  organ_system: string;
  result_value: number | string;
  result_operator?: '=' | '<' | '>' | '<=' | '>=';
  ref_low?: number | null;
  ref_high?: number | null;
  bio_ref_interval: string;
  /** Where the interval behind the position came from. Quantitative positions use only the laboratory's own. */
  reference_source?: 'REPORTING_LABORATORY' | 'CATALOG_EXPECTED_RESULT' | 'NONE';
  /** A catalog default shown for orientation when the report printed no interval; never used for the position. */
  catalog_interval?: string | null;
  catalog_interval_source?: 'CATALOG_SEX_SPECIFIC_DEFAULT' | 'CATALOG_TYPICAL_ADULT_DEFAULT' | null;
  status: 'NORMAL' | 'LOW' | 'HIGH' | 'ABNORMAL' | 'INFO' | 'NO_REFERENCE' | 'INDETERMINATE';
}

export interface LabReportRecord {
  id: number;
  case_id: number;
  lab_name: string;
  report_title: string;
  sample_type: string;
  laboratory_method: string;
  collection_date?: string | null;
  collection_time?: string | null;
  reporting_time?: string | null;
  clinical_summary?: string | null;
  ordered_package_id?: number | null;
  source_file_id?: number | null;
  entry_method?: string;
  recorded_by_id?: number | null;
  patient_sex?: 'M' | 'F' | null;
  results: LabTestResult[];
  flag_counts: Record<string, number>;
  review_status: string;
  notice: string;
  created_at: string;
}

export type NavigationTab = 
  | 'DASHBOARD'
  | 'CASE_MANAGEMENT'
  | 'IMAGE_ANALYSIS'
  | 'ECG_ANALYSIS'
  | 'REPORT_NLP'
  | 'MULTIMODAL_FUSION'
  | 'REPORT_CONCORDANCE'
  | 'ANATOMICAL_3D'
  | 'TIMELINE_FORECASTING'
  | 'LONGITUDINAL_DIFF'
  | 'IEEE_VALIDATION'
  | 'HUMAN_REVIEW'
  | 'CLINICAL_CATALOG'
  | 'USER_MANAGEMENT'
  | 'UNIFIED_VIEW';

export interface AuditEventItem {
  id: number;
  user_id?: number;
  action: string;
  resource_type: string;
  resource_id?: string;
  details?: Record<string, unknown>;
  ip_address?: string;
  timestamp: string;
}

export interface AnatomicalAssetItem {
  id: number;
  name: string;
  system_name: string;
  asset_path: string;
  format: string;
  representation_level: string;
  is_available: boolean;
  notes?: string;
}

export interface SemanticReportDiffItem {
  finding: string;
  anatomy: string;
  classification:
    | 'NEWLY_REPORTED'
    | 'PRESENT_IN_BOTH'
    | 'EXPLICITLY_RESOLVED'
    | 'EXPLICITLY_WORSENED'
    | 'EXPLICITLY_IMPROVED'
    | 'CONTRADICTORY'
    | 'NOT_MENTIONED_IN_CURRENT'
    | 'NOT_MENTIONED_IN_PRIOR'
    | 'UNCERTAIN'
    | 'NOT_COMPARABLE';
  prior_state: {
    text: string;
    negation: string;
    temporality: string;
    exam_date: string;
  };
  current_state: {
    text: string;
    negation: string;
    temporality: string;
    exam_date: string;
  };
  confidence: number;
  clinical_rationale: string;
}

export interface NumericDeltaItem {
  metric_name: string;
  unit: string;
  prior_value: number;
  current_value: number;
  absolute_delta: number;
  percentage_delta: number | null;
  rate_per_day: number | null;
  trend_direction: 'STABLE' | 'INCREASING' | 'DECREASING';
  reference_range: string;
  is_comparable: boolean;
}

export interface ImageComparisonResult {
  status: string;
  is_comparable: boolean;
  prior_image_id?: number;
  prior_filename?: string;
  current_image_id?: number;
  current_filename?: string;
  modality_match?: boolean;
  anatomical_projection?: string;
  registration_method?: string;
  registration_error_pixels?: number;
  registration_tre_mm?: number;
  difference_modes_available?: string[];
  structural_change_detected?: boolean;
  change_region?: string;
  notice?: string;
  reason?: string;
}

export interface TwinStateDelta {
  prior_twin_state: {
    representation_level: string;
    active_mesh: string;
    highlight_region: string;
    status: string;
    color_hex: string;
    opacity: number;
  };
  current_twin_state: {
    representation_level: string;
    active_mesh: string;
    highlight_region: string;
    status: string;
    color_hex: string;
    opacity: number;
  };
  view_modes_supported: string[];
  timeline_horizons_available_days: number[];
}

export interface LongitudinalComparisonResponse {
  status: string;
  case_id: number;
  case_pseudonym: string;
  prior_examination: {
    id: number;
    date: string;
    modality: string;
    indication?: string;
  };
  current_examination: {
    id: number;
    date: string;
    modality: string;
    indication?: string;
  };
  interval_days: number;
  semantic_report_diff: SemanticReportDiffItem[];
  numeric_deltas: NumericDeltaItem[];
  image_comparison: ImageComparisonResult;
  twin_state_delta: TwinStateDelta;
  notice: string;
  reason?: string;
}

export interface IeeeEquationManifestItem {
  equation_id: string;
  section: string;
  title: string;
  formula: string;
  implementation_module: string;
  task: string;
  status: string;
  evaluation_type: string;
  measured_metric: Record<string, unknown>;
  clinical_trial_status?: string;
}

export interface IeeeValidationResponse {
  framework: string;
  manuscript_citation: string;
  status: string;
  database_counts: {
    cases: number;
    findings: number;
    fusion_records: number;
    forecast_records: number;
  };
  equations: IeeeEquationManifestItem[];
  research_notice: string;
}

