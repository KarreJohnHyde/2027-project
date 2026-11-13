import { create } from "zustand";
import {
  ApiError,
  api,
  isServerUnavailable,
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

export function rememberCase(id: number | null) {
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

/**
 * Why the entry page could not tell whether this browser is already signed in. While set, the entry page checks for
 * an existing session again before making a new profile, so a server outage never splits one person into two.
 */
export type SessionCheck = { unavailable: boolean; message: string } | null;

let bootstrapping: Promise<void> | null = null;

type WorkspaceState = {
  booting: boolean;
  sessionCheck: SessionCheck;
  /** An open-workspace installation: there is no sign-in or sign-out, and every case is shared. */
  openWorkspace: boolean;
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
  logout: () => Promise<void>;
  loadShell: () => Promise<void>;
  selectCase: (id: number | null) => void;
  loadEvidence: () => Promise<void>;
  refreshCases: () => Promise<void>;
  upsertCase: (record: Case) => void;
  setNotice: (notice: Notice) => void;
};

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  booting: true,
  sessionCheck: null,
  openWorkspace: false,
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

  // A returning browser goes straight to its workspace: the HttpOnly session cookie (or, once, a sign-in key an
  // earlier version stored) identifies it. Nothing is matched by name, age, gender, address or device.
  bootstrap: () => {
    // The first check shows the "Restoring session" screen (booting starts true); a retry from the entry page keeps
    // the page and its typed details in place until the answer arrives.
    bootstrapping ??= (async () => {
      try {
        const restored = (await api.restoreSession()) ?? (await api.claimLegacySession());
        set({ user: restored?.user ?? null, booting: false, sessionCheck: null, openWorkspace: restored?.open_workspace === true });
        if (restored) await get().loadShell();
      } catch (error) {
        set({ user: null, booting: false, sessionCheck: { unavailable: isServerUnavailable(error), message: errorMessage(error) } });
      } finally {
        bootstrapping = null;
      }
    })();
    return bootstrapping;
  },

  signedIn: async (user) => {
    set({ user, sessionCheck: null });
    await get().loadShell();
  },

  logout: async () => {
    const confirmed = await api.logout();
    set({
      user: null, cases: [], caseId: null, evidence: EMPTY_EVIDENCE, datasetTaskAudit: null, notice: null,
      sessionCheck: confirmed ? null : {
        unavailable: true,
        message: "Signed out on this screen, but the server could not be reached to end the session. Sign out again once it is back.",
      },
    });
  },

  loadShell: async () => {
    try {
      const sessionUserId = get().user?.id;
      const [cases, health] = await Promise.all([api.getCases(), api.getSystemHealth()]);
      if (get().user?.id !== sessionUserId) return;
      const remembered = get().caseId ?? recalledCase();
      const caseId = remembered && cases.some((item) => item.id === remembered) ? remembered : cases[0]?.id ?? null;
      // Case access must not wait for optional registries, which can hash large
      // research checkpoints. Publish the authorised case context immediately.
      set({ cases, health, caseId });
      rememberCase(caseId);
      const loadMetadata = async () => {
        const [models, capabilities, datasets, datasetTaskAudit] = await Promise.allSettled([
          api.getModels(), api.getCapabilities(), api.getDatasets(), api.getDatasetTaskAudit(),
        ]);
        if (get().user?.id !== sessionUserId) return;
        set({
          models: models.status === "fulfilled" ? models.value.models : [],
          capabilities: capabilities.status === "fulfilled" ? capabilities.value.capabilities : [],
          datasets: datasets.status === "fulfilled" ? datasets.value : null,
          datasetTaskAudit: datasetTaskAudit.status === "fulfilled" ? datasetTaskAudit.value : null,
        });
      };
      await Promise.all([get().loadEvidence(), loadMetadata()]);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) void get().logout();
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
