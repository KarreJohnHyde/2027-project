import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { assertReportTrendConsistency, buildReportEvidence, reportDerivedAvailability, reportEvidenceExport } from '../src/lib/reportEvidence.ts';

// Synthetic fields only; no clinical documents or live application state are used.
function fixture() {
  const statement = { id: '1', case_id: '7', source_file_id: '9', entity: 'fixture finding', negation: 'AFFIRMED',
    certainty: 'CERTAIN', temporality: 'CURRENT', experiencer: 'PATIENT', anatomical_site: 'source site', laterality: null,
    source_span: 'Synthetic source sentence.', source_span_start: 0, source_span_end: 26 };
  const measurement = { id: 2, case_id: 7, name: 'hdl_cholesterol', display_name: 'HDL cholesterol', value: 84,
    result_operator: '=', unit: 'mg/dL', reference_low: 40, reference_high: 60, specimen: 'Serum', laboratory_method: 'Enzymatic',
    source_file_id: 9, source_span: 'Synthetic HDL 84 mg/dL.', source_page: 1, source_bbox: [1, 2, 3, 4],
    source_bbox_coordinate_space: 'RENDERED_PAGE_PIXELS', source_image_width: 100, source_image_height: 200,
    documented_date: '2026-01-10', duplicate_of_measurement_id: null };
  const record = (original, keys) => {
    const fields = Object.fromEntries(keys.map(key => [key, original[key]]));
    return { original: fields, effective: { ...fields }, correction_state: 'ORIGINAL_IMMUTABLE', applied_review_id: null, corrections: [] };
  };
  const reviewed = { case_id: 7, notice: 'Approved only.',
    statements: [{ statement_id: 1, ...record(statement, ['entity', 'negation', 'certainty', 'temporality', 'anatomical_site', 'laterality']) }],
    measurements: [{ measurement_id: 2, ...record(measurement, ['display_name', 'value', 'result_operator', 'unit', 'reference_low', 'reference_high', 'specimen', 'laboratory_method']) }] };
  const uploads = [{ id: 9, is_associated: true, withdrawn_at: null, superseded_by_file_id: null }];
  return { statement, measurement, reviewed, uploads, build() { return buildReportEvidence(7, [statement], [measurement], reviewed, uploads); } };
}

function correction(row, { state = 'CORRECTION_APPROVED', reviewId = 11, remove = false, changes = {} } = {}) {
  row.corrections.push({ review_id: reviewId, proposed_by_id: 1, proposed_at: '2026-10-29T01:00:00Z', state,
    decided_by_id: state === 'CORRECTION_PROPOSED' ? null : 2, decided_at: state === 'CORRECTION_PROPOSED' ? null : '2026-10-29T02:00:00Z',
    correction: { action: remove ? 'REMOVE' : 'AMEND', ...changes } });
  if (state === 'CORRECTION_APPROVED') {
    row.applied_review_id = reviewId;
    row.correction_state = remove ? 'REMOVED_IN_EFFECTIVE_VIEW' : 'CORRECTION_APPLIED_TO_EFFECTIVE_VIEW';
    if (!remove) Object.assign(row.effective, changes);
  } else if (row.applied_review_id === null) row.correction_state = state;
}

test('original source rows and provenance are retained without mutation', () => {
  const f = fixture();
  Object.freeze(f.statement); Object.freeze(f.measurement);
  const result = reportEvidenceExport(f.build());
  assert.equal(result.measurements[0].value, 84);
  assert.equal(result.original_extraction.measurements[0], f.measurement);
  assert.equal(result.report_statements[0].source_span, f.statement.source_span);
  assert.deepEqual(result.measurements[0].source_bbox, [1, 2, 3, 4]);
});

test('approved amended values/assertions are displayed/exported alongside immutable originals', () => {
  const f = fixture();
  correction(f.reviewed.measurements[0], { changes: { value: 48, reference_low: 42 } });
  correction(f.reviewed.statements[0], { changes: { negation: 'NEGATED', entity: 'reviewed finding' } });
  const result = reportEvidenceExport(f.build());
  assert.equal(result.measurements[0].value, 48);
  assert.equal(result.measurements[0].reference_low, 42);
  assert.equal(result.report_statements[0].negation, 'NEGATED');
  assert.equal(result.original_extraction.measurements[0].value, 84);
  assert.equal(result.original_extraction.report_statements[0].negation, 'AFFIRMED');
  assert.equal(result.correction_review.measurements[0].applied_review_id, 11);
});

for (const state of ['CORRECTION_PROPOSED', 'CORRECTION_REJECTED']) {
  test(`${state} does not change the effective row and remains in the audit`, () => {
    const f = fixture();
    correction(f.reviewed.measurements[0], { state, changes: { value: 48 } });
    const result = reportEvidenceExport(f.build());
    assert.equal(result.measurements[0].value, 84);
    assert.equal(result.correction_review.measurements[0].corrections[0].state, state);
    assert.deepEqual(reportDerivedAvailability(f.build()), { anatomyWithheld: false, egfrWithheld: false });
  });
}

test('a pending proposal does not hide or replace an earlier approved correction', () => {
  const f = fixture();
  correction(f.reviewed.measurements[0], { changes: { value: 48 } });
  correction(f.reviewed.measurements[0], { state: 'CORRECTION_PROPOSED', reviewId: 12, changes: { value: 47 } });
  const result = reportEvidenceExport(f.build());
  assert.equal(result.measurements[0].value, 48);
  assert.equal(result.correction_review.measurements[0].corrections.length, 2);
});

test('approved removals are excluded from effective rows, not erased from the audit', () => {
  const f = fixture();
  correction(f.reviewed.measurements[0], { remove: true });
  correction(f.reviewed.statements[0], { remove: true });
  const view = f.build();
  const result = reportEvidenceExport(view);
  assert.deepEqual(result.measurements, []); assert.deepEqual(result.report_statements, []);
  assert.equal(result.original_extraction.measurements.length, 1);
  assert.equal(result.original_extraction.report_statements.length, 1);
  assert.equal(view.removedMeasurements.length, 1); assert.equal(view.removedStatements.length, 1);
});

test('duplicate occurrences stay in the audit but are not silently counted twice', () => {
  const f = fixture();
  const duplicate = { ...f.measurement, id: 3, duplicate_of_measurement_id: 2 };
  f.reviewed.measurements.push({ ...f.reviewed.measurements[0], measurement_id: 3 });
  const result = reportEvidenceExport(buildReportEvidence(7, [f.statement], [f.measurement, duplicate], f.reviewed, f.uploads));
  assert.equal(result.measurements.length, 1);
  assert.equal(result.original_extraction.measurements.length, 2);
  assert.equal(result.correction_review.measurements.length, 2);
});

test('cross-case and incomplete correction snapshots fail closed', () => {
  const f = fixture();
  assert.throws(() => buildReportEvidence(8, [f.statement], [f.measurement], f.reviewed, f.uploads), /different case/);
  f.reviewed.measurements = [];
  assert.throws(() => f.build(), /changed while loading/);
});

test('duplicate or unknown review IDs cannot replace missing source records', () => {
  const f = fixture();
  f.reviewed.measurements[0].measurement_id = 99;
  assert.throws(() => f.build(), /missing for measurement/);
  f.reviewed.measurements = [f.reviewed.measurements[0], f.reviewed.measurements[0]];
  assert.throws(() => f.build(), /changed while loading/);
});

test('malformed unapproved changes and absent approvals block a report', () => {
  const f = fixture();
  f.reviewed.measurements[0].effective.value = 48;
  assert.throws(() => f.build(), /Unapproved evidence values changed/);
  f.reviewed.measurements[0].applied_review_id = 11;
  assert.throws(() => f.build(), /no matching approval/);
});

test('only affected raw-input derived summaries are withheld', () => {
  const f = fixture();
  correction(f.reviewed.measurements[0], { changes: { value: 48 } });
  assert.deepEqual(reportDerivedAvailability(f.build()), { anatomyWithheld: true, egfrWithheld: false });
  f.measurement.name = 'creatinine';
  assert.deepEqual(reportDerivedAvailability(f.build()), { anatomyWithheld: true, egfrWithheld: true });
});

for (const [field, value, reason] of [
  ['withdrawn_at', '2026-10-29T02:00:00Z', 'SOURCE_FILE_WITHDRAWN'],
  ['superseded_by_file_id', 10, 'SOURCE_FILE_SUPERSEDED_BY_F10'],
  ['is_associated', false, 'SOURCE_FILE_NOT_ASSOCIATED_WITH_CASE'],
]) {
  test(`${reason} is audit-only and never an active report row`, () => {
    const f = fixture();
    f.uploads[0][field] = value;
    f.measurement.name = 'creatinine';
    const view = f.build();
    const result = reportEvidenceExport(view);
    assert.deepEqual(result.report_statements, []); assert.deepEqual(result.measurements, []);
    assert.equal(result.original_extraction.measurements.length, 1);
    assert.equal(result.inactive_source_evidence.measurements[0].reason, reason);
    assert.deepEqual(reportDerivedAvailability(view), { anatomyWithheld: true, egfrWithheld: true });
    assert.throws(() => assertReportTrendConsistency(view, trend()), /changed while loading/);
  });
}

test('missing source metadata cannot silently activate evidence', () => {
  const f = fixture();
  f.uploads.splice(0);
  const view = f.build();
  assert.equal(view.activeStatements.length, 0);
  assert.equal(view.inactiveMeasurements[0].sourceExclusion, 'SOURCE_FILE_NOT_AVAILABLE');
});

function trend(value = 84, reviewId = null) {
  return [{ points: [{ source_type: 'DOCUMENT_EXTRACTION', measurement_id: 2, documented_value: value,
    documented_unit: 'mg/dL', result_operator: '=', reference_low: 40, reference_high: 60, correction_review_id: reviewId }], excluded: [] }];
}

test('parallel requests straddling a decision cannot produce mismatched report and trends', () => {
  const f = fixture();
  assert.doesNotThrow(() => assertReportTrendConsistency(f.build(), trend()));
  correction(f.reviewed.measurements[0], { changes: { value: 48 } });
  assert.throws(() => assertReportTrendConsistency(f.build(), trend()), /changed while loading/);
  assert.doesNotThrow(() => assertReportTrendConsistency(f.build(), trend(48, 11)));
});

test('removed trend points and stale removal exclusions fail closed', () => {
  const f = fixture();
  const excluded = [{ points: [], excluded: [{ measurement_id: 2, reason: 'REMOVED_BY_APPROVED_CORRECTION_R11' }] }];
  assert.throws(() => assertReportTrendConsistency(f.build(), excluded), /changed while loading/);
  correction(f.reviewed.measurements[0], { remove: true });
  assert.doesNotThrow(() => assertReportTrendConsistency(f.build(), excluded));
  assert.throws(() => assertReportTrendConsistency(f.build(), trend()), /changed while loading/);
});

test('report UI uses reviewed data, schema v3, and a case/revision export guard', () => {
  const source = readFileSync(new URL('../src/pages/ReportsPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /api\.getEffectiveEvidence\(selected\.id\)/);
  assert.match(source, /report\.data\?\.caseId === selected\.id/);
  assert.match(source, /report\.data\.evidenceVersion === evidenceVersion/);
  assert.match(source, /disabled=\{!snapshot\}/);
  assert.match(source, /medtwin-evidence-export-3\.0\.0/);
  assert.match(source, /reportEvidenceExport\(snapshot\.view\)/);
  assert.doesNotMatch(source, /distinctMeasurements\(evidence\.measurements\)/);
});
