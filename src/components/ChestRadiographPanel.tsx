import { useEffect, useMemo, useRef, useState } from "react";
import { Play } from "lucide-react";
import { Badge, Button, Card, ErrorBlock, KeyValue, LoadingBlock, SelectInput, StatusBadge, Table, Unavailable } from "./ui";
import { api, type ChestRadiographOutput, type UploadedFile } from "../services/api";
import { errorMessage, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";

const MODEL_ID = "cxr_torchxrayvision_densenet121";
const OUTLINE_COLORS: Record<string, string> = {
  "Right Lung": "var(--mt-series-1)", "Left Lung": "var(--mt-series-2)", Heart: "var(--mt-critical)", "Facies Diaphragmatica": "var(--mt-warning)",
};
const ZONE_ORDER = ["right_upper", "right_middle", "right_lower", "left_upper", "left_middle", "left_lower"];

/** A 28-by-28 attention grid drawn smooth over the analysed square: yellow to red, faint to strong. */
function AttentionCanvas({ grid }: { grid: number[][] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const size = grid.length;
    const image = context.createImageData(size, size);
    grid.forEach((row, y) => row.forEach((value, x) => {
      const offset = (y * size + x) * 4;
      image.data[offset] = 255;
      image.data[offset + 1] = Math.round(220 * (1 - value));
      image.data[offset + 2] = 0;
      image.data[offset + 3] = Math.round(170 * value);
    }));
    context.putImageData(image, 0, 0);
  }, [grid]);
  return <canvas ref={ref} width={grid.length} height={grid.length} className="h-full w-full" aria-hidden />;
}

function ScoreBar({ score, operatingPoint, margin }: { score: number; operatingPoint: number; margin: number }) {
  return (
    <span className="relative block h-2.5 w-40 rounded-full bg-surface-3" title={`Score ${score.toFixed(3)}; operating point ${operatingPoint}`}>
      <span className="absolute inset-y-0 rounded-full bg-[color-mix(in_srgb,var(--mt-ink-3)_18%,transparent)]" style={{ left: `${(operatingPoint - margin) * 100}%`, width: `${margin * 200}%` }} />
      <span className="absolute inset-y-0 left-0 rounded-full bg-[var(--mt-series-1)]" style={{ width: `${Math.min(1, Math.max(0, score)) * 100}%`, opacity: 0.75 }} />
      <span className="absolute -inset-y-0.5 w-0.5 bg-ink" style={{ left: `${operatingPoint * 100}%` }} />
    </span>
  );
}

function ResultView({ upload, output }: { upload: UploadedFile; output: ChestRadiographOutput }) {
  const imageUrl = useAsync(() => api.getUploadObjectUrl(upload.id), [upload.id]);
  const [attentionFinding, setAttentionFinding] = useState(output.attention[0]?.finding ?? "");
  const [outlines, setOutlines] = useState(true);
  useEffect(() => () => { if (imageUrl.data) URL.revokeObjectURL(imageUrl.data); }, [imageUrl.data]);
  const attention = output.attention.find((item) => item.finding === attentionFinding) ?? output.attention[0];
  const [width, height] = output.image_size;
  const [left, top, side] = output.analysis_square;
  const square = { left: `${(left / width) * 100}%`, top: `${(top / height) * 100}%`, width: `${(side / width) * 100}%`, height: `${(side / height) * 100}%` };
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <label className="text-[11px] text-ink-3">
            Attention for
            <SelectInput className="mt-0.5 h-8 w-56 text-xs" value={attention?.finding ?? ""} onChange={(event) => setAttentionFinding(event.target.value)}>
              {output.attention.map((item) => <option key={item.finding} value={item.finding}>{humanize(item.finding)}</option>)}
            </SelectInput>
          </label>
          <label className="mt-4 flex items-center gap-1.5 text-[11px] text-ink-2"><input type="checkbox" checked={outlines} onChange={(event) => setOutlines(event.target.checked)} /> Anatomy outlines</label>
        </div>
        <div className="relative overflow-hidden rounded-lg border border-line bg-black">
          {imageUrl.data ? <img src={imageUrl.data} alt="Chest radiograph analysed by the research model" className="block w-full" /> : <LoadingBlock label="Loading image" />}
          {attention && <div className="absolute" style={square}><AttentionCanvas grid={attention.grid} /></div>}
          <svg aria-label="Analysed square and anatomy outlines" className="absolute inset-0 h-full w-full" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            <rect x={left} y={top} width={side} height={side} fill="none" stroke="white" strokeDasharray="10 8" strokeWidth={2} opacity={0.7} />
            {outlines && output.anatomy.flatMap((structure) => structure.contours.map((contour, index) => (
              <polyline key={`${structure.name}-${index}`} points={contour.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke={OUTLINE_COLORS[structure.name] ?? "white"} strokeWidth={3} />
            )))}
          </svg>
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-ink-2">
          {output.anatomy.map((structure) => <span key={structure.name} className="flex items-center gap-1"><span aria-hidden className="h-0.5 w-4" style={{ background: OUTLINE_COLORS[structure.name] ?? "white" }} />{structure.name === "Facies Diaphragmatica" ? "Diaphragm" : structure.name}</span>)}
          <span className="flex items-center gap-1"><span aria-hidden className="h-2.5 w-4 rounded-sm bg-gradient-to-r from-yellow-300 to-red-600" />Grad-CAM attention (not a lesion outline)</span>
          <span className="flex items-center gap-1"><span aria-hidden className="h-2.5 w-4 border border-dashed border-ink-3" />Square the models read</span>
        </div>
        {attention && (
          <div className="mt-3">
            <p className="text-[11px] font-medium text-ink-3">Where the {humanize(attention.finding)} score depends on, by lung zone (patient's right and left; each lung's height in thirds)</p>
            <div className="mt-1 grid grid-cols-3 gap-1 text-[11px]">
              {ZONE_ORDER.map((zone) => (
                <span key={zone} className={`rounded-md border border-line px-2 py-1 tabular ${zone === attention.top_zone ? "bg-accent-soft text-ink" : "text-ink-2"}`}>
                  {humanize(zone)} {formatNumber((attention.zones[zone] ?? 0) * 100, 0)}%
                </span>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-ink-3">Outside both lungs: {formatNumber(attention.outside_lungs * 100, 0)}%</p>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div>
          <p className="text-sm font-medium text-ink">{output.summary}</p>
          <p className="mt-1 text-[11px] leading-4 text-ink-3">Each score is scaled by the publisher so {output.operating_point} is that finding's operating point (black line); the grey band (±{output.weak_margin}) marks weak scores. Scores are not probabilities and are not calibrated locally.</p>
        </div>
        <Table headers={["Finding", "Score", "", "Reading"]} dense>
          {output.findings.map((item) => (
            <tr key={item.finding}>
              <td className="text-xs text-ink">{humanize(item.finding)}</td>
              <td className="tabular text-xs text-ink">{item.score.toFixed(2)}</td>
              <td><ScoreBar score={item.score} operatingPoint={output.operating_point} margin={output.weak_margin} /></td>
              <td className="text-[11px] text-ink-2">{item.weak ? "Weak (near the operating point)" : item.above_operating_point ? "Above the operating point" : "Below the operating point"}</td>
            </tr>
          ))}
        </Table>
      </div>
    </div>
  );
}

export default function ChestRadiographPanel({ upload }: { upload: UploadedFile }) {
  const card = useAsync(() => api.getChestRadiographModel(), []);
  const findings = useWorkspace((state) => state.evidence.findings);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const [attested, setAttested] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fresh, setFresh] = useState<ChestRadiographOutput | null>(null);
  const stored = useMemo(() => findings
    .filter((finding) => finding.evidence_provenance?.model_id === MODEL_ID && finding.evidence_provenance?.source_file_sha256 === upload.file_hash)
    .sort((left, right) => right.created_at.localeCompare(left.created_at))[0], [findings, upload.file_hash]);
  const output = fresh ?? (stored?.evidence_provenance?.output as ChestRadiographOutput | undefined) ?? null;

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const result = await api.runChestRadiographAnalysis(upload.id);
      setFresh(result.research_output);
      void loadEvidence();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setRunning(false);
    }
  }

  return (
    <Card
      title="Chest radiograph research model"
      eyebrow="Third-party pretrained · not evaluated by MedTwin · research only"
      className="mt-4"
      actions={card.data && <StatusBadge status={card.data.available ? "READY_UNVALIDATED" : card.data.status} label={card.data.available ? "Weights present · unvalidated" : humanize(card.data.status)} />}
    >
      {card.loading && <LoadingBlock label="Checking the model" />}
      {card.error && <ErrorBlock message={card.error} onRetry={card.reload} />}
      {card.data && !card.data.available && <Unavailable compact code={card.data.status} reason={card.data.reason ?? "The model is not available here."} />}
      {card.data?.available && (
        <>
          <p className="text-xs leading-5 text-ink-2">
            {card.data.publisher.library}: a DenseNet-121 trained by its publisher on public digital chest radiographs scores 18 thoracic findings, and a PSPNet outlines the lungs, heart and diaphragm. {card.data.publisher.local_evaluation} A phone photograph of a printed film is outside their training data.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="flex items-start gap-2 text-xs text-ink-2">
              <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
              This upload is a frontal (PA or AP) chest radiograph.
            </label>
            <Button variant="primary" icon={Play} loading={running} disabled={!attested} onClick={() => void run()}>{output ? "Run again" : "Run chest radiograph model"}</Button>
            {stored && !fresh && <Badge tone="neutral" icon={false}>Showing the stored result of {new Date(stored.created_at).toLocaleString()}</Badge>}
          </div>
          {error && <div className="mt-3"><ErrorBlock message={error} /></div>}
        </>
      )}
      {output && (
        <div className="mt-4 space-y-4 border-t border-line pt-4">
          <ResultView upload={upload} output={output} />
          <div className="grid gap-4 xl:grid-cols-2">
            <div>
              <p className="mb-1 text-xs font-medium text-ink">What the case's reports state, beside the model</p>
              {output.report_comparison.length === 0 ? <p className="text-xs text-ink-2">No report statement names one of the model's 18 findings.</p> : (
                <Table headers={["Finding", "Model", "Reports", "Quote", "Comparison"]} dense>
                  {output.report_comparison.map((row) => (
                    <tr key={row.finding}>
                      <td className="text-xs text-ink">{humanize(row.finding)}</td>
                      <td className="tabular text-xs">{row.score.toFixed(2)}</td>
                      <td className="text-xs">{humanize(row.report_status)}<span className="block text-[11px] text-ink-3">{row.report_entities.join(", ")}</span></td>
                      <td className="max-w-[16rem] text-[11px] text-ink-2">“{row.report_quote}”</td>
                      <td><StatusBadge status={row.status === "AGREES" ? "CONSISTENT" : row.status === "DIFFERS" ? "IDENTITY_REVIEW_REQUIRED" : "INSUFFICIENT_EVIDENCE"} label={humanize(row.status)} /></td>
                    </tr>
                  ))}
                </Table>
              )}
              <p className="mt-1 text-[11px] leading-4 text-ink-3">Agreement is not proof of correctness; a CT or ultrasound report describes a different examination from this radiograph.</p>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-ink">Input checks</p>
              <KeyValue columns={2} items={[
                { label: "Chest anatomy", value: <StatusBadge status={output.input_checks.status === "APPLICABLE" ? "CONSISTENT" : "IDENTITY_REVIEW_REQUIRED"} label={humanize(output.input_checks.status)} /> },
                { label: "Lungs on expected sides", value: output.input_checks.lungs_on_expected_sides ? "Yes" : "No" },
                { label: "Right / left lung area", value: `${formatNumber(output.input_checks.right_lung_fraction * 100, 1)}% / ${formatNumber(output.input_checks.left_lung_fraction * 100, 1)}% of frame` },
                { label: "Heart area", value: `${formatNumber(output.input_checks.heart_fraction * 100, 1)}% of frame` },
                { label: "Autoencoder reconstruction error", value: formatNumber(output.input_checks.autoencoder_reconstruction_error, 3) },
                { label: "Printed text lines", value: output.input_checks.printed_document?.printed_text_lines ?? "Not checked" },
              ]} />
              <p className="mt-1 text-[11px] leading-4 text-ink-3">{output.input_checks.rule} {output.input_checks.autoencoder_note}</p>
            </div>
          </div>
          <p className="text-[11px] leading-4 text-ink-3">{card.data?.publisher.citation} Anatomy: {card.data?.publisher.anatomy_model}. The result is stored as a finding pending human review; nothing is registered to 3-D anatomy.</p>
        </div>
      )}
    </Card>
  );
}
