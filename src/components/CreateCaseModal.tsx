import React, { useState } from 'react';
import { FolderPlus, X, ShieldAlert, Sparkles } from 'lucide-react';

interface CreateCaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateCase: (pseudonym: string, notes?: string) => Promise<void>;
  loading: boolean;
}

export const CreateCaseModal: React.FC<CreateCaseModalProps> = ({
  isOpen,
  onClose,
  onCreateCase,
  loading,
}) => {
  const [pseudonym, setPseudonym] = useState<string>(() => 
    `CASE-MT-2026-${Math.floor(100 + Math.random() * 900)}`
  );
  const [notes, setNotes] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pseudonym.trim()) {
      setErrorMsg('Pseudonym is required to protect patient privacy.');
      return;
    }
    try {
      await onCreateCase(pseudonym.trim(), notes.trim() || undefined);
      onClose();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to create case');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl relative">
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <X size={18} />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <FolderPlus size={20} />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">Create Digital Twin Case</h3>
            <p className="text-xs text-slate-400">Pseudonymized identifier required (no raw patient PHI)</p>
          </div>
        </div>

        {errorMsg && (
          <div className="p-3 mb-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
            <ShieldAlert size={15} className="shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-slate-400 mb-1.5 block">Pseudonymous Case Identifier</label>
            <div className="relative">
              <input
                type="text"
                value={pseudonym}
                onChange={(e) => setPseudonym(e.target.value)}
                placeholder="e.g. CASE-MT-2026-081"
                required
                className="w-full bg-slate-950 text-white font-mono text-xs rounded-xl border border-slate-800 p-2.5 focus:outline-none focus:border-indigo-500"
              />
              <button
                type="button"
                onClick={() => setPseudonym(`CASE-MT-2026-${Math.floor(100 + Math.random() * 900)}`)}
                className="absolute right-2.5 top-2.5 text-slate-500 hover:text-indigo-400 text-xs flex items-center gap-1"
                title="Generate new pseudonym"
              >
                <Sparkles size={13} />
                <span>Auto</span>
              </button>
            </div>
            <span className="text-[11px] text-slate-500 mt-1 block">
              De-identified token assigned for longitudinal record binding.
            </span>
          </div>

          <div>
            <label className="text-xs text-slate-400 mb-1.5 block">Clinical Case Notes (Optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Suspected distal radius fracture with follow-up monitoring..."
              rows={3}
              className="w-full bg-slate-950 text-white text-xs rounded-xl border border-slate-800 p-2.5 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-all shadow-md shadow-indigo-600/20"
            >
              {loading ? 'Creating...' : 'Initialize Case'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
