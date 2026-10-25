import React, { useState, useEffect, useCallback } from 'react';
import { 
  GitCompare, 
  Calendar, 
  ArrowRight, 
  AlertTriangle, 
  FileText, 
  Activity, 
  Box, 
  Download, 
  RefreshCw, 
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
  Sparkles,
  Info
} from 'lucide-react';
import type { 
  Case, 
  LongitudinalComparisonResponse, 
  SemanticReportDiffItem
} from '../types/medtwin';
import { api } from '../services/api';

interface LongitudinalComparisonViewProps {
  activeCase: Case | null;
}

export const LongitudinalComparisonView: React.FC<LongitudinalComparisonViewProps> = ({ activeCase }) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [data, setData] = useState<LongitudinalComparisonResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedDiffItem, setSelectedDiffItem] = useState<SemanticReportDiffItem | null>(null);
  const [copiedNotice, setCopiedNotice] = useState<boolean>(false);
  const [imageDifferenceMode, setImageDifferenceMode] = useState<string>('SIDE_BY_SIDE');

  const fetchComparison = useCallback(async () => {
    if (!activeCase) return;
    setLoading(true);
    setError(null);
    try {
      const comparisonData = await api.compareExaminations(activeCase.id);
      setData(comparisonData);
      if (comparisonData.semantic_report_diff && comparisonData.semantic_report_diff.length > 0) {
        setSelectedDiffItem(comparisonData.semantic_report_diff[0]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch longitudinal comparison';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [activeCase]);

  useEffect(() => {
    if (activeCase) {
      void fetchComparison();
    }
  }, [activeCase, fetchComparison]);

  const handleExportSummary = () => {
    if (!data) return;
    const summary = {
      case_pseudonym: data.case_pseudonym,
      interval_days: data.interval_days,
      prior_exam_date: data.prior_examination?.date,
      current_exam_date: data.current_examination?.date,
      semantic_diffs: data.semantic_report_diff.map(d => ({
        finding: d.finding,
        classification: d.classification,
        rationale: d.clinical_rationale
      })),
      numeric_deltas: data.numeric_deltas.map(n => ({
        metric: n.metric_name,
        prior: n.prior_value,
        current: n.current_value,
        unit: n.unit,
        delta: n.absolute_delta,
        pct: n.percentage_delta,
        rate_per_day: n.rate_per_day,
        trend: n.trend_direction
      })),
      timestamp: new Date().toISOString(),
      disclaimer: data.notice
    };
    navigator.clipboard.writeText(JSON.stringify(summary, null, 2));
    setCopiedNotice(true);
    setTimeout(() => setCopiedNotice(false), 3000);
  };

  const getClassificationBadge = (classification: string) => {
    switch (classification) {
      case 'EXPLICITLY_IMPROVED':
        return <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">EXPLICITLY IMPROVED</span>;
      case 'EXPLICITLY_RESOLVED':
        return <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-teal-950 text-teal-300 border border-teal-800">EXPLICITLY RESOLVED</span>;
      case 'EXPLICITLY_WORSENED':
        return <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950 text-rose-300 border border-rose-800">EXPLICITLY WORSENED</span>;
      case 'NEWLY_REPORTED':
        return <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-800">NEWLY REPORTED</span>;
      case 'PRESENT_IN_BOTH':
        return <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-950 text-blue-300 border border-blue-800">PRESENT IN BOTH</span>;
      case 'CONTRADICTORY':
        return <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-950 text-purple-300 border border-purple-800">CONTRADICTORY</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-slate-800 text-slate-300 border border-slate-700">{classification}</span>;
    }
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'INCREASING':
        return <TrendingUp size={14} className="text-cyan-400" />;
      case 'DECREASING':
        return <TrendingDown size={14} className="text-amber-400" />;
      default:
        return <Minus size={14} className="text-slate-400" />;
    }
  };

  if (!activeCase) {
    return (
      <div className="p-8 text-center bg-slate-900 border border-slate-800 rounded-2xl max-w-lg mx-auto mt-16">
        <GitCompare size={40} className="mx-auto text-slate-600 mb-3" />
        <h3 className="text-lg font-bold text-white mb-1">No Active Case Selected</h3>
        <p className="text-sm text-slate-400">
          Select or create an authorized case in Case Management to run longitudinal Old Self vs. New Self diffing.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/90 border border-slate-800 p-5 rounded-2xl">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-white tracking-tight">Longitudinal "Old Self vs. New Self" Engine</h2>
            <span className="px-2 py-0.5 text-xs font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800 rounded-md">
              IEEE Section IX
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Semantic report diffing, zero-guarded numeric deltas, 2D radiograph registration, and 3D digital twin state transitions.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={fetchComparison}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 rounded-xl transition border border-slate-700 disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Re-compare
          </button>
          <button
            onClick={handleExportSummary}
            disabled={!data}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-cyan-600 hover:bg-cyan-500 rounded-xl transition shadow-md shadow-cyan-600/20 disabled:opacity-50"
          >
            <Download size={14} />
            {copiedNotice ? 'Copied to Clipboard!' : 'Export Summary'}
          </button>
        </div>
      </div>

      {loading && (
        <div className="p-12 text-center bg-slate-900 border border-slate-800 rounded-2xl">
          <RefreshCw size={32} className="mx-auto text-cyan-400 animate-spin mb-3" />
          <p className="text-sm font-semibold text-white">Aligning Chronological Examinations...</p>
          <p className="text-xs text-slate-400 mt-1">Executing rigid registration, extracting semantic diffs, and computing delta rates.</p>
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-950/50 border border-rose-800 rounded-xl text-rose-200 text-xs flex items-center gap-2">
          <AlertTriangle size={16} className="text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {data && !loading && (
        <>
          {/* Comparison Timeline Banner */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Baseline ("Old Self")</span>
              <div className="flex items-center gap-2 mt-1">
                <Calendar size={16} className="text-cyan-400" />
                <span className="font-mono font-bold text-white text-sm">
                  {data.prior_examination?.date ? new Date(data.prior_examination.date).toLocaleDateString() : 'N/A'}
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                  {data.prior_examination?.modality}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1 truncate">
                {data.prior_examination?.indication || 'Acute baseline assessment'}
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl flex flex-col justify-center items-center text-center">
              <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Elapsed Interval</span>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-2xl font-bold font-mono text-cyan-400">{data.interval_days}</span>
                <span className="text-xs text-slate-400">days between exams</span>
              </div>
              <span className="text-[10px] text-emerald-400 mt-0.5 font-semibold">
                Sufficient for longitudinal rate evaluation
              </span>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Current ("New Self")</span>
              <div className="flex items-center gap-2 mt-1">
                <Calendar size={16} className="text-emerald-400" />
                <span className="font-mono font-bold text-white text-sm">
                  {data.current_examination?.date ? new Date(data.current_examination.date).toLocaleDateString() : 'N/A'}
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                  {data.current_examination?.modality}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1 truncate">
                {data.current_examination?.indication || 'Follow-up assessment'}
              </p>
            </div>
          </div>

          {/* Section 1: Semantic Report Diffing Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-cyan-400" />
                <h3 className="font-bold text-white text-sm">Semantic Report Diffing Matrix</h3>
                <span className="text-xs text-slate-500">({data.semantic_report_diff?.length || 0} findings analyzed)</span>
              </div>
              <span className="text-[11px] text-slate-400 italic">
                Rule 9: Missing phrases are never inferred as disease resolution
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-slate-800">
              {/* Finding list */}
              <div className="lg:col-span-5 max-h-[380px] overflow-y-auto divide-y divide-slate-800/60">
                {data.semantic_report_diff?.map((item, idx) => (
                  <div
                    key={idx}
                    onClick={() => setSelectedDiffItem(item)}
                    className={`p-3.5 cursor-pointer transition flex items-center justify-between ${
                      selectedDiffItem?.finding === item.finding
                        ? 'bg-cyan-950/40 border-l-4 border-cyan-500'
                        : 'hover:bg-slate-800/40'
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="font-semibold text-xs text-white">{item.finding}</div>
                      <div className="text-[11px] text-slate-400">{item.anatomy}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      {getClassificationBadge(item.classification)}
                      <ChevronRight size={14} className="text-slate-500" />
                    </div>
                  </div>
                ))}
              </div>

              {/* Finding Detail / Excerpts */}
              <div className="lg:col-span-7 p-5 space-y-4 bg-slate-950/40">
                {selectedDiffItem ? (
                  <>
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="font-bold text-white text-sm">{selectedDiffItem.finding}</h4>
                        <span className="text-xs text-cyan-400 font-mono">{selectedDiffItem.anatomy}</span>
                      </div>
                      <div className="text-right">
                        {getClassificationBadge(selectedDiffItem.classification)}
                        <div className="text-[10px] text-slate-500 mt-1">
                          Confidence: {(selectedDiffItem.confidence * 100).toFixed(0)}%
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {/* Prior State */}
                      <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1.5">
                        <div className="flex items-center justify-between text-[11px] text-slate-400">
                          <span className="font-semibold">Prior State ({new Date(selectedDiffItem.prior_state.exam_date).toLocaleDateString()})</span>
                          <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-slate-300 font-mono">
                            {selectedDiffItem.prior_state.negation}
                          </span>
                        </div>
                        <p className="text-xs text-slate-200 italic bg-slate-950 p-2.5 rounded-lg border border-slate-800/80 leading-relaxed">
                          "{selectedDiffItem.prior_state.text}"
                        </p>
                      </div>

                      {/* Current State */}
                      <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1.5">
                        <div className="flex items-center justify-between text-[11px] text-slate-400">
                          <span className="font-semibold">Current State ({new Date(selectedDiffItem.current_state.exam_date).toLocaleDateString()})</span>
                          <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-slate-300 font-mono">
                            {selectedDiffItem.current_state.negation}
                          </span>
                        </div>
                        <p className="text-xs text-slate-200 italic bg-slate-950 p-2.5 rounded-lg border border-slate-800/80 leading-relaxed">
                          "{selectedDiffItem.current_state.text}"
                        </p>
                      </div>
                    </div>

                    <div className="p-3 rounded-xl bg-cyan-950/30 border border-cyan-800/50 text-xs text-cyan-200">
                      <span className="font-semibold text-cyan-300 block mb-1">Clinical Comparison Rationale:</span>
                      {selectedDiffItem.clinical_rationale}
                    </div>
                  </>
                ) : (
                  <div className="p-8 text-center text-slate-500 text-xs">
                    Select a finding on the left to inspect verbatim source report excerpts and clinical diff rationale.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Section 2: Quantitative Numeric Deltas Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-emerald-400" />
                <h3 className="font-bold text-white text-sm">Quantitative Longitudinal Metric Deltas</h3>
                <span className="text-xs text-slate-500">({data.numeric_deltas?.length || 0} metrics)</span>
              </div>
              <span className="text-[11px] text-slate-400">
                Guarded percentage delta: safe against 0-division
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4">Metric</th>
                    <th className="py-3 px-3">Unit</th>
                    <th className="py-3 px-3">Prior Val</th>
                    <th className="py-3 px-3">Current Val</th>
                    <th className="py-3 px-3">Abs Delta</th>
                    <th className="py-3 px-3">% Delta</th>
                    <th className="py-3 px-3">Rate / Day</th>
                    <th className="py-3 px-3">Trend</th>
                    <th className="py-3 px-4">Reference Range</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-200 font-mono">
                  {data.numeric_deltas?.map((row, i) => (
                    <tr key={i} className="hover:bg-slate-800/40 transition">
                      <td className="py-3 px-4 font-sans font-semibold text-white">{row.metric_name}</td>
                      <td className="py-3 px-3 text-slate-400">{row.unit}</td>
                      <td className="py-3 px-3">{row.prior_value}</td>
                      <td className="py-3 px-3 text-cyan-300 font-bold">{row.current_value}</td>
                      <td className={`py-3 px-3 font-bold ${row.absolute_delta > 0 ? 'text-cyan-400' : 'text-amber-400'}`}>
                        {row.absolute_delta > 0 ? `+${row.absolute_delta}` : row.absolute_delta}
                      </td>
                      <td className="py-3 px-3">
                        {row.percentage_delta !== null ? (
                          <span className={row.percentage_delta > 0 ? 'text-cyan-400' : 'text-amber-400'}>
                            {row.percentage_delta > 0 ? `+${row.percentage_delta.toFixed(1)}%` : `${row.percentage_delta.toFixed(1)}%`}
                          </span>
                        ) : (
                          <span className="text-slate-500">N/A (0 Base)</span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-slate-300">
                        {row.rate_per_day !== null ? `${row.rate_per_day > 0 ? '+' : ''}${row.rate_per_day} /d` : 'N/A'}
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1 font-sans text-[11px]">
                          {getTrendIcon(row.trend_direction)}
                          <span>{row.trend_direction}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-sans text-slate-400">{row.reference_range}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 3: Radiograph Alignment & 3D Digital Twin State Transition */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* 2D Radiograph Comparison */}
            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <GitCompare size={16} className="text-cyan-400" />
                  <h3 className="font-bold text-white text-sm">Medical Radiograph Alignment</h3>
                </div>
                <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                  {data.image_comparison?.status || 'REGISTERED'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs space-y-2">
                <div className="flex items-center justify-between text-slate-300">
                  <span>Alignment Method:</span>
                  <span className="font-mono text-cyan-300 font-semibold">{data.image_comparison?.registration_method}</span>
                </div>
                <div className="flex items-center justify-between text-slate-300">
                  <span>Target Registration Error (TRE):</span>
                  <span className="font-mono text-emerald-400 font-bold">{data.image_comparison?.registration_tre_mm} mm</span>
                </div>
                <div className="flex items-center justify-between text-slate-300">
                  <span>Mean Alignment Residual:</span>
                  <span className="font-mono text-slate-400">{data.image_comparison?.registration_error_pixels} pixels</span>
                </div>
                <div className="flex items-center justify-between text-slate-300">
                  <span>Structural Remodeling:</span>
                  <span className="font-semibold text-emerald-300">{data.image_comparison?.change_region}</span>
                </div>
              </div>

              {/* View mode buttons */}
              <div>
                <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-2">Difference Display Mode</span>
                <div className="flex flex-wrap gap-2">
                  {['SIDE_BY_SIDE', 'SYNCHRONIZED_ZOOM', 'SUBTRACTION_OVERLAY', 'CHECKERBOARD'].map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setImageDifferenceMode(mode)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                        imageDifferenceMode === mode
                          ? 'bg-cyan-600 text-white shadow-sm'
                          : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      {mode.replace(/_/g, ' ')}
                    </button>
                  ))}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 flex items-center justify-around text-center py-6">
                <div>
                  <div className="w-20 h-20 mx-auto rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center font-mono text-[10px] text-slate-400 mb-1">
                    [Prior PA]
                  </div>
                  <span className="text-[10px] text-slate-400 block">{data.image_comparison?.prior_filename}</span>
                </div>
                <ArrowRight size={20} className="text-cyan-400" />
                <div>
                  <div className="w-20 h-20 mx-auto rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center font-mono text-[10px] text-slate-400 mb-1">
                    [Follow-up PA]
                  </div>
                  <span className="text-[10px] text-slate-400 block">{data.image_comparison?.current_filename}</span>
                </div>
              </div>

              <p className="text-[10px] text-slate-500 leading-tight">
                {data.image_comparison?.notice}
              </p>
            </div>

            {/* 3D Digital Twin State Transition */}
            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Box size={16} className="text-purple-400" />
                  <h3 className="font-bold text-white text-sm">3D Anatomical Twin State Transition</h3>
                </div>
                <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-950 text-purple-300 border border-purple-800">
                  {data.twin_state_delta?.prior_twin_state?.representation_level || 'L2_FINDING_ASSOCIATED'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {/* Prior Twin State */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <span className="text-[10px] uppercase font-bold text-rose-400 tracking-wider">Prior Twin State</span>
                  <div className="font-mono text-xs text-white font-bold">
                    {data.twin_state_delta?.prior_twin_state?.status}
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Active Mesh: <span className="font-mono text-slate-300">{data.twin_state_delta?.prior_twin_state?.active_mesh}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px]">
                    <span>Shader Color:</span>
                    <span 
                      className="w-4 h-4 rounded-full border border-slate-600 inline-block shadow-sm"
                      style={{ backgroundColor: data.twin_state_delta?.prior_twin_state?.color_hex }}
                    />
                    <span className="font-mono text-[10px] text-slate-400">{data.twin_state_delta?.prior_twin_state?.color_hex}</span>
                  </div>
                </div>

                {/* Current Twin State */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">Current Twin State</span>
                  <div className="font-mono text-xs text-white font-bold">
                    {data.twin_state_delta?.current_twin_state?.status}
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Active Mesh: <span className="font-mono text-slate-300">{data.twin_state_delta?.current_twin_state?.active_mesh}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px]">
                    <span>Shader Color:</span>
                    <span 
                      className="w-4 h-4 rounded-full border border-slate-600 inline-block shadow-sm"
                      style={{ backgroundColor: data.twin_state_delta?.current_twin_state?.color_hex }}
                    />
                    <span className="font-mono text-[10px] text-slate-400">{data.twin_state_delta?.current_twin_state?.color_hex}</span>
                  </div>
                </div>
              </div>

              <div>
                <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-2">Supported Synchronized View Modes</span>
                <div className="flex flex-wrap gap-2">
                  {data.twin_state_delta?.view_modes_supported?.map((mode) => (
                    <span key={mode} className="px-2.5 py-1 rounded bg-slate-800 text-slate-300 text-xs font-mono border border-slate-700">
                      {mode}
                    </span>
                  ))}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-purple-950/30 border border-purple-800/40 text-xs text-purple-200 flex items-start gap-2">
                <Sparkles size={16} className="text-purple-400 shrink-0 mt-0.5" />
                <span>
                  The 3D anatomical twin switches shader states based on verifiable structural remodeling and held-out TRE gates, preserving atlas fidelity without arbitrary geometry deformation.
                </span>
              </div>
            </div>
          </div>

          {/* Research Notice Footer */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-[11px] text-slate-400 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Info size={14} className="text-cyan-400 shrink-0" />
              <span>{data.notice}</span>
            </div>
            <span className="font-mono text-slate-500">IEEE Ref: MedTwin-2026-SecIX</span>
          </div>
        </>
      )}
    </div>
  );
};
