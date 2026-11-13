import { create } from "zustand";

export type UniversalSelection = {
  caseId: number | null;
  examId: number | null;
  findingId: number | null;
  sourceId: number | null;
  seriesId: string | null;
  sliceIndex: number | null;
  timepoint: string | null;
  structureId: string | null;
  modelId: string | null;
  overlayIds: string[];
  nodeId: string | null;
};
const empty: UniversalSelection = { caseId: null, examId: null, findingId: null, sourceId: null, seriesId: null, sliceIndex: null, timepoint: null, structureId: null, modelId: null, overlayIds: [], nodeId: null };
// Ephemeral only: another account/case must never inherit a source selection.
export const useUniversalSelection = create<UniversalSelection & {
  reset: (caseId?: number | null) => void;
  select: (selection: Partial<Omit<UniversalSelection, "caseId">>) => void;
}>((set) => ({ ...empty, reset: (caseId = null) => set({ ...empty, caseId }), select: (selection) => set(selection) }));
