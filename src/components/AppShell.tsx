import { useEffect, useState, type ReactNode } from "react";
import { Activity, AlertTriangle, CheckCircle2, Info, LoaderCircle, LogOut, Menu, Monitor, Moon, Plus, RefreshCw, Sun, Upload, X, XCircle } from "lucide-react";
import { api } from "../services/api";
import { entryRoleLabel } from "../data/entryRoles";
import { Link, navigate, useLocation } from "../lib/router";
import { usePreferences, type ThemePreference } from "../lib/preferences";
import { NAV_SECTIONS } from "../navigation";
import { useWorkspace } from "../state/workspace";
import { Button, Dialog, IconButton, SelectInput } from "./ui";
import { CreateCaseDialog } from "./CaseDialogs";

const THEME_ORDER: ThemePreference[] = ["system", "light", "dark"];
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };

function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const { path } = useLocation();
  const user = useWorkspace((state) => state.user);
  const logout = useWorkspace((state) => state.logout);
  const openWorkspace = useWorkspace((state) => state.openWorkspace);
  const [confirming, setConfirming] = useState(false);
  const [leaving, setLeaving] = useState(false);
  // A visitor or demo workspace has no password: once this browser signs out, it cannot be reopened. Say so first.
  const passwordless = user?.is_visitor === true || user?.is_guest === true;
  const signOut = () => {
    setLeaving(true);
    void logout().finally(() => setLeaving(false));
  };
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-accent-fg"><Activity size={17} aria-hidden /></div>
        <div>
          <p className="text-sm font-semibold leading-4 text-ink">MedTwin 2.0</p>
          <p className="text-[11px] text-ink-3">Clinical research workspace</p>
        </div>
      </div>
      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2 pb-4">
        {NAV_SECTIONS.map((section) => (
          <div key={section.label} className="mt-3 first:mt-1">
            <p className="px-2.5 pb-1 text-[11px] font-medium text-ink-3">{section.label}</p>
            {section.items.map((item) => {
              // A sub-path with its own entry ("/documents/verify") is not also its parent's page.
              const active = item.path === "/" ? path === "/" : path === item.path
                || (path.startsWith(`${item.path}/`) && !NAV_SECTIONS.some((other) => other.items.some((entry) => entry.path !== item.path && entry.path.startsWith(`${item.path}/`) && (path === entry.path || path.startsWith(`${entry.path}/`)))));
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] transition ${active ? "bg-surface font-medium text-ink shadow-card" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}
                >
                  <Icon aria-hidden size={15} className={active ? "text-accent-text" : "text-ink-3"} />
                  <span className="truncate">{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="border-t border-line p-3">
        <p className="rounded-lg bg-surface-2 p-2.5 text-[11px] leading-4 text-ink-2">Research software. Not a medical device; no diagnostic or treatment claim. Every output needs clinician review.</p>
        {openWorkspace && (
          <p className="mt-2 rounded-lg border border-[color-mix(in_srgb,var(--mt-warning)_45%,transparent)] p-2.5 text-[11px] leading-4 text-ink-2">
            Open workspace: this installation has no sign-in. Everyone who opens it sees and can change every case.
          </p>
        )}
        {user && (
          <div className="mt-3 flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-surface-3 text-[11px] font-semibold text-ink-2">{(user.full_name || user.username).slice(0, 2).toUpperCase()}</div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-ink">{user.full_name || user.username}</p>
              <p className="text-[11px] text-ink-3">
                {user.stated_role
                  ? <>{entryRoleLabel(user.stated_role)}{user.age != null ? ` · ${user.age}` : ""} · self-described</>
                  : <><span className="capitalize">{user.role}</span> · {user.verification_status.toLowerCase()}</>}
              </p>
            </div>
            {!openWorkspace && (
              <IconButton label={user.is_guest ? "End demo" : "Sign out"} icon={LogOut} disabled={leaving} onClick={() => (passwordless ? setConfirming(true) : signOut())} />
            )}
          </div>
        )}
        {confirming && user && (
          <Dialog
            title={user.is_guest ? "End the demo?" : "Sign out of this browser?"}
            onClose={() => setConfirming(false)}
            footer={<>
              <Button onClick={() => setConfirming(false)}>Stay</Button>
              <Button variant="danger" icon={LogOut} loading={leaving} onClick={signOut}>{user.is_guest ? "End demo" : "Sign out"}</Button>
            </>}
          >
            <p className="text-sm leading-6 text-ink-2">
              {user.is_guest
                ? "The demo workspace and its fictional sample case close now. You can start a new demo at any time."
                : "This workspace is remembered by this browser only, with no password. After signing out you cannot reopen it; entering your details again starts a new, empty workspace. Cases you created are not deleted."}
            </p>
          </Dialog>
        )}
      </div>
    </div>
  );
}

/** Serverless demonstration without a hosted database or object store: data does not persist. */
function TemporaryStorageNotice() {
  const temporary = useWorkspace((state) => state.health?.temporary_storage === true);
  if (!temporary) return null;
  return (
    <div role="status" className="mb-4 flex items-start gap-2.5 rounded-lg border border-[color-mix(in_srgb,var(--mt-warning)_45%,transparent)] bg-surface p-3 text-sm text-warning-text">
      <AlertTriangle aria-hidden size={16} className="mt-0.5 shrink-0" />
      <span className="min-w-0 flex-1 text-ink">
        Demonstration deployment: data is kept on a temporary server instance and is lost when it restarts. Use synthetic data only; do not upload patient documents.
      </span>
    </div>
  );
}

const FINISHED_JOB = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const DEMO_POLL_MS = 3000;
const DEMO_POLL_LIMIT = 200;

/**
 * The demo opens before its fictional documents are analysed (by the ordinary pipeline, after the sign-in). Follow
 * those analyses and load each result as it finishes. Nothing is shown that the pipeline has not produced.
 */
function useDemoAnalysis(active: boolean, caseId: number | null) {
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const [progress, setProgress] = useState<{ done: number; total: number; stalled: boolean } | null>(null);
  useEffect(() => {
    if (!active || caseId === null) return;
    let stopped = false;
    let timer: number | undefined;
    let polls = 0;
    let lastDone = -1;
    const check = async () => {
      try {
        const jobs = (await api.getCaseQueuedJobs(caseId)).filter((job) => job.kind === "UPLOAD_ANALYSIS");
        if (stopped) return;
        const done = jobs.filter((job) => FINISHED_JOB.has(job.status)).length;
        polls += 1;
        setProgress({ done, total: jobs.length, stalled: polls >= DEMO_POLL_LIMIT });
        if (lastDone >= 0 && done > lastDone) void loadEvidence();
        lastDone = done;
        if (done < jobs.length && polls < DEMO_POLL_LIMIT) timer = window.setTimeout(() => void check(), DEMO_POLL_MS);
      } catch {
        // Progress is a convenience; the evidence pages and Refresh evidence still work.
      }
    };
    void check();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [active, caseId, loadEvidence]);
  return progress;
}

/** "Try Demo" sign-in: says the sample case is fictional, the sign-in temporary, and how far its analysis has got. */
function GuestNotice() {
  const guest = useWorkspace((state) => state.user?.is_guest === true);
  const caseId = useWorkspace((state) => state.caseId);
  const progress = useDemoAnalysis(guest, caseId);
  if (!guest) return null;
  const analysing = progress !== null && progress.done < progress.total && !progress.stalled;
  const stalled = progress !== null && progress.done < progress.total && progress.stalled;
  return (
    <div role="status" className="mb-4 flex items-start gap-2.5 rounded-lg border border-line bg-surface p-3 text-sm">
      {analysing
        ? <LoaderCircle aria-hidden size={16} className="mt-0.5 shrink-0 animate-spin text-accent-text" />
        : <Info aria-hidden size={16} className="mt-0.5 shrink-0 text-accent-text" />}
      <span className="min-w-0 flex-1 text-ink">
        Guest demo: the sample case and its documents are fictional, and this workspace closes after 24 hours. Every feature is open to you. To keep your own work, end the demo and enter your details.
        {analysing && <span className="mt-1 block text-xs text-ink-2">Analysing the fictional documents: {progress.done} of {progress.total} done. Results appear here as each one finishes.</span>}
        {stalled && <span className="mt-1 block text-xs text-ink-2">The analysis of the fictional documents has not finished ({progress.done} of {progress.total}). Use Refresh evidence later, or start a new demo.</span>}
      </span>
    </div>
  );
}

function NoticeBar() {
  const notice = useWorkspace((state) => state.notice);
  const setNotice = useWorkspace((state) => state.setNotice);
  if (!notice) return null;
  const tone = notice.tone === "error" ? "border-[color-mix(in_srgb,var(--mt-critical)_35%,transparent)] text-critical-text" : "border-[color-mix(in_srgb,var(--mt-good)_35%,transparent)] text-good-text";
  const Icon = notice.tone === "error" ? XCircle : CheckCircle2;
  return (
    <div role={notice.tone === "error" ? "alert" : "status"} className={`mb-4 flex items-start gap-2.5 rounded-lg border bg-surface p-3 text-sm ${tone}`}>
      <Icon aria-hidden size={16} className="mt-0.5 shrink-0" />
      <span className="min-w-0 flex-1 break-words text-ink">{notice.text}</span>
      <button type="button" aria-label="Dismiss" className="rounded p-0.5 text-ink-3 hover:text-ink" onClick={() => setNotice(null)}><X size={15} /></button>
    </div>
  );
}

export function AppShell({ children, fullBleed = false }: { children: ReactNode; fullBleed?: boolean }) {
  const [mobileNav, setMobileNav] = useState(false);
  const [smallScreen, setSmallScreen] = useState(() => window.matchMedia("(max-width: 1023px)").matches);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 1023px)");
    const update = () => setSmallScreen(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const [createOpen, setCreateOpen] = useState(false);
  const { path } = useLocation();
  // Private references are independent of the currently selected shared case.
  const workspace = path !== "/private-references";
  const cases = useWorkspace((state) => state.cases);
  const caseId = useWorkspace((state) => state.caseId);
  const selectCase = useWorkspace((state) => state.selectCase);
  const health = useWorkspace((state) => state.health);
  const loadingEvidence = useWorkspace((state) => state.loadingEvidence);
  const loadShell = useWorkspace((state) => state.loadShell);
  const theme = usePreferences((state) => state.theme);
  const setTheme = usePreferences((state) => state.setTheme);
  const ThemeIcon = THEME_ICON[theme];

  return (
    <div className="min-h-screen bg-page text-ink">
      <a href="#main" className="sr-only z-50 rounded-lg bg-surface p-3 text-accent-text focus:not-sr-only focus:fixed focus:left-3 focus:top-3">Skip to main content</a>
      <aside id="primary-navigation-shell" inert={smallScreen && !mobileNav} aria-hidden={smallScreen && !mobileNav ? true : undefined} className={`fixed inset-y-0 left-0 z-40 w-60 border-r border-line bg-sidebar transition-transform print:hidden lg:translate-x-0 ${mobileNav ? "translate-x-0" : "-translate-x-full"}`}>
        <Sidebar onNavigate={() => setMobileNav(false)} />
      </aside>
      {mobileNav && <button type="button" aria-label="Close navigation" className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setMobileNav(false)} />}

      <div className="lg:pl-60 print:pl-0">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-line bg-[color-mix(in_srgb,var(--mt-page)_88%,transparent)] px-3 backdrop-blur-md print:hidden sm:px-5">
          <IconButton label="Open navigation" icon={Menu} className="lg:hidden" aria-controls="primary-navigation-shell" aria-expanded={mobileNav} onClick={() => setMobileNav(true)} />
          {!workspace && <span className="text-sm font-medium text-ink-2">Private reference library</span>}
          {workspace && (
            <>
              <div className="w-48 min-w-0 sm:w-64">
                <SelectInput aria-label="Selected case" value={caseId ?? ""} onChange={(event) => selectCase(event.target.value ? Number(event.target.value) : null)}>
                  {cases.length === 0 && <option value="">No cases yet</option>}
                  {cases.map((record) => <option key={record.id} value={record.id}>{record.pseudonymous_id}</option>)}
                </SelectInput>
              </div>
              <Button size="sm" icon={Plus} onClick={() => setCreateOpen(true)} className="hidden sm:inline-flex">New case</Button>
            </>
          )}
          <div className="ml-auto flex items-center gap-1.5">
            <span className="hidden items-center gap-1.5 rounded-md border border-line px-2 py-1 text-[11px] text-ink-2 md:inline-flex" title={health?.health_scope}>
              <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${health?.status === "HEALTHY" ? "bg-good" : "bg-ink-3"}`} />
              API {health?.status?.toLowerCase() ?? "checking"}
            </span>
            {workspace && <IconButton label="Refresh evidence" icon={RefreshCw} className={loadingEvidence ? "[&_svg]:animate-spin" : ""} onClick={() => void loadShell()} />}
            <IconButton label={`Theme: ${theme} (click to change)`} icon={ThemeIcon} onClick={() => setTheme(THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length])} />
            {workspace && (
              <Button size="sm" variant="primary" icon={Upload} aria-label="Add evidence" disabled={!caseId} onClick={() => navigate("/upload")}>
                <span className="hidden sm:inline">Add evidence</span>
              </Button>
            )}
          </div>
        </header>
        <main id="main" tabIndex={-1} className={fullBleed ? "" : "mx-auto max-w-[1480px] px-3 py-5 sm:px-6 sm:py-6"}>
          {!fullBleed && <TemporaryStorageNotice />}
          {!fullBleed && <GuestNotice />}
          {!fullBleed && <NoticeBar />}
          {children}
        </main>
      </div>
      {createOpen && <CreateCaseDialog onClose={() => setCreateOpen(false)} />}
    </div>
  );
}
