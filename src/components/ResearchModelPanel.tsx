import { Suspense, lazy, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Check, FlaskConical, Upload, X } from "lucide-react";
import { Badge, Button, Disclosure, ErrorBlock, KeyValue, LoadingBlock, Segmented, SelectInput, StatusBadge, Table, TextInput, Unavailable } from "./ui";
import { api, type BoxComparison, type RunAgreement, type CocoRle, type FilmAssessment, type ReferenceAnnotation, type ReferenceComparison, type ResearchModel, type ResearchOutput, type ResearchRun } from "../services/api";
import { licenceLabel, publicText } from "../lib/displayNames";
import { errorMessage, formatDate, formatNumber, humanize } from "../lib/format";
import { decodeCocoRle } from "../lib/rle";
import { Link } from "../lib/router";
import MaskCorrectionEditor from "./MaskCorrectionEditor";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";

type Rgba = [number, number, number, number];

// three.js is loaded only when a volumetric run's surfaces are opened.
const VolumeSurfaceView = lazy(() => import("./VolumeSurfaceView"));

// One colour per evidence layer, named in the legend and in each panel caption.
const LAYER_RGBA = {
  prediction: [34, 211, 238, 150] as Rgba,
  highlight: [244, 114, 182, 210] as Rgba,
  reference: [250, 204, 21, 150] as Rgba,
  agreement: [34, 197, 94, 165] as Rgba,
  modelOnly: [217, 70, 239, 175] as Rgba,
  referenceOnly: [250, 204, 21, 175] as Rgba,
};

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

function RleLayer({ masks, width, height }: { masks: Array<{ rle: CocoRle; rgba: Rgba }>; width: number; height: number }) {
  const image = useMemo(
    () => maskImage(masks.map(({ rle, rgba }) => ({ mask: decodeCocoRle(rle.counts, rle.size[0], rle.size[1]), rgba })), width, height),
    [masks, width, height],
  );
  return image ? <image href={image} x={0} y={0} width={width} height={height} style={{ imageRendering: "pixelated" }} /> : null;
}

/** What the main viewer draws for a segmentation run once a reference annotation is selected. */
export type LayerMode = "prediction" | "reference" | "comparison";

export interface ReferenceState {
  reference: ReferenceAnnotation;
  comparison: ReferenceComparison;
}

export function OverlayLayer({ output, showBelow, highlight, mode = "prediction", reference = null, opacity = 1 }: { output: ResearchOutput; showBelow: boolean; highlight: number | null; mode?: LayerMode; reference?: ReferenceState | null; opacity?: number }) {
  const masks = useMemo(() => {
    if (output.type !== "segmentation") return [];
    if (mode === "reference" && reference) return [{ rle: reference.reference.rle, rgba: LAYER_RGBA.reference }];
    if (mode === "comparison" && reference) {
      const { regions } = reference.comparison;
      return [{ rle: regions.agreement, rgba: LAYER_RGBA.agreement }, { rle: regions.model_only, rgba: LAYER_RGBA.modelOnly }, { rle: regions.reference_only, rgba: LAYER_RGBA.referenceOnly }];
    }
    return output.segments.map((segment) => ({ rle: segment.rle, rgba: segment.class_index === highlight ? LAYER_RGBA.highlight : LAYER_RGBA.prediction }));
  }, [output, highlight, mode, reference]);
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
  if (output.type === "segmentation") {
    return <g opacity={opacity}><RleLayer masks={masks} width={output.image_size[0]} height={output.image_size[1]} /></g>;
  }
  return null;
}

function Legend({ items }: { items: Array<{ label: string; tag: string; rgba: Rgba }> }) {
  return (
    <ul aria-label="Overlay legend" className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-2">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: rgbaCss(item.rgba) }} />
          {item.label}
          <span className="font-mono text-[10px] text-ink-3">{item.tag}</span>
        </li>
      ))}
    </ul>
  );
}


/** A clinician's decision recorded beside the run; the stored output never changes. */
function RunReview({ run, onReviewed }: { run: ResearchRun; onReviewed: () => void }) {
  const role = useWorkspace((state) => state.user?.role);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const review = run.latest_review;
  async function submit(decision: "CONFIRMED" | "REJECTED") {
    if (!run.finding_id) return;
    setBusy(decision);
    setError(null);
    try {
      await api.submitFindingReview(run.finding_id, decision, comment);
      setComment("");
      onReviewed();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="space-y-2 rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-medium text-ink">Human review</p>
        <StatusBadge status={review?.review_status ?? "PENDING_HUMAN_REVIEW"} />
        {review && <span className="text-[11px] text-ink-3">{formatDate(review.reviewed_at, true)}{review.reviewer_verified_professional ? " · verified clinician" : " · not a verified clinician"}{review.reviewer_comments ? ` · “${review.reviewer_comments}”` : ""}</span>}
      </div>
      <p className="text-[11px] leading-4 text-ink-3">
        The decision is stored beside this run; the model output is never changed. A confirmed output is associated with its organ in the{" "}
        <Link to="/anatomy-studio" className="text-accent-text hover:underline">Anatomy Studio</Link> as a schematic, organ-level link with no location on the model.
      </p>
      {run.finding_id && role ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-48 flex-1 text-[11px] text-ink-3">Comment (optional)<TextInput value={comment} onChange={(event) => setComment(event.target.value)} className="h-8 text-xs" /></label>
          <Button size="sm" icon={Check} loading={busy === "CONFIRMED"} disabled={busy !== null} onClick={() => void submit("CONFIRMED")}>Confirm</Button>
          <Button size="sm" variant="secondary" icon={X} loading={busy === "REJECTED"} disabled={busy !== null} onClick={() => void submit("REJECTED")}>Reject</Button>
        </div>
      ) : null}
      {error && <ErrorBlock message={error} />}
    </div>
  );
}

function MaskedFigure({ imageUrl, size, masks, label, tag }: { imageUrl: string; size: [number, number]; masks: Array<{ rle: CocoRle; rgba: Rgba }>; label: string; tag?: string }) {
  return (
    <figure className="min-w-0">
      <div className="relative overflow-hidden rounded bg-black">
        <img src={imageUrl} alt="" draggable={false} className="block h-auto w-full select-none" />
        {masks.length > 0 && (
          <svg aria-hidden viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
            <RleLayer masks={masks} width={size[0]} height={size[1]} />
          </svg>
        )}
      </div>
      <figcaption className="mt-1 text-[11px] leading-4 text-ink-2">{label}{tag && <span className="ml-1 font-mono text-[10px] text-ink-3">{tag}</span>}</figcaption>
    </figure>
  );
}

const REFERENCE_SOURCES: Array<{ value: ReferenceAnnotation["source"]; label: string }> = [
  { value: "DATASET_PUBLISHER_ANNOTATION", label: "Dataset publisher's mask for this image" },
  { value: "INDEPENDENT_EXPERT_ANNOTATION", label: "Expert annotation made independently of the model" },
];

/** Reference masks for this upload and the per-image agreement of the run's mask with one of them. */
function ReferencePanel({ uploadId, run, output, imageUrl, onChange, classNames }: { uploadId: number; run: ResearchRun; output: Extract<ResearchOutput, { type: "segmentation" }>; imageUrl: string | null; onChange: (state: ReferenceState | null) => void; classNames: string[] }) {
  const role = useWorkspace((state) => state.user?.role);
  const list = useAsync(() => api.listReferenceAnnotations(uploadId), [uploadId]);
  const annotations = useMemo(() => list.data?.annotations ?? [], [list.data]);
  const [chosen, setChosen] = useState<number | null>(null);
  // The newest reference is compared until another one is chosen.
  const selected = chosen ?? annotations[0]?.id ?? null;
  const compared = useAsync(() => (selected === null ? Promise.resolve(null) : api.compareWithReference(run.id, selected)), [run.id, selected]);
  const comparison: ReferenceComparison | null = compared.data ?? null;
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<ReferenceAnnotation["source"]>("DATASET_PUBLISHER_ANNOTATION");
  const [detail, setDetail] = useState("");
  const [className, setClassName] = useState(output.foreground_label ?? output.segments[0]?.segment ?? "");
  const [independent, setIndependent] = useState(false);
  const [saving, setSaving] = useState(false);
  const reference = annotations.find((item) => item.id === selected) ?? null;

  useEffect(() => {
    onChange(reference && comparison ? { reference, comparison } : null);
  }, [reference, comparison, onChange]);

  async function attach() {
    if (!file || !independent) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.addReferenceAnnotation(uploadId, file, { source, sourceDetail: detail.trim(), className: className.trim() });
      setFile(null);
      setIndependent(false);
      list.reload();
      setChosen(created.id);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-line p-3">
      <p className="text-xs font-medium text-ink">Reference annotations and reviewer corrections <span className="font-mono text-[10px] text-ink-3">GROUND_TRUTH · REVIEWER_CORRECTION</span></p>
      {annotations.length === 0 ? (
        <p className="text-[11px] leading-4 text-ink-3">No reference mask or correction is attached to this image, so no agreement can be shown. A mask is compared only when its origin is declared; model output never becomes a reference.</p>
      ) : (
        <SelectInput aria-label="Reference annotation" value={selected ?? ""} onChange={(event) => setChosen(Number(event.target.value))}>
          {annotations.map((item) => <option key={item.id} value={item.id}>#{item.id} · {item.class_name} · {item.source_detail}</option>)}
        </SelectInput>
      )}
      {reference && <p className="text-[11px] leading-4 text-ink-3">{reference.source_label}: {reference.source_detail}. Mask {reference.mask_filename}, thresholded above {reference.binarize_threshold}, SHA-256 <code>{reference.mask_sha256.slice(0, 16)}…</code></p>}
      {comparison && (
        <>
          <KeyValue columns={3} items={[
            { label: "Dice", value: formatNumber(comparison.dice, 3) },
            { label: "IoU", value: formatNumber(comparison.iou, 3) },
            { label: "HD95 (px)", value: comparison.hd95_px === null ? "Not defined" : formatNumber(comparison.hd95_px, 1) },
            { label: "Pixel precision", value: comparison.pixel_precision === null ? "Not defined" : formatNumber(comparison.pixel_precision, 3) },
            { label: "Pixel recall", value: comparison.pixel_recall === null ? "Not defined" : formatNumber(comparison.pixel_recall, 3) },
            { label: "Area model / reference (px)", value: `${formatNumber(comparison.predicted_area_px, 0)} / ${formatNumber(comparison.reference_area_px, 0)}` },
          ]} />
          <p className="text-[11px] leading-4 text-ink-3">{comparison.semantics} Compared: {comparison.compared}.</p>
          {imageUrl && (
            <div className="grid grid-cols-3 gap-2">
              <MaskedFigure imageUrl={imageUrl} size={output.image_size} masks={[]} label="Input" />
              <MaskedFigure imageUrl={imageUrl} size={output.image_size} masks={reference ? [{ rle: reference.rle, rgba: LAYER_RGBA.reference }] : []} label={reference?.layer === "REVIEWER_CORRECTION" ? "Reviewer correction" : "Reference"} tag={reference?.layer ?? "GROUND_TRUTH"} />
              <MaskedFigure imageUrl={imageUrl} size={output.image_size} masks={output.segments.map((segment) => ({ rle: segment.rle, rgba: LAYER_RGBA.prediction }))} label="Model" tag="MODEL_PREDICTION" />
            </div>
          )}
        </>
      )}
      {(error ?? compared.error) && <ErrorBlock message={(error ?? compared.error)!} />}
      {role && imageUrl && (
        <Disclosure summary="Correct the model's mask (brush and eraser)">
          <MaskCorrectionEditor run={run} output={output} imageUrl={imageUrl} classNames={classNames} onSaved={(created) => { list.reload(); setChosen(created.id); }} />
        </Disclosure>
      )}
      {role && (
        <Disclosure summary="Attach a reference mask">
          <form className="space-y-2 p-3" onSubmit={(event) => { event.preventDefault(); void attach(); }}>
            <input type="file" accept=".png,.jpg,.jpeg,.bmp" aria-label="Reference mask file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="block w-full text-xs text-ink-2" />
            <SelectInput aria-label="Reference source" value={source} onChange={(event) => setSource(event.target.value as ReferenceAnnotation["source"])}>
              {REFERENCE_SOURCES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </SelectInput>
            <label className="block text-[11px] text-ink-3">Source detail (dataset, version and split, or annotator)<TextInput value={detail} onChange={(event) => setDetail(event.target.value)} className="h-8 text-xs" /></label>
            <label className="block text-[11px] text-ink-3">Class<TextInput value={className} onChange={(event) => setClassName(event.target.value)} className="h-8 text-xs" /></label>
            <label className="flex items-start gap-2 text-[11px] leading-4 text-ink-2">
              <input type="checkbox" checked={independent} onChange={(event) => setIndependent(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
              <span>This mask was drawn on this exact image and was not derived from any model's output. White (above 127) marks the class.</span>
            </label>
            <Button size="sm" type="submit" icon={Upload} loading={saving} disabled={!file || !independent || detail.trim().length < 3 || !className.trim()}>Attach reference</Button>
          </form>
        </Disclosure>
      )}
    </div>
  );
}

/** Reference boxes for this upload and the per-image agreement of the run's boxes with one of them. */
function BoxReferencePanel({ uploadId, run, output, imageUrl }: { uploadId: number; run: ResearchRun; output: Extract<ResearchOutput, { type: "detection" }>; imageUrl: string | null }) {
  const role = useWorkspace((state) => state.user?.role);
  const list = useAsync(() => api.listReferenceAnnotations(uploadId), [uploadId]);
  const annotations = useMemo(() => (list.data?.annotations ?? []).filter((item) => item.kind === "BOUNDING_BOXES"), [list.data]);
  const [chosen, setChosen] = useState<number | null>(null);
  const selected = chosen ?? annotations[0]?.id ?? null;
  const compared = useAsync(() => (selected === null ? Promise.resolve(null) : api.compareWithReferenceBoxes(run.id, selected)), [run.id, selected]);
  const comparison: BoxComparison | null = compared.data && compared.data.run_id === run.id && compared.data.reference.annotation_id === selected ? compared.data : null;
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<ReferenceAnnotation["source"]>("DATASET_PUBLISHER_ANNOTATION");
  const [detail, setDetail] = useState("");
  const [className, setClassName] = useState(output.class);
  const [independent, setIndependent] = useState(false);
  const [saving, setSaving] = useState(false);
  const reference = annotations.find((item) => item.id === selected) ?? null;
  const [width, height] = output.image_size;

  async function attach() {
    if (!file || !independent) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.addReferenceBoxes(uploadId, file, { source, sourceDetail: detail.trim(), className: className.trim() });
      setFile(null);
      setIndependent(false);
      list.reload();
      setChosen(created.id);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setSaving(false);
    }
  }

  const rect = (box: number[], key: string, colour: string, dashed: boolean) => (
    <rect key={key} x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]} fill="none" stroke={colour}
      strokeWidth={Math.max(1.5, width / 300)} strokeDasharray={dashed ? `${width / 80} ${width / 120}` : undefined} vectorEffect="non-scaling-stroke" />
  );

  return (
    <div className="space-y-3 rounded-lg border border-line p-3">
      <p className="text-xs font-medium text-ink">Reference boxes <span className="font-mono text-[10px] text-ink-3">GROUND_TRUTH</span></p>
      {annotations.length === 0 ? (
        <p className="text-[11px] leading-4 text-ink-3">No reference boxes are attached to this image, so no agreement can be shown. Boxes are compared only when their origin is declared; model output never becomes a reference.</p>
      ) : (
        <SelectInput aria-label="Reference boxes" value={selected ?? ""} onChange={(event) => setChosen(Number(event.target.value))}>
          {annotations.map((item) => <option key={item.id} value={item.id}>#{item.id} · {item.class_name} · {item.boxes?.length ?? 0} box(es) · {item.source_detail}</option>)}
        </SelectInput>
      )}
      {reference && <p className="text-[11px] leading-4 text-ink-3">{reference.source_label}: {reference.source_detail}. File {reference.mask_filename}, SHA-256 <code>{reference.mask_sha256.slice(0, 16)}…</code></p>}
      {comparison && (
        <>
          <KeyValue columns={3} items={[
            { label: "Matched (IoU ≥ 0.5)", value: String(comparison.matched) },
            { label: "Model only", value: String(comparison.model_only) },
            { label: "Reference only", value: String(comparison.reference_only) },
            { label: "Precision", value: comparison.precision === null ? "Not defined" : formatNumber(comparison.precision, 3) },
            { label: "Recall", value: comparison.recall === null ? "Not defined" : formatNumber(comparison.recall, 3) },
            { label: "Mean matched IoU", value: comparison.mean_matched_iou === null ? "Not defined" : formatNumber(comparison.mean_matched_iou, 3) },
          ]} />
          <p className="text-[11px] leading-4 text-ink-3">{comparison.semantics}</p>
          {imageUrl && (
            <figure className="space-y-1">
              <svg viewBox={`0 0 ${width} ${height}`} className="w-full max-w-lg rounded border border-line" role="img"
                aria-label={`Image with ${comparison.matched} matched, ${comparison.model_only} model-only and ${comparison.reference_only} reference-only boxes`}>
                <image href={imageUrl} x={0} y={0} width={width} height={height} />
                {comparison.pairs.map((pair, index) => rect(pair.reference_box, `pr-${index}`, rgbaCss(LAYER_RGBA.reference), true))}
                {comparison.pairs.map((pair, index) => rect(pair.model_box, `pm-${index}`, rgbaCss(LAYER_RGBA.prediction), false))}
                {comparison.reference_only_boxes.map((box, index) => rect(box, `r-${index}`, rgbaCss(LAYER_RGBA.reference), true))}
                {comparison.model_only_boxes.map((item, index) => rect(item.model_box, `m-${index}`, rgbaCss(LAYER_RGBA.prediction), false))}
              </svg>
              <figcaption className="text-[11px] text-ink-3">Dashed: reference boxes. Solid: model boxes above the display threshold ({formatNumber(comparison.display_score_threshold ?? 0, 2)}).</figcaption>
            </figure>
          )}
        </>
      )}
      {(error ?? compared.error) && <ErrorBlock message={(error ?? compared.error)!} />}
      {role && (
        <Disclosure summary="Attach reference boxes">
          <form className="space-y-2 p-3" onSubmit={(event) => { event.preventDefault(); void attach(); }}>
            <input type="file" accept=".json,.txt" aria-label="Reference box file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="block w-full text-xs text-ink-2" />
            <p className="text-[11px] leading-4 text-ink-3">JSON <code>{'{"boxes": [[x1, y1, x2, y2]]}'}</code> or COCO <code>bbox</code> entries in this image's pixels, or YOLO lines (normalised boxes or polygons).</p>
            <SelectInput aria-label="Reference box source" value={source} onChange={(event) => setSource(event.target.value as ReferenceAnnotation["source"])}>
              {REFERENCE_SOURCES.map((item) => <option key={item.value} value={item.value}>{item.label.replace("mask", "boxes")}</option>)}
            </SelectInput>
            <label className="block text-[11px] text-ink-3">Source detail (dataset, version and split, or annotator)<TextInput value={detail} onChange={(event) => setDetail(event.target.value)} className="h-8 text-xs" /></label>
            <label className="block text-[11px] text-ink-3">Class<TextInput value={className} onChange={(event) => setClassName(event.target.value)} className="h-8 text-xs" /></label>
            <label className="flex items-start gap-2 text-[11px] leading-4 text-ink-2">
              <input type="checkbox" checked={independent} onChange={(event) => setIndependent(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
              <span>These boxes were drawn on this exact image and were not derived from any model's output.</span>
            </label>
            <Button size="sm" type="submit" icon={Upload} loading={saving} disabled={!file || !independent || detail.trim().length < 3 || !className.trim()}>Attach reference boxes</Button>
          </form>
        </Disclosure>
      )}
    </div>
  );
}

/** Reviewer corrections of a volume run on the displayed axial plane, and the corrected volume per structure. */
function VolumeCorrectionPanel({ run, output, sliceIndex, sliceImageUrl }: { run: ResearchRun; output: VolumeOutput; sliceIndex: number | null; sliceImageUrl: string | null }) {
  const role = useWorkspace((state) => state.user?.role);
  const summary = useAsync(() => api.getVolumeSliceCorrections(run.id), [run.id]);
  const [ni, nj] = output.volume_shape_ijk;
  // The displayed plane as a 2-D segmentation output on the slice's own (i, j) pixels, as the overlay draws it. Memoised:
  // a new object would reset the editor (its mask restarts from the model) on every summary refresh.
  const sliceOutput = useMemo(() => {
    if (sliceIndex === null) return null;
    const plane = output.slices.find((item) => item.slice_index === sliceIndex) ?? { slice_index: sliceIndex, segments: [] };
    const names = new Map(output.structures.map((item) => [item.class_index, item.structure]));
    return {
      type: "segmentation" as const, image_size: [ni, nj] as [number, number], coordinate_space: "axial index plane (i, j)",
      segments: plane.segments.map((segment) => ({ class_index: segment.class_index, segment: names.get(segment.class_index) ?? `class ${segment.class_index}`, area_px: segment.area_px, rle: segment.rle })),
    } as unknown as Extract<ResearchOutput, { type: "segmentation" }>;
  }, [output, sliceIndex, ni, nj]);
  const data = summary.data;
  return (
    <div className="space-y-3 rounded-lg border border-line p-3">
      <p className="text-xs font-medium text-ink">Reviewer corrections of this volume <span className="font-mono text-[10px] text-ink-3">REVIEWER_CORRECTION</span></p>
      {summary.error && <ErrorBlock message={summary.error} />}
      {data && data.corrected_slices.length > 0 && (
        <>
          <Table headers={["Structure", "Model (mL)", "Corrected (mL)", "Slices corrected"]} dense>
            {data.structures.map((item) => (
              <tr key={item.structure}>
                <td className="text-ink">{humanize(item.structure)}</td>
                <td className="tabular text-ink-2">{formatNumber(item.model_volume_ml, 2)}</td>
                <td className="tabular text-ink-2">{formatNumber(item.corrected_volume_ml, 2)}</td>
                <td className="tabular text-ink-2">{item.slices_corrected}</td>
              </tr>
            ))}
          </Table>
          <p className="text-[11px] leading-4 text-ink-3">{data.semantics} Corrected planes: {data.corrected_slices.map((item) => `${item.slice_index} (${humanize(item.structure)}, +${item.voxels_added}/−${item.voxels_removed})`).join("; ")}.</p>
        </>
      )}
      {data && data.corrected_slices.length === 0 && <p className="text-[11px] leading-4 text-ink-3">No slice of this run has been corrected.</p>}
      {role && sliceOutput && sliceImageUrl ? (
        <Disclosure summary={`Correct axial plane ${sliceIndex} (brush and eraser)`}>
          <MaskCorrectionEditor key={`${run.id}-${sliceIndex}`} run={run} output={sliceOutput} imageUrl={sliceImageUrl} classNames={output.structures.map((item) => item.structure)}
            save={(mask, fields) => api.addVolumeSliceCorrection(run.id, sliceIndex as number, mask, fields)} onSaved={() => summary.reload()} />
        </Disclosure>
      ) : role ? <p className="text-[11px] leading-4 text-ink-3">Show the axial plane to correct it here (corrections are made one axial index plane at a time).</p> : null}
    </div>
  );
}

/** Two runs on this image side by side, with their agreement (neither is ground truth). */
function RunAgreementPanel({ run, candidates, imageUrl }: { run: ResearchRun; candidates: ResearchRun[]; imageUrl: string | null }) {
  const [otherId, setOtherId] = useState<number>(candidates[0].id);
  const other = candidates.find((item) => item.id === otherId) ?? candidates[0];
  const agreement = useAsync(() => api.compareRuns(run.id, other.id), [run.id, other.id]);
  // useAsync keeps the previous data while a new request runs; never show it under the new selection.
  const result: RunAgreement | null = agreement.data && agreement.data.run_ids[0] === run.id && agreement.data.run_ids[1] === other.id ? agreement.data : null;
  const name = (item: ResearchRun) => `#${item.id} · ${String(item.research_provenance.model_display_name ?? item.model_name)}`;
  const first = run.research_output;
  const second = other.research_output;
  const boxes = (items: number[][], colour: string, dashed: boolean, size: [number, number]) => items.map((box, index) => (
    <rect key={`${colour}-${index}`} x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]} fill="none" stroke={colour}
      strokeWidth={Math.max(1.5, size[0] / 300)} strokeDasharray={dashed ? `${size[0] / 80} ${size[0] / 120}` : undefined} vectorEffect="non-scaling-stroke" />
  ));
  const metrics = !result ? [] : result.kind === "segmentation" ? [
    { label: "Foreground Dice", value: formatNumber(result.foreground_dice ?? 0, 3) },
    { label: "Foreground IoU", value: formatNumber(result.foreground_iou ?? 0, 3) },
    { label: "Area first / second (px)", value: `${formatNumber(result.area_px?.[0] ?? 0, 0)} / ${formatNumber(result.area_px?.[1] ?? 0, 0)}` },
  ] : result.kind === "detection" ? [
    { label: "Matched (IoU ≥ 0.5)", value: String(result.matched) },
    { label: "Only first / only second", value: `${result.only_first} / ${result.only_second}` },
    { label: "Mean matched IoU", value: result.mean_matched_iou == null ? "Not defined" : formatNumber(result.mean_matched_iou, 3) },
  ] : result.kind === "classification" ? [
    { label: "Top class first / second", value: `${humanize(result.top_classes?.[0] ?? "")} / ${humanize(result.top_classes?.[1] ?? "")}` },
    { label: "Same top class", value: result.same_top_class ? "Yes" : "No" },
  ] : result.kind === "multilabel_classification" ? [
    { label: "At threshold, first", value: (result.positive_labels?.[0] ?? []).map(humanize).join(", ") || "none" },
    { label: "At threshold, second", value: (result.positive_labels?.[1] ?? []).map(humanize).join(", ") || "none" },
  ] : Object.entries(result.shared_structures ?? {}).map(([structure, value]) => ({
    label: humanize(structure), value: `${formatNumber(value.volume_ml[0], 1)} / ${formatNumber(value.volume_ml[1], 1)} mL (Δ ${formatNumber(value.difference_ml, 1)})`,
  }));
  return (
    <Disclosure summary={`Compare with another run on this image (${candidates.length} available)`}>
      <div className="space-y-3 p-3">
        <SelectInput aria-label="Run to compare with" value={other.id} onChange={(event) => setOtherId(Number(event.target.value))}>
          {candidates.map((item) => <option key={item.id} value={item.id}>{name(item)}</option>)}
        </SelectInput>
        {agreement.loading && <LoadingBlock label="Comparing runs" />}
        {agreement.error && <ErrorBlock message={agreement.error} />}
        {result && (
          <>
            <p className="text-[11px] text-ink-2">First: {name(run)}. Second: {name(other)}.</p>
            <KeyValue columns={3} items={metrics} />
            <p className="text-[11px] leading-4 text-ink-3">{result.semantics}{result.note ? ` ${result.note}` : ""}</p>
            {imageUrl && first?.type === "segmentation" && second?.type === "segmentation" && (
              <div className="grid grid-cols-2 gap-2">
                <MaskedFigure imageUrl={imageUrl} size={first.image_size} masks={first.segments.map((segment) => ({ rle: segment.rle, rgba: LAYER_RGBA.prediction }))} label="First run" tag="MODEL_PREDICTION" />
                <MaskedFigure imageUrl={imageUrl} size={second.image_size} masks={second.segments.map((segment) => ({ rle: segment.rle, rgba: LAYER_RGBA.reference }))} label="Second run" tag="MODEL_PREDICTION" />
              </div>
            )}
            {imageUrl && first?.type === "detection" && result.kind === "detection" && (
              <figure className="space-y-1">
                <svg viewBox={`0 0 ${first.image_size[0]} ${first.image_size[1]}`} className="w-full max-w-lg rounded border border-line" role="img" aria-label="Boxes of both runs on the image">
                  <image href={imageUrl} x={0} y={0} width={first.image_size[0]} height={first.image_size[1]} />
                  {boxes([...(result.pairs ?? []).map((pair) => pair.first_box), ...(result.only_first_boxes ?? [])], rgbaCss(LAYER_RGBA.prediction), false, first.image_size)}
                  {boxes([...(result.pairs ?? []).map((pair) => pair.second_box), ...(result.only_second_boxes ?? [])], rgbaCss(LAYER_RGBA.reference), true, first.image_size)}
                </svg>
                <figcaption className="text-[11px] text-ink-3">Solid: first run. Dashed: second run. Boxes above each run's own display threshold.</figcaption>
              </figure>
            )}
          </>
        )}
      </div>
    </Disclosure>
  );
}

/** Mounts the 3-D view (three.js, WebGL context, server-side marching cubes) only once it is opened. */
function SurfacesToggle({ runId }: { runId: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2">
      <Button size="sm" variant="secondary" onClick={() => setOpen((value) => !value)}>
        {open ? "Hide" : "Show"} patient-derived 3-D surfaces of this mask (scan voxel frame)
      </Button>
      {open && (
        <Suspense fallback={<LoadingBlock label="Loading 3-D view" />}>
          <VolumeSurfaceView runId={runId} colors={STRUCTURE_RGBA} />
        </Suspense>
      )}
    </div>
  );
}

export function ResultView({ run, showBelow = false, setShowBelow = () => undefined, highlight = null, setHighlight = () => undefined }: { run: ResearchRun; showBelow?: boolean; setShowBelow?: (value: boolean) => void; highlight?: number | null; setHighlight?: (value: number | null) => void }) {
  const output = run.research_output;
  if (!output) return <div className="space-y-2"><Unavailable compact code={run.status} reason={run.error_message?.startsWith("MODEL_INPUT_PHOTOGRAPHED_FILM") ? "This run abstained because the upload is a suspected photographed film. No prediction, lesion mask or patient-space location was produced." : run.error_message ?? "The run recorded no model output."} /><details className="text-xs text-ink-3"><summary>Run #{run.id} · technical provenance</summary><p>{run.model_name} · {formatDate(run.completed_at ?? run.started_at, true)}</p><p>{run.error_message}</p></details></div>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="warning">Research only · not clinically validated</Badge>
        <StatusBadge status={run.latest_review?.review_status ?? "PENDING_HUMAN_REVIEW"} />
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
          {output.clinical_metadata && <p className="text-xs leading-5 text-ink-2">
            Recorded research attributes: age {output.clinical_metadata.values.age}, region {humanize(output.clinical_metadata.values.region)},
            gender {output.clinical_metadata.values.gender ? humanize(output.clinical_metadata.values.gender) : "not documented"}.
            {" "}{output.clinical_metadata.source}. These values were supplied explicitly and were not inferred from the photograph.
          </p>}
        </>
      )}
      {output.type === "multilabel_classification" && (
        <>
          <p className="text-sm text-ink">At or above threshold: {output.positive_labels.length ? output.positive_labels.map(humanize).join(", ") : "none"}.</p>
          <Table headers={["Label", "Probability", "Threshold", "Reading"]} dense>
            {output.labels.map((item) => (
              <tr key={item.label}>
                <td className="text-ink">{humanize(item.label)}</td>
                <td className="tabular text-ink-2">{formatNumber(item.probability, 3)}</td>
                <td className="tabular text-ink-3">{formatNumber(item.threshold, 3)}</td>
                <td>{item.at_or_above_threshold ? <Badge tone="warning">At or above</Badge> : <span className="text-[11px] text-ink-3">Below</span>}</td>
              </tr>
            ))}
          </Table>
          <p className="text-[11px] leading-4 text-ink-3">{output.probability_semantics} {output.threshold_semantics} No overlay: the model reads the whole slice and does not localise. {output.numeric_precision}.</p>
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
            ...(output.demographic_inputs ? [{ label: "Fused inputs", value: `age ${formatNumber(output.demographic_inputs.age_years, 0)} y, sex ${output.demographic_inputs.sex} (${output.demographic_inputs.sources.map(humanize).join(", ")})` }] : []),
          ]} />
          {output.demographic_inputs?.warnings.length ? <p className="text-[11px] leading-4 text-warning-text">{output.demographic_inputs.warnings.join("; ")}.</p> : null}
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
            <Disclosure summary="Held-out volume agreement of this model (its internal test set)">
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
          <SurfacesToggle key={run.id} runId={run.id} />
          <p className="text-[11px] leading-4 text-ink-3">{output.volume_semantics} Voxel spacing {output.voxel_spacing_mm.map((value) => formatNumber(value, 3)).join(" × ")} mm from the NIfTI header. Masks are drawn on the axial index plane of the current slice.</p>
        </>
      )}
      {output.type === "series_slice_multilabel" && (
        <>
          <p className="text-sm text-ink">
            {humanize(output.series_level.label)}: highest probability over {output.series_level.coverage} <span className="tabular font-semibold">{output.series_level.probability.toFixed(3)}</span> (slice {output.series_level.slice_index + 1}),{" "}
            {output.series_level.at_or_above_threshold ? "at or above" : "below"} its threshold {output.series_level.threshold.toFixed(3)}.
          </p>
          {!output.series_level.complete_coverage && <p className="text-xs text-warning-text">Partial: slices outside the model's training images were not analysed, so a finding on them cannot appear here.</p>}
          <p className="text-[11px] leading-4 text-ink-3">{output.series_level.rule}</p>
          <p className="text-xs text-ink-2">{output.slices_analysed} slices analysed, {output.slices_refused} outside the model's training images (not analysed); slices with a label at or above threshold: {output.slices_with_positive_labels.length ? output.slices_with_positive_labels.map((index) => index + 1).join(", ") : "none"}.</p>
          {output.label_maxima && output.label_maxima.length > 0 && (
            <Table headers={["Label", "Highest over the series", "Threshold", "Slice", "At or above threshold"]} dense>
              {output.label_maxima.map((item) => (
                <tr key={item.label}>
                  <td className="text-ink">{humanize(item.label)}</td>
                  <td className="tabular text-ink">{item.probability.toFixed(3)}</td>
                  <td className="tabular text-ink-3">{item.threshold.toFixed(3)}</td>
                  <td className="tabular text-ink-3">{item.slice_index + 1}</td>
                  <td>{item.at_or_above_threshold ? <StatusBadge status="REVIEW" label="Yes" /> : <span className="text-ink-3">No</span>}</td>
                </tr>
              ))}
            </Table>
          )}
          {output.slice_input && <p className="text-[11px] leading-4 text-ink-3">Model input: {output.slice_input}.</p>}
          {output.series_pipeline_external_evaluation && (
            <p className="text-[11px] leading-4 text-ink-2">
              This checkpoint, run through this same series pipeline, was evaluated externally on {publicText(output.series_pipeline_external_evaluation.dataset)}
              {output.series_pipeline_external_evaluation.scored_scans !== null && ` (${output.series_pipeline_external_evaluation.scored_scans} scans scored)`}
              {output.series_pipeline_external_evaluation.any_haemorrhage?.auroc != null && `: any-haemorrhage AUROC ${output.series_pipeline_external_evaluation.any_haemorrhage.auroc.toFixed(3)}`}
              {output.series_pipeline_external_evaluation.any_haemorrhage?.sensitivity != null && `, sensitivity ${(output.series_pipeline_external_evaluation.any_haemorrhage.sensitivity * 100).toFixed(1)}%`}
              {output.series_pipeline_external_evaluation.any_haemorrhage?.specificity != null && `, specificity ${(output.series_pipeline_external_evaluation.any_haemorrhage.specificity * 100).toFixed(1)}%`}
              {" "}at the same thresholds. A research measurement, not clinical validation; this result still needs review.
            </p>
          )}
          <div className="max-h-64 overflow-auto">
            <Table headers={["Slice", "Applicability", "At or above threshold"]} dense>
              {output.slices.map((item) => (
                <tr key={item.slice_index}>
                  <td className="tabular text-ink">{item.slice_index + 1}</td>
                  <td className="tabular text-ink-3">{formatNumber(item.applicability_score, 2)}{item.status !== "ANALYSED" && <span className="ml-1 text-warning-text">· not analysed</span>}</td>
                  <td className="text-ink-2">{item.status === "ANALYSED" ? (item.positive_labels?.length ? item.positive_labels.map(humanize).join(", ") : "none") : "—"}</td>
                </tr>
              ))}
            </Table>
          </div>
          <p className="text-[11px] leading-4 text-ink-3">{output.probability_semantics} Slices were windowed at level {output.window.center} / width {output.window.width} HU ({output.window.source}); applicability limit {formatNumber(output.applicability.limit, 2)} ({output.applicability.calibration}; {output.applicability.rule}). {output.numeric_precision}.</p>
        </>
      )}
      {output.type === "regression" && (
        <>
          <p className="text-sm text-ink">Estimated LVEF <span className="tabular font-semibold">{formatNumber(output.ef_percent, 1)}%</span>{output.band ? <span className="text-ink-2"> · {output.band}</span> : null}</p>
          <ClipStrip values={output.clip_ef_percent} starts={output.clip_starts} />
          <p className="text-[11px] leading-4 text-ink-3">{output.estimate_semantics} {output.clip_ef_percent.length} clips of {output.clip_frames} frames (every {output.frame_period}nd frame), starting at the frames shown. {output.numeric_precision}.</p>
        </>
      )}
      <Disclosure summary="Run provenance">
        <pre className="max-h-60 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-5 text-ink-2">{JSON.stringify(run.research_provenance, null, 2)}</pre>
      </Disclosure>
    </div>
  );
}

/** Per-clip estimates on a fixed 0-100 % scale with the mean marked; each bar names its clip on hover. */
function ClipStrip({ values, starts }: { values: number[]; starts: number[] }) {
  const height = 64;
  const gap = 2;
  const width = Math.max(120, values.length * 12);
  const bar = Math.max(3, (width - gap * (values.length - 1)) / Math.max(1, values.length));
  const mean = values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
  const y = (value: number) => height - (Math.min(100, Math.max(0, value)) / 100) * height;
  return (
    <figure className="space-y-1">
      <svg role="img" aria-label={`Ejection fraction estimate per clip, ${values.length} clips, mean ${formatNumber(mean, 1)}%`} viewBox={`0 0 ${width} ${height}`} className="h-16 w-full max-w-md" preserveAspectRatio="none">
        <line x1={0} x2={width} y1={y(50)} y2={y(50)} stroke="var(--mt-line)" strokeDasharray="3 3" strokeWidth={1} />
        {values.map((value, index) => (
          <rect key={index} x={index * (bar + gap)} y={y(value)} width={bar} height={height - y(value)} rx={2} fill="var(--mt-accent)">
            <title>{`Clip from frame ${starts[index] ?? "?"}: ${formatNumber(value, 1)}%`}</title>
          </rect>
        ))}
        <line x1={0} x2={width} y1={y(mean)} y2={y(mean)} stroke="var(--mt-ink)" strokeWidth={1.5} />
      </svg>
      <figcaption className="text-[11px] text-ink-3">Clip estimates (0-100 %); solid line: mean {formatNumber(mean, 1)}%; dashed line: 50 %.</figcaption>
    </figure>
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
    .map(([key, value]) => ({ label: key === "test_n" && model.task === "volumetric_semantic_segmentation" ? "Test volumes" : METRIC_LABELS[key] ?? humanize(key), value: key === "test_n" || key === "test_patients" ? String(value) : formatNumber(value as number, 3) }));
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="text-xs font-medium text-ink">Internal held-out evaluation (public dataset, same source distribution)</p>
      <div className="mt-2"><KeyValue columns={2} items={items} /></div>
      <p className="mt-2 text-[11px] leading-4 text-ink-3">Licence: {licenceLabel({ name: model.dataset_license })} (<Link to="/attribution" className="text-accent-text hover:underline">data sources and licences</Link>). Checkpoint SHA-256 <code>{model.checkpoint_sha256?.slice(0, 16)}…</code></p>
    </div>
  );
}

// Output types each upload kind can hold; a stored run of another kind is not offered for overlay.
const OUTPUT_TYPES: Record<ResearchInput, ReadonlySet<string>> = {
  image_2d: new Set(["classification", "multilabel_classification", "detection", "segmentation"]),
  volume_nifti: new Set(["volume_segmentation"]),
};

function legendFor(output: ResearchOutput, mode: LayerMode, highlight: number | null, layer: ReferenceAnnotation["layer"] = "GROUND_TRUTH", ofThisRun = false) {
  if (output.type === "detection") return [{ label: "Model boxes (dashed: below threshold)", tag: "MODEL_PREDICTION", rgba: LAYER_RGBA.prediction }];
  // "Removed/added by the reviewer" only describes a correction compared with the run it was made from.
  const correction = layer === "REVIEWER_CORRECTION" && ofThisRun;
  if (mode === "reference" && layer === "REVIEWER_CORRECTION") return [{ label: "Reviewer correction", tag: layer, rgba: LAYER_RGBA.reference }];
  if (mode === "reference") return [{ label: correction ? "Reviewer correction" : "Reference annotation", tag: layer, rgba: LAYER_RGBA.reference }];
  if (mode === "comparison") {
    return [
      { label: "Both", tag: "AGREEMENT", rgba: LAYER_RGBA.agreement },
      { label: correction ? "Removed by the reviewer" : "Model only", tag: "MODEL_PREDICTION", rgba: LAYER_RGBA.modelOnly },
      { label: correction ? "Added by the reviewer" : "Reference only", tag: layer, rgba: LAYER_RGBA.referenceOnly },
    ];
  }
  return [
    { label: "Model mask", tag: "MODEL_PREDICTION", rgba: LAYER_RGBA.prediction },
    ...(highlight !== null ? [{ label: "Highlighted segment", tag: "MODEL_PREDICTION", rgba: LAYER_RGBA.highlight }] : []),
  ];
}

/** TotalSegmentator on a CT NIfTI: a third-party model run through its own endpoint, stored like the volumetric runs. */
function CtOrganAction({ uploadId, onRun }: { uploadId: number; onRun: (run: ResearchRun) => void }) {
  const card = useAsync(() => api.getCtOrganModel(), []);
  const [attested, setAttested] = useState(false);
  const [fast, setFast] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const check = card.data?.local_external_check ?? null;

  async function run() {
    setBusy("Segmenting (this can take a minute)");
    setError(null);
    try {
      onRun(await api.runCtOrganSegmentation(uploadId, fast, (job) => setBusy(`${humanize(job.status)}${job.message ? ` · ${job.message}` : ""}`)));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Disclosure summary="CT organ segmentation (TotalSegmentator, third-party)">
      <div className="space-y-2 text-xs text-ink-2">
        {card.error && <ErrorBlock message={card.error} onRetry={card.reload} />}
        {card.data && !card.data.available && <Unavailable compact code={card.data.status} reason={card.data.reason ?? "TotalSegmentator is not installed on this server."} />}
        {card.data?.available && (
          <>
            <p className="leading-4">{card.data.publisher.name}: {card.data.publisher.version}, {card.data.publisher.licence}. Trained by its publisher on {card.data.publisher.training_data}; not trained by MedTwin. {card.data.publisher.citation}</p>
            {check ? (
              <p className="leading-4">Local check on {check.scans} {check.reference} scans ({check.mode}): lung Dice {formatNumber(check.dice_lungs.mean, 3)} (95% CI {formatNumber(check.dice_lungs.ci95[0], 3)}–{formatNumber(check.dice_lungs.ci95[1], 3)}). {check.note}</p>
            ) : <p className="leading-4">No local check on held-out scans has been recorded for this model yet.</p>}
            <Segmented label="Model resolution" size="sm" value={fast ? "fast" : "full"} onChange={(value) => setFast(value === "fast")} options={[
              { value: "fast", label: "Fast (3 mm)" }, ...(card.data.full_resolution ? [{ value: "full", label: "Full (1.5 mm)" }] : []),
            ]} />
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
              <span>I confirm this upload is a CT volume. The server refuses volumes whose voxel values are not Hounsfield units (for example MRI) or whose spacing is implausible.</span>
            </label>
            <Button variant="primary" icon={FlaskConical} disabled={!attested} loading={busy !== null} onClick={() => void run()}>{busy ?? "Segment CT structures"}</Button>
          </>
        )}
        {error && <ErrorBlock message={error} />}
      </div>
    </Disclosure>
  );
}

/** A run made before EXIF orientation handling used the stored grid, which differs from the displayed one
 * when the image is stored rotated or mirrored (orientation 2-8): its coordinates cannot be drawn. */
function unoriented(output: ResearchOutput, exifOrientation: number): boolean {
  return exifOrientation !== 1 && (output.type === "detection" || output.type === "segmentation") && output.exif_orientation_applied === undefined;
}

/** The DICOM frame a 2-D run read, when it read one. */
function AutomaticModelSelection({ uploadId, sourceType, types, frameIndex, onSelected }: {
  uploadId: number; sourceType: string; types: Array<[string, string]>; frameIndex?: number;
  onSelected: (modelId: string, source: string) => void;
}) {
  const [source, setSource] = useState("");
  const [task, setTask] = useState("auto");
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.selectUploadModel>> | null>(null);
  const [resultContext, setResultContext] = useState("");
  const selectionContext = JSON.stringify([sourceType || source, task, target, frameIndex]);
  const currentContext = useRef(selectionContext);
  useEffect(() => { currentContext.current = selectionContext; }, [selectionContext]);
  const [error, setError] = useState<string | null>(null);
  async function select() {
    setBusy(true); setError(null); setResult(null);
    try {
      const plan = await api.selectUploadModel(uploadId, { declared_input_type: sourceType || source || undefined,
        task, target: target.trim() || undefined, frame_index: frameIndex });
      if (currentContext.current !== selectionContext) return;
      setResultContext(selectionContext);
      setResult(plan);
      if (plan.status === "SELECTED" && plan.selected_model_id && plan.declared_input_type) onSelected(plan.selected_model_id, plan.declared_input_type);
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <Disclosure summary="Automatically match a research model to the task">
    <div className="space-y-3 text-xs text-ink-2">
      <p>Match the declared source and requested task against registered model contracts. Multiple matches require a more specific task or target. Selection still requires source confirmation and content checks before execution.</p>
      {!sourceType && <label className="block">Source input
        <SelectInput aria-label="Automatic model source" value={source} onChange={(event) => { setSource(event.target.value); setResult(null); }}>
          <option value="">Use digital metadata when available</option>
          {types.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </SelectInput>
      </label>}
      <label className="block">Requested task
        <SelectInput aria-label="Automatic model task" value={task} onChange={(event) => { setTask(event.target.value); setResult(null); }}>
          <option value="auto">Any supported task</option><option value="classification">Classification</option>
          <option value="detection">Locate with boxes</option><option value="segmentation">Segment structures</option>
          <option value="forecast">Forecast an outcome</option>
        </SelectInput>
      </label>
      <label className="block">Target class (optional; exact registered class)
        <TextInput aria-label="Automatic model target" value={target} onChange={(event) => { setTarget(event.target.value); setResult(null); }} />
      </label>
      <Button loading={busy} onClick={() => void select()}>Find compatible model</Button>
      {result && resultContext === selectionContext && <div role="status" aria-label="Model routing result"><StatusBadge status={result.status} /><p className="mt-2">{humanize(result.reason)}</p>
        {result.candidates.map((candidate) => <p key={candidate.model_id}>{candidate.display_name}</p>)}
        {result.notice && <p className="mt-2">{result.notice}</p>}
        {result.rejected.length > 0 && <p className="mt-2">{result.rejected.length} candidate(s) failed their research or input gates.</p>}
      </div>}
      {error && <ErrorBlock message={error} />}
    </div>
  </Disclosure>;
}

function runFrame(output: ResearchOutput | null | undefined): number | null {
  return output && "dicom_frame" in output && output.dicom_frame ? output.dicom_frame.frame_index : null;
}

export default function ResearchModelPanel({ uploadId, input, assessment, axialSlice = null, onOverlay, imageUrl = null, sliceImageUrl = null, exifOrientation = 1, dicomFrames = null, displayedFrame = null }: { uploadId: number; input: ResearchInput | null; assessment?: FilmAssessment; axialSlice?: number | null; onOverlay: (overlay: OverlayState | null) => void; imageUrl?: string | null; sliceImageUrl?: string | null; exifOrientation?: number;
  /** Frame count of a DICOM upload (null for other containers); multi-frame files run on the displayed frame. */
  dicomFrames?: number | null; displayedFrame?: number | null }) {
  const listing = useAsync(() => api.getResearchModels(), []);
  const evidenceVersion = useWorkspace((state) => state.evidenceVersion);
  const stored = useAsync(() => api.listResearchRuns(uploadId), [uploadId, evidenceVersion]);
  const [declaredInput, setDeclaredInput] = useState("");
  const [skinAge, setSkinAge] = useState("");
  const [skinRegion, setSkinRegion] = useState("");
  const [skinGender, setSkinGender] = useState<"" | "MALE" | "FEMALE">("");
  const filmBlocked = assessment?.inference_eligibility === "ABSTAIN_FILM_INPUT";
  // Only models whose upload contract matches this file; ECG models run from Multimodal, survival models never run on uploads.
  const runnable = (listing.data?.models ?? []).filter((model) => model.gate.allowed && (model.inference_input ?? "image_2d") === input && (input !== "image_2d" || model.supported_modalities.includes(declaredInput)));
  const storedRuns = useMemo(
    () => (stored.data?.runs ?? []).filter((item) => input !== null && (item.status === "ABSTAIN" || (item.research_output && OUTPUT_TYPES[input].has(item.research_output.type)))),
    [stored.data, input],
  );
  const [modelId, setModelId] = useState<string>("");
  const model = runnable.find((item) => item.model_id === modelId) ?? (runnable.length === 1 ? runnable[0] : null);
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [restored, setRestored] = useState(false);
  const [showBelow, setShowBelow] = useState(false);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [layerMode, setLayerMode] = useState<LayerMode>("prediction");
  const [opacity, setOpacity] = useState(0.8);
  const [referenceState, setReferenceState] = useState<ReferenceState | null>(null);
  const inputType = input === "image_2d" ? declaredInput : model?.supported_modalities[0] ?? "";
  useEffect(() => {
    setSkinAge("");
    setSkinRegion("");
    setSkinGender("");
    setAttested(false);
  }, [uploadId, model?.model_id]);

  // A stored run is shown again after a reload: the newest one, once per upload.
  useEffect(() => {
    if (restored || !stored.data) return;
    setRestored(true);
    if (run === null && storedRuns.length > 0) setRun(storedRuns[0]);
  }, [restored, stored.data, storedRuns, run]);

  useEffect(() => {
    setReferenceState(null);
    setLayerMode("prediction");
  }, [run?.id]);

  useEffect(() => {
    if (filmBlocked) { onOverlay(null); return; }
    const output = run?.research_output;
    if (output?.type === "volume_segmentation") {
      // Volume masks exist per axial index plane; other planes show the image without an overlay.
      onOverlay(axialSlice === null ? null : { sourceSize: [output.volume_shape_ijk[0], output.volume_shape_ijk[1]], layer: <VolumeSliceLayer output={output} slice={axialSlice} highlight={highlight} /> });
      return;
    }
    if (!output || (output.type !== "detection" && output.type !== "segmentation") || unoriented(output, exifOrientation)) {
      onOverlay(null);
      return;
    }
    // A run on one frame of a multi-frame DICOM is drawn on that frame only.
    const frame = runFrame(output);
    if (dicomFrames !== null && dicomFrames > 1 && frame !== null && frame !== (displayedFrame ?? 0)) {
      onOverlay(null);
      return;
    }
    onOverlay({ sourceSize: output.image_size, layer: <OverlayLayer output={output} showBelow={showBelow} highlight={highlight} mode={referenceState ? layerMode : "prediction"} reference={referenceState} opacity={opacity} /> });
  }, [run, showBelow, highlight, axialSlice, onOverlay, layerMode, referenceState, opacity, exifOrientation, filmBlocked, dicomFrames, displayedFrame]);

  async function refresh(runId: number) {
    // The single run (with its latest review), so a run outside the stored-run listing stays open.
    try {
      setRun(await api.getResearchRun(runId));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      stored.reload();
    }
  }

  async function execute() {
    if (!model || !attested || filmBlocked) return;
    setBusy("Running");
    setError(null);
    try {
      const frameIndex = dicomFrames !== null && dicomFrames > 1 ? displayedFrame ?? 0 : undefined;
      const clinicalFeatures = model.requires_clinical_features
        ? { age: Number(skinAge), region: skinRegion, ...(skinGender ? { gender: skinGender } : {}) } : undefined;
      if (model.requires_clinical_features && (!skinAge.trim() || !Number.isFinite(Number(skinAge)) || !skinRegion)) {
        throw new Error("Enter the documented age and lesion region before running the image and attributes model.");
      }
      const result = await api.runResearchModel(uploadId, model.model_id, inputType, (job) => setBusy(`${humanize(job.status)}${job.message ? ` · ${job.message}` : ""}`), { frameIndex, clinicalFeatures });
      setRun(result);
      setHighlight(null);
      stored.reload();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
      stored.reload();
    }
  }

  if (listing.loading && !filmBlocked) return <LoadingBlock label="Reading model registry" />;
  if (listing.error && !filmBlocked) return <ErrorBlock message={listing.error} onRetry={listing.reload} />;
  if (!input) return <Unavailable compact code="INPUT_NOT_SUPPORTED" reason="The registered research models accept 2-D PNG/JPEG/BMP images or DICOM frames, and NIfTI, NRRD or MetaImage volumes; whole-slide images are not supported by them (no pathology model is registered)." />;
  const ctAction = input === "volume_nifti" ? (
    <CtOrganAction uploadId={uploadId} onRun={(result) => { setRun(result); setHighlight(null); stored.reload(); }} />
  ) : null;
  // Stored and current runs show whether or not a registered model can run now (a CT run needs none).
  const results = (
    <RunResults uploadId={uploadId} storedRuns={storedRuns} run={run} setRun={setRun} highlight={highlight} setHighlight={setHighlight}
      showBelow={showBelow} setShowBelow={setShowBelow} referenceState={referenceState} setReferenceState={setReferenceState}
      layerMode={layerMode} setLayerMode={setLayerMode} opacity={opacity} setOpacity={setOpacity} imageUrl={imageUrl}
      exifOrientation={exifOrientation} refresh={refresh} models={listing.data?.models ?? []} axialSlice={axialSlice} sliceImageUrl={sliceImageUrl} />
  );
  if (filmBlocked) return <div className="space-y-3">
    <StatusBadge status="ABSTAIN" label="Film input — viewing and report synthesis available" />
    <p className="text-sm text-ink-2">This upload is a suspected photographed CT film or montage. Native slice models require a digital slice from their supported input distribution. Selecting a crop does not make it a native slice.</p>
    <p className="text-xs text-ink-2">Inspect the candidate panels on the left, review the report, or add a de-identified native image to run an applicable model.</p>
    <div className="flex gap-3 text-xs text-accent-text"><Link to="/documents">Review report</Link><Link to="/multimodal">Open evidence synthesis</Link><Link to="/upload">Add native image</Link></div>
    {results}
  </div>;
  const inputSelector = input === "image_2d" ? <label className="block text-xs text-ink-2">Image type (confirm from the source)
    <SelectInput aria-label="Research image type" value={declaredInput} onChange={(event) => { setDeclaredInput(event.target.value); setModelId(""); setAttested(false); }}>
      <option value="">Select image type</option>
      {Object.entries(listing.data?.input_types ?? {}).filter(([key]) => (listing.data?.models ?? []).some((item) => (item.inference_input ?? "image_2d") === "image_2d" && item.supported_modalities.includes(key))).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </SelectInput>
  </label> : null;
  const automaticSelector = <AutomaticModelSelection key={uploadId} uploadId={uploadId} sourceType={declaredInput}
    frameIndex={dicomFrames !== null && dicomFrames > 1 ? displayedFrame ?? 0 : undefined}
    types={Object.entries(listing.data?.input_types ?? {}).filter(([key]) => (listing.data?.models ?? []).some((item) => (item.inference_input ?? "image_2d") === input && item.supported_modalities.includes(key)))}
    onSelected={(id, source) => { setDeclaredInput(source); setModelId(id); setAttested(false); setRun(null); }} />;
  const modelSelector = runnable.length > 0 ? <label className="block text-xs text-ink-2">Model (manual selection or automatic match)
    <SelectInput aria-label="Research model" value={model?.model_id ?? ""} onChange={(event) => { setModelId(event.target.value); setAttested(false); setRun(null); }}>
      <option value="">Choose a specific research task/model</option>
      {runnable.map((item) => <option key={item.model_id} value={item.model_id}>{item.display_name}</option>)}
    </SelectInput>
  </label> : null;
  if (!model) {
    return (
      <div className="space-y-3">
        {ctAction}
        {inputSelector}
        {automaticSelector}
        {modelSelector}
        <Unavailable compact code={runnable.length > 1 ? "MODEL_SELECTION_REQUIRED" : input === "image_2d" && !declaredInput ? "INPUT_REQUIRED" : "NO_RUNNABLE_RESEARCH_MODEL"} reason={runnable.length > 1 ? "Several distinct models support this input. Match a specific task automatically or select a model explicitly." : input === "image_2d" && !declaredInput ? "Choose the source image type to see compatible research models." : "No registered research model for this input passes the checkpoint, licence and evaluation gates."} />
        {results}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-[11px] leading-4 text-ink-2">{listing.data?.notice}</p>
      {ctAction}
      {inputSelector}
      {automaticSelector}
      {modelSelector}
      {model.requires_clinical_features && <div className="rounded-lg border border-line p-3 text-xs text-ink-2">
        <p className="mb-2">Documented attributes for this lesion. Values are recorded with the research output and need human review.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <label>Age in years<TextInput aria-label="Skin research age" type="number" min={model.clinical_metadata_contract?.age_range[0] ?? 0}
            max={model.clinical_metadata_contract?.age_range[1] ?? 120} value={skinAge} onChange={(event) => { setSkinAge(event.target.value); setAttested(false); }} /></label>
          <label>Lesion region<SelectInput aria-label="Skin research region" value={skinRegion} onChange={(event) => { setSkinRegion(event.target.value); setAttested(false); }}>
            <option value="">Select documented region</option>{model.clinical_metadata_contract?.categories.region.map((region) => <option key={region} value={region}>{humanize(region)}</option>)}
          </SelectInput></label>
          <label>Recorded gender (optional)<SelectInput aria-label="Skin research gender" value={skinGender} onChange={(event) => { setSkinGender(event.target.value as "" | "MALE" | "FEMALE"); setAttested(false); }}>
            <option value="">Not documented</option><option value="MALE">Male</option><option value="FEMALE">Female</option>
          </SelectInput></label>
        </div>
        <p className="mt-2">Age must be within the model's recorded training range. Missing gender uses the training-defined missing-value category. No attribute is inferred from the photograph.</p>
      </div>}
      <Disclosure summary="Model evaluation and licence (public dataset)"><Evaluation model={model} /></Disclosure>
      <label className="flex items-start gap-2 text-xs text-ink-2">
        <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
        <span>I confirm this upload is a {listing.data?.input_types[inputType] ?? humanize(inputType)}, the input type this model was trained on. {input === "volume_nifti" ? "The server checks channel count, voxel spacing, axis layout and (for brain models) the share of non-zero voxels against the development data; it cannot verify the MRI sequences, their order, the view or the cardiac phase." : "The server refuses images that read as printed documents or lie outside this model's training distribution (applicability gate); it cannot confirm the modality, and it also refuses some genuine images of the right kind."}</span>
      </label>
      {dicomFrames !== null && input === "image_2d" && (
        <p className="text-[11px] leading-4 text-ink-2">
          DICOM {dicomFrames > 1 ? `frame ${(displayedFrame ?? 0) + 1} of ${dicomFrames} (the frame on display)` : "frame"} is converted to 8 bits with the model's declared DICOM window if it has one, otherwise the file's own window; the conversion is recorded with the run and the converted frame must still pass the applicability gate.
        </p>
      )}
      <Button variant="primary" icon={FlaskConical} disabled={!attested} loading={busy !== null} onClick={execute}>{busy ?? "Run research model"}</Button>
      {error && <ErrorBlock message={error} />}
      {results}
    </div>
  );
}

function RunResults({ uploadId, storedRuns, run, setRun, highlight, setHighlight, showBelow, setShowBelow, referenceState, setReferenceState,
  layerMode, setLayerMode, opacity, setOpacity, imageUrl, exifOrientation, refresh, models, axialSlice, sliceImageUrl }: {
  axialSlice: number | null; sliceImageUrl: string | null;
  uploadId: number; storedRuns: ResearchRun[]; run: ResearchRun | null; setRun: (run: ResearchRun | null) => void;
  highlight: number | null; setHighlight: (value: number | null) => void; showBelow: boolean; setShowBelow: (value: boolean) => void;
  referenceState: ReferenceState | null; setReferenceState: (state: ReferenceState | null) => void; layerMode: LayerMode; setLayerMode: (mode: LayerMode) => void;
  opacity: number; setOpacity: (value: number) => void; imageUrl: string | null; exifOrientation: number; refresh: (runId: number) => Promise<void>;
  models: ResearchModel[];
}) {
  return (
    <>
      {storedRuns.length > 0 && (
        <label className="block text-xs text-ink-2">
          Stored runs on this upload
          <SelectInput aria-label="Stored research run" value={run?.id ?? ""} onChange={(event) => { setRun(storedRuns.find((item) => item.id === Number(event.target.value)) ?? null); setHighlight(null); }}>
            {run && !storedRuns.some((item) => item.id === run.id) && <option value={run.id}>Run #{run.id}</option>}
            {storedRuns.map((item) => (
              <option key={item.id} value={item.id}>
                #{item.id} · {String(item.research_provenance.model_display_name ?? item.model_name)} · {formatDate(item.completed_at ?? item.started_at, true)} · {item.status === "ABSTAIN" ? "Abstained — no prediction" : item.latest_review ? humanize(item.latest_review.review_status) : "Pending review"}
              </option>
            ))}
          </SelectInput>
        </label>
      )}
      {run?.research_output && unoriented(run.research_output, exifOrientation) && (
        <Unavailable compact code="RUN_ON_UNORIENTED_GRID" reason="This run predates EXIF orientation handling and this image is stored rotated or mirrored, so its coordinates do not match the displayed image. Run the model again." />
      )}
      {run && <ResultView run={run} showBelow={showBelow} setShowBelow={setShowBelow} highlight={highlight} setHighlight={setHighlight} />}
      {run?.research_output && (run.research_output.type === "segmentation" || run.research_output.type === "detection") && (
        <div className="space-y-2">
          {run.research_output.type === "segmentation" && referenceState && (
            <Segmented label="Overlay layer" size="sm" value={layerMode} onChange={setLayerMode} options={[
              { value: "prediction", label: "Model" }, { value: "reference", label: "Reference" }, { value: "comparison", label: "Agreement" },
            ]} />
          )}
          {run.research_output.type === "segmentation" && (
            <label className="flex items-center gap-2 text-[11px] text-ink-2">
              Overlay opacity
              <input type="range" min={0} max={100} value={Math.round(opacity * 100)} onChange={(event) => setOpacity(Number(event.target.value) / 100)} aria-label="Overlay opacity" className="w-32 accent-[var(--mt-accent)]" />
              <span className="tabular">{Math.round(opacity * 100)}%</span>
              <span className="text-ink-3">(0% shows the original image)</span>
            </label>
          )}
          <Legend items={legendFor(run.research_output, referenceState ? layerMode : "prediction", highlight, referenceState?.reference.layer, referenceState?.comparison.correction_of_this_run ?? false)} />
        </div>
      )}
      {run?.finding_id && <RunReview run={run} onReviewed={() => void refresh(run.id)} />}
      {run?.research_output?.type === "segmentation" && (
        <ReferencePanel key={run.id} uploadId={uploadId} run={run} output={run.research_output} imageUrl={imageUrl} onChange={setReferenceState}
          classNames={models.find((item) => item.model_id === run.model_name)?.supported_classes ?? []} />
      )}
      {run?.research_output?.type === "detection" && (
        <BoxReferencePanel key={`boxes-${run.id}`} uploadId={uploadId} run={run} output={run.research_output} imageUrl={imageUrl} />
      )}
      {run?.research_output?.type === "volume_segmentation" && (
        <VolumeCorrectionPanel key={`volume-${run.id}`} run={run} output={run.research_output} sliceIndex={axialSlice} sliceImageUrl={sliceImageUrl} />
      )}
      {run?.research_output && storedRuns.some((item) => item.id !== run.id && item.research_output?.type === run.research_output?.type) && (
        <RunAgreementPanel key={`agreement-${run.id}`} run={run} candidates={storedRuns.filter((item) => item.id !== run.id && item.research_output?.type === run.research_output?.type)} imageUrl={imageUrl} />
      )}
    </>
  );
}
