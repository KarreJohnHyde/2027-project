import { useState } from 'react';
import { UserCheck, CheckCircle2, XCircle, Edit3, MessageSquare, Clock } from 'lucide-react';
import type { Finding, ReviewStatus } from '../types/medtwin';

interface HumanReviewPanelProps {
  findings: Finding[];
  onSubmitReview: (findingId: string, status: ReviewStatus, notes?: string) => void;
  loading: boolean;
}

export const HumanReviewPanel: React.FC<HumanReviewPanelProps> = ({
  findings,
  onSubmitReview,
  loading,
}) => {
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>('CONFIRMED');
  const [reviewComment, setReviewComment] = useState<string>('');

  const handleOpenReview = (f: Finding) => {
    setSelectedFindingId(f.id);
    setReviewStatus(f.review_status === 'PENDING_HUMAN_REVIEW' ? 'CONFIRMED' : f.review_status);
    setReviewComment(f.review_comments || '');
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFindingId) return;
    onSubmitReview(selectedFindingId, reviewStatus, reviewComment);
    setSelectedFindingId(null);
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 mb-6 shadow-xl">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <UserCheck size={18} />
            </div>
            <h3 className="text-sm font-bold text-white">Human Clinician Review & Audit Trail</h3>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800">
              IEEE Section IV, VII
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Every AI model finding is marked PENDING_HUMAN_REVIEW until explicitly validated by an authorized clinician.
          </p>
        </div>
      </div>

      {/* Findings Table */}
      <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950 mb-5">
        {findings.length > 0 ? (
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">Modality / Task</th>
                <th className="p-3">Model Finding</th>
                <th className="p-3">Confidence</th>
                <th className="p-3">Review Status</th>
                <th className="p-3">Clinician Notes</th>
                <th className="p-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-850">
              {findings.map((f) => (
                <tr key={f.id} className="hover:bg-slate-900/40">
                  <td className="p-3">
                    <span className="font-semibold text-white">{f.task_name}</span>
                    <span className="block text-[10px] text-slate-500 font-mono">
                      {f.modality} • {f.model_version}
                    </span>
                  </td>
                  <td className="p-3 font-medium text-slate-200">{f.finding_label}</td>
                  <td className="p-3">
                    <span className="text-slate-200 font-mono">
                      {(f.raw_confidence * 100).toFixed(1)}%
                    </span>
                    {f.calibrated_confidence && (
                      <span className="block text-[10px] text-emerald-400">
                        Cal: {(f.calibrated_confidence * 100).toFixed(1)}%
                      </span>
                    )}
                  </td>
                  <td className="p-3">
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold ${
                      f.review_status === 'CONFIRMED'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        : f.review_status === 'REJECTED'
                        ? 'bg-rose-950 text-rose-300 border border-rose-800'
                        : f.review_status === 'AMENDED'
                        ? 'bg-amber-950 text-amber-300 border border-amber-800'
                        : 'bg-slate-900 text-amber-300 border border-amber-900/80 animate-pulse'
                    }`}>
                      {f.review_status === 'CONFIRMED' && <CheckCircle2 size={11} />}
                      {f.review_status === 'REJECTED' && <XCircle size={11} />}
                      {f.review_status === 'AMENDED' && <Edit3 size={11} />}
                      {f.review_status === 'PENDING_HUMAN_REVIEW' && <Clock size={11} />}
                      <span>{f.review_status}</span>
                    </span>
                  </td>
                  <td className="p-3 text-slate-400 italic max-w-xs truncate">
                    {f.review_comments || 'No comments'}
                  </td>
                  <td className="p-3 text-right">
                    <button
                      type="button"
                      onClick={() => handleOpenReview(f)}
                      className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors"
                    >
                      Review
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-center p-8 text-slate-500 text-xs">
            No findings generated yet for this case.
          </div>
        )}
      </div>

      {/* Review Modal Form */}
      {selectedFindingId && (
        <div className="p-4 rounded-xl bg-slate-950 border border-indigo-500/40 mt-4 space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <h4 className="text-xs font-bold text-white flex items-center gap-2">
              <MessageSquare size={14} className="text-indigo-400" />
              <span>Record Clinician Assessment</span>
            </h4>
            <span className="text-[11px] text-slate-500 font-mono">
              Finding ID: {selectedFindingId.substring(0, 8)}...
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Assessment Determination</label>
              <div className="flex flex-wrap gap-2">
                {(['CONFIRMED', 'REJECTED', 'AMENDED'] as ReviewStatus[]).map((status) => (
                  <button
                    key={status}
                    type="button"
                    onClick={() => setReviewStatus(status)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                      reviewStatus === status
                        ? status === 'CONFIRMED'
                          ? 'bg-emerald-600 text-white border-emerald-500'
                          : status === 'REJECTED'
                          ? 'bg-rose-600 text-white border-rose-500'
                          : 'bg-amber-600 text-white border-amber-500'
                        : 'bg-slate-900 text-slate-400 border-slate-800 hover:bg-slate-800'
                    }`}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-slate-400 mb-1 block">Clinical Assessment Notes</label>
              <textarea
                value={reviewComment}
                onChange={(e) => setReviewComment(e.target.value)}
                placeholder="Enter clinical rationale, secondary verification notes, or amendment..."
                rows={2}
                className="w-full bg-slate-900 text-white text-xs rounded-xl border border-slate-800 p-2.5 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setSelectedFindingId(null)}
                className="px-3 py-1.5 rounded-lg bg-slate-900 text-slate-400 hover:text-white text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Submit Assessment'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
