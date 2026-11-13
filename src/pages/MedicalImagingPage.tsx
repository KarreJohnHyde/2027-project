import { useEffect, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import ResearchModelPanel, { ResultView, VolumeSliceLayer, type OverlayState, type ResearchInput } from "../components/ResearchModelPanel";
import ChestRadiographPanel from "../components/ChestRadiographPanel";
import VideoFramePanel from "../components/VideoFramePanel";
import EchoEfPanel from "../components/EchoEfPanel";
import WsiPanel from "../components/WsiPanel";
import FilmPanelPreview from "../components/FilmPanelPreview";
import MultimodelPanel from "../components/MultimodelPanel";
import { Badge, Button, Card, Disclosure, EmptyState, ErrorBlock, KeyValue, LoadingBlock, PageHeader, Segmented, SelectInput, StatusBadge, Table, TextInput } from "../components/ui";
import { api, type DicomSeriesReport, type ImagingMetadata, type RenderInfo, type ResearchRun, type SeriesRenderInfo, type UploadedFile } from "../services/api";
import { errorMessage, formatDate, formatNumber, humanize } from "../lib/format";
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
    // Capturing the pointer for a drag would retarget the click away from the viewer's own buttons.
    if (event.target instanceof Element && event.target.closest("button")) return;
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

function Viewer({ upload }: { upload: UploadedFile }) {
  const uploadId = upload.id;
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
  const dicom = data.container === "DICOM";
  // A DICOM frame runs through the 2-D models (converted server-side); NRRD and MetaImage volumes through the volume models.
  const researchInput: ResearchInput | null = raster || dicom ? "image_2d" : volume ? "volume_nifti" : null;
  // Volume masks are per axial index plane, so the overlay follows the displayed axial slice only.
  const axialSlice = volume && axis === "axial" && info ? info.slice_index : null;
  const hounsfield = info?.rescale?.units === "HU";
  const sliceCount = info?.slice_count ?? data.slices ?? 1;
  const film = data.input_assessment?.inference_eligibility === "ABSTAIN_FILM_INPUT";

  return (
    <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
      <Card title={data.filename} eyebrow={`${data.container}${data.modality_tag ? ` · ${data.modality_tag}` : ""}`} actions={<StatusBadge status={data.inference.status} />}>
        {data.deidentification_warnings.length > 0 && (
          <div role="alert" className="mb-3 flex items-start gap-2 rounded-lg border border-[color-mix(in_srgb,var(--mt-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--mt-warning)_10%,transparent)] p-3 text-sm text-warning-text">
            <AlertTriangle aria-hidden size={16} className="mt-0.5 shrink-0" />
            <span>Possible residual identifiers despite the de-identification attestation: {data.deidentification_warnings.join("; ")}. Values are never displayed; review and re-export the file.</span>
          </div>
        )}
        {film && data.input_assessment && <FilmPanelPreview key={`film-${uploadId}`} uploadId={uploadId} assessment={data.input_assessment} />}
        {film ? <Disclosure summary="Original film montage — source pixels"><p className="mb-2 text-xs text-ink-3">Candidate panels are viewing crops. Original image, labels and source marks are preserved.</p>{renderError ? <ErrorBlock message={renderError} /> : image ? <PanZoomImage src={image.url} alt={data.filename} /> : <LoadingBlock label="Rendering" />}</Disclosure> : renderError ? <ErrorBlock message={renderError} /> : image ? <PanZoomImage src={image.url} alt={`${data.filename} ${info ? `slice ${info.slice_index + 1}` : ""}`} overlay={raster || dicom || axialSlice !== null ? overlay : null} /> : <LoadingBlock label="Rendering" />}
        {data.container === "WSI" && data.wsi && <div className="mt-4"><WsiPanel uploadId={uploadId} slide={data.wsi} /></div>}
        {!raster && data.container !== "WSI" && (
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
        {!film && data.input_assessment && <FilmPanelPreview key={`film-${uploadId}`} uploadId={uploadId} assessment={data.input_assessment} />}
        <p className="mt-3 text-xs leading-5 text-ink-2">{data.inference.reason}</p>
      </Card>
      <div className="space-y-4">
        <Card title="Research models" eyebrow="Research only · overlay in source pixels">
          {/* Sibling keys must differ; each panel still resets when the upload changes. */}
          <ResearchModelPanel key={`research-${uploadId}`} uploadId={uploadId} input={researchInput} assessment={data.input_assessment} axialSlice={axialSlice} onOverlay={setOverlay} imageUrl={raster || dicom ? image?.url ?? null : null} sliceImageUrl={axialSlice !== null ? image?.url ?? null : null} exifOrientation={data.exif_orientation ?? 1}
            dicomFrames={dicom ? sliceCount : null} displayedFrame={dicom ? info?.slice_index ?? 0 : null} />
          {(raster || (dicom && sliceCount === 1)) && <MultimodelPanel key={`multimodel-${uploadId}`} uploadId={uploadId} assessment={data.input_assessment} />}
        </Card>
        <Card title="Spatial metadata">
          <KeyValue items={[
            { label: raster ? "Image dimensions (pixels)" : "Dimensions", value: data.dimensions.filter((value) => value !== null).join(" × ") },
            { label: raster ? "Raster frames (not CT slices)" : "Slices / frames", value: String(data.slices) },
            { label: "Spacing (mm)", value: data.spacing_mm ? data.spacing_mm.map((value) => formatNumber(value, 4)).join(" × ") : raster ? "Uncalibrated raster — millimetres cannot be recovered" : "Not available" },
            { label: "Spatial frame", value: raster ? "Source pixels only; no patient coordinates" : humanize(data.spatial_metadata) },
            ...(data.orientation ? [{ label: "Orientation (axcodes)", value: data.orientation }] : []),
            ...(!raster ? [{ label: "Body part (DICOM)", value: data.body_part ?? "Not recorded" }, { label: "Associated systems", value: (data.body_part_systems ?? []).length ? (data.body_part_systems ?? []).map(humanize).join(", ") : "None (no anatomical metadata)" }] : []),
            { label: "SHA-256", value: data.sha256, mono: true },
          ]} />
        </Card>
        {/* A whole-slide thumbnail has no intensity window; its pyramid and resolution are in the slide panel. */}
        {info && info.window && (
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
      {raster && !film && <div className="xl:col-span-2"><ChestRadiographPanel key={`cxr-${upload.id}`} upload={upload} /></div>}
    </div>
  );
}

/** A multi-file DICOM series: assembled by geometry, displayed plane by plane, optionally segmented. */
function SeriesViewer({ caseId, uploads }: { caseId: number; uploads: UploadedFile[] }) {
  const [chosen, setChosen] = useState<number[]>(() => uploads.map((upload) => upload.id));
  const [report, setReport] = useState<DicomSeriesReport | null>(null);
  const [axis, setAxis] = useState<"axial" | "coronal" | "sagittal">("axial");
  const [index, setIndex] = useState<number | null>(null);
  const [windowing, setWindowing] = useState<{ center: number; width: number } | null>(null);
  const [image, setImage] = useState<{ url: string; info: SeriesRenderInfo } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attested, setAttested] = useState(false);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [phase, setPhase] = useState<number>(0);
  const [modelId, setModelId] = useState("");
  const listing = useAsync(() => api.getResearchModels(), []);
  // Series reach the single-sequence volume models (cardiac segmenter, CT volume models) and the neighbouring-slice head CT models.
  const seriesModels = (listing.data?.models ?? []).filter((item) => item.gate.allowed && (item.inference_input === "head_ct_series"
    || (item.inference_input === "volume_nifti" && ["MRI", "CT_ABDOMEN_VOLUME", "CT_CHEST_VOLUME"].some((type) => item.supported_modalities.includes(type)))));
  const model = seriesModels.find((item) => item.model_id === modelId) ?? seriesModels[0] ?? null;
  const declaredInput: "MRI" | "CT_ABDOMEN_VOLUME" | "CT_CHEST_VOLUME" | "HEAD_CT_SERIES" = model?.inference_input === "head_ct_series" ? "HEAD_CT_SERIES"
    : model?.supported_modalities.includes("MRI") ? "MRI" : model?.supported_modalities.includes("CT_CHEST_VOLUME") ? "CT_CHEST_VOLUME" : "CT_ABDOMEN_VOLUME";
  const ordered = report?.status === "ASSEMBLED" ? report.ordered_upload_ids ?? null : null;
  const phaseChoice = report?.cardiac_phases && (report.issues.includes("CARDIAC_PHASE_REQUIRED") || report.phase !== undefined) ? report : null;

  useEffect(() => {
    if (!ordered) return;
    let cancelled = false;
    let created: string | null = null;
    api.renderDicomSeries(caseId, ordered, { axis, index, ...(windowing ?? {}) }).then(
      (result) => {
        created = result.url;
        if (cancelled) URL.revokeObjectURL(result.url);
        else {
          setImage(result);
          setError(null);
        }
      },
      (failure: unknown) => !cancelled && setError(errorMessage(failure)),
    );
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [caseId, ordered, axis, index, windowing]);

  async function assemble(selectedPhase: number | null = null) {
    setBusy("Assembling");
    setError(null);
    setRun(null);
    setImage(null);
    setIndex(null);
    try {
      setReport(await api.assembleDicomSeries(caseId, chosen, selectedPhase));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  async function segment() {
    if (!model || !ordered) return;
    setBusy("Running");
    setError(null);
    try {
      // The ordered uploads already hold one image per position (the assembled phase), so no phase is sent again.
      setRun(await api.runSeriesResearchModel(caseId, ordered, model.model_id, (job) => setBusy(`${humanize(job.status)}${job.message ? ` · ${job.message}` : ""}`),
        { declaredInputType: declaredInput, shortAxisAttested: declaredInput === "MRI" && attested }));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  const output = run?.research_output?.type === "volume_segmentation" ? run.research_output : null;
  const info = image?.info ?? null;
  const overlay: OverlayState | null = output && info && axis === "axial"
    ? { sourceSize: [info.shape[1], info.shape[0]], layer: <VolumeSliceLayer output={output} slice={info.index} highlight={null} /> }
    : null;
  return (
    <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
      <Card title="DICOM series" eyebrow="Ordered by slice position, not file order">
        {error && <ErrorBlock message={error} />}
        {report?.status === "ASSEMBLED" ? (
          image ? <PanZoomImage src={image.url} alt={`Series ${axis} plane ${image.info.index + 1}`} overlay={overlay} /> : <LoadingBlock label="Rendering" />
        ) : (
          <p className="text-sm text-ink-2">Choose the files of one series and assemble them. Slices are ordered by their position along the slice normal; a series with missing, duplicate or irregular slices is rejected with every reason.</p>
        )}
        {info && (
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <Segmented label="Plane" value={axis} onChange={(next) => { setAxis(next); setIndex(null); }} options={[{ value: "axial", label: "Slices" }, { value: "coronal", label: "Rows" }, { value: "sagittal", label: "Columns" }]} size="sm" />
            <label className="flex items-center gap-2 text-xs text-ink-2">
              Position
              <input type="range" min={0} max={info.count - 1} value={info.index} onChange={(event) => setIndex(Number(event.target.value))} className="w-40 accent-[var(--mt-accent)]" aria-label="Series position" />
              <span className="tabular">{info.index + 1}/{info.count}</span>
            </label>
            <div className="flex flex-wrap gap-1">
              {CT_PRESETS.map((preset) => <Button key={preset.id} size="sm" variant={windowing?.center === preset.center && windowing.width === preset.width ? "primary" : "secondary"} onClick={() => setWindowing({ center: preset.center, width: preset.width })}>{preset.label}</Button>)}
              <Button size="sm" variant={windowing ? "secondary" : "primary"} onClick={() => setWindowing(null)}>Auto</Button>
            </div>
          </div>
        )}
        {info && <p className="mt-2 text-[11px] text-ink-3">{info.plane}; pixel {formatNumber(info.pixel_spacing_mm.vertical, 3)} × {formatNumber(info.pixel_spacing_mm.horizontal, 3)} mm (vertical × horizontal); window {formatNumber(info.window.low, 1)} to {formatNumber(info.window.high, 1)}.</p>}
      </Card>
      <div className="space-y-4">
        <Card title="Files">
          <div className="max-h-48 space-y-1 overflow-auto text-xs">
            {uploads.map((upload) => (
              <label key={upload.id} className="flex items-center gap-2">
                <input type="checkbox" checked={chosen.includes(upload.id)} onChange={(event) => setChosen(event.target.checked ? [...chosen, upload.id] : chosen.filter((id) => id !== upload.id))} />
                {upload.filename}
              </label>
            ))}
          </div>
          <Button className="mt-3" size="sm" disabled={chosen.length < 2 || busy !== null} loading={busy === "Assembling"} onClick={() => void assemble()}>Assemble series</Button>
          {phaseChoice && (
            <div className="mt-3 space-y-2 border-t border-line pt-3">
              <p className="text-[11px] leading-4 text-ink-2">{phaseChoice.phase_semantics}</p>
              <label className="block text-xs text-ink-2">
                Cardiac phase ({phaseChoice.cardiac_phases} per slice position)
                <SelectInput aria-label="Cardiac phase" value={String(phase)} onChange={(event) => setPhase(Number(event.target.value))}>
                  {(phaseChoice.phase_trigger_times_ms ?? []).map((time, ordinal) => <option key={ordinal} value={ordinal}>Phase {ordinal + 1} · trigger {formatNumber(time, 0)} ms</option>)}
                </SelectInput>
              </label>
              <Button size="sm" disabled={busy !== null} onClick={() => void assemble(phase)}>Assemble this phase</Button>
            </div>
          )}
        </Card>
        {report && (
          <Card title="Geometry" actions={<StatusBadge status={report.status} />}>
            <KeyValue columns={1} items={[
              ...(report.issues.length ? [{ label: "Issues", value: report.issues.map(humanize).join(", ") }] : []),
              ...(report.shape_slices_rows_columns ? [{ label: "Slices × rows × columns", value: report.shape_slices_rows_columns.join(" × ") }] : []),
              ...(report.spacing_mm ? [{ label: "Spacing (mm)", value: `row ${formatNumber(report.spacing_mm.row, 4)}, column ${formatNumber(report.spacing_mm.column, 4)}, slice ${formatNumber(report.spacing_mm.slice, 4)}` }] : []),
              ...(report.warnings.length ? [{ label: "Warnings", value: report.warnings.map(humanize).join(", ") }] : []),
              ...(report.identifying_tags_present?.length ? [{ label: "Identifying elements present", value: report.identifying_tags_present.join(", ") }] : []),
            ]} />
          </Card>
        )}
        {ordered && (
          <Card title="Research model on this series" eyebrow="Research only · cardiac short-axis cine MRI or abdominal CT">
            {!model ? (
              <p className="text-xs text-ink-2">No volumetric research model that takes a single-sequence series passes the gate on this server.</p>
            ) : (
              <div className="space-y-3">
                {seriesModels.length > 1 && (
                  <label className="block text-xs text-ink-2">
                    Model
                    <SelectInput aria-label="Series research model" value={model.model_id} onChange={(event) => { setModelId(event.target.value); setAttested(false); setRun(null); }}>
                      {seriesModels.map((item) => <option key={item.model_id} value={item.model_id}>{item.display_name}</option>)}
                    </SelectInput>
                  </label>
                )}
                <p className="text-[11px] leading-4 text-ink-2">
                  {declaredInput === "MRI"
                    ? `${model.display_name}. The development frames carry no patient orientation, so the server runs the model under all 16 axis conventions, keeps the one whose ventricle layout matches the development frames, and requires the right ventricle to lie anterior-right of the left ventricle in this series' patient coordinates. The slice normal must be oblique (short-axis stacks are double-oblique).`
                    : declaredInput === "HEAD_CT_SERIES"
                      ? `${model.display_name}. Every slice is windowed as the training images were, stacked with its neighbours and checked against the model's applicability reference; slices outside it are not analysed, and a series with more than half of them outside is refused.`
                      : `${model.display_name}. The series is permuted and flipped into the development orientation from its DICOM geometry (exact, no resampling) and must hold Hounsfield units inside the development range.`}
                </p>
                <label className="flex items-start gap-2 text-xs text-ink-2">
                  <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-0.5" />
                  {declaredInput === "MRI"
                    ? "This series is a cardiac cine-MRI short-axis stack at end-diastole or end-systole (tags cannot show the view or the phase)."
                    : declaredInput === "HEAD_CT_SERIES"
                      ? "This series is a non-contrast axial head CT (every slice of one series)."
                      : declaredInput === "CT_CHEST_VOLUME"
                        ? "This series is a thoracic CT volume."
                        : "This series is a contrast-enhanced abdominal CT volume."}
                </label>
                <Button size="sm" disabled={!attested || busy !== null} loading={busy !== null && busy !== "Assembling"} onClick={segment}>{busy && busy !== "Assembling" ? busy : "Run segmenter"}</Button>
                {run && <ResultView run={run} />}
              </div>
            )}
          </Card>
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
  const dicom = images.filter((upload) => upload.filename.toLowerCase().endsWith(".dcm") && upload.is_associated && !upload.withdrawn_at);
  const requested = Number(search.get("upload")) || null;
  // The case and its uploads load after the first render (e.g. on a deep link), so the
  // defaults are derived until the user makes an explicit choice.
  const [chosenTab, setTab] = useState<"viewer" | "series" | "support" | null>(null);
  const tab = chosenTab ?? (selected || requested ? "viewer" : "support");
  const [uploadId, setUploadId] = useState<number | null>(null);
  const active = images.find((upload) => upload.id === (uploadId ?? requested)) ?? images[0] ?? null;
  const exams = new Map(selected?.examinations.map((exam) => [exam.id, exam]) ?? []);
  return (
    <>
      <PageHeader
        eyebrow="Medical Imaging"
        title="Imaging viewer and modality coverage"
        description="CT, MRI, X-ray, ultrasound, PET, angiography, endoscopy and other containers are read and displayed with their spatial metadata; multi-file DICOM series are assembled by slice position. No clinically validated model is configured. Research-only models trained on public datasets can be run on PNG/JPEG/BMP uploads (after an applicability check against each model's training images), on NIfTI volumes (cardiac cine MRI frames, brain diffusion MRI for stroke lesions, multi-sequence brain MRI for gliomas), on assembled cardiac MRI series and frame by frame on GI endoscopy videos (MP4/AVI); their outputs are labelled as research and stay pending review."
        actions={<Segmented label="Imaging view" value={tab} onChange={setTab} options={[{ value: "viewer", label: "Viewer" }, { value: "series", label: "DICOM series" }, { value: "support", label: "Modality support" }]} />}
      />
      {tab === "support" ? <ModalitySupport /> : tab === "series" && selected ? (
        dicom.length < 2
          ? <EmptyState title="No multi-file DICOM series" detail="Upload the files of one series (two or more DICOM Part 10 slices) to assemble and view it here." action={<Link to="/upload" className="text-sm text-accent-text hover:underline">Open the upload center</Link>} />
          : <SeriesViewer key={selected.id} caseId={selected.id} uploads={dicom} />
      ) : !selected ? (
        <EmptyState title="Select a case" detail="The viewer shows imaging uploaded to the selected case." />
      ) : images.length === 0 ? (
        <EmptyState title="No imaging uploads" detail="Upload DICOM (Part 10), NIfTI, NRRD, MetaImage, PNG, JPEG or BMP files to view them here." action={<Link to="/upload" className="text-sm text-accent-text hover:underline">Open the upload center</Link>} />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="w-80"><SelectInput aria-label="Imaging upload" value={active?.id ?? ""} onChange={(event) => setUploadId(Number(event.target.value))}>{images.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename}</option>)}</SelectInput></div>
            {active?.examination_id && <span className="text-xs text-ink-3">Examination {formatDate(exams.get(active.examination_id)?.exam_date)}</span>}
          </div>
          {active && (/\.(mp4|avi)$/i.test(active.filename) ? (
            <div className="space-y-4">
              <EchoEfPanel key={`echo-${active.id}`} upload={active} />
              <VideoFramePanel key={`video-${active.id}`} upload={active} />
            </div>
          ) : <Viewer key={active.id} upload={active} />)}
        </>
      )}
    </>
  );
}
