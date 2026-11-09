import { lazy, Suspense, useEffect, useState, type ComponentType } from "react";
import { FolderOpen, LoaderCircle } from "lucide-react";
import { AppShell } from "./components/AppShell";
import { CreateCaseDialog } from "./components/CaseDialogs";
import { Button, EmptyState, LoadingBlock } from "./components/ui";
import { useLocation } from "./lib/router";
import "./lib/preferences";
import { NAV_ITEMS } from "./navigation";
import EntryPage from "./pages/EntryPage";
import { useSelectedCase, useWorkspace } from "./state/workspace";

type Route = { component: ComponentType; needsCase?: boolean; fullBleed?: boolean; title: string };

const page = (loader: () => Promise<{ default: ComponentType }>) => lazy(loader);

const ROUTES: Record<string, Route> = {
  "/": { component: page(() => import("./pages/OverviewPage")), title: "Overview Dashboard" },
  "/cases": { component: page(() => import("./pages/CaseWorkspacePage")), needsCase: true, title: "Case Workspace" },
  "/private-references": { component: page(() => import("./pages/PrivateReferencesPage")), title: "Private reference cases" },
  "/examples": { component: page(() => import("./pages/PublicExamplesPage")), title: "Public case examples" },
  "/upload": { component: page(() => import("./pages/UploadCenterPage")), needsCase: true, title: "Upload Center" },
  "/documents": { component: page(() => import("./pages/DocumentIntelligencePage")), needsCase: true, title: "Document Intelligence" },
  "/documents/verify": { component: page(() => import("./pages/DocumentVerificationPage")), needsCase: true, title: "Document Verification" },
  "/imaging": { component: page(() => import("./pages/MedicalImagingPage")), title: "Medical Imaging" },
  "/biomarkers": { component: page(() => import("./pages/BiomarkerAnalyticsPage")), needsCase: true, title: "Biomarker Analytics" },
  "/history": { component: page(() => import("./pages/HistoricalComparisonPage")), needsCase: true, title: "Historical Comparison" },
  "/anatomy-studio": { component: page(() => import("./pages/AnatomyStudioPage")), fullBleed: true, title: "Live Anatomy Studio" },
  "/prognosis-studio": { component: page(() => import("./pages/PrognosisStudioPage")), needsCase: true, title: "Prognosis Studio" },
  "/multimodal": { component: page(() => import("./pages/MultimodalPage")), needsCase: true, title: "Multimodal Intelligence" },
  "/risk": { component: page(() => import("./pages/RiskExplainabilityPage")), title: "Risk & Explainability" },
  "/research/analytics": { component: page(() => import("./pages/ResearchAnalyticsPage")), title: "Research Analytics" },
  "/models": { component: page(() => import("./pages/ModelRegistryPage")), title: "Model Registry" },
  "/datasets": { component: page(() => import("./pages/DatasetRegistryPage")), title: "Dataset Registry" },
  "/validation": { component: page(() => import("./pages/ValidationCenterPage")), title: "Validation Center" },
  "/reports": { component: page(() => import("./pages/ReportsPage")), needsCase: true, title: "Reports" },
  "/settings": { component: page(() => import("./pages/SettingsPage")), title: "Settings" },
  "/portal": { component: page(() => import("./pages/PortalPage")), title: "My record" },
  "/attribution": { component: page(() => import("./pages/AttributionPage")), title: "Data sources and licences" },
};

const NotFound = page(() => import("./pages/NotFoundPage"));
const PERSONAL_PATHS = new Set(["/portal", "/settings", "/attribution"]);

function NeedsCase({ title }: { title: string }) {
  const [creating, setCreating] = useState(false);
  return (
    <>
      <EmptyState
        icon={FolderOpen}
        title={`${title} needs a case`}
        detail="Create or select a pseudonymous research case first. Evidence is always bound to an authorised case."
        action={<Button variant="primary" onClick={() => setCreating(true)}>Create a case</Button>}
      />
      {creating && <CreateCaseDialog onClose={() => setCreating(false)} />}
    </>
  );
}

function App() {
  const booting = useWorkspace((state) => state.booting);
  const user = useWorkspace((state) => state.user);
  const bootstrap = useWorkspace((state) => state.bootstrap);
  const signedIn = useWorkspace((state) => state.signedIn);
  const selected = useSelectedCase();
  const { path } = useLocation();
  const route = ROUTES[path];
  const publicExamples = path === "/examples";
  const title = route?.title ?? NAV_ITEMS.find((item) => item.path === path)?.label ?? "Not found";

  useEffect(() => {
    if (!publicExamples) void bootstrap();
  }, [bootstrap, publicExamples]);

  useEffect(() => {
    document.title = `${title} · MedTwin 2.0`;
  }, [title]);

  if (publicExamples && route) {
    const PublicPage = route.component;
    return <Suspense fallback={<LoadingBlock label="Loading public examples" />}><PublicPage /></Suspense>;
  }
  if (booting) {
    return (
      <div className="grid min-h-screen place-items-center bg-page text-sm text-ink-2">
        <span className="inline-flex items-center gap-2"><LoaderCircle aria-hidden className="animate-spin" size={17} /> Restoring session</span>
      </div>
    );
  }
  if (!user) return <EntryPage onEnter={(next) => void signedIn(next)} />;

  // Every account has the whole workspace; each sees only its own cases and those shared with it.
  const Page = route?.component ?? NotFound;
  const personal = PERSONAL_PATHS.has(path);
  return (
    <AppShell fullBleed={route?.fullBleed}>
      <Suspense fallback={<div className={route?.fullBleed ? "p-6" : ""}><LoadingBlock label={`Loading ${title}`} /></div>}>
        {route?.needsCase && !selected && !personal ? <NeedsCase title={title} /> : <Page />}
      </Suspense>
    </AppShell>
  );
}

export default App;
