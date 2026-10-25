import React from 'react';
import { 
  FolderGit2, 
  Image as ImageIcon, 
  Activity, 
  FileText, 
  CheckCircle2, 
  Clock, 
  XCircle, 
  Box, 
  TrendingUp, 
  ArrowUpRight, 
  ShieldAlert, 
  Cpu, 
  Calendar,
  Plus
} from 'lucide-react';
import type { 
  Case, 
  CaseStats, 
  Examination, 
  Finding, 
  MultimodalFusionRecord, 
  NavigationTab, 
  UploadedFile 
} from '../types/medtwin';

interface DashboardViewProps {
  cases: Case[];
  activeCase: Case | null;
  caseStats: CaseStats | null;
  examinations: Examination[];
  findings: Finding[];
  files: UploadedFile[];
  fusionRecord: MultimodalFusionRecord | null;
  onNavigateTab: (tab: NavigationTab) => void;
  onOpenCreateCase: () => void;
  onOpenFileUpload: () => void;
  systemStatus: {
    app_name: string;
    version: string;
    active_cases_count: number;
    models_status: Record<string, string>;
  } | null;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  cases,
  activeCase,
  caseStats,
  examinations,
  findings,
  files,
  fusionRecord,
  onNavigateTab,
  onOpenCreateCase,
  onOpenFileUpload,
  systemStatus,
}) => {
  const imagesCount = files.filter(f => f.modality === 'IMAGE').length;
  const ecgCount = files.filter(f => f.modality === 'ECG').length;
  const reportCount = files.filter(f => f.modality === 'REPORT').length;
  const pendingReviews = findings.filter(f => f.review_status === 'PENDING_HUMAN_REVIEW').length;
  const completedReviews = findings.filter(f => f.review_status === 'CONFIRMED' || f.review_status === 'AMENDED').length;
  const rejectedFindings = findings.filter(f => f.review_status === 'REJECTED' || f.evidence_status === 'REJECT' || f.evidence_status === 'ERROR').length;

  // Check if findings are synthetic demo vs actual model
  const isDemoActive = findings.some(f => Boolean(f.details_json?.is_demo)) || (caseStats && 'is_demo_data' in caseStats ? Boolean((caseStats as unknown as { is_demo_data: boolean }).is_demo_data) : false);

  return (
    <div className="space-y-6">
      {/* Welcome & Data Provenance Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-900 to-indigo-950/40 border border-slate-800 rounded-2xl p-5 md:p-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase font-bold tracking-wider text-cyan-400">MedTwin Executive Control</span>
              <span className="text-slate-600">•</span>
              <span className="text-xs text-slate-400">Research Prototype Dashboard</span>
            </div>
            <h2 className="text-xl md:text-2xl font-bold text-white mt-1 tracking-tight">
              Multimodal 3D Digital Twin Command Center
            </h2>
            <p className="text-xs text-slate-300 mt-1 max-w-2xl leading-relaxed">
              Synthesizes 2D musculoskeletal radiographs (MURA protocol), multi-lead ECG time-series (PTB-XL),
              and de-identified narrative clinical reports into a unified 3D anatomical twin.
            </p>
          </div>

          {/* Actual vs Demo Data Distinction Badge */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 shrink-0">
            <div className={`px-3 py-1.5 rounded-xl border text-xs font-semibold flex items-center gap-2 ${
              isDemoActive 
                ? 'bg-amber-950/60 border-amber-800 text-amber-300' 
                : 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
            }`}>
              <span className={`w-2 h-2 rounded-full ${isDemoActive ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'}`} />
              <span>{isDemoActive ? 'DEMO / SYNTHETIC RESEARCH DATA' : 'ACTUAL ANALYSIS RUN'}</span>
            </div>

            <button
              type="button"
              onClick={onOpenCreateCase}
              className="px-3.5 py-2 rounded-xl text-xs font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-all flex items-center gap-1.5"
            >
              <Plus size={14} />
              <span>Create New Case</span>
            </button>

            <button
              type="button"
              onClick={onOpenFileUpload}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 shadow-md shadow-cyan-600/20 transition-all hover:scale-[1.02]"
            >
              Upload Digital Record
            </button>
          </div>
        </div>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {/* Cases */}
        <div 
          onClick={() => onNavigateTab('CASE_MANAGEMENT')}
          className="bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 cursor-pointer transition-all flex flex-col justify-between group"
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Cases</span>
            <FolderGit2 size={16} className="text-indigo-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-white">{cases.length}</span>
            <span className="text-[10px] text-indigo-400 flex items-center">Manage <ArrowUpRight size={10} /></span>
          </div>
        </div>

        {/* Radiographs */}
        <div 
          onClick={() => onNavigateTab('IMAGE_ANALYSIS')}
          className="bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 cursor-pointer transition-all flex flex-col justify-between group"
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Radiographs</span>
            <ImageIcon size={16} className="text-cyan-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-white">{imagesCount}</span>
            <span className="text-[10px] text-cyan-400 flex items-center">Inspect <ArrowUpRight size={10} /></span>
          </div>
        </div>

        {/* ECG Records */}
        <div 
          onClick={() => onNavigateTab('ECG_ANALYSIS')}
          className="bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 cursor-pointer transition-all flex flex-col justify-between group"
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>ECG Signals</span>
            <Activity size={16} className="text-emerald-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-white">{ecgCount}</span>
            <span className="text-[10px] text-emerald-400 flex items-center">Waveforms <ArrowUpRight size={10} /></span>
          </div>
        </div>

        {/* Reports */}
        <div 
          onClick={() => onNavigateTab('REPORT_NLP')}
          className="bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 cursor-pointer transition-all flex flex-col justify-between group"
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Reports</span>
            <FileText size={16} className="text-amber-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-white">{reportCount}</span>
            <span className="text-[10px] text-amber-400 flex items-center">NLP <ArrowUpRight size={10} /></span>
          </div>
        </div>

        {/* Completed Analyses */}
        <div 
          onClick={() => onNavigateTab('MULTIMODAL_FUSION')}
          className="bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 cursor-pointer transition-all flex flex-col justify-between group"
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Completed</span>
            <CheckCircle2 size={16} className="text-emerald-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-white">{completedReviews}</span>
            <span className="text-[10px] text-emerald-400 flex items-center">Fused <ArrowUpRight size={10} /></span>
          </div>
        </div>

        {/* Pending Reviews */}
        <div 
          onClick={() => onNavigateTab('HUMAN_REVIEW')}
          className="bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 cursor-pointer transition-all flex flex-col justify-between group"
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Pending Review</span>
            <Clock size={16} className="text-amber-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className={`text-2xl font-bold ${pendingReviews > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
              {pendingReviews}
            </span>
            <span className="text-[10px] text-amber-400 flex items-center">Review <ArrowUpRight size={10} /></span>
          </div>
        </div>

        {/* Rejected / Quality Rejections */}
        <div 
          onClick={() => onNavigateTab('HUMAN_REVIEW')}
          className="bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 cursor-pointer transition-all flex flex-col justify-between group"
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Rejected</span>
            <XCircle size={16} className="text-rose-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className={`text-2xl font-bold ${rejectedFindings > 0 ? 'text-rose-400' : 'text-slate-400'}`}>
              {rejectedFindings}
            </span>
            <span className="text-[10px] text-rose-400 flex items-center">Audits <ArrowUpRight size={10} /></span>
          </div>
        </div>
      </div>

      {/* Main Grid: Recent Examinations & Active Twin Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Chronological Examinations & Modality Synthesis */}
        <div className="lg:col-span-2 space-y-6">
          {/* Active Case Summary Card */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3.5 mb-4">
              <div className="flex items-center gap-2">
                <FolderGit2 size={18} className="text-cyan-400" />
                <h3 className="text-sm font-bold text-white">Active Case Profile: {activeCase?.pseudonym || 'No Case Selected'}</h3>
              </div>
              <button
                type="button"
                onClick={() => onNavigateTab('CASE_MANAGEMENT')}
                className="text-xs text-cyan-400 hover:underline flex items-center gap-1"
              >
                <span>Switch Case</span>
                <ArrowUpRight size={12} />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-[10px] uppercase font-semibold text-slate-500">Pseudonym Token</span>
                <div className="text-sm font-mono font-bold text-white mt-0.5">{activeCase?.pseudonym}</div>
                <span className="text-[10px] text-slate-500">De-identified ID</span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-[10px] uppercase font-semibold text-slate-500">Multimodal Fusion</span>
                <div className="text-sm font-bold text-purple-400 mt-0.5">
                  {fusionRecord?.fusion_status || 'NOT_RUN'}
                </div>
                <span className="text-[10px] text-slate-500">
                  {fusionRecord?.paired_data_validated ? 'Paired Validation Passed' : 'Awaiting 2+ Modalities'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-[10px] uppercase font-semibold text-slate-500">3D Registration Gate</span>
                <div className="text-sm font-bold text-emerald-400 mt-0.5">
                  L1 Generic / L2 Gated
                </div>
                <span className="text-[10px] text-slate-500">Held-out TRE Evaluator</span>
              </div>
            </div>

            {/* Quick Actions to Specialized Pages */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
              <button
                type="button"
                onClick={() => onNavigateTab('IMAGE_ANALYSIS')}
                className="p-2.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-left transition-colors flex items-center gap-2 text-xs"
              >
                <ImageIcon size={14} className="text-cyan-400" />
                <span className="font-semibold text-slate-200">X-Ray Analysis</span>
              </button>

              <button
                type="button"
                onClick={() => onNavigateTab('ECG_ANALYSIS')}
                className="p-2.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-left transition-colors flex items-center gap-2 text-xs"
              >
                <Activity size={14} className="text-emerald-400" />
                <span className="font-semibold text-slate-200">ECG Waveforms</span>
              </button>

              <button
                type="button"
                onClick={() => onNavigateTab('ANATOMICAL_3D')}
                className="p-2.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-left transition-colors flex items-center gap-2 text-xs"
              >
                <Box size={14} className="text-indigo-400" />
                <span className="font-semibold text-slate-200">3D Anatomy</span>
              </button>

              <button
                type="button"
                onClick={() => onNavigateTab('TIMELINE_FORECASTING')}
                className="p-2.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-left transition-colors flex items-center gap-2 text-xs"
              >
                <TrendingUp size={14} className="text-purple-400" />
                <span className="font-semibold text-slate-200">Forecasting</span>
              </button>
            </div>
          </div>

          {/* Chronological Examinations Feed */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3.5 mb-4">
              <div className="flex items-center gap-2">
                <Calendar size={18} className="text-emerald-400" />
                <h3 className="text-sm font-bold text-white">Longitudinal Examination Feed ({examinations.length})</h3>
              </div>
              <button
                type="button"
                onClick={() => onNavigateTab('TIMELINE_FORECASTING')}
                className="text-xs text-emerald-400 hover:underline flex items-center gap-1"
              >
                <span>Timeline View</span>
                <ArrowUpRight size={12} />
              </button>
            </div>

            {examinations.length > 0 ? (
              <div className="space-y-3">
                {examinations.map((exam, idx) => (
                  <div 
                    key={exam.id}
                    className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 flex items-start justify-between gap-3"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
                        {exam.examination_type === 'IMAGE' && <ImageIcon size={15} className="text-cyan-400" />}
                        {exam.examination_type === 'ECG' && <Activity size={15} className="text-emerald-400" />}
                        {exam.examination_type === 'REPORT' && <FileText size={15} className="text-amber-400" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-xs text-white">
                            Exam #{idx + 1}: {exam.examination_type}
                          </span>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                            {new Date(exam.timestamp).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 mt-1">
                          {exam.clinician_notes || 'Routine follow-up evaluation.'}
                        </p>
                      </div>
                    </div>
                    <span className="text-[10px] text-slate-500 shrink-0 font-mono">
                      ID: {exam.id.substring(0, 8)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-xs text-slate-500">
                No dated examinations logged for this case.
              </div>
            )}
          </div>
        </div>

        {/* Right Col: ML Model Telemetry & Research Safety */}
        <div className="space-y-6">
          {/* Model Status Card */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-xl">
            <div className="flex items-center gap-2 border-b border-slate-800 pb-3 mb-4">
              <Cpu size={18} className="text-cyan-400" />
              <h3 className="text-sm font-bold text-white">Machine Learning Telemetry</h3>
            </div>

            <div className="space-y-2.5 text-xs">
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-slate-400">Radiograph Classifier</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                  ResNet-18 (MURA)
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-slate-400">ECG Signal Model</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                  1D-CNN (PTB-XL)
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-slate-400">Clinical Report NLP</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                  Rule+Transformer
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-slate-400">Multimodal Gated Fusion</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-purple-950 text-purple-300 border border-purple-800">
                  Eqs. 8–10 Masked
                </span>
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-slate-400">Arun 3D Registration Gate</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800">
                  Held-Out TRE ≤ 5mm
                </span>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800 text-[11px] text-slate-500">
              {systemStatus ? (
                <div>
                  <span className="font-semibold text-slate-400">{systemStatus.app_name}</span> v{systemStatus.version} • {systemStatus.active_cases_count} Active Cases
                </div>
              ) : (
                <span>Backend runtime: FastAPI 0.115 + PyTorch 2.4.</span>
              )}
            </div>
          </div>

          {/* Research Safety Mandate */}
          <div className="bg-amber-500/10 border border-amber-500/20 rounded-2xl p-5 text-xs text-amber-200">
            <div className="flex items-center gap-2 font-bold text-amber-400 mb-2">
              <ShieldAlert size={16} />
              <span>Research Mandate & Human Oversight</span>
            </div>
            <p className="leading-relaxed text-slate-300">
              MedTwin never claims to replace clinicians or diagnose diseases. Every model output is marked
              <code className="text-amber-400 mx-1">PENDING_HUMAN_REVIEW</code> until validated by an authorized clinician.
              Missing modalities never fabricate positive findings, and generic Blender meshes are never represented as patient-specific anatomy.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
