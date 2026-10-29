import type { AnatomyEvidenceItem, ReportStatement } from "../services/api";

export interface Group<T> {
  key: string;
  first: T;
  members: T[];
}

/** Items that share a key, in first-seen order. */
export function groupInOrder<T>(items: readonly T[], keyOf: (item: T) => string): Group<T>[] {
  const groups = new Map<string, Group<T>>();
  for (const item of items) {
    const key = keyOf(item);
    const group = groups.get(key);
    if (group) group.members.push(item);
    else groups.set(key, { key, first: item, members: [item] });
  }
  return [...groups.values()];
}

/**
 * A report repeats a finding in FINDINGS and IMPRESSION, and a photographed packet can repeat a
 * page: statements from one document that say the same thing about the same structure are one
 * finding mentioned more than once. The free-text site wording ("LUNG", "pulmonary") is not
 * compared; the anatomy system, atlas structure and side are. Different documents are never
 * merged: each is its own dated observation.
 */
export function statementGroupKey(statement: ReportStatement): string {
  return [
    statement.source_file_id ?? "", statement.entity.toLowerCase(), statement.negation, statement.certainty,
    statement.temporality, statement.experiencer, statement.anatomy_system ?? "", statement.atlas_structure_id ?? "",
    statement.laterality ?? "",
  ].join("|");
}

/** Report statements repeated in one document are one evidence entry; other kinds stay separate. */
export function anatomyEvidenceGroupKey(item: AnatomyEvidenceItem): string {
  if (item.kind !== "REPORT_STATEMENT") return `${item.kind}|${item.id}|${item.system ?? ""}`;
  return [
    item.kind, item.source_file_id ?? "", item.label.toLowerCase(), item.assertion ?? "", item.certainty ?? "", item.temporality ?? "",
    item.system ?? "", item.atlas_structure_id ?? item.candidate_atlas_structure_id ?? "", item.mapping_state,
  ].join("|");
}
