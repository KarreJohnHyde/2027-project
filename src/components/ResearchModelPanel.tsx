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

/** Upload kinds the research models run on; anything else has no upload inference path. */
export type ResearchInput = "image_2d" | "volume_nifti";

// One fixed colour per cardiac structure (ACDC label ids); the legend and table name each one.
const STRUCTURE_RGBA: Record<number, [number, number, number, number]> = { 1: [56, 132, 255, 140], 2: [245, 170, 40, 140], 3: [236, 72, 153, 140] };

function rgbaCss([r, g, b]: [number, number, number, number]): string {
  return `rgb(${r} ${g} ${b})`;
}

export type VolumeOutput = Extract<ResearchOutput, { type: "volume_segmentation" }>;

export function VolumeSliceLayer({ output, slice, highlight }: { output: VolumeOutput; slice: number; highlight: number | null }) {
  const [width, height] = output.volume_shape_ijk;
  const image = useMemo(() => {
    const plane = output.slices[slice];
    if (!plane) return null;
    return maskImage(
      plane.segments
        .filter((segment) => highlight === null || segment.class_index === highlight)
        .map((segment) => ({ mask: decodeCocoRle(segment.rle.counts, segment.rle.size[0], segment.rle.size[1]), rgba: STRUCTURE_RGBA[segment.class_index] ?? [34, 211, 238, 120] })),
      width,
      height,
    );
  }, [output, slice, highlight, width, height]);
  return image ? <image href={image} x={0} y={0} width={width} height={height} style={{ imageRendering: "pixelated" }} /> : null;
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

export function ResultView({ run, showBelow = false, setShowBelow = () => undefined, highlight = null, setHighlight = () => undefined }: { run: ResearchRun; showBelow?: boolean; setShowBelow?: (value: boolean) => void; highlight?: number | null; setHighlight?: (value: number | null) => void }) {
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
      {output.type === "ecg_multilabel" && (
        <>
          <p className="text-sm text-ink">At or above the validation-chosen threshold: {output.positive_classes.length ? output.positive_classes.join(", ") : "no class"}.</p>
          <Table headers={["Class", "Probability", "Threshold", "At/above"]} dense>
            {output.classes.map((item) => (
              <tr key={item.class}>
                <td className="text-ink">{item.class}</td>
                <td className="tabular text-ink-2">{formatNumber(item.probability, 3)}</td>
                <td className="tabular text-ink-2">{formatNumber(item.threshold, 3)}</td>
                <td>{item.at_or_above_threshold ? <Badge tone="neutral" icon={false}>Yes</Badge> : <span className="text-xs text-ink-3">No</span>}</td>
              </tr>
            ))}
          </Table>
          <KeyValue items={[
            { label: "Input", value: `${output.input.format} · ${formatNumber(output.input.sampling_rate_hz, 0)} Hz · ${formatNumber(output.input.duration_s, 1)} s` },
            { label: "Leads", value: output.input.leads.join(", ") },
            { label: "Peak |amplitude|", value: `${formatNumber(output.input.peak_abs_amplitude_mv, 2)} mV` },
            { label: "Precision", value: output.numeric_precision },
          ]} />
          <p className="text-[11px] leading-4 text-ink-3">{output.probability_semantics} {output.threshold_semantics} {output.input.processing} {output.input.notes.join(" ")} PTB-XL superclasses are ECG annotation groups, not confirmed clinical diagnoses.</p>
        </>
      )}
      {output.type === "volume_segmentation" && (
        <>
          <Table headers={["Structure", "Voxels", "Volume (mL)"]} dense>
            {output.structures.map((item) => (
              <tr key={item.class_index}>
                <td className="text-ink"><span aria-hidden className="mr-2 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: rgbaCss(STRUCTURE_RGBA[item.class_index] ?? [34, 211, 238, 1]) }} />{humanize(item.structure)}</td>
                <td className="tabular text-ink-2">{formatNumber(item.voxels, 0)}</td>
                <td className="tabular text-ink-2">{formatNumber(item.volume_ml, 1)}</td>
              </tr>
            ))}
          </Table>
          <SelectInput aria-label="Highlight structure" value={highlight ?? ""} onChange={(event) => setHighlight(event.target.value === "" ? null : Number(event.target.value))}>
            <option value="">All structures</option>
            {output.structures.map((item) => <option key={item.class_index} value={item.class_index}>{humanize(item.structure)}</option>)}
          </SelectInput>
          {Object.keys(output.held_out_volume_agreement).length > 0 && (
            <Disclosure summary="Held-out volume agreement of this model (internal ACDC test set)">
              <Table headers={["Index", "Bias (mL)", "95% limits (mL)"]} dense>
                {Object.entries(output.held_out_volume_agreement).map(([key, value]) => (
                  <tr key={key}>
                    <td className="text-ink">{humanize(key)}</td>
                    <td className="tabular text-ink-2">{formatNumber(value.bias_ml, 1)}</td>
                    <td className="tabular text-ink-2">{value.limits_of_agreement_ml ? `${formatNumber(value.limits_of_agreement_ml[0], 1)} to ${formatNumber(value.limits_of_agreement_ml[1], 1)}` : "—"}</td>
                  </tr>
                ))}
              </Table>
            </Disclosure>
          )}
          {output.input_warnings.length > 0 && <p className="text-[11px] leading-4 text-warning-text">Input notes: {output.input_warnings.join("; ")}.</p>}
          <p className="text-[11px] leading-4 text-ink-3">{output.volume_semantics} Voxel spacing {output.voxel_spacing_mm.map((value) => formatNumber(value, 3)).join(" × ")} mm from the NIfTI header. Masks are drawn on the axial index plane of the current slice.</p>
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
    .map(([key, value]) => ({ label: key === "test_n" && model.task === "volumetric_semantic_segmentation" ? "Test frames" : METRIC_LABELS[key] ?? humanize(key), value: key === "test_n" ? String(value) : formatNumber(value as number, 3) }));
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="text-xs font-medium text-ink">Internal held-out evaluation (public dataset, same source distribution)</p>
      <div className="mt-2"><KeyValue columns={2} items={items} /></div>
      <p className="mt-2 text-[11px] leading-4 text-ink-3">Licence: {licenceLabel({ name: model.dataset_license })} (<Link to="/attribution" className="text-accent-text hover:underline">data sources and licences</Link>). Checkpoint SHA-256 <code>{model.checkpoint_sha256?.slice(0, 16)}…</code></p>
    </div>
  );
}

export default function ResearchModelPanel({ uploadId, input, axialSlice = null, onOverlay }: { uploadId: number; input: ResearchInput | null; axialSlice?: number | null; onOverlay: (overlay: OverlayState | null) => void }) {
  const listing = useAsync(() => api.getResearchModels(), []);
  // Only models whose upload contract matches this file; ECG models run from Multimodal, survival models never run on uploads.
  const runnable = (listing.data?.models ?? []).filter((model) => model.gate.allowed && (model.inference_input ?? "image_2d") === input);
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
    if (output?.type === "volume_segmentation") {
      // Volume masks exist per axial index plane; other planes show the image without an overlay.
      onOverlay(axialSlice === null ? null : { sourceSize: [output.volume_shape_ijk[0], output.volume_shape_ijk[1]], layer: <VolumeSliceLayer output={output} slice={axialSlice} highlight={highlight} /> });
      return;
    }
    if (!output || (output.type !== "detection" && output.type !== "segmentation")) {
      onOverlay(null);
      return;
    }
    onOverlay({ sourceSize: output.image_size, layer: <OverlayLayer output={output} showBelow={showBelow} highlight={highlight} /> });
  }, [run, showBelow, highlight, axialSlice, onOverlay]);

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
  if (!input) return <Unavailable compact code="INPUT_NOT_SUPPORTED" reason="The registered research models accept decoded 2D PNG/JPEG/BMP images and single-frame NIfTI cardiac MRI volumes; DICOM, NRRD and MetaImage files are not supported by them." />;
  if (!model) return <Unavailable compact code="NO_RUNNABLE_RESEARCH_MODEL" reason={input === "volume_nifti" ? "No volumetric research model passes the gate (verified licence, held-out report, checkpoint hash, recorded input envelope)." : "No registered research model passes the gate (verified licence, held-out report, checkpoint hash)."} />;

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
        <span>I confirm this upload is a {listing.data?.input_types[inputType] ?? humanize(inputType)}, the input type this model was trained on. {input === "volume_nifti" ? "The server checks dimensionality and voxel spacing against the development data; it cannot verify the sequence, view or cardiac phase." : "MedTwin does not detect out-of-distribution inputs."}</span>
      </label>
      <Button variant="primary" icon={FlaskConical} disabled={!attested} loading={busy !== null} onClick={execute}>{busy ?? "Run research model"}</Button>
      {error && <ErrorBlock message={error} />}
      {run && <ResultView run={run} showBelow={showBelow} setShowBelow={setShowBelow} highlight={highlight} setHighlight={setHighlight} />}
    </div>
  );
}
