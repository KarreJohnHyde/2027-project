import React from 'react';
import { 
  FolderGit2, 
  Plus, 
  FileText, 
  Image as ImageIcon, 
  Activity, 
  Layers, 
  GitCompare, 
  Upload,
  Calendar,
  AlertCircle
} from 'lucide-react';
import type { Case, CaseStats } from '../types/medtwin';

interface CaseHeaderProps {
  cases: Case[];
  activeCase: Case | null;
  onSelectCase: (caseId: string) => void;
  onOpenCreateCase: () => void;
  onOpenFileUpload: () => void;
  caseStats: CaseStats | null;
}

export const CaseHeader: React.FC<CaseHeaderProps> = ({
  cases,
  activeCase,
  onSelectCase,
  onOpenCreateCase,
  onOpenFileUpload,
  caseStats,
}) => {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 md:p-6 mb-6 shadow-xl">
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
        {/* Case Selector */}
        <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <FolderGit2 size={20} />
            </div>
            <div>
              <span className="text-xs uppercase font-semibold tracking-wider text-slate-400">
                Active Digital Twin Case
              </span>
              <div className="flex items-center gap-2 mt-0.5">
                <select
                  value={activeCase?.id || ''}
                  onChange={(e) => onSelectCase(e.target.value)}
                  className="bg-slate-950 text-white font-semibold text-sm rounded-lg border border-slate-700 px-3 py-1.5 focus:outline-none focus:border-indigo-500"
                >
                  {cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.pseudonym} ({c.id.substring(0, 8)}...)
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-950/80 border border-slate-800 px-3 py-2 rounded-lg">
            <Calendar size={13} className="text-slate-500" />
            <span>Created: {activeCase ? new Date(activeCase.created_at).toLocaleDateString() : 'N/A'}</span>
          </div>

          <button
            type="button"
            onClick={onOpenCreateCase}
            className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-2 rounded-lg transition-colors"
          >
            <Plus size={14} />
            <span>New Case</span>
          </button>
        </div>

        {/* Upload Action */}
        <div className="flex items-center gap-3 w-full lg:w-auto justify-end">
          <button
            type="button"
            onClick={onOpenFileUpload}
            className="flex items-center gap-2 text-sm font-semibold text-white bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 px-4 py-2 rounded-xl shadow-lg shadow-indigo-500/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <Upload size={16} />
            <span>Upload Medical File</span>
          </button>
        </div>
      </div>

      {/* Case KPI Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-4">
        {/* Radiograph */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Radiograph</span>
            <ImageIcon size={14} className="text-cyan-400" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xl font-bold text-white">{caseStats?.images_count ?? 0}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
              (caseStats?.images_count ?? 0) > 0 ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-slate-900 text-slate-500'
            }`}>
              {(caseStats?.images_count ?? 0) > 0 ? 'Available' : 'Missing'}
            </span>
          </div>
        </div>

        {/* ECG Record */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Digital ECG</span>
            <Activity size={14} className="text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xl font-bold text-white">{caseStats?.ecg_count ?? 0}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
              (caseStats?.ecg_count ?? 0) > 0 ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-slate-900 text-slate-500'
            }`}>
              {(caseStats?.ecg_count ?? 0) > 0 ? 'Available' : 'Missing'}
            </span>
          </div>
        </div>

        {/* Clinical Report */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Clinical Report</span>
            <FileText size={14} className="text-indigo-400" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xl font-bold text-white">{caseStats?.reports_count ?? 0}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
              (caseStats?.reports_count ?? 0) > 0 ? 'bg-indigo-950 text-indigo-300 border border-indigo-800' : 'bg-slate-900 text-slate-500'
            }`}>
              {(caseStats?.reports_count ?? 0) > 0 ? 'Available' : 'Missing'}
            </span>
          </div>
        </div>

        {/* Multimodal Fusion Status */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Masked Fusion</span>
            <Layers size={14} className="text-purple-400" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-sm font-bold text-white truncate">
              {caseStats?.fusion_status || 'NOT_EVALUATED'}
            </span>
            <span className="text-[10px] text-slate-500">Eq. 8–10</span>
          </div>
        </div>

        {/* Concordance Flags */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Discordance Flags</span>
            <GitCompare size={14} className="text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className={`text-xl font-bold ${
              (caseStats?.concordance_flags_count ?? 0) > 0 ? 'text-amber-400' : 'text-emerald-400'
            }`}>
              {caseStats?.concordance_flags_count ?? 0}
            </span>
            {(caseStats?.concordance_flags_count ?? 0) > 0 ? (
              <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold bg-amber-950 text-amber-300 border border-amber-800 flex items-center gap-0.5">
                <AlertCircle size={10} /> Review
              </span>
            ) : (
              <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                Clear
              </span>
            )}
          </div>
        </div>

        {/* Pending Human Reviews */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Pending Review</span>
            <AlertCircle size={14} className="text-rose-400" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xl font-bold text-rose-300">{caseStats?.pending_reviews_count ?? 0}</span>
            <span className="text-[10px] text-slate-500">Unreviewed</span>
          </div>
        </div>
      </div>
    </div>
  );
};
