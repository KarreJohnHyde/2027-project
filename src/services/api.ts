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

import type { ReferenceReport, ReferenceSummary } from '../types/privateReferences';

/** Where earlier versions kept a sign-in key in localStorage; read once to move the browser to a cookie session, then removed. */
const LEGACY_TOKEN_KEY = 'medtwin_token';
const LEGACY_VISITOR_KEY = 'medtwin.visitor';
/** Sent on every request from this app. The server requires it before a cookie-authenticated write (a CSRF guard). */
export const CLIENT_HEADER = 'X-MedTwin-Client';
const CLIENT_NAME = 'web';
const configuredOrigin = (import.meta.env.VITE_MEDTWIN_API_URL as string | undefined)
  ?.trim()
  .replace(/\/+$/, '');
/** The session cookie travels with same-origin requests; a separately hosted API needs it sent explicitly. */
export const API_CREDENTIALS: RequestCredentials = configuredOrigin ? 'include' : 'same-origin';

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
  /** A "Try the demo" account: temporary sign-in, fictional sample case. */
  is_guest?: boolean;
  /** An entry-page account: no password; this browser keeps its key. */
  is_visitor?: boolean;
  age?: number | null;
  gender?: string | null;
  stated_role?: string | null;
  created_at: string;
}

/** A value from ENTRY_ROLE_GROUPS (src/data/entryRoles.ts): a clinical role, specialty or department. Grants nothing. */
export type EntryRole = string;
export type EntryGender = 'female' | 'male' | 'other' | 'prefer_not_to_say';

/** The entry page. The role is self-described and grants no privileges. */
export interface VisitorEntry {
  name: string;
  age?: number | null;
  gender?: EntryGender | null;
  role: EntryRole;
}

export type BrowserSessionKind = 'VISITOR' | 'GUEST' | 'ACCOUNT';

/** A signed-in browser. The session itself is an HttpOnly cookie the page cannot read; this is the profile only. */
export interface BrowserSession {
  user: User;
  session: { kind: BrowserSessionKind; expires_at: string; rotated?: boolean };
  /** This installation runs as an open workspace: no sign-in, every browser opens the shared workspace. */
  open_workspace?: boolean;
}

export interface GuestSession extends BrowserSession {
  case_id: number;
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
  result_ref: { inference_run_id?: number; run_status?: string; analysis_status?: string; models_with_outputs?: number; results?: Array<{ model_id: string; run_id: number; status: string; reason: string | null }> } | null;
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

/** One sampled frame of an endoscopy video and what the still-image model gave for it. */
export interface VideoFrameRecord {
  frame_index: number;
  time_s: number;
  quality: { brightness: number; dark_fraction: number; sharpness_laplacian_variance: number };
  status: 'SCORED' | 'REFUSED_BY_APPLICABILITY_CHECK';
  reason?: string;
  result?:
    | { kind: 'segmentation'; area_px: number; area_fraction: number; segments: Array<{ class_index: number; segment: string; area_px: number; rle: CocoRle }>; foreground_label?: string; image_size: [number, number] }
    | { kind: 'classification'; top_class: string; top_probability: number; top_classes: Array<{ class: string; probability: number }> }
    | { kind: 'detection'; boxes_above_threshold: number; boxes: DetectionBox[]; class?: string; image_size: [number, number] };
}

export interface VideoTimelineOutput {
  type: 'video_frame_timeline';
  video: VideoMetadata;
  model_id: string;
  sampling: { interval_s: number; max_frames: number; requested_frames: number; decoded_frames: number; method?: string; variable_frame_rate_suspected?: boolean };
  frames: VideoFrameRecord[];
  scored_frames: number;
  refused_frames: number;
  coordinate_space: string;
  semantics: string;
  summary?: { frames_with_mask?: number; first_time_with_mask_s?: number | null; label?: string | null; top_class_counts?: Record<string, number> };
  /** Marked regions linked between sampled frames (not evaluated on video). */
  tracking?: { method: string; status: string; semantics: string; tracks: Array<{ track_id: number; frames_marked: number; first_time_s: number; last_time_s: number }> };
  /** Runs of the same per-frame top class (classification models). */
  class_runs?: { status: string; semantics: string; top_class_changes: number; runs: Array<{ top_class: string; first_time_s: number; last_time_s: number; frames: number }> };
}

export interface VideoMetadata {
  fps: number;
  frame_count: number;
  duration_s: number;
  width: number;
  height: number;
  codec: string;
}

/** Per-slice labels of a neighbouring-slice model on an ordered DICOM series. */
export interface SeriesSliceOutput {
  type: 'series_slice_multilabel';
  slices: Array<{ slice_index: number; upload_id: number | null; applicability_score: number; status: 'ANALYSED' | 'REFUSED_OUT_OF_DISTRIBUTION';
    labels?: Array<{ label: string; probability: number; threshold: number; at_or_above_threshold: boolean }>; positive_labels?: string[] }>;
  slices_analysed: number;
  slices_refused: number;
  series_level: { label: string; probability: number; threshold: number; at_or_above_threshold: boolean; slice_index: number; coverage: string;
    complete_coverage: boolean; rule: string };
  slices_with_positive_labels: number[];
  window: { center: number; width: number; source: string };
  applicability: { limit: number; calibration: string; rule: string };
  numeric_precision: string;
  probability_semantics: string;
}

export type ResearchOutput =
  | VideoTimelineOutput
  | SeriesSliceOutput
  | {
      type: 'classification';
      clinical_metadata?: { fields: string[]; values: { age: number; region: string; gender?: string }; source: string; preprocessing_version: string; imputed_fields: string[] };
      classes: Array<{ class: string; probability: number }>;
      top_class: string;
      top_probability: number;
      probability_semantics: string;
      dicom_frame?: DicomFrameConversion;
    }
  | {
      type: 'multilabel_classification';
      labels: Array<{ label: string; probability: number; threshold: number; at_or_above_threshold: boolean }>;
      positive_labels: string[];
      numeric_precision: string;
      probability_semantics: string;
      threshold_semantics: string;
      dicom_frame?: DicomFrameConversion;
    }
  | {
      type: 'detection';
      class: string;
      coordinate_space: string;
      dicom_frame?: DicomFrameConversion;
      image_size: [number, number];
      display_score_threshold: number;
      boxes: DetectionBox[];
      score_semantics: string;
      /** EXIF orientation tag applied before inference; absent on runs made before orientation handling. */
      exif_orientation_applied?: number;
    }
  | {
      type: 'segmentation';
      coordinate_space: string;
      dicom_frame?: DicomFrameConversion;
      exif_orientation_applied?: number;
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
      /** Fusion models: the age and sex used and where they came from. */
      demographic_inputs?: { age_years: number; sex: 'M' | 'F'; sources: string[]; warnings: string[]; encoding: string };
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
    }
  | {
      /** Ejection fraction from an echocardiography video: the mean of clip estimates (research regression). */
      type: 'regression';
      target: string;
      unit: string;
      ef_percent: number;
      clip_ef_percent: number[];
      clip_starts: number[];
      clip_frames: number;
      frame_period: number;
      band: string | null;
      numeric_precision: string;
      estimate_semantics: string;
    };

/** Inputs some research models need besides the upload itself. */
export interface ResearchRunOptions {
  /** WFDB signal file (.dat) uploaded alongside a .hea header. */
  companionUploadId?: ResourceId;
  /** CSV ECG records carry no amplitude unit. */
  amplitudeUnit?: 'mV' | 'uV';
  /** Demographic-fusion ECG models: when omitted, the case's latest reviewed demographics are used. */
  ageYears?: number;
  sex?: 'M' | 'F';
  /** Multi-frame DICOM uploads to a 2-D model: the frame to analyse (0-based). */
  frameIndex?: number;
  clinicalFeatures?: { age: number; region: string; gender?: 'MALE' | 'FEMALE' };
}

/** How a DICOM frame was converted to the 8-bit raster a 2-D model read (absent for PNG/JPEG/BMP runs). */
export interface DicomFrameConversion {
  source_container: 'DICOM';
  modality_tag: string | null;
  photometric_interpretation: string;
  frame_index: number;
  frame_count: number;
  bits_stored: number;
  pixel_grid: string;
  window?: { source: string; center?: number; width?: number; low?: number; high?: number; function: string; basis?: string; monochrome1_inverted: boolean };
  colour?: string;
  warnings: string[];
}

export interface ResearchRun extends AnalysisJob {
  research_output: ResearchOutput | null;
  research_provenance: Record<string, unknown>;
  /** The finding a reviewer confirms or rejects; the run's output itself never changes. */
  finding_id?: number | null;
  latest_review?: {
    review_id: number;
    review_status: HumanReviewDecision;
    reviewer_id: number | null;
    reviewer_comments: string | null;
    reviewed_at: string | null;
    original_output_preserved: boolean;
    reviewer_role?: string | null;
    /** Any account may review; this says whether the reviewer was a verified clinician. */
    reviewer_verified_professional?: boolean;
  } | null;
}

export type CocoRle = { size: [number, number]; counts: string };

export interface VolumeSurfaces {
  run_id: number;
  frame: 'VOXEL_GRID_SCALED_MM';
  voxel_spacing_mm: [number, number, number];
  extent_mm: [number, number, number];
  registered_to_atlas: false;
  anatomy_link_level: string;
  semantics: string;
  surfaces: Array<{ class_index: number; structure: string; voxels: number; volume_ml: number; triangles: number; vertices_mm: number[]; faces: number[] }>;
}

/** A reference mask attached to an image upload (GROUND_TRUTH layer), kept apart from model output. */
/** Whole-slide image description (pyramidal TIFF) as returned in imaging metadata. */
export interface WsiDescription {
  format: string;
  dimensions: [number, number];
  levels: Array<{ level: number; width: number; height: number; downsample: number; tiled: boolean; tile: [number, number] | null }>;
  microns_per_pixel: number | null;
  objective_magnification: number | null;
}

export interface WsiTissueGrid {
  upload_id: number;
  tile_size_px: number;
  tissue_tiles: Array<[number, number]>;
  tissue_tile_count: number;
  total_tiles: number;
  tissue_fraction_of_thumbnail: number;
  rule: string;
  semantics: string;
}

/** Reviewer corrections of a volumetric run, per axial plane, with the corrected volume per structure. */
export interface VolumeCorrectionSummary {
  semantics: string;
  structures: Array<{ structure: string; model_voxels: number; corrected_voxels: number; model_volume_ml: number; corrected_volume_ml: number; slices_corrected: number }>;
  corrected_slices: Array<{ slice_index: number; structure: string; annotation_id: number; voxels_added: number; voxels_removed: number; dice_with_model: number; source_detail: string; created_at: string | null }>;
}

/** Agreement between two runs on one upload (server: app/services/run_agreement.py). Fields depend on `kind`. */
export interface RunAgreement {
  run_ids: [number, number];
  models: [string, string];
  comparison: 'MODEL_VS_MODEL_AGREEMENT';
  semantics: string;
  kind: 'segmentation' | 'detection' | 'classification' | 'multilabel_classification' | 'volume_segmentation';
  foreground_dice?: number;
  foreground_iou?: number;
  area_px?: [number, number];
  shared_classes?: Record<string, { dice: number; iou: number } | [number, number]>;
  matched?: number;
  only_first?: number;
  only_second?: number;
  mean_matched_iou?: number | null;
  pairs?: Array<{ first_box: number[]; second_box: number[]; iou: number }>;
  only_first_boxes?: number[][];
  only_second_boxes?: number[][];
  top_classes?: [string, string];
  same_top_class?: boolean;
  positive_labels?: [string[], string[]];
  shared_labels?: Record<string, { probabilities: [number, number]; at_or_above_threshold: [boolean, boolean] }>;
  shared_structures?: Record<string, { volume_ml: [number, number]; difference_ml: number }>;
  note?: string;
}

/** Per-image agreement of a detection run's boxes (above its display threshold) with reference boxes, matched at IoU >= 0.5. */
export interface BoxComparison {
  run_id: number;
  comparison: 'PER_IMAGE_BOX_AGREEMENT';
  semantics: string;
  reference: { annotation_id: number; source: string; source_detail: string; class_name: string };
  display_score_threshold: number | null;
  matched: number;
  model_only: number;
  reference_only: number;
  precision: number | null;
  recall: number | null;
  mean_matched_iou: number | null;
  pairs: Array<{ model_box: number[]; score: number; reference_box: number[]; iou: number }>;
  model_only_boxes: Array<{ model_box: number[]; score: number; best_iou: number }>;
  reference_only_boxes: number[][];
}

export interface ReferenceAnnotation {
  id: number;
  file_id: number;
  kind: 'SEGMENTATION_MASK' | 'BOUNDING_BOXES' | 'VOLUME_SLICE_CORRECTION';
  /** VOLUME_SLICE_CORRECTION only: the axial index plane edited. */
  slice_index?: number | null;
  /** BOUNDING_BOXES only: [x1, y1, x2, y2] in source image pixels. */
  boxes?: number[][] | null;
  /** REVIEWER_CORRECTION: the model's mask edited by a reviewer, anchored to that output (not independent ground truth). */
  layer: 'GROUND_TRUTH' | 'REVIEWER_CORRECTION';
  source: 'DATASET_PUBLISHER_ANNOTATION' | 'INDEPENDENT_EXPERT_ANNOTATION' | 'REVIEWER_CORRECTION_OF_MODEL_OUTPUT';
  derived_from_run_id: number | null;
  source_label: string;
  source_detail: string;
  class_name: string;
  mask_filename: string;
  mask_sha256: string;
  binarize_threshold: number;
  image_size: [number, number];
  rle: CocoRle;
  area_px: number;
  created_by_id: number | null;
  created_at: string | null;
}

/** Per-image agreement of one run's mask with one reference annotation (not a performance estimate). */
export interface ReferenceComparison {
  run_id: number;
  comparison: 'PER_IMAGE_AGREEMENT';
  semantics: string;
  compared: string;
  /** True only when a reviewer correction is compared with the run it was made from. */
  correction_of_this_run?: boolean;
  reference: { annotation_id: number; source: string; source_detail: string; class_name: string };
  dice: number;
  iou: number;
  pixel_precision: number | null;
  pixel_recall: number | null;
  reference_area_px: number;
  predicted_area_px: number;
  hd95_px: number | null;
  assd_px: number | null;
  regions: { agreement: CocoRle; model_only: CocoRle; reference_only: CocoRle };
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
  inference_input?: 'image_2d' | 'ecg_12lead' | 'tabular_survival' | 'volume_nifti' | 'echo_video' | 'head_ct_series';
  run_scope?: 'RESEARCH' | 'EXPLORATORY_ONLY';
  dataset_license: string | null;
  model_card_path: string | null;
  evaluation_report_path: string | null;
  checkpoint_sha256: string | null;
  output_status: string;
  held_out_evaluation?: Record<string, unknown>;
  /** Inputs besides the upload that a fusion model takes (e.g. age_years, sex). */
  demographic_inputs?: string[];
  requires_clinical_features?: boolean;
  clinical_metadata_contract?: { age_range: [number, number]; categories: { gender: string[]; region: string[] } } | null;
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
  /** True for statements of an earlier analysis of a report that was analysed again (returned only on request). */
  analysis_superseded?: boolean;
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
  /** The atlas name the documented region resolves to (the region text is as read). */
  atlas_structure_name?: string | null;
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
  highlight: { organ_schematic: boolean; verified_structures: string[]; spatially_registered: string[]; documented_structures?: string[]; verified_structure_names?: string[]; documented_structure_names?: string[] };
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
  input_assessment?: FilmAssessment;
  /** Whole-slide images (container WSI) only. */
  wsi?: WsiDescription;
  upload_id: number;
  filename: string;
  sha256: string;
  container: string;
  dimensions: Array<number | null>;
  /** Raster images: the EXIF orientation tag (1 = stored upright); dimensions are as displayed. */
  exif_orientation?: number;
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
  /** Cine series: images per slice position (cardiac phases), their median trigger times and the phase assembled. */
  cardiac_phases?: number;
  phase_trigger_times_ms?: number[];
  phase?: number;
  phase_semantics?: string;
  modality_tags?: string[];
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
  /** peak_xy and region_box_xyxy (source pixels) exist on runs made since the localisation evaluation. */
  attention: Array<{ finding: string; zones: Record<string, number>; outside_lungs: number; top_zone: string | null; grid: number[][]; peak_xy?: [number, number] | null; region_box_xyxy?: [number, number, number, number] | null; region_rule?: string }>;
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
  /** Attention peak vs radiologist boxes (NIH ChestX-ray14), when evaluated. */
  attention_localisation?: {
    overall: { boxes: number; pointing_hit_rate: number; chance_hit_rate: number; mean_iou: number };
    per_finding: Record<string, { boxes: number; pointing_hit_rate: number; chance_hit_rate: number; mean_iou: number }>;
    dataset: string; rule: string; caveats: string[]; report_path: string;
  } | null;
}

/** TotalSegmentator (third-party CT organ segmentation): availability, publisher and the local check on LUNA16. */
export interface CtOrganModelCard {
  model_id: string;
  display_name: string;
  output_status: string;
  available: boolean;
  status: string;
  reason?: string;
  fast?: boolean;
  full_resolution?: boolean;
  device?: string;
  publisher: { name: string; version: string; licence: string; citation: string; training_data: string };
  local_external_check: {
    reference: string;
    scans: number;
    mode: string;
    dice_lungs: { mean: number; ci95: [number, number]; median: number; min: number };
    note: string;
  } | null;
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
  evidence_synthesis?: EvidenceSynthesis | null;
  paired_data_validated: boolean;
  abstention_reason: string | null;
  notice: string;
}

export interface FilmAssessment {
  version: string;
  source_type: string;
  inference_eligibility: string;
  model_compatibility: string;
  classification_basis: string;
  limitations: string[];
  source_annotations: { coloured_marks_suspected: boolean; is_ai_mask: boolean };
  panels: Array<{ panel_id: number; row: number; column: number; bbox_xyxy: number[] }>;
}

export interface EvidenceSynthesis {
  version: string;
  status: string;
  summary: string;
  concordance: string;
  evidence_mask: Record<string, number>;
  model_output_mask: Record<string, number>;
  report_findings: Array<{
    entity: string; assertion: string; laterality: string | null; anatomical_site: string | null;
    review_status: string; anatomical_association: string; examination_id: number | null; atlas_structure_id: string | null;
    sources: Array<{ upload_id: number; statement_id: number; page: number | null; sha256: string;
      source_span: string; normalized_span: string; review_status: string }>;
  }>;
  model_findings: Array<{ model_id: string; model_version: string; modality: string; label: string; run_id: number; run_ids: number[]; upload_id: number; upload_ids: number[]; review_status: string; validation_status: string }>;
  abstentions: Array<{ upload_id: number; model_id: string; reason: string; status: string; attempt_count: number; run_ids: number[]; job_ids: number[] }>;
  contradictions: Array<{ type: string; resolution: string }>;
  limitations: string[];
  /** Earlier analyses of re-analysed reports; kept as history, excluded from these findings. */
  superseded_report_run_ids?: number[];
  /** Secondary NLP model readings of the same report text; listed, not counted as findings. */
  secondary_model_mentions?: Array<{ entity: string; assertion: string; laterality: string | null; anatomical_site: string | null;
    category: string; extractor_versions: string[]; statement_ids: number[] }>;
}

export interface CaseWorkflow {
  version: string; case_id: number; generated_at: string;
  mode: "EMPTY" | "COMBINED" | "DOCUMENT_ONLY" | "SCAN_ONLY";
  evidence_mask: Record<string, number>; model_output_mask: Record<string, number>;
  pending_report_upload_ids: number[]; active_report_job_ids: number[]; unlinked_upload_ids: number[];
  stages: Array<{ id: string; title: string; status: string; detail: string; path: string; source_upload_ids: number[] }>;
  sources: Array<{ upload_id: number; sha256: string; modality: string; examination_id: number | null; latest_run_id: number | null; latest_run_status: string }>;
  examinations: Array<{ id: number; date: string; modality: string; upload_ids: number[] }>;
  forecast_evaluation_ids: number[]; clinical_validation: string;
}

export interface BaselineForecast {
  id: number; predicted_value: number | null; unit: string; observations_count: number;
  ineligibility_reason: string | null; notice: string;
  chronological_series: Array<{ date: string; value: number; upload_id: number; source_span: string }>;
  baseline_analysis: { status: string; method: string; version: string; validation_status: string;
    forecast_date: string | null; interval_reason: string;
    observed_change: { absolute: number; from_date: string; to_date: string; clinical_direction: string } | null;
    backtest: { mae: number; rmse: number; folds: unknown[]; maximum_evaluated_horizon_days: number } | null };
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
  original_value?: number;
  correction_review_id?: number | null;
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
  correction_review_id?: number | null;
  correction_state?: string;
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
  evidence_view?: string;
  excluded_evidence?: Array<{ kind: string; id: number; source_file_id: number; reason: string }>;
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
  /** Third-party models served through their own endpoint rather than the generic research route. */
  inference_route?: string;
  /** A narrower local check than a held-out evaluation (e.g. one organ, or attention localisation only). */
  local_evaluation?: { scope: string; dataset: string; headline: string; report_path: string };
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

const UNAVAILABLE_STATUSES = new Set([0, 502, 503, 504]);

/** The server could not be reached or is not answering (no network, proxy without a backend, gateway timeout). */
export function isServerUnavailable(error: unknown): boolean {
  return error instanceof ApiError && UNAVAILABLE_STATUSES.has(error.status);
}

const UNREACHABLE_MESSAGE = 'The MedTwin server could not be reached. Check the connection, or start the server, then try again.';

function resourcePath(id: ResourceId): string {
  return encodeURIComponent(String(id));
}

function readLegacyToken(): string | null {
  try {
    const direct = window.localStorage.getItem(LEGACY_TOKEN_KEY);
    if (direct) return direct;
    const visitor = JSON.parse(window.localStorage.getItem(LEGACY_VISITOR_KEY) ?? 'null') as { token?: unknown } | null;
    return visitor && typeof visitor.token === 'string' ? visitor.token : null;
  } catch {
    return null;
  }
}

function clearLegacyKeys(): void {
  try {
    window.localStorage.removeItem(LEGACY_TOKEN_KEY);
    window.localStorage.removeItem(LEGACY_VISITOR_KEY);
  } catch {
    // Storage may be blocked; there is then nothing stored to remove.
  }
}

const RETRY_DELAYS_MS = [500, 1500];

/** Retry a call that is safe to repeat (a read, or a write carrying an Idempotency-Key) while the server is unavailable. */
async function withRetry<T>(call: () => Promise<T>): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await call();
    } catch (error) {
      if (!isServerUnavailable(error) || attempt >= RETRY_DELAYS_MS.length) throw error;
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
    }
  }
}

/** A fresh key for one press of "Enter MedTwin" or "Try Demo"; retries of that press reuse it. */
export function newIdempotencyKey(prefix: string): string {
  // getRandomValues, unlike randomUUID, also exists on plain-http pages such as a LAN address.
  const random = Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte: number) => byte.toString(16).padStart(2, '0')).join('');
  return `${prefix}-${random}`;
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
  /**
   * A bearer token held in memory only, for a caller that sets one explicitly. The web app itself signs in with the
   * HttpOnly session cookie, which scripts on the page cannot read, so nothing secret is kept in browser storage.
   */
  private token: string | null = null;

  setToken(token: string | null): void {
    this.token = token;
  }

  getToken(): string | null {
    return this.token;
  }

  /** Headers every request from this app carries: the client marker and, if one was set, the in-memory bearer token. */
  authHeaders(): Record<string, string> {
    return { [CLIENT_HEADER]: CLIENT_NAME, ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}) };
  }

  /** fetch with the session cookie, the client header and network failures reported as "server unavailable". */
  private async send(url: string, options: RequestInit, headers: Headers): Promise<Response> {
    headers.set(CLIENT_HEADER, CLIENT_NAME);
    try {
      return await fetch(url, { ...options, headers, credentials: API_CREDENTIALS });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw error;
      throw new ApiError(0, UNREACHABLE_MESSAGE);
    }
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

    const response = await this.send(`${API_V1_BASE}${endpoint}`, options, headers);
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
      // Likewise a 502/503/504 page from a proxy or gateway: the server is not answering.
      const gatewayPage = UNAVAILABLE_STATUSES.has(response.status) && typeof detail !== 'string';
      const message = rejectedBeforeApi
        ? 'The file is larger than this server accepts, so it was rejected before reaching MedTwin (HTTP 413).'
        : gatewayPage
          ? `The MedTwin server is not answering (HTTP ${response.status}). Try again in a moment.`
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
    const response = await this.send(`${API_V1_BASE}${endpoint}`, body === undefined ? {} : { method: 'POST', body: JSON.stringify(body) }, headers);
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

  /**
   * This browser's sign-in, restored from its HttpOnly session cookie: null when there is none (the entry page is
   * shown). Throws an unavailable ApiError (see isServerUnavailable) when the server cannot be reached.
   */
  async restoreSession(): Promise<BrowserSession | null> {
    try {
      return await withRetry(() => this.request<BrowserSession>('/auth/session', { cache: 'no-store' }, false));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  }

  /**
   * A browser that kept a sign-in key from an earlier version moves to a cookie session once: the server checks that
   * key exactly as any bearer request, then the stored key is removed. Null when there is no key or it is no longer
   * valid; an unavailable server keeps the key for the next visit.
   */
  async claimLegacySession(): Promise<BrowserSession | null> {
    const legacy = typeof window === 'undefined' ? null : readLegacyToken();
    if (!legacy) return null;
    try {
      const claimed = await this.request<BrowserSession>('/auth/session/claim', { method: 'POST', headers: { Authorization: `Bearer ${legacy}` } }, false);
      clearLegacyKeys();
      return claimed;
    } catch (error) {
      if (!isServerUnavailable(error)) clearLegacyKeys();
      if (error instanceof ApiError && [400, 401, 403].includes(error.status)) return null;
      throw error;
    }
  }

  /** A one-time sign-in link (issued on the server's machine) opens a registered account in this browser. */
  redeemSignInLink(code: string): Promise<BrowserSession> {
    return this.request<BrowserSession>('/auth/link', { method: 'POST', body: JSON.stringify({ code }) }, false);
  }

  /** An existing password account (the separate account page, not the entry page) signs this browser in by cookie. */
  login(username: string, password: string): Promise<BrowserSession> {
    return this.request<BrowserSession>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }, false);
  }

  /**
   * The entry page: a name and a self-described role (age and gender optional) make a new visitor profile, remembered
   * by this browser's session cookie. Retries of one submission share its idempotency key, so a network retry
   * never makes a second profile.
   */
  enterWorkspace(entry: VisitorEntry, idempotencyKey: string): Promise<BrowserSession> {
    return withRetry(() => this.request<BrowserSession>(
      '/auth/enter',
      { method: 'POST', body: JSON.stringify(entry), headers: { 'Idempotency-Key': idempotencyKey } },
      false,
    ));
  }

  /** Try Demo: a temporary guest account with one fictional sample case, isolated from every other account. */
  startGuestDemo(idempotencyKey: string): Promise<GuestSession> {
    return withRetry(() => this.request<GuestSession>('/auth/guest', { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey } }, false));
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

  /** Sign this browser out: the server revokes the session and clears its cookie. False when the server could not be reached. */
  async logout(): Promise<boolean> {
    this.setToken(null);
    if (typeof window !== 'undefined') clearLegacyKeys();
    try {
      await this.request<void>('/auth/logout', { method: 'POST' }, false);
      return true;
    } catch (error) {
      return !isServerUnavailable(error);
    }
  }

  getMe(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  getPrivateReferences(): Promise<ReferenceSummary[]> {
    return this.request<ReferenceSummary[]>('/private-references', { cache: 'no-store' });
  }

  getPrivateReference(id: string): Promise<ReferenceReport> {
    return this.request<ReferenceReport>(`/private-references/${encodeURIComponent(id)}`, { cache: 'no-store' });
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

  getResearchJobs(): Promise<{ available: boolean; observed_at: string; scope: string; notice: string;
    jobs: Array<{ id: string; label: string; status: string; last_event_at: string | null; completed: number | null; expected: number | null; failed: number | null;
      transfer?: { received_bytes: number; expected_bytes: number; verified: false } | null }> }> {
    return this.request('/system/research-jobs');
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
      request.withCredentials = API_CREDENTIALS === 'include';
      for (const [name, value] of Object.entries(this.authHeaders())) request.setRequestHeader(name, value);
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded / event.total);
      };
      request.onerror = () => reject(new ApiError(0, 'The upload stopped: the MedTwin server could not be reached. Try again.'));
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

  getCaseQueuedJobs(caseId: ResourceId): Promise<QueuedJob[]> {
    return this.request<QueuedJob[]>(`/cases/${resourcePath(caseId)}/jobs`, { cache: 'no-store' });
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

  selectUploadModel(uploadId: ResourceId, options: { declared_input_type?: string; task: string; target?: string; frame_index?: number }): Promise<{
    status: string; reason: string; selected_model_id: string | null; declared_input_type?: string;
    notice?: string; candidates: Array<{ model_id: string; display_name: string }>; rejected: Array<{ model_id: string; reasons: string[] }>;
  }> {
    return this.request(`/uploads/${resourcePath(uploadId)}/model-selection`, { method: 'POST', body: JSON.stringify(options) });
  }

  getResearchLearning(): Promise<{
    notice: string; clinical_activation: boolean; strategies: string[];
    benchmark: { dataset: string; status: string; labeled_rows: number; unlabeled_rows: number; pseudo_labeled_rows: number;
      metrics: { supervised_seed: { accuracy: number }; semi_supervised: { accuracy: number }; offline_workflow_policy: { coverage: number; selective_accuracy: number | null } } } | null;
  }> {
    return this.request('/research-learning');
  }

  getResearchModelEvaluation(modelId: string): Promise<{ model_id: string; task: string; gate: { allowed: boolean; blockers: string[] }; report: Record<string, unknown> }> {
    return this.request(`/research-models/${encodeURIComponent(modelId)}/evaluation`);
  }

  /** Earlier research runs on one upload, newest first, each with its latest review. */
  listResearchRuns(uploadId: ResourceId): Promise<{ file_id: number; runs: ResearchRun[] }> {
    return this.request(`/uploads/${resourcePath(uploadId)}/research-inference`);
  }

  getVideoMetadata(uploadId: ResourceId): Promise<VideoMetadata & { file_id: number; filename: string }> {
    return this.request(`/uploads/${resourcePath(uploadId)}/video`);
  }

  /** One decoded video frame as an object URL (the caller revokes it). */
  async getVideoFrameUrl(uploadId: ResourceId, index: number): Promise<string> {
    const { blob } = await this.requestBlob(`/uploads/${resourcePath(uploadId)}/video/frame?index=${index}`);
    return URL.createObjectURL(blob);
  }

  /** Scores sampled frames of an endoscopy video with a still-image research model. */
  async runVideoFrameAnalysis(uploadId: ResourceId, modelId: string, intervalS: number, maxFrames: number, onQueued?: (job: QueuedJob) => void): Promise<ResearchRun> {
    const response = await this.request<ResearchRun | { queued_job: QueuedJob }>(`/uploads/${resourcePath(uploadId)}/video-frame-analysis`, {
      method: 'POST',
      body: JSON.stringify({ model_id: modelId, interval_s: intervalS, max_frames: maxFrames, attest_gi_endoscopy_video: true }),
    });
    if (!('queued_job' in response)) return response;
    return this.getResearchRun(await this.waitForJob(response.queued_job, onQueued));
  }

  listReferenceAnnotations(uploadId: ResourceId): Promise<{ file_id: number; annotations: ReferenceAnnotation[] }> {
    return this.request(`/uploads/${resourcePath(uploadId)}/reference-annotations`);
  }

  addReferenceAnnotation(uploadId: ResourceId, mask: File, fields: { source: ReferenceAnnotation['source']; sourceDetail: string; className: string }): Promise<ReferenceAnnotation> {
    const form = new FormData();
    form.append('mask', mask);
    form.append('source', fields.source);
    form.append('source_detail', fields.sourceDetail);
    form.append('class_name', fields.className);
    return this.request<ReferenceAnnotation>(`/uploads/${resourcePath(uploadId)}/reference-annotations`, { method: 'POST', body: form });
  }

  /** Saves a reviewer's edit of a 2-D segmentation run's mask; the run itself is unchanged. */
  addMaskCorrection(runId: ResourceId, mask: Blob, fields: { className: string; note: string }): Promise<ReferenceAnnotation & { comparison_with_run: ReferenceComparison }> {
    const form = new FormData();
    form.append('mask', mask, 'correction.png');
    form.append('class_name', fields.className);
    form.append('note', fields.note);
    return this.request<ReferenceAnnotation & { comparison_with_run: ReferenceComparison }>(`/research-inference/${resourcePath(runId)}/mask-corrections`, { method: 'POST', body: form });
  }

  compareWithReference(runId: ResourceId, annotationId: ResourceId): Promise<ReferenceComparison> {
    return this.request<ReferenceComparison>(`/research-inference/${resourcePath(runId)}/reference-comparison/${resourcePath(annotationId)}`);
  }

  /** Reference boxes (JSON or YOLO text, in the image's pixels) as a GROUND_TRUTH layer. */
  addReferenceBoxes(uploadId: ResourceId, boxes: File, fields: { source: ReferenceAnnotation['source']; sourceDetail: string; className: string }): Promise<ReferenceAnnotation> {
    const form = new FormData();
    form.append('boxes', boxes);
    form.append('source', fields.source);
    form.append('source_detail', fields.sourceDetail);
    form.append('class_name', fields.className);
    return this.request<ReferenceAnnotation>(`/uploads/${resourcePath(uploadId)}/reference-boxes`, { method: 'POST', body: form });
  }

  /** Saves a reviewer's edit of one axial plane of a volumetric run's mask; the run itself is unchanged. */
  addVolumeSliceCorrection(runId: ResourceId, sliceIndex: number, mask: Blob, fields: { className: string; note: string }): Promise<ReferenceAnnotation & { summary: VolumeCorrectionSummary }> {
    const form = new FormData();
    form.append('mask', mask, `slice-${sliceIndex}.png`);
    form.append('slice_index', String(sliceIndex));
    form.append('class_name', fields.className);
    form.append('note', fields.note);
    return this.request<ReferenceAnnotation & { summary: VolumeCorrectionSummary }>(`/research-inference/${resourcePath(runId)}/volume-slice-corrections`, { method: 'POST', body: form });
  }

  getVolumeSliceCorrections(runId: ResourceId): Promise<VolumeCorrectionSummary & { run_id: number }> {
    return this.request(`/research-inference/${resourcePath(runId)}/volume-slice-corrections`);
  }

  /** Model-versus-model agreement on one upload; neither run is ground truth. */
  compareRuns(runId: ResourceId, otherRunId: ResourceId): Promise<RunAgreement> {
    return this.request<RunAgreement>(`/research-inference/${resourcePath(runId)}/agreement/${resourcePath(otherRunId)}`);
  }

  compareWithReferenceBoxes(runId: ResourceId, annotationId: ResourceId): Promise<BoxComparison> {
    return this.request<BoxComparison>(`/research-inference/${resourcePath(runId)}/reference-comparison/${resourcePath(annotationId)}`);
  }

  async runResearchModel(uploadId: ResourceId, modelId: string, declaredInputType: string, onQueued?: (job: QueuedJob) => void, options: ResearchRunOptions = {}): Promise<ResearchRun> {
    const response = await this.request<ResearchRun | { queued_job: QueuedJob }>(`/uploads/${resourcePath(uploadId)}/research-inference`, {
      method: 'POST',
      body: JSON.stringify({
        model_id: modelId,
        declared_input_type: declaredInputType,
        ...(options.companionUploadId !== undefined ? { companion_upload_id: options.companionUploadId } : {}),
        ...(options.amplitudeUnit ? { amplitude_unit: options.amplitudeUnit } : {}),
        ...(options.ageYears !== undefined ? { age_years: options.ageYears } : {}),
        ...(options.sex ? { sex: options.sex } : {}),
        ...(options.frameIndex !== undefined ? { frame_index: options.frameIndex } : {}),
        ...(options.clinicalFeatures ? { clinical_features: options.clinicalFeatures } : {}),
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

  assembleDicomSeries(caseId: ResourceId, uploadIds: number[], phase: number | null = null): Promise<DicomSeriesReport> {
    return this.request<DicomSeriesReport>(`/cases/${resourcePath(caseId)}/dicom-series/assemble`, {
      method: 'POST', body: JSON.stringify({ upload_ids: uploadIds, ...(phase !== null ? { phase } : {}) }),
    });
  }

  async renderDicomSeries(caseId: ResourceId, uploadIds: number[], plane: { axis: 'axial' | 'coronal' | 'sagittal'; index: number | null; center?: number; width?: number; phase?: number | null }): Promise<{ url: string; info: SeriesRenderInfo }> {
    const { blob, headers } = await this.requestBlob(`/cases/${resourcePath(caseId)}/dicom-series/render`, {
      upload_ids: uploadIds, axis: plane.axis, ...(plane.index !== null ? { index: plane.index } : {}),
      ...(plane.center !== undefined && plane.width !== undefined ? { center: plane.center, width: plane.width } : {}),
      ...(plane.phase !== undefined && plane.phase !== null ? { phase: plane.phase } : {}),
    });
    return { url: URL.createObjectURL(blob), info: JSON.parse(headers.get('X-MedTwin-Render') ?? '{}') as SeriesRenderInfo };
  }

  async runSeriesResearchModel(caseId: ResourceId, uploadIds: number[], modelId: string, onQueued?: (job: QueuedJob) => void,
    options: { declaredInputType?: 'MRI' | 'CT_ABDOMEN_VOLUME' | 'CT_CHEST_VOLUME' | 'HEAD_CT_SERIES'; phase?: number | null; shortAxisAttested?: boolean } = {}): Promise<ResearchRun> {
    const response = await this.request<ResearchRun | { queued_job: QueuedJob }>(`/cases/${resourcePath(caseId)}/dicom-series/research-inference`, {
      method: 'POST', body: JSON.stringify({
        upload_ids: uploadIds, model_id: modelId, declared_input_type: options.declaredInputType ?? 'MRI',
        ...(options.phase !== undefined && options.phase !== null ? { phase: options.phase } : {}),
        short_axis_attested: options.shortAxisAttested ?? false,
      }),
    });
    if (!('queued_job' in response)) return response;
    return this.getResearchRun(await this.waitForJob(response.queued_job, onQueued));
  }

  getResearchRun(runId: ResourceId): Promise<ResearchRun> {
    return this.request<ResearchRun>(`/research-inference/${resourcePath(runId)}`);
  }

  /** Surfaces of a volumetric run's own mask, in the scan's voxel frame (mm); not registered to the atlas. */
  getVolumeSurfaces(runId: ResourceId): Promise<VolumeSurfaces> {
    return this.request<VolumeSurfaces>(`/research-inference/${resourcePath(runId)}/surfaces`);
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
    samePatientConfirmed = false,
  ): Promise<TResponse> {
    return this.request<TResponse>(`/cases/${resourcePath(caseId)}/compare`, {
      method: 'POST',
      body: JSON.stringify({
        prior_exam_id: priorExamId,
        current_exam_id: currentExamId,
        same_patient_confirmed: samePatientConfirmed,
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

  /** A region of a whole-slide image at one pyramid level (object URL of a PNG). */
  async getWsiRegionUrl(uploadId: ResourceId, region: { level: number; x: number; y: number; width: number; height: number }): Promise<string> {
    const query = new URLSearchParams({ level: String(region.level), x: String(region.x), y: String(region.y), width: String(region.width), height: String(region.height) });
    const { blob } = await this.requestBlob(`/uploads/${resourcePath(uploadId)}/wsi/region?${query}`);
    return URL.createObjectURL(blob);
  }

  getWsiTissue(uploadId: ResourceId): Promise<WsiTissueGrid> {
    return this.request<WsiTissueGrid>(`/uploads/${resourcePath(uploadId)}/wsi/tissue`);
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

  getCtOrganModel(): Promise<CtOrganModelCard> {
    return this.request<CtOrganModelCard>('/ct-organ-model');
  }

  /** Runs TotalSegmentator (third-party) on a CT NIfTI upload; the result is a volumetric research run pending review.
   * With a background worker the request returns a queued job, which is followed to its run. */
  async runCtOrganSegmentation(uploadId: ResourceId, fast: boolean, onQueued?: (job: QueuedJob) => void): Promise<ResearchRun> {
    const response = await this.request<ResearchRun | { queued_job: QueuedJob }>(`/uploads/${resourcePath(uploadId)}/ct-organ-segmentation`, {
      method: 'POST',
      body: JSON.stringify({ attest_ct_volume: true, fast }),
    });
    if (!('queued_job' in response)) return response;
    return this.getResearchRun(await this.waitForJob(response.queued_job, onQueued));
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

  getEvidenceSynthesis(caseId: ResourceId): Promise<EvidenceSynthesis> {
    return this.request<EvidenceSynthesis>(`/cases/${resourcePath(caseId)}/evidence-synthesis`);
  }

  getCaseWorkflow(caseId: ResourceId): Promise<CaseWorkflow> {
    return this.request<CaseWorkflow>(`/cases/${resourcePath(caseId)}/workflow`);
  }

  processPendingReports(caseId: ResourceId): Promise<{ workflow: CaseWorkflow; notice: string; results: Array<{ upload_id: number; status: string; reason?: string; job?: QueuedJob }> }> {
    return this.request(`/cases/${resourcePath(caseId)}/workflow/process-reports`, { method: "POST", body: JSON.stringify({ max_reports: 10 }) });
  }

  getPdfFilmAssessment(uploadId: number, page: number): Promise<FilmAssessment> {
    return this.request<FilmAssessment>(`/uploads/${uploadId}/pages/${page}/film-assessment`);
  }

  runMultimodel(uploadId: number, modelIds: string[], declaredInputType: string): Promise<{ queued_job: QueuedJob }> {
    return this.request<{ queued_job: QueuedJob }>(`/uploads/${uploadId}/multimodel`, { method: "POST", body: JSON.stringify({ model_ids: modelIds, declared_input_type: declaredInputType }) });
  }

  evaluateBaseline(caseId: number, target: string, unit: string, horizon: number, method: "persistence" | "linear"): Promise<BaselineForecast> {
    return this.request<BaselineForecast>(`/cases/${caseId}/forecast`, { method: "POST", body: JSON.stringify({
      case_id: caseId, target_metric: target, unit, horizon_days: horizon, method, same_patient_confirmed: true,
    }) });
  }

  getForecastHistory(caseId: number): Promise<Array<{ id: number; target_metric: string; unit: string; horizon_days: number; predicted_value: number | null; eligibility_status: string; baseline_analysis: BaselineForecast["baseline_analysis"] | null; created_at: string }>> {
    return this.request(`/cases/${caseId}/forecast-history`);
  }

  linkUploadExamination(uploadId: number, examId: number, dateAttributeId?: number): Promise<UploadedFile> {
    return this.request<UploadedFile>(`/uploads/${uploadId}/examination`, { method: "PATCH", body: JSON.stringify({
      examination_id: examId, same_patient_confirmed: true, source_date_attribute_id: dateAttributeId,
    }) });
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
