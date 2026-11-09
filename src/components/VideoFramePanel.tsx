import { useEffect, useMemo, useState } from "react";
import { Play } from "lucide-react";
import { Badge, Button, Card, ErrorBlock, KeyValue, LoadingBlock, SelectInput, TextInput, Unavailable } from "./ui";
import { api, type ResearchRun, type UploadedFile, type VideoFrameRecord, type VideoTimelineOutput } from "../services/api";
import { decodeCocoRle } from "../lib/rle";
import { errorMessage, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const MASK_RGBA: [number, number, number, number] = [34, 211, 238, 150];

function maskUrl(record: VideoFrameRecord): string | null {
  if (record.result?.kind !== "segmentation" || record.result.area_px === 0) return null;
  const [width, height] = record.result.image_size;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return null;
  const image = context.createImageData(width, height);
  for (const segment of record.result.segments) {
    const mask = decodeCocoRle(segment.rle.counts, segment.rle.size[0], segment.rle.size[1]);
    for (let index = 0; index < mask.length; index += 1) if (mask[index]) image.data.set(MASK_RGBA, index * 4);
  }
  context.putImageData(image, 0, 0);
  return canvas.toDataURL("image/png");
}

/** The value drawn for one frame in the timeline: mask share, top-class probability or box count. */
function frameValue(record: VideoFrameRecord): number {
  if (record.status !== "SCORED" || !record.result) return 0;
  if (record.result.kind === "segmentation") return Math.min(1, record.result.area_fraction * 10);
  if (record.result.kind === "classification") return record.result.top_probability;
  return Math.min(1, record.result.boxes_above_threshold / 3);
}

function Timeline({ output, selected, onSelect }: { output: VideoTimelineOutput; selected: number; onSelect: (position: number) => void }) {
  const duration = Math.max(output.video.duration_s, 0.001);
  return (
    <div>
      <div role="listbox" aria-label="Sampled frames" className="relative h-16 w-full overflow-hidden rounded border border-line bg-surface-2">
        {output.frames.map((record, position) => {
          const value = frameValue(record);
          const refused = record.status !== "SCORED";
          return (
            <button
              key={record.frame_index}
              type="button"
              role="option"
              aria-selected={position === selected}
              title={`${formatNumber(record.time_s, 1)} s · ${refused ? "refused by the applicability check" : record.result?.kind === "classification" ? `${humanize(record.result.top_class)} ${formatNumber(record.result.top_probability, 2)}` : record.result?.kind === "segmentation" ? `${formatNumber(record.result.area_fraction * 100, 1)}% of the frame masked` : `${record.result?.kind === "detection" ? record.result.boxes_above_threshold : 0} box(es)`}`}
              onClick={() => onSelect(position)}
              className="absolute bottom-0 top-0 -translate-x-1/2 px-0.5"
              style={{ left: `${(record.time_s / duration) * 100}%` }}
            >
              <span className={`absolute bottom-0 left-0 right-0 mx-auto w-1.5 rounded-t-sm ${refused ? "bg-ink-3 opacity-40" : "bg-[var(--mt-series-1)]"} ${position === selected ? "ring-2 ring-[var(--mt-accent)]" : ""}`}
                style={{ height: refused ? "20%" : `${Math.max(6, value * 100)}%` }} />
            </button>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-ink-3"><span>0 s</span><span>{formatNumber(duration, 1)} s</span></div>
    </div>
  );
}

function FrameView({ uploadId, record }: { uploadId: number; record: VideoFrameRecord }) {
  // The decoded image is kept with its frame index, so a mask is never drawn over the previous frame while the next one decodes.
  const [frame, setFrame] = useState<{ index: number; url: string } | null>(null);
  const [error, setError] = useState<{ index: number; message: string } | null>(null);
  const overlay = useMemo(() => maskUrl(record), [record]);
  const url = frame?.index === record.frame_index ? frame.url : null;
  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    const index = record.frame_index;
    api.getVideoFrameUrl(uploadId, index).then(
      (value) => { created = value; if (cancelled) URL.revokeObjectURL(value); else setFrame({ index, url: value }); },
      (failure: unknown) => { if (!cancelled) setError({ index, message: errorMessage(failure) }); },
    );
    return () => { cancelled = true; if (created) URL.revokeObjectURL(created); };
  }, [uploadId, record.frame_index]);
  const failed = error?.index === record.frame_index ? error.message : null;
  const size = record.result && "image_size" in record.result ? record.result.image_size : null;
  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded bg-black">
        {failed ? <ErrorBlock message={failed} /> : url ? <img src={url} alt={`Video frame at ${formatNumber(record.time_s, 1)} s`} className="block h-auto w-full" /> : <LoadingBlock label="Decoding frame" />}
        {url && overlay && <img src={overlay} alt="" aria-hidden className="absolute inset-0 h-full w-full" style={{ imageRendering: "pixelated" }} />}
        {url && size && record.result?.kind === "detection" && (
          <svg aria-hidden viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
            {record.result.boxes.map((box, index) => {
              const [x1, y1, x2, y2] = box.bbox_xyxy;
              return <rect key={index} x={x1} y={y1} width={x2 - x1} height={y2 - y1} fill="none" stroke="var(--mt-overlay-model)" strokeWidth={Math.max(1.5, size[0] / 300)} />;
            })}
          </svg>
        )}
      </div>
      <KeyValue columns={3} items={[
        { label: "Time", value: `${formatNumber(record.time_s, 2)} s (frame ${record.frame_index})` },
        { label: "Status", value: record.status === "SCORED" ? "Scored" : "Refused by the applicability check" },
        { label: "Result", value: !record.result ? "—" : record.result.kind === "segmentation" ? `${formatNumber(record.result.area_fraction * 100, 2)}% of the frame (${formatNumber(record.result.area_px, 0)} px)` : record.result.kind === "classification" ? `${humanize(record.result.top_class)} ${formatNumber(record.result.top_probability, 3)}` : `${record.result.boxes_above_threshold} box(es) at or above threshold` },
        { label: "Brightness", value: formatNumber(record.quality.brightness, 3) },
        { label: "Dark share", value: `${formatNumber(record.quality.dark_fraction * 100, 1)}%` },
        { label: "Sharpness (Laplacian variance)", value: formatNumber(record.quality.sharpness_laplacian_variance, 1) },
      ]} />
      {record.reason && <p className="text-[11px] leading-4 text-ink-3">{record.reason}</p>}
    </div>
  );
}

/** GI endoscopy video: frames sampled at an interval, each scored by a still-image research model after its own applicability check. */
export default function VideoFramePanel({ upload }: { upload: UploadedFile }) {
  const metadata = useAsync(() => api.getVideoMetadata(upload.id), [upload.id]);
  const listing = useAsync(() => api.getResearchModels(), []);
  const runs = useAsync(() => api.listResearchRuns(upload.id), [upload.id]);
  const models = (listing.data?.models ?? []).filter((model) => model.gate.allowed && (model.inference_input ?? "image_2d") === "image_2d" && model.supported_modalities.includes("ENDOSCOPY"));
  const [modelId, setModelId] = useState<string | null>(null);
  const [intervalText, setIntervalText] = useState("1");
  const [maxFrames, setMaxFrames] = useState("120");
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fresh, setFresh] = useState<ResearchRun | null>(null);
  const [position, setPosition] = useState(0);
  const model = models.find((item) => item.model_id === modelId) ?? models[0] ?? null;
  const stored = (runs.data?.runs ?? []).find((run) => run.research_output?.type === "video_frame_timeline") ?? null;
  const run = fresh ?? stored;
  const output = run?.research_output?.type === "video_frame_timeline" ? run.research_output : null;
  const intervalValue = Number(intervalText);
  const maxValue = Number(maxFrames);
  const valid = Number.isFinite(intervalValue) && intervalValue >= 0.2 && intervalValue <= 30 && Number.isInteger(maxValue) && maxValue >= 1 && maxValue <= 240;

  async function execute() {
    if (!model) return;
    setBusy("Running");
    setError(null);
    try {
      const result = await api.runVideoFrameAnalysis(upload.id, model.model_id, intervalValue, maxValue, (job) => setBusy(`${humanize(job.status)}${job.message ? ` · ${job.message}` : ""}`));
      setFresh(result);
      setPosition(0);
      runs.reload();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  const record = output?.frames[Math.min(position, Math.max(0, (output?.frames.length ?? 1) - 1))] ?? null;
  return (
    <Card title={upload.filename} eyebrow="Endoscopy video · research only">
      {metadata.loading && <LoadingBlock label="Reading the video" />}
      {metadata.error && <ErrorBlock message={metadata.error} onRetry={metadata.reload} />}
      {metadata.data && (
        <KeyValue columns={3} items={[
          { label: "Duration", value: `${formatNumber(metadata.data.duration_s, 1)} s` },
          { label: "Frames", value: `${formatNumber(metadata.data.frame_count, 0)} at ${formatNumber(metadata.data.fps, 2)} fps` },
          { label: "Frame size", value: `${metadata.data.width} × ${metadata.data.height} px · ${metadata.data.codec}` },
        ]} />
      )}
      <div className="mt-4 space-y-3 border-t border-line pt-4">
        <p className="text-[11px] leading-4 text-ink-2">
          Frames are sampled at a fixed interval and each one goes through the chosen still-image endoscopy model exactly like an uploaded image: the model's own applicability check first, then the model.
          Frames are scored independently (no smoothing or tracking), and no model here was trained or evaluated on video.
        </p>
        {listing.loading ? <LoadingBlock label="Reading model registry" /> : models.length === 0 ? (
          <Unavailable compact code="NO_ENDOSCOPY_MODEL" reason="No still-image endoscopy research model passes the gate." />
        ) : (
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs text-ink-2">Model
              <SelectInput aria-label="Endoscopy research model" value={model?.model_id ?? ""} onChange={(event) => setModelId(event.target.value)}>
                {models.map((item) => <option key={item.model_id} value={item.model_id}>{item.display_name}</option>)}
              </SelectInput>
            </label>
            <label className="text-xs text-ink-2">Every (s)<TextInput type="number" min={0.2} max={30} step={0.1} value={intervalText} onChange={(event) => setIntervalText(event.target.value)} className="h-8 w-20 text-xs" /></label>
            <label className="text-xs text-ink-2">At most (frames)<TextInput type="number" min={1} max={240} value={maxFrames} onChange={(event) => setMaxFrames(event.target.value)} className="h-8 w-24 text-xs" /></label>
          </div>
        )}
        <label className="flex items-start gap-2 text-xs text-ink-2">
          <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
          This is a GI endoscopy video (colonoscopy, gastroscopy or similar), de-identified.
        </label>
        <Button variant="primary" icon={Play} disabled={!model || !attested || !valid} loading={busy !== null} onClick={() => void execute()}>{busy ?? "Score sampled frames"}</Button>
        {error && <ErrorBlock message={error} />}
      </div>
      {output && record && (
        <div className="mt-4 space-y-3 border-t border-line pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="warning">Research only · per-frame still-image model</Badge>
            <span className="text-[11px] text-ink-3">Run #{run?.id} · {output.scored_frames} scored, {output.refused_frames} refused of {output.sampling.decoded_frames} sampled frames</span>
            {output.summary?.frames_with_mask !== undefined && <span className="text-[11px] text-ink-2">Mask in {output.summary.frames_with_mask} frame(s){output.summary.first_time_with_mask_s !== null && output.summary.first_time_with_mask_s !== undefined ? `, first at ${formatNumber(output.summary.first_time_with_mask_s, 1)} s` : ""}</span>}
          </div>
          {output.sampling.variable_frame_rate_suspected && <p className="text-[11px] leading-4 text-warning-text">The decoder's frame times drift from frame number / frame rate: this looks like a variable-frame-rate video, so sampled frames are not evenly spaced in time. Times shown are the decoder's.</p>}
          <Timeline output={output} selected={position} onSelect={setPosition} />
          <FrameView uploadId={upload.id} record={record} />
          <p className="text-[11px] leading-4 text-ink-3">{output.semantics} Bars: mask share (×10), top-class probability or box count; grey bars are frames the applicability check refused.</p>
          {output.tracking && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-ink">Linked regions <span className="font-mono text-[10px] text-ink-3">{output.tracking.status}</span></p>
              {output.tracking.tracks.length === 0 ? <p className="text-[11px] text-ink-3">No region was marked on any scored frame.</p> : (
                <ul className="space-y-0.5 text-[11px] text-ink-2">
                  {output.tracking.tracks.map((track) => (
                    <li key={track.track_id} className="tabular">Track {track.track_id}: marked on {track.frames_marked} sampled frame(s), {formatNumber(track.first_time_s, 1)}–{formatNumber(track.last_time_s, 1)} s</li>
                  ))}
                </ul>
              )}
              <p className="text-[11px] leading-4 text-ink-3">{output.tracking.semantics}</p>
            </div>
          )}
          {output.class_runs && (
            <p className="text-[11px] leading-4 text-ink-3">
              The per-frame top class changed {output.class_runs.top_class_changes} time(s): {output.class_runs.runs.map((item) => `${item.top_class} ${formatNumber(item.first_time_s, 1)}–${formatNumber(item.last_time_s, 1)} s`).join("; ")}. {output.class_runs.semantics}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
