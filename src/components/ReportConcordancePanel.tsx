import { GitCompare, Play, AlertTriangle, CheckCircle2, ShieldAlert, Info } from 'lucide-react';
import type { ConcordanceRecord } from '../types/medtwin';

interface ReportConcordancePanelProps {
  concordanceRecords: ConcordanceRecord[];
  onRunConcordance: () => void;
  loading: boolean;
}

export const ReportConcordancePanel: React.FC<ReportConcordancePanelProps> = ({
  concordanceRecords,
  onRunConcordance,
  loading,
}) => {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 mb-6 shadow-xl">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <GitCompare size={18} />
            </div>
            <h3 className="text-sm font-bold text-white">Report Concordance Cross-Check</h3>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-950 text-amber-300 border border-amber-800">
              IEEE Section VII
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Compares clinical report text statements against model findings. Flags potential discordance for human review.
          </p>
        </div>

        <button
          type="button"
          disabled={loading}
          onClick={onRunConcordance}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow-md shadow-amber-600/20 transition-all disabled:opacity-50"
        >
          <Play size={13} />
          <span>{loading ? 'Evaluating...' : 'Run Concordance Cross-Check'}</span>
        </button>
      </div>

      {/* Mandatory Source Preservation Notice */}
      <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 mb-5 flex items-start gap-3">
        <Info size={16} className="text-amber-400 shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <strong>Evidence Preservation Guarantee:</strong> Concordance analysis never automatically modifies
          the clinician's report text or changes model outputs. Agreement does not prove correctness;
          disagreement generates an explicit review flag for clinician review.
        </div>
      </div>

      {/* Concordance Table */}
      <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950">
        {concordanceRecords.length > 0 ? (
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">Category</th>
                <th className="p-3">Model Finding</th>
                <th className="p-3">Report Statement</th>
                <th className="p-3">Concordance Status</th>
                <th className="p-3">Review Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-850">
              {concordanceRecords.map((rec) => (
                <tr key={rec.id} className="hover:bg-slate-900/40">
                  <td className="p-3 font-semibold text-slate-200">{rec.finding_category}</td>
                  <td className="p-3">
                    <span className="font-medium text-white">{rec.model_label}</span>
                    <span className="block text-[10px] text-slate-500">
                      Modality: {rec.model_modality} ({(rec.model_confidence * 100).toFixed(0)}%)
                    </span>
                  </td>
                  <td className="p-3">
                    <span className="italic text-slate-300">"{rec.report_statement_text}"</span>
                    <span className="block text-[10px] text-slate-500">
                      State: {rec.report_negated ? 'NEGATED in report' : 'AFFIRMED in report'}
                    </span>
                  </td>
                  <td className="p-3">
                    {rec.is_concordant ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                        <CheckCircle2 size={12} /> CONCORDANT
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-800">
                        <AlertTriangle size={12} /> DISCORDANCE FLAG
                      </span>
                    )}
                  </td>
                  <td className="p-3 text-slate-400">
                    {rec.review_flag ? (
                      <span className="text-amber-400 font-medium flex items-center gap-1">
                        <ShieldAlert size={13} /> Requires Review
                      </span>
                    ) : (
                      <span className="text-slate-500">None required</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-center p-8 text-slate-500 text-xs">
            No concordance evaluations executed yet. Click "Run Concordance Cross-Check" to compare.
          </div>
        )}
      </div>
    </div>
  );
};
