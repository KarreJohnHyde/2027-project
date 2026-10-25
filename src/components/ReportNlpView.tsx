import { useState } from 'react';
import { 
  FileText, 
  CheckCircle2, 
  Play, 
  AlertTriangle, 
  ShieldCheck, 
  Info,
  Search,
  Filter,
  Eye,
  EyeOff,
  Layers,
  Sparkles
} from 'lucide-react';
import type { UploadedFile, ClinicalReportStatement } from '../types/medtwin';

interface ReportNlpViewProps {
  files: UploadedFile[];
  reportStatements: ClinicalReportStatement[];
  onRunNlpAnalysis: (fileId: string) => void;
  loadingAnalysis: boolean;
  onOpenFileUpload?: () => void;
}

export const ReportNlpView: React.FC<ReportNlpViewProps> = ({
  files,
  reportStatements,
  onRunNlpAnalysis,
  loadingAnalysis,
  onOpenFileUpload,
}) => {
  const reportFiles = files.filter((f) => f.modality === 'REPORT');
  const [selectedFileId, setSelectedFileId] = useState<string>(
    reportFiles.length > 0 ? reportFiles[0].id : ''
  );
  const [showDeidHighlight, setShowDeidHighlight] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [filterNegation, setFilterNegation] = useState<'ALL' | 'AFFIRMED' | 'NEGATED'>('ALL');

  const activeFile = reportFiles.find((f) => f.id === selectedFileId) || reportFiles[0];

  // Clinical report text sample for demonstration
  const sampleReportText = `[EXAMINATION: PA & LATERAL LEFT WRIST RADIOGRAPH + CONCOMITANT 12-LEAD ECG]
EXAMINATION DATE: 2026-03-14 09:42 UTC
PATIENT IDENTIFIER: PSEUDO-WRIST-01 (MURA_PATIENT_0042)
REFERRING PHYSICIAN: [REDACTED_PROVIDER_DR_CHEN]
FACILITY: [REDACTED_HOSPITAL_METRO_GENERAL]

CLINICAL HISTORY:
42-year-old patient presents to the urgent orthopedic consultation following a fall onto an outstretched left hand (FOOSH mechanism). Complains of acute focal wrist pain, focal tenderness over the dorsal distal forearm, and prominent acute dorsal soft tissue swelling. No history of prior osseous trauma, osteopenia, or chronic inflammatory arthropathy.

FINDINGS & IMPRESSION:
1. SKELETAL ANATOMY & ALIGNMENT:
Acute transverse, non-comminuted fracture of the distal radius metaphysis with approximately 2.5 mm dorsal displacement and 8 degrees dorsal tilt. Radial inclination remains within acceptable limits. No acute cortical disruption or occult fracture line visualized within the scaphoid bone. Distal radioulnar joint (DRUJ) alignment is preserved without frank diastasis.

2. SOFT TISSUES:
Focal soft tissue prominence along the dorsal and radial aspects consistent with post-traumatic hematoma and acute periarticular edema.

3. CONCOMITANT DIGITAL ELECTROPHYSIOLOGY:
Standard 12-lead digital ECG confirms regular normal sinus rhythm at 72 bpm. PR interval 158 ms, QRS duration 86 ms, QTc 418 ms. Axis is normal. No acute ST-segment elevation, ST depression, or pathological T-wave inversions.

SUMMARY IMPRESSION:
- Acute, minimally displaced distal radius fracture.
- Negated scaphoid fracture.
- Normal sinus rhythm on concomitant 12-lead ECG.`;

  // Filter structured statements
  const filteredStatements = reportStatements.filter((stmt) => {
    const matchesSearch = 
      stmt.entity_text.toLowerCase().includes(searchTerm.toLowerCase()) ||
      stmt.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
      stmt.temporality.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesNegation = 
      filterNegation === 'ALL' ||
      (filterNegation === 'NEGATED' && stmt.is_negated) ||
      (filterNegation === 'AFFIRMED' && !stmt.is_negated);

    return matchesSearch && matchesNegation;
  });

  return (
    <div className="space-y-6">
      {/* Top Banner & Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-2xl bg-slate-900/80 border border-slate-800 shadow-xl backdrop-blur-md">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shadow-inner">
            <FileText size={26} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white tracking-tight">Clinical Report NLP Analysis</h2>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800">
                Safe Harbor De-identified
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Structured clinical entity extraction, NegEx assertion parsing, temporality analysis, and text provenance.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3">
          {reportFiles.length > 0 && activeFile && (
            <button
              type="button"
              disabled={loadingAnalysis}
              onClick={() => onRunNlpAnalysis(activeFile.id)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-50"
            >
              <Play size={14} />
              <span>{loadingAnalysis ? 'Extracting Statements...' : 'Extract Clinical Statements'}</span>
            </button>
          )}

          {onOpenFileUpload && (
            <button
              type="button"
              onClick={onOpenFileUpload}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-all"
            >
              <FileText size={14} />
              <span>Upload Report Document</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Grid: Narrative Text Reader (Left 6 cols) & Structured Statements (Right 6 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Narrative Medical Text & De-identification */}
        <div className="lg:col-span-6 flex flex-col gap-5">
          <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 shadow-xl flex flex-col gap-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <ShieldCheck size={16} className="text-indigo-400" />
                <h3 className="text-sm font-bold text-white">Narrative Clinical Note</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowDeidHighlight(!showDeidHighlight)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                  showDeidHighlight
                    ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {showDeidHighlight ? <Eye size={13} /> : <EyeOff size={13} />}
                <span>{showDeidHighlight ? 'De-ID Highlighting ON' : 'Plain Text'}</span>
              </button>
            </div>

            {/* Narrative Text Container */}
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800/80 text-xs text-slate-300 font-mono leading-relaxed h-[420px] overflow-y-auto whitespace-pre-wrap select-text">
              {showDeidHighlight ? (
                <div>
                  <div className="mb-2 p-2 rounded bg-indigo-950/40 border border-indigo-800/60 text-indigo-300 text-[11px]">
                    <span className="font-bold">Rule-based masking preview:</span> Not a HIPAA Safe Harbor determination; independent privacy review is required.
                  </div>
                  {sampleReportText}
                </div>
              ) : (
                sampleReportText
              )}
            </div>

            {/* Safeguards Summary */}
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-start gap-2.5">
              <Info size={16} className="text-amber-400 shrink-0 mt-0.5" />
              <div>
                <strong>IEEE Statement Extraction Principle:</strong> The NLP engine identifies what the clinician's
                report states—it does <em>not</em> independently generate a diagnosis, nor does it alter or overwrite
                the signed clinical document.
              </div>
            </div>
          </div>

          {/* Associated Report Files List */}
          <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 shadow-xl">
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Layers size={14} className="text-indigo-400" />
              Associated Clinical Report Files ({reportFiles.length})
            </h3>

            {reportFiles.length > 0 ? (
              <div className="space-y-2">
                {reportFiles.map((file) => (
                  <div
                    key={file.id}
                    onClick={() => setSelectedFileId(file.id)}
                    className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                      selectedFileId === file.id
                        ? 'bg-indigo-950/30 border-indigo-500/40'
                        : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                        <FileText size={16} />
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-white">{file.file_name}</div>
                        <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                          SHA256: {file.sha256_hash ? `${file.sha256_hash.slice(0, 16)}...` : 'N/A'} • {(file.file_size_bytes / 1024).toFixed(1)} KB
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                        file.is_associated 
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' 
                          : 'bg-amber-950 text-amber-300 border border-amber-800'
                      }`}>
                        {file.is_associated ? 'ASSOCIATED' : 'UNASSOCIATED'}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono text-slate-400 bg-slate-900 border border-slate-800">
                        {file.mime_type}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 text-center border border-dashed border-slate-800 rounded-xl text-slate-400 text-xs">
                <AlertTriangle size={20} className="mx-auto mb-1 text-amber-500" />
                <span>No clinical report files attached to this case. Upload a narrative note to extract statements.</span>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Structured Statements Table */}
        <div className="lg:col-span-6 flex flex-col gap-5">
          <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 shadow-xl flex flex-col gap-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <h3 className="text-sm font-bold text-white">Extracted Clinical Statements</h3>
                <p className="text-[11px] text-slate-400">Clinical-BERT / NegEx Pipeline with Span Offsets</p>
              </div>
              <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800">
                {filteredStatements.length} Entities
              </span>
            </div>

            {/* Filter and Search Bar */}
            <div className="flex items-center gap-3">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-2.5 text-slate-500" />
                <input
                  type="text"
                  placeholder="Filter by entity, category, or anatomy..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800 text-[11px]">
                <Filter size={12} className="text-slate-500 ml-1.5 mr-0.5" />
                <button
                  type="button"
                  onClick={() => setFilterNegation('ALL')}
                  className={`px-2 py-0.5 rounded transition-all ${
                    filterNegation === 'ALL'
                      ? 'bg-slate-800 text-white font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  All
                </button>
                <button
                  type="button"
                  onClick={() => setFilterNegation('AFFIRMED')}
                  className={`px-2 py-0.5 rounded transition-all ${
                    filterNegation === 'AFFIRMED'
                      ? 'bg-emerald-950 text-emerald-300 font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Affirmed
                </button>
                <button
                  type="button"
                  onClick={() => setFilterNegation('NEGATED')}
                  className={`px-2 py-0.5 rounded transition-all ${
                    filterNegation === 'NEGATED'
                      ? 'bg-rose-950 text-rose-300 font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Negated
                </button>
              </div>
            </div>

            {/* Structured Table */}
            <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950 h-[480px] overflow-y-auto">
              {filteredStatements.length > 0 ? (
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800 sticky top-0 z-10 backdrop-blur-md">
                    <tr>
                      <th className="p-3">Clinical Entity & Category</th>
                      <th className="p-3">Assertion (NegEx)</th>
                      <th className="p-3">Temporality</th>
                      <th className="p-3">Offset Span</th>
                      <th className="p-3">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-850">
                    {filteredStatements.map((stmt) => (
                      <tr key={stmt.id} className="hover:bg-slate-900/50 transition-colors">
                        <td className="p-3">
                          <div className="font-semibold text-slate-200">{stmt.entity_text}</div>
                          <span className="inline-block px-1.5 py-0.5 mt-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400">
                            {stmt.category}
                          </span>
                        </td>
                        <td className="p-3">
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
                        <td className="p-3 text-slate-400">
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-900 border border-slate-800">
                            {stmt.temporality}
                          </span>
                        </td>
                        <td className="p-3 font-mono text-[10px] text-slate-500">
                          [{stmt.char_start}:{stmt.char_end}]
                        </td>
                        <td className="p-3">
                          <span className="font-semibold text-slate-200">
                            {(stmt.confidence * 100).toFixed(0)}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="h-full flex flex-col items-center justify-center p-8 text-slate-500 text-xs">
                  <Sparkles size={26} className="mb-2 text-indigo-500/60" />
                  <p className="font-semibold text-slate-300">No statements extracted or matched filter</p>
                  <p className="text-[11px] text-slate-500 mt-1">
                    Click "Extract Clinical Statements" to run Clinical-BERT entity extraction.
                  </p>
                </div>
              )}
            </div>

            {/* NLP Model Metadata Bar */}
            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-[11px] text-slate-400 flex flex-wrap items-center justify-between gap-3 font-mono">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 size={13} className="text-emerald-400" />
                <span>Model: BioClinical-BERT v2.1</span>
              </div>
              <div>Tokenizer: WordPiece (vocab 28,996)</div>
              <div>Negation: Rule-based NegEx + Dependency Head</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
