import { useEffect, useMemo, useState, type ReactNode } from "react";
import { FlaskConical } from "lucide-react";
import { Badge, Button, Disclosure, ErrorBlock, KeyValue, LoadingBlock, SelectInput, StatusBadge, Table, Unavailable } from "./ui";
import { api, type ResearchModel, type ResearchOutput, type ResearchRun } from "../services/api";
import { licenceLabel } from "../lib/displayNames";
import { errorMessage, formatNumber, humanize } from "../lib/format";
import { decodeCocoRle } from "../lib/rle";
import { Link } from "../lib/router";
import { useAsync } from "../lib/useAsync";

function maskImage(masks: Array<{ mask: Uint8Array; rgba: [number, number, number, number] }>, width: number, height: number): string {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return "";
  const image = context.createImageData(width, height);
  for (const { mask, rgba } of masks) {
    for (let index = 0; index < mask.length; index += 1) {
      if (!mask[index]) continue;
      image.data.set(rgba, index * 4);
    }
  }
  context.putImageData(image, 0, 0);
  return canvas.toDataURL("image/png");
}

export interface OverlayState {
  sourceSize: [number, number];
  layer: ReactNode;
}

function OverlayLayer({ output, showBelow, highlight }: { output: ResearchOutput; showBelow: boolean; highlight: number | null }) {
  const segmentationImage = useMemo(() => {
    if (output.type !== "segmentation") return null;
    const [width, height] = output.image_size;
    return maskImage(
      output.segments.map((segment) => ({
        mask: decodeCocoRle(segment.rle.counts, segment.rle.size[0], segment.rle.size[1]),
        rgba: segment.class_index === highlight ? [244, 114, 182, 210] : [34, 211, 238, 120],
      })),
      width,
      height,
    );
  }, [output, highlight]);
  if (output.type === "detection") {
    const stroke = Math.max(1.5, output.image_size[0] / 300);
    return (
      <>
        {output.boxes.filter((box) => box.above_display_threshold || showBelow).map((box, index) => {
          const [x1, y1, x2, y2] = box.bbox_xyxy;
          return (
            <g key={index}>
              <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} fill="none" stroke="var(--mt-overlay-model)" strokeWidth={stroke} strokeDasharray={box.above_display_threshold ? undefined : `${stroke * 3} ${stroke * 2}`} />
              <text x={x1 + stroke} y={Math.max(y1 - stroke * 2, stroke * 8)} fill="var(--mt-overlay-model)" fontSize={stroke * 8} fontFamily="ui-sans-serif, system-ui">{formatNumber(box.score, 2)}</text>
            </g>
          );
        })}
      </>
    );
  }
  if (output.type === "segmentation" && segmentationImage) {
    return <image href={segmentationImage} x={0} y={0} width={output.image_size[0]} height={output.image_size[1]} style={{ imageRendering: "pixelated" }} />;
  }
  return null;
}

function ResultView({ run, showBelow, setShowBelow, highlight, setHighlight }: { run: ResearchRun; showBelow: boolean; setShowBelow: (value: boolean) => void; highlight: number | null; setHighlight: (value: number | null) => void }) {
  const output = run.research_output;
  if (!output) return <Unavailable compact code={run.status} reason={run.error_message ?? "The run recorded no model output."} />;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="warning">Research only · not clinically validated</Badge>
        <StatusBadge status="PENDING_HUMAN_REVIEW" />
        <span className="text-[11px] text-ink-3">Run #{run.id} · {formatNumber(run.execution_time_ms ?? 0, 0)} ms</span>
      </div>
      {output.type === "classification" && (
        <>
          <Table headers={["Class", "Probability"]} dense>
            {output.classes.map((item) => (
              <tr key={item.class}>
                <td className="text-ink">{humanize(item.class)}</td>
                <td className="tabular text-ink-2">{formatNumber(item.probability, 3)}</td>
              </tr>
            ))}
          </Table>
          <p className="text-[11px] leading-4 text-ink-3">{output.probability_semantics} No overlay: the model classifies the whole image and does not localise.</p>
        </>
      )}
      {output.type === "detection" && (
        <>
          <p className="text-sm text-ink">{output.boxes.filter((box) => box.above_display_threshold).length} {humanize(output.class)} box(es) at or above the validation-chosen threshold {formatNumber(output.display_score_threshold, 2)}; {output.boxes.length} proposals in total.</p>
          <label className="flex items-center gap-2 text-xs text-ink-2">
            <input type="checkbox" checked={showBelow} onChange={(event) => setShowBelow(event.target.checked)} className="accent-[var(--mt-accent)]" />
            Show proposals below threshold (dashed)
          </label>
          <p className="text-[11px] leading-4 text-ink-3">{output.score_semantics} Boxes are drawn in {output.coordinate_space}.</p>
        </>
      )}
      {output.type === "segmentation" && (
        <>
          <p className="text-sm text-ink">{output.segments.length} segment class(es) predicted; {formatNumber(output.vessel_area_px, 0)} px labelled as {output.foreground_label ?? "vessel"}.</p>
          <SelectInput aria-label="Highlight segment" value={highlight ?? ""} onChange={(event) => setHighlight(event.target.value === "" ? null : Number(event.target.value))}>
            <option value="">All segments (one colour)</option>
            {output.segments.map((segment) => <option key={segment.class_index} value={segment.class_index}>{segment.segment} · {formatNumber(segment.area_px, 0)} px</option>)}
          </SelectInput>
          <p className="text-[11px] leading-4 text-ink-3">Masks are predicted at the model grid and mapped back to {output.coordinate_space} with nearest-neighbour resampling.</p>
        </>
      )}
      <Disclosure summary="Run provenance">
        <pre className="max-h-60 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-5 text-ink-2">{JSON.stringify(run.research_provenance, null, 2)}</pre>
      </Disclosure>
    </div>
  );
}

const METRIC_LABELS: Record<string, string> = {
  test_n: "Test images", accuracy: "Accuracy", macro_f1: "Macro-F1", ece_temperature_scaled: "ECE (temperature-scaled)",
  map_50_95: "mAP@[.50:.95]", ap_50: "AP50", mean_foreground_dice: "Mean foreground Dice", vessel_dice: "Foreground (all classes) Dice",
};

function Evaluation({ model }: { model: ResearchModel }) {
  const evaluation = model.held_out_evaluation ?? {};
  const items = Object.entries(evaluation)
    .filter(([, value]) => typeof value === "number")
    .map(([key, value]) => ({ label: METRIC_LABELS[key] ?? humanize(key), value: key === "test_n" ? String(value) : formatNumber(value as number, 3) }));
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="text-xs font-medium text-ink">Internal held-out evaluation (public dataset, same source distribution)</p>
      <div className="mt-2"><KeyValue columns={2} items={items} /></div>
      <p className="mt-2 text-[11px] leading-4 text-ink-3">Licence: {licenceLabel({ name: model.dataset_license })} (<Link to="/attribution" className="text-accent-text hover:underline">data sources and licences</Link>). Checkpoint SHA-256 <code>{model.checkpoint_sha256?.slice(0, 16)}…</code></p>
    </div>
  );
}

export default function ResearchModelPanel({ uploadId, raster, onOverlay }: { uploadId: number; raster: boolean; onOverlay: (overlay: OverlayState | null) => void }) {
  const listing = useAsync(() => api.getResearchModels(), []);
  // ECG and tabular survival models are registered evidence, not image-upload models.
  const runnable = (listing.data?.models ?? []).filter((model) => model.gate.allowed && (model.inference_input ?? "image_2d") === "image_2d");
  const [modelId, setModelId] = useState<string>("");
  const model = runnable.find((item) => item.model_id === modelId) ?? runnable[0] ?? null;
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [showBelow, setShowBelow] = useState(false);
  const [highlight, setHighlight] = useState<number | null>(null);
  const inputType = model?.supported_modalities[0] ?? "";

  useEffect(() => {
    const output = run?.research_output;
    if (!output || output.type === "classification") {
      onOverlay(null);
      return;
    }
    onOverlay({ sourceSize: output.image_size, layer: <OverlayLayer output={output} showBelow={showBelow} highlight={highlight} /> });
  }, [run, showBelow, highlight, onOverlay]);

  async function execute() {
    if (!model) return;
    setBusy("Running");
    setError(null);
    try {
      const result = await api.runResearchModel(uploadId, model.model_id, inputType, (job) => setBusy(`${humanize(job.status)}${job.message ? ` · ${job.message}` : ""}`));
      setRun(result);
      setHighlight(null);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  if (listing.loading) return <LoadingBlock label="Reading model registry" />;
  if (listing.error) return <ErrorBlock message={listing.error} onRetry={listing.reload} />;
  if (!raster) return <Unavailable compact code="INPUT_NOT_SUPPORTED" reason="The registered research models accept decoded 2D PNG/JPEG/BMP images; DICOM and volumetric inputs are not supported by them." />;
  if (!model) return <Unavailable compact code="NO_RUNNABLE_RESEARCH_MODEL" reason="No registered research model passes the gate (verified licence, held-out report, checkpoint hash)." />;

  return (
    <div className="space-y-3">
      <p className="text-[11px] leading-4 text-ink-2">{listing.data?.notice}</p>
      <label className="block text-xs text-ink-2">
        Model
        <SelectInput aria-label="Research model" value={model.model_id} onChange={(event) => { setModelId(event.target.value); setAttested(false); setRun(null); }}>
          {runnable.map((item) => <option key={item.model_id} value={item.model_id}>{item.display_name}</option>)}
        </SelectInput>
      </label>
      <Evaluation model={model} />
      <label className="flex items-start gap-2 text-xs text-ink-2">
        <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
        <span>I confirm this upload is a {listing.data?.input_types[inputType] ?? humanize(inputType)}, the input type this model was trained on. MedTwin does not detect out-of-distribution inputs.</span>
      </label>
      <Button variant="primary" icon={FlaskConical} disabled={!attested} loading={busy !== null} onClick={execute}>{busy ?? "Run research model"}</Button>
      {error && <ErrorBlock message={error} />}
      {run && <ResultView run={run} showBelow={showBelow} setShowBelow={setShowBelow} highlight={highlight} setHighlight={setHighlight} />}
    </div>
  );
}
