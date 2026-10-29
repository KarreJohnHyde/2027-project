import assert from 'node:assert/strict';
import test from 'node:test';
import { anatomyEvidenceGroupKey, groupInOrder, statementGroupKey } from '../src/lib/findingGroups.ts';

// Synthetic statements only; no clinical documents are used.
function statement(id, overrides = {}) {
  return { id: String(id), source_file_id: '9', entity: 'Interstitial opacity', negation: 'AFFIRMED', certainty: 'CERTAIN',
    temporality: 'CURRENT', experiencer: 'PATIENT', anatomy_system: 'lungs', atlas_structure_id: null, laterality: null,
    anatomical_site: 'Bilateral lung', section: 'FINDINGS', ...overrides };
}

test('a finding repeated in FINDINGS and IMPRESSION of one document is one group', () => {
  const groups = groupInOrder([
    statement(1),
    statement(2, { section: 'IMPRESSION', anatomical_site: 'LUNG', entity: 'interstitial opacity' }),
    statement(3, { entity: 'Pleural effusion', negation: 'NEGATED' }),
  ], statementGroupKey);
  assert.deepEqual(groups.map((group) => group.members.map((item) => item.id)), [['1', '2'], ['3']]);
  assert.equal(groups[0].first.id, '1');
});

test('assertion, side, organ and document keep statements apart', () => {
  const groups = groupInOrder([
    statement(1),
    statement(2, { negation: 'NEGATED' }),
    statement(3, { laterality: 'LEFT' }),
    statement(4, { anatomy_system: 'liver' }),
    statement(5, { source_file_id: '10' }),
    statement(6, { certainty: 'HYPOTHETICAL' }),
  ], statementGroupKey);
  assert.equal(groups.length, 6);
});

test('only repeated report statements are grouped in the anatomy evidence list', () => {
  const item = (id, kind, overrides = {}) => ({ id, kind, source_file_id: 9, label: 'Honeycombing', assertion: 'AFFIRMED', certainty: 'CERTAIN',
    temporality: 'CURRENT', system: 'lungs', atlas_structure_id: null, candidate_atlas_structure_id: null, mapping_state: 'SCHEMATIC_ORGAN_ONLY', ...overrides });
  const groups = groupInOrder([item(1, 'REPORT_STATEMENT'), item(2, 'REPORT_STATEMENT'), item(3, 'MEASUREMENT'), item(4, 'MEASUREMENT')], anatomyEvidenceGroupKey);
  assert.deepEqual(groups.map((group) => group.members.length), [2, 1, 1]);
});
