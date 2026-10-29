import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import * as reportEvidence from '../src/lib/reportEvidence.ts';

const require = createRequire(import.meta.url);
const root = fileURLToPath(new URL('../', import.meta.url));

/** In-memory React server render with synthetic state. No browser, login, network or disk writes. */
function renderReport({ reviewedState = 'CORRECTION_APPLIED_TO_EFFECTIVE_VIEW', loading = false, failed = false,
  snapshotCase = 7, snapshotRevision = 1, withdrawn = false } = {}) {
  const statement = { id: '1', case_id: '7', source_file_id: '9', entity: 'fixture finding', negation: 'AFFIRMED',
    certainty: 'CERTAIN', temporality: 'CURRENT', experiencer: 'PATIENT', anatomical_site: null, laterality: null,
    source_span: 'Synthetic source sentence.' };
  const measurement = { id: 2, case_id: 7, source_file_id: 9, name: 'hdl_cholesterol', display_name: 'HDL cholesterol', value: 84,
    result_operator: '=', unit: 'mg/dL', reference_low: 40, reference_high: 60, reference_text: '40–60 mg/dL',
    reference_source: 'DOCUMENTED_IN_SOURCE', specimen: 'Serum', laboratory_method: 'Enzymatic',
    source_span: 'Synthetic HDL 84 mg/dL.', documented_date: '2026-01-10' };
  const fields = Object.fromEntries(['display_name', 'value', 'result_operator', 'unit', 'reference_low', 'reference_high', 'specimen', 'laboratory_method'].map(key => [key, measurement[key]]));
  const statementFields = Object.fromEntries(['entity', 'negation', 'temporality', 'certainty', 'anatomical_site', 'laterality'].map(key => [key, statement[key]]));
  const approved = ['CORRECTION_APPLIED_TO_EFFECTIVE_VIEW', 'REMOVED_IN_EFFECTIVE_VIEW'].includes(reviewedState);
  const review = { measurement_id: 2, original: fields, effective: { ...fields, value: reviewedState === 'CORRECTION_APPLIED_TO_EFFECTIVE_VIEW' ? 48 : 84 },
    correction_state: reviewedState, applied_review_id: approved ? 11 : null,
    corrections: [{ review_id: 11, proposed_by_id: 1, proposed_at: '2026-10-29T01:00:00Z', state: approved ? 'CORRECTION_APPROVED' : reviewedState,
      decided_by_id: approved ? 2 : null, decided_at: approved ? '2026-10-29T02:00:00Z' : null,
      correction: { target_measurement_id: 2, action: reviewedState === 'REMOVED_IN_EFFECTIVE_VIEW' ? 'REMOVE' : 'AMEND', corrected_value: 48 } }] };
  const reviewed = { case_id: 7, notice: 'Original extraction is unchanged.', measurements: [review], statements: [{ statement_id: 1,
    original: statementFields, effective: statementFields, correction_state: 'ORIGINAL_IMMUTABLE', applied_review_id: null, corrections: [] }] };
  const evidence = { uploads: [{ id: 9, filename: 'synthetic.txt', modality: 'REPORT', file_hash: 'a'.repeat(64), is_associated: true,
    withdrawn_at: withdrawn ? '2026-10-29T03:00:00Z' : null }], jobs: [], findings: [], statements: [statement], measurements: [measurement], attributes: [], provenance: [] };
  const selected = { id: 7, pseudonymous_id: 'SYNTHETIC-REPORT', examinations: [] };
  const state = { evidence, evidenceVersion: 1, loadingEvidence: false, loadEvidence: async () => {}, capabilities: [], health: { version: 'test' } };
  const snapshot = { caseId: snapshotCase, evidenceVersion: snapshotRevision, source: evidence, reviewed,
    view: reportEvidence.buildReportEvidence(7, evidence.statements, evidence.measurements, reviewed, evidence.uploads),
    trends: { series: [] }, anatomy: { systems: {}, spatial_registration: { status: 'NOT_VALIDATED' } },
    egfr: { equation: { display: 'synthetic equation' }, results: [], status: 'NO_CREATININE_DOCUMENTED' }, prognosis: [], generatedAt: '2026-10-29T03:00:00Z' };
  const stubs = {
    [path.join(root, 'src/services/api.ts')]: { api: {} },
    [path.join(root, 'src/state/workspace.ts')]: { useWorkspace: selector => selector(state), useSelectedCase: () => selected },
    [path.join(root, 'src/lib/useAsync.ts')]: { useAsync: () => ({ data: failed ? null : snapshot, loading, error: failed ? 'Synthetic unavailable response' : null }) },
    [path.join(root, 'src/lib/reportEvidence.ts')]: reportEvidence,
  };
  const cache = new Map();
  function load(file) {
    if (stubs[file]) return stubs[file];
    if (cache.has(file)) return cache.get(file).exports;
    const module = { exports: {} };
    cache.set(file, module);
    const output = ts.transpileModule(readFileSync(file, 'utf8'), { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
    } }).outputText;
    const resolve = specifier => {
      if (!specifier.startsWith('.')) return require(specifier);
      const base = path.resolve(path.dirname(file), specifier);
      const target = [base, `${base}.ts`, `${base}.tsx`].find(candidate => existsSync(candidate));
      if (!target) throw new Error(`Unresolved render-test dependency ${specifier}`);
      return load(target);
    };
    new Function('require', 'module', 'exports', output)(resolve, module, module.exports);
    return module.exports;
  }
  const Page = load(path.join(root, 'src/pages/ReportsPage.tsx')).default;
  return renderToStaticMarkup(React.createElement(Page));
}

test('approved report renders corrected value and immutable original with review ID', () => {
  const html = renderReport();
  assert.match(html, /48 mg\/dL/);
  assert.match(html, /Original: HDL cholesterol · 84 mg\/dL/);
  assert.match(html, /Review #11/);
  assert.match(html, /Approved — applied/);
  assert.match(html, /Synthetic HDL 84 mg\/dL/);
  assert.match(html, /Mapping summary withheld/);
});

test('pending report never renders its proposed value as an effective measurement', () => {
  const html = renderReport({ reviewedState: 'CORRECTION_PROPOSED' });
  assert.match(html, /84 mg\/dL/);
  assert.doesNotMatch(html, /48 mg\/dL/);
  assert.match(html, /Pending — not applied/);
});

test('approved removal stays visible only in the audit section', () => {
  const html = renderReport({ reviewedState: 'REMOVED_IN_EFFECTIVE_VIEW' });
  const active = html.split('Reviewed measurements (distinct observations)')[1].split('Approved removals')[0];
  assert.doesNotMatch(active, /84 mg\/dL/);
  assert.match(html, /Measurement #2: HDL cholesterol · 84 mg\/dL/);
});

test('withdrawn evidence is audit-only rather than an active report result', () => {
  const html = renderReport({ withdrawn: true });
  assert.match(html, /Withdrawn — audit only/);
  assert.match(html, /Inactive-source evidence/);
  assert.match(html, /Source file withdrawn/);
  const active = html.split('Reviewed measurements (distinct observations)')[1].split('Inactive-source evidence')[0];
  assert.doesNotMatch(active, /48 mg\/dL/);
});

for (const options of [{ loading: true }, { failed: true }, { snapshotCase: 8 }, { snapshotRevision: 0 }]) {
  test(`unavailable or stale render disables export: ${JSON.stringify(options)}`, () => {
    const html = renderReport(options);
    assert.match(html, /Reviewed report unavailable/);
    assert.doesNotMatch(html, /48 mg\/dL/);
    assert.match(html, /<button[^>]*disabled=""[^>]*>.*?Export JSON/s);
  });
}
