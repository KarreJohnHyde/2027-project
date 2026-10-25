import { useState, type ReactNode } from "react";
import { Activity, CheckCircle2, LogOut, Menu, Monitor, Moon, Plus, RefreshCw, Sun, Upload, X, XCircle } from "lucide-react";
import { Link, navigate, useLocation } from "../lib/router";
import { usePreferences, type ThemePreference } from "../lib/preferences";
import { NAV_SECTIONS } from "../navigation";
import { useWorkspace } from "../state/workspace";
import { Button, IconButton, SelectInput } from "./ui";
import { CreateCaseDialog } from "./CaseDialogs";

const THEME_ORDER: ThemePreference[] = ["system", "light", "dark"];
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };

function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const { path } = useLocation();
  const user = useWorkspace((state) => state.user);
  const logout = useWorkspace((state) => state.logout);
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
              const active = item.path === "/" ? path === "/" : path === item.path || path.startsWith(`${item.path}/`);
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
        {user && (
          <div className="mt-3 flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-surface-3 text-[11px] font-semibold text-ink-2">{(user.full_name || user.username).slice(0, 2).toUpperCase()}</div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-ink">{user.full_name || user.username}</p>
              <p className="text-[11px] capitalize text-ink-3">{user.role}</p>
            </div>
            <IconButton label="Sign out" icon={LogOut} onClick={logout} />
          </div>
        )}
      </div>
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
  const [createOpen, setCreateOpen] = useState(false);
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
      <aside className={`fixed inset-y-0 left-0 z-40 w-60 border-r border-line bg-sidebar transition-transform print:hidden lg:translate-x-0 ${mobileNav ? "translate-x-0" : "-translate-x-full"}`}>
        <Sidebar onNavigate={() => setMobileNav(false)} />
      </aside>
      {mobileNav && <button type="button" aria-label="Close navigation" className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setMobileNav(false)} />}

      <div className="lg:pl-60 print:pl-0">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-line bg-[color-mix(in_srgb,var(--mt-page)_88%,transparent)] px-3 backdrop-blur-md print:hidden sm:px-5">
          <IconButton label="Open navigation" icon={Menu} className="lg:hidden" onClick={() => setMobileNav(true)} />
          <div className="w-48 min-w-0 sm:w-64">
            <SelectInput aria-label="Selected case" value={caseId ?? ""} onChange={(event) => selectCase(event.target.value ? Number(event.target.value) : null)}>
              {cases.length === 0 && <option value="">No cases yet</option>}
              {cases.map((record) => <option key={record.id} value={record.id}>{record.pseudonymous_id}</option>)}
            </SelectInput>
          </div>
          <Button size="sm" icon={Plus} onClick={() => setCreateOpen(true)} className="hidden sm:inline-flex">New case</Button>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="hidden items-center gap-1.5 rounded-md border border-line px-2 py-1 text-[11px] text-ink-2 md:inline-flex" title={health?.health_scope}>
              <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${health?.status === "HEALTHY" ? "bg-good" : "bg-ink-3"}`} />
              API {health?.status?.toLowerCase() ?? "checking"}
            </span>
            <IconButton label="Refresh evidence" icon={RefreshCw} className={loadingEvidence ? "[&_svg]:animate-spin" : ""} onClick={() => void loadShell()} />
            <IconButton label={`Theme: ${theme} (click to change)`} icon={ThemeIcon} onClick={() => setTheme(THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length])} />
            <Button size="sm" variant="primary" icon={Upload} disabled={!caseId} onClick={() => navigate("/upload")}>
              <span className="hidden sm:inline">Add evidence</span>
            </Button>
          </div>
        </header>
        <main id="main" className={fullBleed ? "" : "mx-auto max-w-[1480px] px-3 py-5 sm:px-6 sm:py-6"}>
          {!fullBleed && <NoticeBar />}
          {children}
        </main>
      </div>
      {createOpen && <CreateCaseDialog onClose={() => setCreateOpen(false)} />}
    </div>
  );
}
