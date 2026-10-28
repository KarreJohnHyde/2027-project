import { useState } from "react";
import { ErrorBlock, KeyValue, LoadingBlock, SelectInput, Unavailable, Button } from "./ui";
import { api, type SignalPreview, type UploadedFile } from "../services/api";
import { formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const WINDOW_SECONDS = [5, 10, 30];
const CHANNELS_PER_PAGE = 12;
const TRACE_HEIGHT = 44;
const WIDTH = 900;

function Traces({ preview }: { preview: SignalPreview }) {
  const height = preview.channels.length * TRACE_HEIGHT;
  return (
    <svg viewBox={`0 0 ${WIDTH} ${height + 18}`} className="h-auto w-full rounded-md border border-line bg-surface" role="img"
      aria-label={`Signals from ${formatNumber(preview.start_s, 1)} s to ${formatNumber(preview.start_s + preview.duration_s, 1)} s`}>
      {preview.channels.map((channel, row) => {
        const low = channel.window_min ?? 0;
        const high = channel.window_max ?? 1;
        const span = high - low || 1;
        const top = row * TRACE_HEIGHT + 4;
        const x = (i: number) => (i / Math.max(channel.points - 1, 1)) * (WIDTH - 120) + 110;
        const y = (value: number) => top + (TRACE_HEIGHT - 8) * (1 - (value - low) / span);
        // Each point is a min/max pair; drawing both keeps peaks the reduction would otherwise hide.
        const path = channel.max.map((value, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(value).toFixed(1)} L${x(i).toFixed(1)},${y(channel.min[i]).toFixed(1)}`).join(" ");
        return (
          <g key={channel.index}>
            <text x={4} y={top + TRACE_HEIGHT / 2} className="fill-current text-[10px] text-ink-2">{channel.label.slice(0, 16)}</text>
            <text x={4} y={top + TRACE_HEIGHT / 2 + 11} className="fill-current text-[9px] text-ink-3">{formatNumber(span, 3)} {channel.unit}</text>
            <path d={path} fill="none" stroke="currentColor" strokeWidth={0.8} className="text-accent-text" />
          </g>
        );
      })}
      <text x={110} y={height + 14} className="fill-current text-[10px] text-ink-3">{formatNumber(preview.start_s, 1)} s</text>
      <text x={WIDTH - 10} y={height + 14} textAnchor="end" className="fill-current text-[10px] text-ink-3">{formatNumber(preview.start_s + preview.duration_s, 1)} s</text>
    </svg>
  );
}

/** EDF/BDF recordings (EEG and other physiological signals): structure and waveforms as recorded; no model. */
export default function SignalRecordingPanel({ uploads }: { uploads: UploadedFile[] }) {
  const recordings = uploads.filter((upload) => upload.modality === "SIGNAL" && upload.is_associated && !upload.withdrawn_at);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [start, setStart] = useState(0);
  const [duration, setDuration] = useState(10);
  const [page, setPage] = useState(0);
  const recording = recordings.find((upload) => upload.id === selectedId) ?? recordings[0] ?? null;
  const header = useAsync(() => (recording ? api.getSignalHeader(recording.id) : Promise.resolve(null)), [recording?.id]);
  const channels = (header.data?.signals ?? []).slice(page * CHANNELS_PER_PAGE, (page + 1) * CHANNELS_PER_PAGE).map((signal) => signal.index);
  const preview = useAsync(
    () => (recording && channels.length ? api.getSignalPreview(recording.id, start, duration, channels) : Promise.resolve(null)),
    [recording?.id, start, duration, channels.join(",")],
  );

  if (recordings.length === 0) {
    return <Unavailable compact code="NO_SIGNAL_RECORDING" reason="Upload an EDF, EDF+ or BDF recording (EEG or another physiological signal). Scans or photographs of printed tracings are images, not signals." />;
  }
  const info = header.data;
  const pages = info ? Math.ceil(info.signals.length / CHANNELS_PER_PAGE) : 0;
  const end = info ? info.duration_s : 0;
  return (
    <div className="space-y-3">
      <label className="block text-xs text-ink-2">
        Recording
        <SelectInput aria-label="Signal recording" value={recording?.id ?? ""} onChange={(event) => { setSelectedId(Number(event.target.value)); setStart(0); setPage(0); }}>
          {recordings.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename}</option>)}
        </SelectInput>
      </label>
      {header.loading && <LoadingBlock label="Reading the recording header" />}
      {header.error && <ErrorBlock message={header.error} onRetry={header.reload} />}
      {info && (
        <>
          <KeyValue columns={3} items={[
            { label: "Format", value: info.format },
            { label: "Duration", value: `${formatNumber(info.duration_s, 1)} s` },
            { label: "Signals", value: String(info.signals.length) },
            { label: "Recording start", value: info.start ?? "Not documented" },
            { label: "Patient field", value: humanize(info.patient_identification_field) },
            { label: "Annotations", value: String(info.annotations.length) },
          ]} />
          {info.warnings.map((warning) => <p key={warning} className="text-xs text-warning-text">{warning}</p>)}
          <p className="text-[11px] text-ink-3">{info.model}</p>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Button variant="secondary" disabled={start <= 0} onClick={() => setStart(Math.max(0, start - duration))}>Earlier</Button>
            <Button variant="secondary" disabled={start + duration >= end} onClick={() => setStart(Math.min(Math.max(end - duration, 0), start + duration))}>Later</Button>
            <SelectInput aria-label="Window length" value={duration} onChange={(event) => setDuration(Number(event.target.value))}>
              {WINDOW_SECONDS.map((seconds) => <option key={seconds} value={seconds}>{seconds} s window</option>)}
            </SelectInput>
            {pages > 1 && (
              <SelectInput aria-label="Channel page" value={page} onChange={(event) => setPage(Number(event.target.value))}>
                {Array.from({ length: pages }, (_, index) => <option key={index} value={index}>Channels {index * CHANNELS_PER_PAGE + 1}–{Math.min((index + 1) * CHANNELS_PER_PAGE, info.signals.length)}</option>)}
              </SelectInput>
            )}
          </div>
          {preview.error && <ErrorBlock message={preview.error} onRetry={preview.reload} />}
          {preview.data && <Traces preview={preview.data} />}
          {preview.data && <p className="text-[11px] text-ink-3">Each trace is scaled to its own range in this window (shown beside the label). {preview.data.reduction}.</p>}
          {info.annotations.length > 0 && (
            <ul className="max-h-40 space-y-1 overflow-auto text-xs text-ink-2">
              {info.annotations.map((note, index) => (
                <li key={index}>
                  <button type="button" className="underline-offset-2 hover:underline" onClick={() => setStart(Math.max(0, Math.min(note.onset_s, Math.max(end - duration, 0))))}>
                    {formatNumber(note.onset_s, 2)} s
                  </button>{note.duration_s !== null ? ` (${formatNumber(note.duration_s, 2)} s)` : ""} · {note.text}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
