import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { Button, ErrorBlock, LoadingBlock, SelectInput, Unavailable } from "./ui";
import { ResultView } from "./ResearchModelPanel";
import { api, type ResearchRun, type UploadedFile } from "../services/api";
import { errorMessage, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const suffix = (upload: UploadedFile) => upload.filename.toLowerCase().split(".").pop() ?? "";

/** Research inference for digital 12-lead ECG records (WFDB header + signal file, or CSV). */
export default function EcgResearchPanel({ uploads }: { uploads: UploadedFile[] }) {
  const listing = useAsync(() => api.getResearchModels(), []);
  const models = (listing.data?.models ?? []).filter((model) => model.gate.allowed && model.inference_input === "ecg_12lead");
  const usable = uploads.filter((upload) => upload.modality === "ECG" && upload.is_associated && !upload.withdrawn_at);
  const records = usable.filter((upload) => ["hea", "csv"].includes(suffix(upload)));
  const signals = usable.filter((upload) => suffix(upload) === "dat");
  const [recordId, setRecordId] = useState<number | null>(null);
  const [signalId, setSignalId] = useState<number | null>(null);
  const [unit, setUnit] = useState<"" | "mV" | "uV">("");
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const model = models[0] ?? null;
  const record = records.find((upload) => upload.id === recordId) ?? records[0] ?? null;
  const wfdb = record !== null && suffix(record) === "hea";
  const signal = wfdb ? signals.find((upload) => upload.id === signalId) ?? null : null;
  const ready = model !== null && record !== null && attested && (wfdb ? signal !== null : unit !== "");

  async function execute() {
    if (!model || !record) return;
    setBusy("Running");
    setError(null);
    try {
      setRun(await api.runResearchModel(record.id, model.model_id, "ECG", (job) => setBusy(`${humanize(job.status)}${job.message ? ` · ${job.message}` : ""}`),
        wfdb ? { companionUploadId: signal?.id } : { amplitudeUnit: unit || undefined }));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  if (listing.loading) return <LoadingBlock label="Reading model registry" />;
  if (listing.error) return <ErrorBlock message={listing.error} onRetry={listing.reload} />;
  if (!model) return <Unavailable compact code="NO_RUNNABLE_ECG_MODEL" reason="No ECG research model passes the gate (verified licence, held-out report, checkpoint hash)." />;
  if (records.length === 0) {
    return <Unavailable compact code="NO_DIGITAL_ECG_RECORD" reason="Upload a WFDB record (the .hea header and its .dat signal file) or a CSV with a time column in seconds. Photographs and scans of printed ECGs are images, not signals; this model cannot read them." />;
  }
  return (
    <div className="space-y-3">
      <p className="text-[11px] leading-4 text-ink-2">{listing.data?.notice} Model: {model.display_name}. Records must be resting 12-lead ECGs at 100 Hz lasting 10 s; nothing is resampled, cropped or padded, and anything else is refused.</p>
      <label className="block text-xs text-ink-2">
        Record
        <SelectInput aria-label="ECG record" value={record?.id ?? ""} onChange={(event) => { setRecordId(Number(event.target.value)); setSignalId(null); setRun(null); }}>
          {records.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename}</option>)}
        </SelectInput>
      </label>
      {wfdb ? (
        <label className="block text-xs text-ink-2">
          Signal file (.dat) of this record
          <SelectInput aria-label="WFDB signal file" value={signal?.id ?? ""} onChange={(event) => setSignalId(event.target.value === "" ? null : Number(event.target.value))}>
            <option value="">Select the signal upload</option>
            {signals.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename}</option>)}
          </SelectInput>
          <span className="mt-1 block text-[11px] text-ink-3">The header's per-lead checksums prove the pairing; a mismatched file is refused.</span>
        </label>
      ) : (
        <label className="block text-xs text-ink-2">
          Amplitude unit of the CSV values
          <SelectInput aria-label="CSV amplitude unit" value={unit} onChange={(event) => setUnit(event.target.value as "" | "mV" | "uV")}>
            <option value="">Declare the unit</option>
            <option value="mV">Millivolts (mV)</option>
            <option value="uV">Microvolts (µV)</option>
          </SelectInput>
        </label>
      )}
      <label className="flex items-start gap-2 text-xs text-ink-2">
        <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
        <span>I confirm this is a {listing.data?.input_types.ECG ?? "resting 12-lead ECG recording"}. The server checks the sampling rate, duration, lead set and signal quality; it cannot verify acquisition conditions.</span>
      </label>
      <Button variant="primary" icon={FlaskConical} disabled={!ready} loading={busy !== null} onClick={execute}>{busy ?? "Run ECG research model"}</Button>
      {error && <ErrorBlock message={error} />}
      {run && <ResultView run={run} />}
    </div>
  );
}
