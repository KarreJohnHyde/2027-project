import React, { useState } from 'react';
import { 
  FolderGit2, 
  Plus, 
  Upload, 
  FileCheck, 
  Calendar, 
  AlertTriangle, 
  CheckCircle2, 
  Image as ImageIcon, 
  Activity, 
  FileText, 
  ShieldAlert, 
  RefreshCw
} from 'lucide-react';
import type { Case, Examination, UploadedFile, ModalityType } from '../types/medtwin';
import { api } from '../services/api';

interface CaseManagementViewProps {
  cases: Case[];
  activeCase: Case | null;
  onSelectCase: (caseId: string) => void;
  onOpenCreateCase: () => void;
  onOpenFileUpload: () => void;
  examinations: Examination[];
  files: UploadedFile[];
  onRefreshCase: () => void;
  loading: boolean;
}

export const CaseManagementView: React.FC<CaseManagementViewProps> = ({
  cases,
  activeCase,
  onSelectCase,
  onOpenCreateCase,
  onOpenFileUpload,
  examinations,
  files,
  onRefreshCase,
  loading,
}) => {
  // New Examination Form state
  const [examDate, setExamDate] = useState<string>(() => new Date().toISOString().split('T')[0]);
  const [examModality, setExamModality] = useState<ModalityType>('IMAGE');
  const [examIndication, setExamIndication] = useState<string>('');
  const [examSubmitting, setExamSubmitting] = useState<boolean>(false);
  const [examError, setExamError] = useState<string | null>(null);

  // File Association State
  const [togglingFileId, setTogglingFileId] = useState<string | null>(null);

  const handleAddExamination = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeCase) return;
    setExamSubmitting(true);
    setExamError(null);
    try {
      const fullTimestamp = new Date(examDate).toISOString();
      await api.createExamination(activeCase.id, examModality, fullTimestamp, examIndication.trim() || undefined);
      setExamIndication('');
      onRefreshCase();
    } catch (err: unknown) {
      setExamError(err instanceof Error ? err.message : 'Failed to add examination');
    } finally {
      setExamSubmitting(false);
    }
  };

  const handleToggleAssociation = async (file: UploadedFile) => {
    setTogglingFileId(file.id);
    try {
      const newStatus = !file.is_associated;
      const newReason = newStatus 
        ? 'Verified patient accession correspondence.' 
        : 'Excluded: Unrelated record from different accession.';
      await api.updateFileAssociation(file.id, newStatus, newReason);
      onRefreshCase();
    } catch (err: unknown) {
      alert(`Failed to update file association: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setTogglingFileId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Case Selector */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-xl">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <FolderGit2 size={20} className="text-cyan-400" />
              <h2 className="text-lg font-bold text-white tracking-tight">Case Management & Evidence Association</h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Select or create pseudonymous patient cases. Track dated examinations and manage strict digital record association.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onOpenCreateCase}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
            >
              <Plus size={14} />
              <span>Create New Case</span>
            </button>

            <button
              type="button"
              onClick={onOpenFileUpload}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 shadow-md shadow-cyan-600/20 transition-all hover:scale-[1.02]"
            >
              <Upload size={14} />
              <span>Upload Record</span>
            </button>
          </div>
        </div>

        {/* Case Selector Dropdown & Meta */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <div>
            <label className="text-[11px] font-semibold text-slate-400 mb-1 block">Active Case Selection</label>
            <select
              value={activeCase?.id || ''}
              onChange={(e) => onSelectCase(e.target.value)}
              className="w-full bg-slate-950 text-white font-mono text-xs rounded-xl border border-slate-800 p-2.5 focus:outline-none focus:border-cyan-500"
            >
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.pseudonym} — {c.notes ? c.notes.substring(0, 30) + '...' : 'No notes'}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[11px] font-semibold text-slate-400 mb-1 block">Pseudonym Token</label>
            <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono font-bold text-cyan-400">
              {activeCase?.pseudonym || 'None'}
            </div>
          </div>

          <div>
            <label className="text-[11px] font-semibold text-slate-400 mb-1 block">Creation Timestamp</label>
            <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300">
              {activeCase?.created_at ? new Date(activeCase.created_at).toLocaleString() : 'N/A'}
            </div>
          </div>
        </div>
      </div>

      {/* Mandatory Patient Association Rule Banner */}
      <div className="p-4 rounded-xl bg-slate-950 border border-cyan-900/60 text-xs text-slate-300 flex items-start gap-3 shadow-md">
        <ShieldAlert size={18} className="text-cyan-400 shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <strong className="text-cyan-300">Strict Case Association Mandate:</strong> Never assume that unrelated digital records
          belong to the same patient. Every uploaded file must be independently verified. Files toggled to
          <span className="text-rose-400 font-semibold mx-1">UNASSOCIATED</span> are strictly prevented from entering case-level
          multimodal fusion or longitudinal progression analysis.
        </div>
      </div>

      {/* Digital Records Association Table */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3.5 mb-4">
          <div className="flex items-center gap-2">
            <FileCheck size={18} className="text-cyan-400" />
            <h3 className="text-sm font-bold text-white">Ingested Digital Records & Association Status ({files.length})</h3>
          </div>
          <button
            type="button"
            onClick={onRefreshCase}
            disabled={loading}
            className="text-xs text-slate-400 hover:text-white flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>

        {files.length > 0 ? (
          <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">Modality / File</th>
                  <th className="p-3">MIME / Format</th>
                  <th className="p-3">SHA-256 Hash</th>
                  <th className="p-3">File Size</th>
                  <th className="p-3">Association Status</th>
                  <th className="p-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850">
                {files.map((file) => (
                  <tr key={file.id} className="hover:bg-slate-900/40">
                    <td className="p-3">
                      <div className="flex items-center gap-2.5">
                        <div className="p-1.5 rounded-lg bg-slate-900 border border-slate-800">
                          {file.modality === 'IMAGE' && <ImageIcon size={14} className="text-cyan-400" />}
                          {file.modality === 'ECG' && <Activity size={14} className="text-emerald-400" />}
                          {file.modality === 'REPORT' && <FileText size={14} className="text-amber-400" />}
                        </div>
                        <div>
                          <span className="font-semibold text-white block">{file.file_name}</span>
                          <span className="text-[10px] text-slate-500 font-mono">Modality: {file.modality}</span>
                        </div>
                      </div>
                    </td>

                    <td className="p-3 font-mono text-[11px] text-slate-300">
                      {file.mime_type}
                    </td>

                    <td className="p-3 font-mono text-[10px] text-slate-400" title={file.sha256_hash}>
                      {file.sha256_hash ? `${file.sha256_hash.substring(0, 16)}...` : 'N/A'}
                    </td>

                    <td className="p-3 font-mono text-[11px] text-slate-300">
                      {(file.file_size_bytes / 1024).toFixed(1)} KB
                    </td>

                    <td className="p-3">
                      {file.is_associated ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                          <CheckCircle2 size={11} /> ASSOCIATED
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold bg-rose-950 text-rose-300 border border-rose-800">
                          <AlertTriangle size={11} /> UNASSOCIATED (EXCLUDED)
                        </span>
                      )}
                      {file.association_reason && (
                        <span className="block text-[10px] text-slate-500 mt-0.5 truncate max-w-xs">
                          {file.association_reason}
                        </span>
                      )}
                    </td>

                    <td className="p-3 text-right">
                      <button
                        type="button"
                        disabled={togglingFileId === file.id}
                        onClick={() => handleToggleAssociation(file)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
                          file.is_associated
                            ? 'bg-rose-950/40 hover:bg-rose-900/60 border-rose-800 text-rose-300'
                            : 'bg-emerald-950/40 hover:bg-emerald-900/60 border-emerald-800 text-emerald-300'
                        }`}
                      >
                        {togglingFileId === file.id 
                          ? 'Updating...' 
                          : file.is_associated ? 'Disassociate' : 'Associate to Case'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-10 rounded-xl bg-slate-950 border border-slate-850 text-xs text-slate-500">
            No digital records uploaded for this case yet.
          </div>
        )}
      </div>

      {/* Add Examination Logger Form */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-xl">
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3 mb-4">
          <Calendar size={18} className="text-emerald-400" />
          <h3 className="text-sm font-bold text-white">Log Dated Clinical Examination</h3>
        </div>

        {examError && (
          <div className="p-3 mb-4 rounded-xl bg-rose-950 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
            <AlertTriangle size={15} />
            <span>{examError}</span>
          </div>
        )}

        <form onSubmit={handleAddExamination} className="grid grid-cols-1 sm:grid-cols-4 gap-4 items-end">
          <div>
            <label className="text-[11px] font-semibold text-slate-400 mb-1 block">Examination Date</label>
            <input
              type="date"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
              required
              className="w-full bg-slate-950 text-white text-xs rounded-xl border border-slate-800 p-2.5 focus:outline-none focus:border-emerald-500 font-mono"
            />
          </div>

          <div>
            <label className="text-[11px] font-semibold text-slate-400 mb-1 block">Modality</label>
            <select
              value={examModality}
              onChange={(e) => setExamModality(e.target.value as ModalityType)}
              className="w-full bg-slate-950 text-white text-xs rounded-xl border border-slate-800 p-2.5 focus:outline-none focus:border-emerald-500"
            >
              <option value="IMAGE">Medical Radiograph (IMAGE)</option>
              <option value="ECG">Digital ECG (ECG)</option>
              <option value="REPORT">Clinical Report (REPORT)</option>
            </select>
          </div>

          <div>
            <label className="text-[11px] font-semibold text-slate-400 mb-1 block">Clinical Indication / Reason</label>
            <input
              type="text"
              value={examIndication}
              onChange={(e) => setExamIndication(e.target.value)}
              placeholder="e.g. 6-month routine wrist evaluation"
              className="w-full bg-slate-950 text-white text-xs rounded-xl border border-slate-800 p-2.5 focus:outline-none focus:border-emerald-500"
            />
          </div>

          <button
            type="submit"
            disabled={examSubmitting}
            className="w-full py-2.5 px-4 rounded-xl text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 shadow-md shadow-emerald-600/20 transition-all disabled:opacity-50 flex items-center justify-center gap-1.5"
          >
            <Plus size={14} />
            <span>{examSubmitting ? 'Logging...' : 'Add Examination'}</span>
          </button>
        </form>

        {/* Logged Chronological Examinations List */}
        <div className="mt-4 pt-3 border-t border-slate-800">
          <div className="text-xs font-semibold text-slate-400 mb-2">
            Chronological Recorded Examinations ({examinations.length})
          </div>
          {examinations.length > 0 ? (
            <div className="space-y-1.5 max-h-36 overflow-y-auto">
              {examinations.map((ex) => (
                <div key={ex.id} className="p-2 rounded-lg bg-slate-950 border border-slate-850 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-cyan-400">{new Date(ex.timestamp).toLocaleDateString()}</span>
                    <span className="text-slate-300 font-medium">[{ex.examination_type}]</span>
                    <span className="text-slate-400 truncate max-w-xs">{ex.clinician_notes || 'Routine follow-up'}</span>
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">Exam #{ex.id.slice(0, 8)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-slate-500 italic">No examinations logged for this case yet.</div>
          )}
        </div>
      </div>
    </div>
  );
};
