import { create } from "zustand";
import {
  ApiError,
  api,
  type AnalysisJob,
  type Case,
  type CapabilityRecord,
  type DatasetRegistryResponse,
  type DatasetTaskAuditResponse,
  type DocumentedAttribute,
  type Finding,
  type MedicalMeasurement,
  type ModelRegistryRecord,
  type ProvenanceEvent,
  type ReportStatement,
  type SystemHealth,
  type UploadedFile,
  type User,
} from "../services/api";
import { errorMessage } from "../lib/format";

const CASE_KEY = "medtwin.selectedCase";

function rememberCase(id: number | null) {
  try {
    if (id === null) window.localStorage.removeItem(CASE_KEY);
    else window.localStorage.setItem(CASE_KEY, String(id));
  } catch {
    // Remembering the selection is a convenience only.
  }
}

function recalledCase(): number | null {
  try {
    const value = window.localStorage.getItem(CASE_KEY);
    return value ? Number(value) : null;
  } catch {
    return null;
  }
}

export type CaseEvidence = {
  uploads: UploadedFile[];
  jobs: AnalysisJob[];
  findings: Finding[];
  statements: ReportStatement[];
  measurements: MedicalMeasurement[];
  provenance: ProvenanceEvent[];
  attributes: DocumentedAttribute[];
};

const EMPTY_EVIDENCE: CaseEvidence = { uploads: [], jobs: [], findings: [], statements: [], measurements: [], provenance: [], attributes: [] };

type Notice = { tone: "success" | "error" | "info"; text: string } | null;

type WorkspaceState = {
  booting: boolean;
  user: User | null;
  cases: Case[];
  caseId: number | null;
  evidence: CaseEvidence;
  evidenceVersion: number;
  loadingEvidence: boolean;
  health: SystemHealth | null;
  models: ModelRegistryRecord[];
  capabilities: CapabilityRecord[];
  datasets: DatasetRegistryResponse | null;
  datasetTaskAudit: DatasetTaskAuditResponse | null;
  notice: Notice;
  bootstrap: () => Promise<void>;
  signedIn: (user: User) => Promise<void>;
  logout: () => void;
  loadShell: () => Promise<void>;
  selectCase: (id: number | null) => void;
  loadEvidence: () => Promise<void>;
  refreshCases: () => Promise<void>;
  upsertCase: (record: Case) => void;
  setNotice: (notice: Notice) => void;
};

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  booting: true,
  user: null,
  cases: [],
  caseId: null,
  evidence: EMPTY_EVIDENCE,
  evidenceVersion: 0,
  loadingEvidence: false,
  health: null,
  models: [],
  capabilities: [],
  datasets: null,
  datasetTaskAudit: null,
  notice: null,

  bootstrap: async () => {
    if (!api.getToken()) {
      set({ booting: false });
      return;
    }
    try {
      const user = await api.getMe();
      set({ user, booting: false });
      await get().loadShell();
    } catch {
      api.logout();
      set({ user: null, booting: false });
    }
  },

  signedIn: async (user) => {
    set({ user });
    await get().loadShell();
  },

  logout: () => {
    api.logout();
    set({ user: null, cases: [], caseId: null, evidence: EMPTY_EVIDENCE, datasetTaskAudit: null, notice: null });
  },

  loadShell: async () => {
    try {
      const [cases, health] = await Promise.all([api.getCases(), api.getSystemHealth()]);
      const [models, capabilities, datasets, datasetTaskAudit] = await Promise.allSettled([
        api.getModels(),
        api.getCapabilities(),
        api.getDatasets(),
        api.getDatasetTaskAudit(),
      ]);
      const remembered = get().caseId ?? recalledCase();
      const caseId = remembered && cases.some((item) => item.id === remembered) ? remembered : cases[0]?.id ?? null;
      set({
        cases,
        health,
        models: models.status === "fulfilled" ? models.value.models : [],
        capabilities: capabilities.status === "fulfilled" ? capabilities.value.capabilities : [],
        datasets: datasets.status === "fulfilled" ? datasets.value : null,
        datasetTaskAudit: datasetTaskAudit.status === "fulfilled" ? datasetTaskAudit.value : null,
        caseId,
      });
      rememberCase(caseId);
      await get().loadEvidence();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) get().logout();
      else set({ notice: { tone: "error", text: errorMessage(error) } });
    }
  },

  selectCase: (id) => {
    set({ caseId: id, evidence: EMPTY_EVIDENCE });
    rememberCase(id);
    void get().loadEvidence();
  },

  loadEvidence: async () => {
    const caseId = get().caseId;
    if (caseId === null) {
      set({ evidence: EMPTY_EVIDENCE, evidenceVersion: get().evidenceVersion + 1 });
      return;
    }
    set({ loadingEvidence: true });
    try {
      const [uploads, jobs, findings, statements, measurements, provenance, attributes] = await Promise.all([
        api.getCaseUploads(caseId),
        api.getCaseAnalysisJobs(caseId),
        api.getCaseFindings(caseId),
        api.getReportStatements(caseId),
        api.getCaseMeasurements(caseId),
        api.getCaseProvenance(caseId),
        api.getDocumentedAttributes(caseId),
      ]);
      if (get().caseId !== caseId) return;
      set({ evidence: { uploads, jobs, findings, statements, measurements, provenance, attributes }, evidenceVersion: get().evidenceVersion + 1 });
    } catch (error) {
      set({ notice: { tone: "error", text: errorMessage(error) } });
    } finally {
      set({ loadingEvidence: false });
    }
  },

  refreshCases: async () => {
    const caseId = get().caseId;
    const cases = await api.getCases();
    const detail = caseId ? await api.getCase(caseId) : null;
    set({ cases: cases.map((item) => (detail && item.id === detail.id ? detail : item)) });
  },

  upsertCase: (record) => {
    const cases = get().cases.some((item) => item.id === record.id) ? get().cases.map((item) => (item.id === record.id ? record : item)) : [record, ...get().cases];
    set({ cases });
  },

  setNotice: (notice) => set({ notice }),
}));

export function useSelectedCase(): Case | null {
  return useWorkspace((state) => state.cases.find((item) => item.id === state.caseId) ?? null);
}
