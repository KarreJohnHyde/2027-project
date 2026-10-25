import React from 'react';
import { 
  LayoutDashboard, 
  FolderGit2, 
  Image as ImageIcon, 
  Activity, 
  FileText, 
  Layers, 
  GitCompare, 
  Box, 
  TrendingUp, 
  UserCheck, 
  Stethoscope, 
  LogOut,
  Cpu,
  User as UserIcon,
  Eye,
  History,
  Award
} from 'lucide-react';
import type { NavigationTab, User, Case } from '../types/medtwin';

interface SidebarProps {
  currentTab: NavigationTab;
  onSelectTab: (tab: NavigationTab) => void;
  user: User | null;
  onLogout: () => void;
  activeCase: Case | null;
  pendingReviewsCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  user,
  onLogout,
  activeCase,
  pendingReviewsCount,
}) => {
  const navItems: { id: NavigationTab; label: string; icon: React.ReactNode; badge?: string | number; badgeColor?: string }[] = [
    { id: 'DASHBOARD', label: 'Dashboard', icon: <LayoutDashboard size={18} /> },
    { id: 'CASE_MANAGEMENT', label: 'Case Management', icon: <FolderGit2 size={18} /> },
    { id: 'IMAGE_ANALYSIS', label: 'Medical Image (X-Ray)', icon: <ImageIcon size={18} /> },
    { id: 'ECG_ANALYSIS', label: 'Digital ECG Waveforms', icon: <Activity size={18} /> },
    { id: 'REPORT_NLP', label: 'Clinical Report NLP', icon: <FileText size={18} /> },
    { id: 'MULTIMODAL_FUSION', label: 'Masked Gated Fusion', icon: <Layers size={18} />, badge: 'Eq. 8–10', badgeColor: 'bg-purple-950 text-purple-300 border-purple-800' },
    { id: 'REPORT_CONCORDANCE', label: 'Report Concordance', icon: <GitCompare size={18} /> },
    { id: 'ANATOMICAL_3D', label: '3D Anatomical Twin', icon: <Box size={18} />, badge: 'L1/L2', badgeColor: 'bg-cyan-950 text-cyan-300 border-cyan-800' },
    { id: 'TIMELINE_FORECASTING', label: 'Longitudinal Forecasting', icon: <TrendingUp size={18} /> },
    { id: 'LONGITUDINAL_DIFF', label: 'Old vs New Self (Diff)', icon: <History size={18} />, badge: 'Sec. IX', badgeColor: 'bg-cyan-950 text-cyan-300 border-cyan-800' },
    { id: 'IEEE_VALIDATION', label: 'IEEE Validation (Eqs. 1–16)', icon: <Award size={18} />, badge: 'Manuscript', badgeColor: 'bg-indigo-950 text-indigo-300 border-indigo-800' },
    { 
      id: 'HUMAN_REVIEW', 
      label: 'Clinician Review & Audit', 
      icon: <UserCheck size={18} />, 
      badge: pendingReviewsCount > 0 ? `${pendingReviewsCount} pending` : undefined,
      badgeColor: 'bg-amber-950 text-amber-300 border-amber-800'
    },
    { id: 'CLINICAL_CATALOG', label: 'Diagnostic Packages', icon: <Stethoscope size={18} /> },
    { id: 'UNIFIED_VIEW', label: 'Unified All-in-One View', icon: <Eye size={18} /> },
    { id: 'USER_MANAGEMENT', label: 'User & Roles', icon: <UserIcon size={18} /> },
  ];

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800/80 flex flex-col justify-between shrink-0 select-none">
      {/* Brand & Active Case indicator */}
      <div>
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-cyan-500/20">
              <Cpu size={20} />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-white text-base tracking-tight">MedTwin</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800">
                  IEEE
                </span>
              </div>
              <span className="text-[10px] text-slate-400 block leading-tight">
                3D Anatomical Twin Framework
              </span>
            </div>
          </div>
        </div>

        {/* Active Case Context Pill */}
        {activeCase && (
          <div className="mx-3 mt-3 p-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-xs">
            <div className="flex items-center justify-between text-slate-400 mb-1">
              <span className="text-[10px] uppercase font-semibold tracking-wider">Active Twin Target</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            </div>
            <div className="font-mono font-bold text-cyan-400 truncate">
              {activeCase.pseudonym}
            </div>
            <div className="text-[10px] text-slate-500 truncate mt-0.5">
              {activeCase.notes || 'De-identified longitudinal record'}
            </div>
          </div>
        )}

        {/* Navigation Items */}
        <nav className="p-2 space-y-1 mt-2 overflow-y-auto max-h-[calc(100vh-270px)]">
          {navItems.map((item) => {
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left ${
                  isActive
                    ? 'bg-gradient-to-r from-cyan-500/20 to-indigo-500/20 text-cyan-300 border border-cyan-500/30 font-semibold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2.5 truncate">
                  <span className={isActive ? 'text-cyan-400' : 'text-slate-500'}>
                    {item.icon}
                  </span>
                  <span className="truncate">{item.label}</span>
                </div>
                {item.badge && (
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border font-mono font-semibold shrink-0 ${item.badgeColor || 'bg-slate-900 text-slate-300 border-slate-700'}`}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* User Session & Logout */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/80">
        <div className="p-2 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 truncate">
            <div className="w-7 h-7 rounded-lg bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center text-xs font-bold shrink-0">
              {user?.full_name?.charAt(0) || user?.username?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="truncate text-left">
              <div className="text-xs font-semibold text-white truncate">
                {user?.full_name || user?.username || 'Authenticated User'}
              </div>
              <div className="text-[10px] text-slate-400 uppercase tracking-wider font-mono">
                {user?.role || 'CLINICIAN'}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-950/30 transition-colors shrink-0"
            title="Log out of session"
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </aside>
  );
};
