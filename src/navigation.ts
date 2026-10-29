import {
  Activity,
  BarChart3,
  Box,
  BrainCircuit,
  ClipboardCheck,
  Database,
  FileCheck2,
  FileSearch,
  FileText,
  FolderKanban,
  GitCompareArrows,
  Layers3,
  LineChart,
  ScanLine,
  Settings,
  ShieldQuestion,
  TrendingUp,
  UserRound,
} from "lucide-react";

export type NavItem = {
  path: string;
  label: string;
  icon: typeof Activity;
  summary: string;
  needsCase?: boolean;
  /** Shown to personal (patient or caregiver) accounts, which see nothing else. */
  personal?: boolean;
};

export const NAV_SECTIONS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Case evidence",
    items: [
      { path: "/", label: "Overview Dashboard", icon: Activity, summary: "Case, capability and system status at a glance." },
      { path: "/cases", label: "Case Workspace", icon: FolderKanban, summary: "Examinations, uploads, processing history and sharing.", needsCase: true },
      { path: "/documents", label: "Document Intelligence", icon: FileSearch, summary: "Source-linked statements, context and measurements.", needsCase: true },
      { path: "/documents/verify", label: "Document Verification", icon: FileCheck2, summary: "Each page beside what was extracted from it, checked item by item.", needsCase: true },
      { path: "/imaging", label: "Medical Imaging", icon: ScanLine, summary: "Viewer, modality support and model coverage.", needsCase: true },
      { path: "/biomarkers", label: "Biomarker Analytics", icon: LineChart, summary: "Dated series, documented intervals and trend statistics.", needsCase: true },
      { path: "/history", label: "Historical Comparison", icon: GitCompareArrows, summary: "Examination-pair deltas and report changes.", needsCase: true },
    ],
  },
  {
    label: "Studios",
    items: [
      { path: "/anatomy-studio", label: "Live Anatomy Studio", icon: Box, summary: "Ten anatomical systems with evidence-linked inspection." },
      { path: "/prognosis-studio", label: "Prognosis Studio", icon: TrendingUp, summary: "Scenario A/B availability with observed evidence.", needsCase: true },
      { path: "/multimodal", label: "Multimodal Intelligence", icon: BrainCircuit, summary: "Modality inventory, fusion and concordance status.", needsCase: true },
      { path: "/risk", label: "Risk & Explainability", icon: ShieldQuestion, summary: "Risk instruments, blockers and explanation methods." },
    ],
  },
  {
    label: "Research",
    items: [
      { path: "/research/analytics", label: "Research Analytics", icon: BarChart3, summary: "Charts of real workspace data with provenance." },
      { path: "/models", label: "Model Registry", icon: Layers3, summary: "Model states and activation gates." },
      { path: "/datasets", label: "Dataset Registry", icon: Database, summary: "Audited datasets, integrity and readiness." },
      { path: "/validation", label: "Validation Center", icon: ClipboardCheck, summary: "Held-out evaluation, traceability and test evidence." },
      { path: "/reports", label: "Reports", icon: FileText, summary: "Evidence-linked research reports and exports.", needsCase: true },
    ],
  },
  {
    label: "System",
    items: [
      { path: "/portal", label: "My record", icon: UserRound, summary: "Your documents and reviewed results (patients and caregivers).", personal: true },
      { path: "/settings", label: "Settings", icon: Settings, summary: "Theme, detail level, privacy and environment.", personal: true },
    ],
  },
];

export const NAV_ITEMS = NAV_SECTIONS.flatMap((section) => section.items);
