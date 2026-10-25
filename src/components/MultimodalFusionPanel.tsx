import { Layers, Play, AlertOctagon, ShieldCheck } from 'lucide-react';
import type { MultimodalFusionRecord } from '../types/medtwin';

interface MultimodalFusionPanelProps {
  fusionRecord: MultimodalFusionRecord | null;
  onRunFusion: (forcePairedCheck: boolean) => void;
  loading: boolean;
}

export const MultimodalFusionPanel: React.FC<MultimodalFusionPanelProps> = ({
  fusionRecord,
  onRunFusion,
  loading,
}) => {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 mb-6 shadow-xl">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-400">
              <Layers size={18} />
            </div>
            <h3 className="text-sm font-bold text-white">Masked Gated Multimodal Fusion (Eqs. 8–10)</h3>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-950 text-purple-300 border border-purple-800">
              IEEE Section VI-C
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Combines available modalities dynamically. Abstains explicitly on 0 inputs; skips fusion on 1 input.
          </p>
        </div>

        <button
          type="button"
          disabled={loading}
          onClick={() => onRunFusion(true)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md shadow-purple-600/20 transition-all disabled:opacity-50"
        >
          <Play size={13} />
          <span>{loading ? 'Evaluating...' : 'Evaluate Masked Fusion'}</span>
        </button>
      </div>

      {/* Availability Masks Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
        {/* Image Mask */}
        <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400">Modality Mask m_I</span>
            <div className="text-sm font-bold text-white mt-0.5">Radiograph Input</div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
              fusionRecord?.image_present ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-slate-900 text-slate-500'
            }`}>
              m_I = {fusionRecord?.image_present ? '1' : '0'}
            </span>
          </div>
        </div>

        {/* ECG Mask */}
        <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400">Modality Mask m_E</span>
            <div className="text-sm font-bold text-white mt-0.5">Digital ECG Input</div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
              fusionRecord?.ecg_present ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-slate-900 text-slate-500'
            }`}>
              m_E = {fusionRecord?.ecg_present ? '1' : '0'}
            </span>
          </div>
        </div>

        {/* Report Mask */}
        <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400">Modality Mask m_R</span>
            <div className="text-sm font-bold text-white mt-0.5">Clinical Report NLP</div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
              fusionRecord?.report_present ? 'bg-indigo-950 text-indigo-300 border border-indigo-800' : 'bg-slate-900 text-slate-500'
            }`}>
              m_R = {fusionRecord?.report_present ? '1' : '0'}
            </span>
          </div>
        </div>
      </div>

      {/* Fusion Status & Weights */}
      {fusionRecord ? (
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Execution Status:</span>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  fusionRecord.fusion_status === 'COMPLETED'
                    ? 'bg-purple-950 text-purple-300 border border-purple-800'
                    : fusionRecord.fusion_status === 'ABSTAIN'
                    ? 'bg-rose-950 text-rose-300 border border-rose-800'
                    : 'bg-amber-950 text-amber-300 border border-amber-800'
                }`}>
                  {fusionRecord.fusion_status}
                </span>
              </div>
              {fusionRecord.abstention_reason && (
                <p className="text-xs text-amber-400 mt-1 flex items-center gap-1.5">
                  <AlertOctagon size={13} />
                  <span>Abstention / Reason: {fusionRecord.abstention_reason}</span>
                </p>
              )}
            </div>

            {/* Fused Prediction */}
            {fusionRecord.fused_prediction_label && (
              <div className="text-right">
                <span className="text-xs text-slate-400">Multimodal Gated Prediction</span>
                <div className="text-base font-bold text-white mt-0.5">
                  {fusionRecord.fused_prediction_label}
                </div>
                <div className="text-xs text-emerald-400 font-medium">
                  Confidence: {fusionRecord.fused_confidence ? `${(fusionRecord.fused_confidence * 100).toFixed(1)}%` : 'N/A'}
                </div>
              </div>
            )}
          </div>

          {/* Attention Weights Alpha_k */}
          {fusionRecord.fusion_status === 'COMPLETED' && (
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-xs font-semibold text-slate-300 mb-3 block">
                Normalized Attention Gating Weights (Eq. 9: ∑ α_k = 1.0)
              </span>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span>α_Image</span>
                    <span className="font-mono text-cyan-400">
                      {fusionRecord.alpha_image ? fusionRecord.alpha_image.toFixed(3) : '0.000'}
                    </span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800">
                    <div 
                      className="bg-cyan-500 h-2 rounded-full transition-all"
                      style={{ width: `${(fusionRecord.alpha_image || 0) * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span>α_ECG</span>
                    <span className="font-mono text-emerald-400">
                      {fusionRecord.alpha_ecg ? fusionRecord.alpha_ecg.toFixed(3) : '0.000'}
                    </span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800">
                    <div 
                      className="bg-emerald-500 h-2 rounded-full transition-all"
                      style={{ width: `${(fusionRecord.alpha_ecg || 0) * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span>α_Report</span>
                    <span className="font-mono text-indigo-400">
                      {fusionRecord.alpha_report ? fusionRecord.alpha_report.toFixed(3) : '0.000'}
                    </span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800">
                    <div 
                      className="bg-indigo-500 h-2 rounded-full transition-all"
                      style={{ width: `${(fusionRecord.alpha_report || 0) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Paired-data verification badge */}
          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            <span className="flex items-center gap-1.5">
              <ShieldCheck size={14} className="text-purple-400" />
              <span>Genuinely paired case validation required (no artificial cross-dataset pairing)</span>
            </span>
            <span className="font-mono text-slate-400">Model: {fusionRecord.fusion_model_version}</span>
          </div>
        </div>
      ) : (
        <div className="text-center p-6 border border-dashed border-slate-800 rounded-xl text-slate-500 text-xs">
          Click "Evaluate Masked Fusion" to compute multimodal gating weights.
        </div>
      )}
    </div>
  );
};
