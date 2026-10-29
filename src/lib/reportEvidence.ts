import type { BiomarkerSeries, EffectiveEvidenceRecord, EffectiveEvidenceResponse, MedicalMeasurement, ReportStatement, UploadedFile } from "../services/api";

function assertReviewContract<T extends object, C>(review: EffectiveEvidenceRecord<T, C>) {
  const applied = review.corrections.find((entry) => entry.review_id === review.applied_review_id);
  if (review.applied_review_id !== null && applied?.state !== "CORRECTION_APPROVED") {
    throw new Error("A report correction has no matching approval. Refresh the report before exporting.");
  }
  if (review.applied_review_id === null && Object.keys(review.original).some((key) =>
    review.original[key as keyof T] !== review.effective[key as keyof T])) {
    throw new Error("Unapproved evidence values changed. The reviewed report cannot be exported.");
  }
  if (["CORRECTION_APPLIED_TO_EFFECTIVE_VIEW", "REMOVED_IN_EFFECTIVE_VIEW"].includes(review.correction_state)
    !== (review.applied_review_id !== null)) {
    throw new Error("Correction state and approval disagree. Refresh the report before exporting.");
  }
}

/** Join reviewed fields to immutable source records, never treating a missing review response as approval. */
export function buildReportEvidence(
  caseId: number,
  statements: ReportStatement[],
  measurements: MedicalMeasurement[],
  reviewed: EffectiveEvidenceResponse,
  uploads: Pick<UploadedFile, "id" | "is_associated" | "withdrawn_at" | "superseded_by_file_id">[],
) {
  if (reviewed.case_id !== caseId || statements.some((row) => Number(row.case_id) !== caseId)
    || measurements.some((row) => row.case_id !== caseId)) {
    throw new Error("Report evidence belongs to a different case. Refresh the report before exporting.");
  }
  const statementIndex = new Map(reviewed.statements.map((row) => [String(row.statement_id), row]));
  const measurementIndex = new Map(reviewed.measurements.map((row) => [row.measurement_id, row]));
  const sourceIndex = new Map(uploads.map((row) => [String(row.id), row]));
  function sourceExclusion(sourceId: string | number | null) {
    const source = sourceId === null ? null : sourceIndex.get(String(sourceId));
    if (!source) return "SOURCE_FILE_NOT_AVAILABLE";
    if (source.withdrawn_at) return "SOURCE_FILE_WITHDRAWN";
    if (source.superseded_by_file_id != null) return `SOURCE_FILE_SUPERSEDED_BY_F${source.superseded_by_file_id}`;
    return source.is_associated ? null : "SOURCE_FILE_NOT_ASSOCIATED_WITH_CASE";
  }
  if (statementIndex.size !== statements.length || measurementIndex.size !== measurements.length
    || statementIndex.size !== reviewed.statements.length || measurementIndex.size !== reviewed.measurements.length) {
    throw new Error("Source and correction records changed while loading. Refresh the report before exporting.");
  }
  const statementRows = statements.map((original) => {
    const review = statementIndex.get(String(original.id));
    if (!review) throw new Error(`Correction state is missing for statement #${original.id}. Refresh the report.`);
    assertReviewContract(review);
    return { original, review, effective: review.effective, removed: review.correction_state === "REMOVED_IN_EFFECTIVE_VIEW", sourceExclusion: sourceExclusion(original.source_file_id) };
  });
  const measurementRows = measurements.map((original) => {
    const review = measurementIndex.get(original.id);
    if (!review) throw new Error(`Correction state is missing for measurement #${original.id}. Refresh the report.`);
    assertReviewContract(review);
    return { original, review, effective: review.effective, removed: review.correction_state === "REMOVED_IN_EFFECTIVE_VIEW", sourceExclusion: sourceExclusion(original.source_file_id) };
  });
  return {
    statementRows,
    measurementRows,
    activeStatements: statementRows.filter((row) => !row.removed && !row.sourceExclusion),
    // Source occurrence identity is immutable and matches the trend service's deduplication policy.
    activeMeasurements: measurementRows.filter((row) => !row.removed && !row.sourceExclusion && row.original.duplicate_of_measurement_id == null),
    removedStatements: statementRows.filter((row) => row.removed),
    removedMeasurements: measurementRows.filter((row) => row.removed),
    inactiveStatements: statementRows.filter((row) => row.sourceExclusion !== null),
    inactiveMeasurements: measurementRows.filter((row) => row.sourceExclusion !== null),
  };
}

export type ReportEvidence = ReturnType<typeof buildReportEvidence>;

/** Separate API requests can straddle a review decision; refuse a mixed report instead of hiding it. */
export function assertReportTrendConsistency(view: ReportEvidence, series: BiomarkerSeries[]) {
  const measurements = new Map(view.measurementRows.map((row) => [row.original.id, row]));
  const mismatch = () => { throw new Error("Trends and reviewed measurements changed while loading. Refresh the report before exporting."); };
  for (const item of series) {
    for (const point of item.points) {
      if (point.source_type !== "DOCUMENT_EXTRACTION" || point.measurement_id === null) continue;
      const row = measurements.get(point.measurement_id);
      const reviewId = "correction_review_id" in point ? point.correction_review_id : null;
      if (!row || row.removed || row.sourceExclusion || row.review.applied_review_id !== reviewId
        || row.effective.value !== point.documented_value || row.effective.unit !== point.documented_unit
        || row.effective.result_operator !== point.result_operator
        || row.effective.reference_low !== point.reference_low || row.effective.reference_high !== point.reference_high) mismatch();
    }
    for (const excluded of item.excluded) {
      if (!excluded.reason.startsWith("REMOVED_BY_APPROVED_CORRECTION_R") || excluded.measurement_id === null) continue;
      const row = measurements.get(excluded.measurement_id);
      if (!row?.removed || excluded.reason !== `REMOVED_BY_APPROVED_CORRECTION_R${row.review.applied_review_id}`) mismatch();
    }
  }
}

/** These services still use extraction rows, so their summaries cannot silently accompany corrections. */
export function reportDerivedAvailability(view: ReportEvidence) {
  const affectedMeasurements = view.measurementRows.filter((row) => row.review.applied_review_id !== null || row.sourceExclusion !== null);
  return {
    anatomyWithheld: affectedMeasurements.length > 0 || view.statementRows.some((row) => row.review.applied_review_id !== null || row.sourceExclusion !== null),
    egfrWithheld: affectedMeasurements.some((row) => ["creatinine", "egfr_documented"].includes(row.original.name)),
  };
}

/** Version 3 exports separate effective fields from original extraction and the complete decision trail. */
export function reportEvidenceExport(view: ReportEvidence) {
  return {
    evidence_policy: "APPROVED_CORRECTIONS_ONLY; removed and inactive-source rows excluded; original extraction retained",
    report_statements: view.activeStatements.map(({ original, effective, review }) => ({
      id: original.id, source_file_id: original.source_file_id, source_span: original.source_span,
      source_span_start: original.source_span_start, source_span_end: original.source_span_end,
      ...effective, experiencer: original.experiencer,
      correction_state: review.correction_state, applied_review_id: review.applied_review_id,
    })),
    measurements: view.activeMeasurements.map(({ original, effective, review }) => ({
      id: original.id, name: original.name, source_file_id: original.source_file_id, source_span: original.source_span,
      source_span_start: original.source_span_start, source_span_end: original.source_span_end,
      source_page: original.source_page, source_bbox: original.source_bbox,
      source_bbox_coordinate_space: original.source_bbox_coordinate_space,
      source_image_width: original.source_image_width, source_image_height: original.source_image_height,
      documented_date: original.documented_date, source_occurrences: original.source_occurrences,
      ...effective, correction_state: review.correction_state, applied_review_id: review.applied_review_id,
    })),
    original_extraction: {
      report_statements: view.statementRows.map((row) => row.original),
      measurements: view.measurementRows.map((row) => row.original),
    },
    correction_review: {
      statements: view.statementRows.map((row) => row.review),
      measurements: view.measurementRows.map((row) => row.review),
    },
    inactive_source_evidence: {
      statements: view.inactiveStatements.map((row) => ({ statement_id: row.original.id, reason: row.sourceExclusion })),
      measurements: view.inactiveMeasurements.map((row) => ({ measurement_id: row.original.id, reason: row.sourceExclusion })),
    },
  };
}
