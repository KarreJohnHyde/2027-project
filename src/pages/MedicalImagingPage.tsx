import { useEffect, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import ResearchModelPanel, { type OverlayState, type ResearchInput } from "../components/ResearchModelPanel";
import { Badge, Button, Card, Disclosure, EmptyState, ErrorBlock, KeyValue, LoadingBlock, PageHeader, Segmented, SelectInput, StatusBadge, Table, TextInput } from "../components/ui";
import { api, type ImagingMetadata, type RenderInfo } from "../services/api";
import { formatDate, formatNumber, humanize } from "../lib/format";
import { Link, useLocation } from "../lib/router";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

const CT_PRESETS = [
  { id: "soft", label: "Soft tissue", center: 40, width: 400 },
  { id: "lung", label: "Lung", center: -600, width: 1500 },
  { id: "bone", label: "Bone", center: 300, width: 1500 },
  { id: "brain", label: "Brain", center: 40, width: 80 },
];

function PanZoomImage({ src, alt, overlay }: { src: string; alt: string; overlay?: OverlayState | null }) {
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  function onWheel(event: WheelEvent<HTMLDivElement>) {
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    setView((current) => ({ ...current, scale: Math.min(16, Math.max(0.25, current.scale * factor)) }));
  }
  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    drag.current = { x: event.clientX - view.x, y: event.clientY - view.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (drag.current) setView((current) => ({ ...current, x: event.clientX - drag.current!.x, y: event.clientY - drag.current!.y }));
  }
  return (
    <div className="relative h-[58vh] min-h-80 overflow-hidden rounded-lg bg-black" onWheel={onWheel} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => (drag.current = null)} role="img" aria-label={alt}>
      {/* Image and overlay share one transformed box; the SVG viewBox is the source pixel grid. */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}>
        <div className="relative max-h-full max-w-full">
          <img src={src} alt={alt} draggable={false} className="block max-h-[max(58vh,20rem)] max-w-full select-none [image-rendering:pixelated]" />
          {overlay && (
            <svg aria-label="Research model overlay" viewBox={`0 0 ${overlay.sourceSize[0]} ${overlay.sourceSize[1]}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
              {overlay.layer}
            </svg>
          )}
        </div>
      </div>
      <div className="absolute bottom-2 left-2 flex items-center gap-2 rounded-md bg-black/65 px-2 py-1 text-[11px] text-white">
        <span className="tabular">{Math.round(view.scale * 100)}%</span>
        <button type="button" aria-label="Reset zoom" onClick={() => setView({ scale: 1, x: 0, y: 0 })}><RotateCcw size={12} /></button>
      </div>
    </div>
  );
}

function Viewer({ uploadId }: { uploadId: number }) {
  const metadata = useAsync(() => api.getImagingMetadata(uploadId), [uploadId]);
  const raster = metadata.data?.container === "PNG" || metadata.data?.container === "JPEG" || metadata.data?.container === "BMP";
  const [axis, setAxis] = useState<"axial" | "coronal" | "sagittal">("axial");
  const [index, setIndex] = useState<number | null>(null);
  const [windowing, setWindowing] = useState<{ center: number; width: number } | null>(null);
  const [image, setImage] = useState<{ url: string; info: RenderInfo | null } | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [overlay, setOverlay] = useState<OverlayState | null>(null);

  useEffect(() => {
    if (!metadata.data) return;
    let cancelled = false;
    let created: string | null = null;
    const request = raster
      ? api.getUploadObjectUrl(uploadId).then((url) => ({ url, info: null }))
      : api.renderImagingSlice(uploadId, { axis, index: index ?? undefined, ...(windowing ?? {}) });
    request.then(
      (result) => {
        created = result.url;
        if (cancelled) URL.revokeObjectURL(result.url);
        else {
          setImage(result);
          setRenderError(null);
        }
      },
      (error: unknown) => !cancelled && setRenderError(error instanceof Error ? error.message : String(error)),
    );
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [metadata.data, raster, uploadId, axis, index, windowing]);

  if (metadata.loading || !metadata.data) return metadata.error ? <ErrorBlock message={metadata.error} onRetry={metadata.reload} /> : <LoadingBlock label="Reading image metadata" />;
  const data: ImagingMetadata = metadata.data;
  const info = image?.info ?? null;
  const volume = data.container === "NIFTI" || data.container === "NRRD" || data.container === "METAIMAGE";
  const researchInput: ResearchInput | null = raster ? "image_2d" : data.container === "NIFTI" ? "volume_nifti" : null;
  // Volume masks are per axial index plane, so the overlay follows the displayed axial slice only.
  const axialSlice = data.container === "NIFTI" && axis === "axial" && info ? info.slice_index : null;
  const hounsfield = info?.rescale?.units === "HU";
  const sliceCount = info?.slice_count ?? data.slices ?? 1;

  return (
    <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
      <Card title={data.filename} eyebrow={`${data.container}${data.modality_tag ? ` · ${data.modality_tag}` : ""}`} actions={<StatusBadge status={data.inference.status} />}>
        {data.deidentification_warnings.length > 0 && (
          <div role="alert" className="mb-3 flex items-start gap-2 rounded-lg border border-[color-mix(in_srgb,var(--mt-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--mt-warning)_10%,transparent)] p-3 text-sm text-warning-text">
            <AlertTriangle aria-hidden size={16} className="mt-0.5 shrink-0" />
            <span>Possible residual identifiers despite the de-identification attestation: {data.deidentification_warnings.join("; ")}. Values are never displayed; review and re-export the file.</span>
          </div>
        )}
        {renderError ? <ErrorBlock message={renderError} /> : image ? <PanZoomImage src={image.url} alt={`${data.filename} ${info ? `slice ${info.slice_index + 1}` : ""}`} overlay={raster || axialSlice !== null ? overlay : null} /> : <LoadingBlock label="Rendering" />}
        {!raster && (
          <div className="mt-3 flex flex-wrap items-end gap-3">
            {volume && <Segmented label="Plane" value={axis} onChange={(next) => { setAxis(next); setIndex(null); }} options={[{ value: "axial", label: "Axial idx" }, { value: "coronal", label: "Coronal idx" }, { value: "sagittal", label: "Sagittal idx" }]} size="sm" />}
            {sliceCount > 1 && (
              <label className="flex items-center gap-2 text-xs text-ink-2">
                Slice
                <input type="range" min={0} max={sliceCount - 1} value={info?.slice_index ?? 0} onChange={(event) => setIndex(Number(event.target.value))} className="w-40 accent-[var(--mt-accent)]" aria-label="Slice index" />
                <span className="tabular">{(info?.slice_index ?? 0) + 1}/{sliceCount}</span>
              </label>
            )}
            {hounsfield && (
              <div className="flex flex-wrap gap-1">
                {CT_PRESETS.map((preset) => <Button key={preset.id} size="sm" variant={windowing?.center === preset.center && windowing.width === preset.width ? "primary" : "secondary"} onClick={() => setWindowing({ center: preset.center, width: preset.width })}>{preset.label}</Button>)}
                <Button size="sm" variant={windowing ? "secondary" : "primary"} onClick={() => setWindowing(null)}>Auto</Button>
              </div>
            )}
            <form className="flex items-end gap-1.5" onSubmit={(event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              const center = Number(form.get("center"));
              const width = Number(form.get("width"));
              if (Number.isFinite(center) && width > 0) setWindowing({ center, width });
            }}>
              <label className="text-[11px] text-ink-3">Level<TextInput name="center" defaultValue={windowing?.center ?? ""} className="h-8 w-20 text-xs" /></label>
              <label className="text-[11px] text-ink-3">Width<TextInput name="width" defaultValue={windowing?.width ?? ""} className="h-8 w-20 text-xs" /></label>
              <Button size="sm" type="submit">Apply</Button>
            </form>
          </div>
        )}
        <p className="mt-3 text-[11px] leading-4 text-ink-3">Clinical inference: {data.inference.reason}</p>
      </Card>
      <div className="space-y-4">
        <Card title="Research models" eyebrow="Research only · overlay in source pixels">
          <ResearchModelPanel uploadId={uploadId} input={researchInput} axialSlice={axialSlice} onOverlay={setOverlay} />
        </Card>
        <Card title="Spatial metadata">
          <KeyValue items={[
            { label: "Dimensions", value: data.dimensions.filter((value) => value !== null).join(" × ") },
            { label: "Slices / frames", value: String(data.slices) },
            { label: "Spacing (mm)", value: data.spacing_mm ? data.spacing_mm.map((value) => formatNumber(value, 4)).join(" × ") : "Not available" },
            { label: "Spatial frame", value: humanize(data.spatial_metadata) },
            ...(data.orientation ? [{ label: "Orientation (axcodes)", value: data.orientation }] : []),
            { label: "Body part (DICOM)", value: data.body_part ?? "Not recorded" },
            { label: "Associated systems", value: (data.body_part_systems ?? []).length ? (data.body_part_systems ?? []).map(humanize).join(", ") : "None (no anatomical metadata)" },
            { label: "SHA-256", value: data.sha256, mono: true },
          ]} />
        </Card>
        {info && (
          <Card title="Display mapping">
            <KeyValue columns={1} items={[
              { label: "Window", value: `${formatNumber(info.window.low, 1)} to ${formatNumber(info.window.high, 1)} (${humanize(info.window.source)})` },
              ...(info.rescale ? [{ label: "Rescale", value: `slope ${info.rescale.slope}, intercept ${info.rescale.intercept} → ${humanize(info.rescale.units)}` }] : []),
              { label: "Display ↔ source", value: info.display_to_source },
              ...(info.plane_definition ? [{ label: "Plane", value: info.plane_definition }] : []),
            ]} />
          </Card>
        )}
        {data.technical_tags && (
          <Disclosure summary="Technical DICOM elements (identifying elements excluded)">
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-5 text-ink-2">{JSON.stringify(data.technical_tags, null, 2)}</pre>
          </Disclosure>
        )}
      </div>
    </div>
  );
}

function ModalitySupport() {
  const registry = useAsync(() => api.getModalities(), []);
  if (!registry.data) return registry.error ? <ErrorBlock message={registry.error} onRetry={registry.reload} /> : <LoadingBlock />;
  return (
    <Card title="Modality support" eyebrow={registry.data.notice} padded={false}>
      <Table headers={["Modality", "File formats", "File support", "Preprocessing", "AI model", "Validated tasks", "Unsupported tasks"]} dense>
        {registry.data.modalities.map((entry) => (
          <tr key={entry.id}>
            <td><span className="font-medium text-ink">{entry.label}</span><span className="block text-[11px] text-ink-3">{entry.group}{entry.dicom_modality_codes.length ? ` · ${entry.dicom_modality_codes.join("/")}` : ""}</span></td>
            <td className="max-w-[12rem]"><div className="flex flex-wrap gap-1">{entry.supported_file_formats.map((format) => <Badge key={format.format} tone={format.available && format.upload_accepted ? "good" : "unavailable"} title={format.note}>{humanize(format.format)}</Badge>)}</div></td>
            <td><StatusBadge status={entry.file_support_status} /></td>
            <td className="max-w-[14rem] text-xs text-ink-2">{entry.supported_preprocessing.join("; ") || "—"}</td>
            <td className="max-w-[12rem] text-xs text-ink-2">{entry.available_ai_models.length ? entry.available_ai_models.map((model) => `${model.display_name} (${humanize(model.status)}${model.research_inference ? "; runnable for research only" : ""})`).join("; ") : "None registered"}</td>
            <td className="text-xs text-ink-2">{entry.validated_tasks.length ? entry.validated_tasks.join(", ") : <StatusBadge status="NOT_VALIDATED" label="None" />}</td>
            <td className="max-w-[14rem] text-xs text-ink-2">{entry.unsupported_tasks.map((task) => task.task).join(", ")}{entry.notes.map((note) => <span key={note} className="mt-0.5 block text-[11px] text-ink-3">{note}</span>)}</td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

export default function MedicalImagingPage() {
  const { search } = useLocation();
  const selected = useSelectedCase();
  const uploads = useWorkspace((state) => state.evidence.uploads);
  const images = uploads.filter((upload) => upload.modality === "IMAGE");
  const requested = Number(search.get("upload")) || null;
  // The case and its uploads load after the first render (e.g. on a deep link), so the
  // defaults are derived until the user makes an explicit choice.
  const [chosenTab, setTab] = useState<"viewer" | "support" | null>(null);
  const tab = chosenTab ?? (selected || requested ? "viewer" : "support");
  const [uploadId, setUploadId] = useState<number | null>(null);
  const active = images.find((upload) => upload.id === (uploadId ?? requested)) ?? images[0] ?? null;
  const exams = new Map(selected?.examinations.map((exam) => [exam.id, exam]) ?? []);
  return (
    <>
      <PageHeader
        eyebrow="Medical Imaging"
        title="Imaging viewer and modality coverage"
        description="CT, MRI, X-ray, ultrasound, PET, angiography, endoscopy and other containers are read and displayed with their spatial metadata. No clinically validated model is configured. Research-only models trained on public datasets can be run on PNG/JPEG/BMP uploads and on single-frame NIfTI cardiac MRI volumes; their outputs are labelled as research and stay pending review."
        actions={<Segmented label="Imaging view" value={tab} onChange={setTab} options={[{ value: "viewer", label: "Viewer" }, { value: "support", label: "Modality support" }]} />}
      />
      {tab === "support" ? <ModalitySupport /> : !selected ? (
        <EmptyState title="Select a case" detail="The viewer shows imaging uploaded to the selected case." />
      ) : images.length === 0 ? (
        <EmptyState title="No imaging uploads" detail="Upload DICOM (Part 10), NIfTI, NRRD, MetaImage, PNG, JPEG or BMP files to view them here." action={<Link to="/upload" className="text-sm text-accent-text hover:underline">Open the upload center</Link>} />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="w-80"><SelectInput aria-label="Imaging upload" value={active?.id ?? ""} onChange={(event) => setUploadId(Number(event.target.value))}>{images.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename}</option>)}</SelectInput></div>
            {active?.examination_id && <span className="text-xs text-ink-3">Examination {formatDate(exams.get(active.examination_id)?.exam_date)}</span>}
          </div>
          {active && <Viewer key={active.id} uploadId={active.id} />}
        </>
      )}
    </>
  );
}
