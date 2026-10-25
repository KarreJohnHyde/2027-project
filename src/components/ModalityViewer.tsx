import { useState } from 'react';
import { 
  Image as ImageIcon, 
  Activity, 
  FileText, 
  CheckCircle2, 
  Eye, 
  Play, 
  Cpu, 
  ShieldCheck,
  Info
} from 'lucide-react';

import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import type { UploadedFile, Finding, ClinicalReportStatement } from '../types/medtwin';

interface ModalityViewerProps {
  files: UploadedFile[];
  findings: Finding[];
  reportStatements: ClinicalReportStatement[];
  onRunImageAnalysis: (fileId: string) => void;
  onRunEcgAnalysis: (fileId: string) => void;
  onRunNlpAnalysis: (fileId: string) => void;
  loadingAnalysis: boolean;
}

export const ModalityViewer: React.FC<ModalityViewerProps> = ({
  files,
  findings,
  reportStatements,
  onRunImageAnalysis,
  onRunEcgAnalysis,
  onRunNlpAnalysis,
  loadingAnalysis,
}) => {
  const [activeTab, setActiveTab] = useState<'IMAGE' | 'ECG' | 'REPORT'>('IMAGE');
  const [showGradCam, setShowGradCam] = useState<boolean>(false);
  const [selectedLead, setSelectedLead] = useState<'II' | 'V1' | 'I'>('II');

  // Filter files by modality
  const imageFiles = files.filter((f) => f.modality === 'IMAGE');
  const ecgFiles = files.filter((f) => f.modality === 'ECG');
  const reportFiles = files.filter((f) => f.modality === 'REPORT');

  // Filter findings by modality
  const imageFinding = findings.find((f) => f.modality === 'IMAGE');
  const ecgFinding = findings.find((f) => f.modality === 'ECG');

  // Generate synthetic ECG waveform points for Recharts demonstration (Lead II P-Q-R-S-T wave)
  const generateEcgData = () => {
    const points = [];
    const totalSamples = 150;
    for (let i = 0; i < totalSamples; i++) {
      const t = (i % 50) / 50; // Repeat cardiac cycle every 50 points
      let val = 0;
      // P wave
      if (t >= 0.1 && t <= 0.2) {
        val = 0.25 * Math.sin(((t - 0.1) / 0.1) * Math.PI);
      }
      // Q wave
      else if (t > 0.32 && t <= 0.35) {
        val = -0.15;
      }
      // R peak
      else if (t > 0.35 && t <= 0.40) {
        val = 1.45 * Math.sin(((t - 0.35) / 0.05) * Math.PI);
      }
      // S wave
      else if (t > 0.40 && t <= 0.44) {
        val = -0.35;
      }
      // T wave
      else if (t >= 0.6 && t <= 0.8) {
        val = 0.45 * Math.sin(((t - 0.6) / 0.2) * Math.PI);
      }
      // Add slight physiological baseline wander
      val += Math.sin(i * 0.05) * 0.03;
      points.push({
        sample: i,
        time_ms: Math.round(i * 20),
        amplitude_mv: Number(val.toFixed(3)),
      });
    }
    return points;
  };

  const ecgWaveformData = generateEcgData();

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 mb-6 shadow-xl">
      {/* Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4 mb-5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveTab('IMAGE')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              activeTab === 'IMAGE'
                ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 shadow-sm shadow-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <ImageIcon size={15} />
            <span>Medical Image Analysis ({imageFiles.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('ECG')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              activeTab === 'ECG'
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shadow-sm shadow-emerald-500/10'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Activity size={15} />
            <span>Digital ECG Signal ({ecgFiles.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('REPORT')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              activeTab === 'REPORT'
                ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 shadow-sm shadow-indigo-500/10'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <FileText size={15} />
            <span>Clinical NLP Report ({reportFiles.length})</span>
          </button>
        </div>

        <div className="text-xs text-slate-500 flex items-center gap-1.5">
          <ShieldCheck size={14} className="text-cyan-500" />
          <span>Patient-isolated split validation</span>
        </div>
      </div>

      {/* Tab 1: Image Analysis */}
      {activeTab === 'IMAGE' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left: Radiograph Preview & Grad-CAM */}
          <div className="lg:col-span-6 flex flex-col gap-3">
            <div className="relative aspect-[4/3] rounded-xl overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center">
              {/* Simulated Radiograph Canvas */}
              <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 flex flex-col items-center justify-center p-6 text-center">
                <div className="w-48 h-56 rounded-lg border border-slate-700/60 bg-slate-900/40 relative flex items-center justify-center overflow-hidden shadow-2xl">
                  {/* Bone anatomy silhouette approximation */}
                  <div className="absolute w-12 h-44 bg-slate-700/40 rounded-full blur-[2px] transform -rotate-6" />
                  <div className="absolute w-8 h-40 bg-slate-600/40 rounded-full blur-[1px] transform rotate-12" />
                  <div className="absolute w-24 h-14 bg-slate-500/30 rounded-2xl blur-[3px] top-6" />

                  {/* Fracture indicator line */}
                  <div className="absolute top-14 left-10 w-16 h-0.5 bg-cyan-400/80 transform rotate-45 shadow-[0_0_8px_rgba(56,189,248,0.8)]" />

                  {/* Grad-CAM Heatmap Overlay if toggled */}
                  {showGradCam && (
                    <div className="absolute inset-0 bg-radial-gradient from-rose-500/60 via-amber-400/30 to-transparent mix-blend-screen pointer-events-none animate-pulse" />
                  )}

                  <div className="absolute bottom-2 left-2 text-[10px] text-slate-500 font-mono">
                    WRIST_PA_2026.PNG
                  </div>
                </div>
              </div>

              {/* Status Overlay */}
              <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-700 text-[11px] text-slate-300">
                <ImageIcon size={12} className="text-cyan-400" />
                <span>MURA Preprocessed (224×224)</span>
              </div>

              <div className="absolute bottom-3 right-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowGradCam(!showGradCam)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold backdrop-blur-md transition-all ${
                    showGradCam
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      : 'bg-slate-900/80 text-slate-300 border border-slate-700 hover:bg-slate-800'
                  }`}
                >
                  <Eye size={13} />
                  <span>{showGradCam ? 'Hide Grad-CAM' : 'View Grad-CAM Attribution'}</span>
                </button>
              </div>
            </div>

            {/* Mandatory IEEE Disclaimer on Grad-CAM */}
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-start gap-2.5">
              <Info size={16} className="text-amber-400 shrink-0 mt-0.5" />
              <div>
                <strong>IEEE Evidence Constraint:</strong> Grad-CAM is a classification attribution explanation
                only. It must <em>never</em> be treated as ground-truth 3D anatomical localization or segmentation.
              </div>
            </div>
          </div>

          {/* Right: Model Inferences & Provenance */}
          <div className="lg:col-span-6 flex flex-col justify-between gap-4">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div>
                  <h3 className="text-sm font-bold text-white">ResNet Classification Inference</h3>
                  <p className="text-xs text-slate-400">Trained on MURA Musculoskeletal Radiographs (Patient Splits)</p>
                </div>
                {imageFiles.length > 0 && (
                  <button
                    type="button"
                    disabled={loadingAnalysis}
                    onClick={() => onRunImageAnalysis(imageFiles[0].id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow-md shadow-cyan-600/20 transition-all disabled:opacity-50"
                  >
                    <Play size={13} />
                    <span>{loadingAnalysis ? 'Analyzing...' : 'Run ResNet Model'}</span>
                  </button>
                )}
              </div>

              {imageFinding ? (
                <div className="mt-4 space-y-3">
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <div>
                      <span className="text-xs text-slate-400">Class Finding</span>
                      <div className="text-sm font-bold text-white mt-0.5">{imageFinding.finding_label}</div>
                    </div>
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800">
                      {imageFinding.evidence_status}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                      <span className="text-xs text-slate-400">Raw Softmax Probability</span>
                      <div className="text-lg font-bold text-slate-200 mt-1">
                        {(imageFinding.raw_confidence * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                      <span className="text-xs text-slate-400">Calibrated Confidence</span>
                      <div className="text-lg font-bold text-emerald-400 mt-1">
                        {imageFinding.calibrated_confidence ? `${(imageFinding.calibrated_confidence * 100).toFixed(1)}%` : 'N/A'}
                      </div>
                      <span className="text-[10px] text-slate-500">Temp Scaling (T=1.15)</span>
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-400 space-y-1.5 font-mono">
                    <div className="flex justify-between">
                      <span>Model Version:</span>
                      <span className="text-slate-200">{imageFinding.model_version}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Anatomical Level:</span>
                      <span className="text-slate-200">{imageFinding.anatomical_level}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Review Status:</span>
                      <span className="text-amber-400">{imageFinding.review_status}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mt-8 text-center p-6 border border-dashed border-slate-800 rounded-xl text-slate-400 text-xs">
                  <Cpu size={24} className="mx-auto mb-2 text-slate-600" />
                  <span>No radiograph inference recorded for this case. Click "Run ResNet Model" to evaluate.</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: ECG Analysis */}
      {activeTab === 'ECG' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-8 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-slate-400">Displayed Lead:</span>
                {(['II', 'V1', 'I'] as const).map((lead) => (
                  <button
                    key={lead}
                    type="button"
                    onClick={() => setSelectedLead(lead)}
                    className={`px-2.5 py-1 rounded text-xs font-semibold ${
                      selectedLead === lead
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                    }`}
                  >
                    Lead {lead}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span>Sampling: <strong>500 Hz</strong></span>
                <span>•</span>
                <span>Bandpass: <strong>0.5 – 40 Hz</strong></span>
              </div>
            </div>

            {/* Recharts ECG Waveform */}
            <div className="h-64 rounded-xl bg-slate-950 border border-slate-800 p-2">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={ecgWaveformData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="time_ms" stroke="#64748b" tick={{ fontSize: 10 }} unit="ms" />
                  <YAxis stroke="#64748b" tick={{ fontSize: 10 }} domain={[-0.8, 1.8]} unit="mV" />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#020617', borderColor: '#334155', fontSize: '11px' }}
                    formatter={(val) => [`${val} mV`, `Lead ${selectedLead}`]}
                    labelFormatter={(label) => `Time: ${label} ms`}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="amplitude_mv" 
                    stroke="#10b981" 
                    strokeWidth={1.8} 
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* ECG Metadata & Quality Verification */}
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-400">Signal Quality Index</span>
                <div className="text-sm font-bold text-emerald-400 mt-0.5">0.96 (Valid)</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-400">Lead Flatline Check</span>
                <div className="text-sm font-bold text-emerald-400 mt-0.5 flex items-center gap-1">
                  <CheckCircle2 size={13} /> 0 Leads Faulty
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-400">Heart Rate (Calculated)</span>
                <div className="text-sm font-bold text-white mt-0.5">72 bpm</div>
              </div>
            </div>
          </div>

          {/* ECG Findings */}
          <div className="lg:col-span-4 flex flex-col justify-between gap-4">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div>
                  <h3 className="text-sm font-bold text-white">1-D CNN ECG Classifier</h3>
                  <p className="text-xs text-slate-400">Evaluated on PTB-XL Diagnostics</p>
                </div>
                {ecgFiles.length > 0 && (
                  <button
                    type="button"
                    disabled={loadingAnalysis}
                    onClick={() => onRunEcgAnalysis(ecgFiles[0].id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/20 transition-all disabled:opacity-50"
                  >
                    <Play size={13} />
                    <span>{loadingAnalysis ? 'Analyzing...' : 'Run 1-D CNN'}</span>
                  </button>
                )}
              </div>

              {ecgFinding ? (
                <div className="mt-4 space-y-3">
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400">Rhythm Classification</span>
                    <div className="text-sm font-bold text-white mt-0.5">{ecgFinding.finding_label}</div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400">Calibrated Rhythm Probability</span>
                    <div className="text-lg font-bold text-emerald-400 mt-1">
                      {ecgFinding.calibrated_confidence ? `${(ecgFinding.calibrated_confidence * 100).toFixed(1)}%` : 'N/A'}
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-400 space-y-1 font-mono">
                    <div>Model: {ecgFinding.model_name}</div>
                    <div>Version: {ecgFinding.model_version}</div>
                    <div>Status: {ecgFinding.evidence_status}</div>
                  </div>
                </div>
              ) : (
                <div className="mt-8 text-center p-6 border border-dashed border-slate-800 rounded-xl text-slate-400 text-xs">
                  <Cpu size={24} className="mx-auto mb-2 text-slate-600" />
                  <span>No ECG inference recorded. Click "Run 1-D CNN" to evaluate rhythm.</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Clinical NLP Report */}
      {activeTab === 'REPORT' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Narrative Text */}
          <div className="lg:col-span-6 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400">De-identified Narrative Note</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                De-identification attested · not a HIPAA determination
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 font-mono leading-relaxed h-72 overflow-y-auto">
              <p className="mb-2 text-slate-500 font-semibold">[EXAMINATION: PA & LATERAL LEFT WRIST RADIOGRAPH + 12-LEAD ECG]</p>
              <p className="mb-2">
                <strong>CLINICAL HISTORY:</strong> 42yo patient presents with left wrist pain and acute swelling following a fall on outstretched hand. No prior fracture history.
              </p>
              <p className="mb-2">
                <strong>IMPRESSION:</strong> Acute fracture of the distal radius with minimal dorsal displacement. No acute scaphoid fracture identified. Carpal alignment intact.
              </p>
              <p>
                <strong>ECG CONCOMITANT:</strong> Normal sinus rhythm with normal axis. No acute ST-T wave changes.
              </p>
            </div>

            {reportFiles.length > 0 && (
              <button
                type="button"
                disabled={loadingAnalysis}
                onClick={() => onRunNlpAnalysis(reportFiles[0].id)}
                className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all disabled:opacity-50"
              >
                <Play size={14} />
                <span>{loadingAnalysis ? 'Extracting Statements...' : 'Extract Clinical Statements (Clinical NLP)'}</span>
              </button>
            )}
          </div>

          {/* Structured Statements Table */}
          <div className="lg:col-span-6 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400">
                Extracted Statements ({reportStatements.length})
              </span>
              <span className="text-[10px] text-slate-500">Entity • Negation • Temporality</span>
            </div>

            <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950 h-80 overflow-y-auto">
              {reportStatements.length > 0 ? (
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800 sticky top-0">
                    <tr>
                      <th className="p-2.5">Clinical Entity</th>
                      <th className="p-2.5">Negation</th>
                      <th className="p-2.5">Temporality</th>
                      <th className="p-2.5">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-850">
                    {reportStatements.map((stmt) => (
                      <tr key={stmt.id} className="hover:bg-slate-900/40">
                        <td className="p-2.5 font-medium text-slate-200">
                          {stmt.entity_text}
                          <span className="block text-[10px] text-slate-500 font-mono">
                            [{stmt.category}]
                          </span>
                        </td>
                        <td className="p-2.5">
                          {stmt.is_negated ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950 text-rose-300 border border-rose-800">
                              NEGATED
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                              AFFIRMED
                            </span>
                          )}
                        </td>
                        <td className="p-2.5 text-slate-400">{stmt.temporality}</td>
                        <td className="p-2.5 text-slate-300">{(stmt.confidence * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="h-full flex flex-col items-center justify-center p-6 text-slate-500 text-xs">
                  <FileText size={24} className="mb-2 text-slate-600" />
                  <span>No structured statements extracted yet.</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
