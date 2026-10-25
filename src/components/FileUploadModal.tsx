import { useState } from 'react';
import { Upload, X, FileText, Image as ImageIcon, Activity, ShieldAlert } from 'lucide-react';
import type { ModalityType } from '../types/medtwin';

interface FileUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (file: File, modality: ModalityType, isAssociated: boolean) => Promise<void>;
  loading: boolean;
}

export const FileUploadModal: React.FC<FileUploadModalProps> = ({
  isOpen,
  onClose,
  onUpload,
  loading,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [modality, setModality] = useState<ModalityType>('IMAGE');
  const [isAssociated, setIsAssociated] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (file.size > 25 * 1024 * 1024) {
        setErrorMsg('File size exceeds the 25 MB safety limit.');
        return;
      }
      setSelectedFile(file);
      setErrorMsg(null);

      // Auto-suggest modality by file extension
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (['png', 'jpg', 'jpeg', 'dcm'].includes(ext || '')) {
        setModality('IMAGE');
      } else if (['csv', 'dat', 'hea'].includes(ext || '')) {
        setModality('ECG');
      } else if (['txt', 'pdf'].includes(ext || '')) {
        setModality('REPORT');
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMsg('Please select a file to upload.');
      return;
    }
    try {
      await onUpload(selectedFile, modality, isAssociated);
      onClose();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Upload failed');
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
          <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
            <Upload size={20} />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">Upload Medical Digital Record</h3>
            <p className="text-xs text-slate-400">Digital files only (Software-only framework)</p>
          </div>
        </div>

        {errorMsg && (
          <div className="p-3 mb-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
            <ShieldAlert size={15} className="shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File input */}
          <div className="border-2 border-dashed border-slate-700 hover:border-cyan-500/50 rounded-xl p-5 text-center transition-colors">
            <input
              type="file"
              id="file-upload"
              onChange={handleFileChange}
              className="hidden"
              accept=".png,.jpg,.jpeg,.bmp,.dcm,.csv,.txt"
            />
            <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center">
              <Upload size={28} className="text-slate-500 mb-2" />
              <span className="text-xs font-semibold text-slate-200">
                {selectedFile ? selectedFile.name : 'Click to choose medical record'}
              </span>
              <span className="text-[11px] text-slate-500 mt-1">
                Supported: PNG, JPEG, CSV, TXT (Max 25 MB)
              </span>
            </label>
          </div>

          {/* Modality radio */}
          <div>
            <label className="text-xs text-slate-400 mb-1.5 block">Record Modality</label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setModality('IMAGE')}
                className={`flex flex-col items-center p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                  modality === 'IMAGE'
                    ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/40'
                    : 'bg-slate-950 text-slate-400 border-slate-800'
                }`}
              >
                <ImageIcon size={16} className="mb-1" />
                <span>Radiograph</span>
              </button>

              <button
                type="button"
                onClick={() => setModality('ECG')}
                className={`flex flex-col items-center p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                  modality === 'ECG'
                    ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/40'
                    : 'bg-slate-950 text-slate-400 border-slate-800'
                }`}
              >
                <Activity size={16} className="mb-1" />
                <span>Digital ECG</span>
              </button>

              <button
                type="button"
                onClick={() => setModality('REPORT')}
                className={`flex flex-col items-center p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                  modality === 'REPORT'
                    ? 'bg-indigo-500/10 text-indigo-300 border-indigo-500/40'
                    : 'bg-slate-950 text-slate-400 border-slate-800'
                }`}
              >
                <FileText size={16} className="mb-1" />
                <span>Clinical Note</span>
              </button>
            </div>
          </div>

          {/* Association toggle */}
          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between text-xs">
            <div>
              <span className="font-semibold text-slate-200">Case Association Binding</span>
              <p className="text-[11px] text-slate-500">Unassociated files cannot enter fusion</p>
            </div>
            <input
              type="checkbox"
              checked={isAssociated}
              onChange={(e) => setIsAssociated(e.target.checked)}
              className="accent-cyan-500 w-4 h-4 cursor-pointer"
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
              disabled={loading || !selectedFile}
              className="px-5 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 disabled:opacity-50 transition-all shadow-md shadow-indigo-600/20"
            >
              {loading ? 'Uploading & Hashing...' : 'Upload & Compute Hash'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
