import { useEffect, useState } from "react";
import { api, type FilmAssessment, type QueuedJob } from "../services/api";
import { useAsync } from "../lib/useAsync";
import { errorMessage, humanize } from "../lib/format";
import { useWorkspace } from "../state/workspace";
import { Button, Disclosure, ErrorBlock, SelectInput, StatusBadge } from "./ui";

export default function MultimodelPanel({ uploadId, assessment }: { uploadId: number; assessment?: FilmAssessment }) {
  const listing = useAsync(() => api.getResearchModels(), []);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const [input, setInput] = useState("HEAD_CT");
  const [models, setModels] = useState<string[]>([]);
  const [job, setJob] = useState<QueuedJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const terminal = job && ["SUCCEEDED", "FAILED", "CANCELLED"].includes(job.status);
  const filmBlocked = assessment?.inference_eligibility === "ABSTAIN_FILM_INPUT";
  const outputs = job?.result_ref?.results ?? [];
  const produced = outputs.filter((item) => ["COMPLETED", "PENDING_HUMAN_REVIEW"].includes(item.status) && !item.reason).length;
  const analysisStatus = job?.result_ref?.analysis_status ?? (outputs.length ? produced === 0 ? "ABSTAIN" : produced === outputs.length ? "COMPLETED" : "PARTIAL" : job?.status === "FAILED" ? "ERROR" : "NOT_RUN");
  useEffect(() => {
    if (!job || terminal) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api.getQueuedJob(job.id).then((next) => { if (!cancelled) setJob(next); }, (err: unknown) => { if (!cancelled) setError(errorMessage(err)); });
    }, 1500);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [job, terminal]);
  useEffect(() => { if (terminal) void loadEvidence(); }, [terminal, loadEvidence]);
  async function run() {
    if (filmBlocked || !models.length) return;
    setBusy(true); setError(null); setJob(null);
    try { setJob((await api.runMultimodel(uploadId, models, input)).queued_job); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }
  const candidates = (listing.data?.models ?? []).filter((m) => (m.inference_input ?? "image_2d") === "image_2d" && m.supported_modalities.includes(input));
  if (filmBlocked) return <p className="mt-3 border-t border-line pt-3 text-xs text-ink-2">Multimodel inference requires a compatible native image. The film assessment applies to every native-image model; repeated attempts will not produce additional evidence.</p>;
  return <Disclosure summary="Multimodel analysis · separate runs, no probability averaging">
    <div className="space-y-3 pt-3">
      {listing.error && <ErrorBlock message={listing.error} onRetry={listing.reload} />}
      <SelectInput aria-label="Multimodel input type" value={input} onChange={(event) => { setInput(event.target.value); setModels([]); setJob(null); }}>{Object.entries(listing.data?.input_types ?? { HEAD_CT: "Non-contrast head CT" }).filter(([key]) => !["ECG", "MRI", "BRAIN_MRI_DIFFUSION", "BRAIN_MRI_MULTISEQUENCE"].includes(key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</SelectInput>
      {candidates.map((model) => <label key={model.model_id} className="flex items-start gap-2 text-xs text-ink-2"><input type="checkbox" disabled={!model.gate.allowed || (models.length >= 6 && !models.includes(model.model_id))} checked={models.includes(model.model_id)} onChange={(event) => setModels((current) => event.target.checked ? [...current, model.model_id] : current.filter((id) => id !== model.model_id))} /><span>{model.display_name}<span className="mt-1 block text-[11px] text-ink-3">{model.gate.allowed ? humanize(model.task) : model.gate.blockers.join(", ")}</span></span></label>)}
      {!candidates.length && <p className="text-xs text-ink-3">No registered models support this input contract.</p>}
      <p className="text-[11px] text-ink-3">Each selected model must pass its own checkpoint, input and applicability gates. Film photographs may produce only abstentions. Incompatible label meanings are not combined.</p>
      <Button size="sm" loading={busy || Boolean(job && !terminal)} disabled={!models.length} onClick={() => void run()}>Run selected models</Button>
      {error && <ErrorBlock message={error} />}
      {job && <><p className="text-xs text-ink-2">Job #{job.id} · {terminal ? "Execution finished" : humanize(job.status)}</p>{terminal && <div className="space-y-1 text-xs text-ink-2"><StatusBadge status={analysisStatus} label={analysisStatus === "ABSTAIN" ? "All models abstained — no predictions" : humanize(analysisStatus)} /><p>{produced} of {outputs.length} models produced outputs.</p></div>}{job.last_error && <p className="text-xs text-warning-text">{job.last_error}</p>}{outputs.map((result) => <div key={result.run_id} className="text-xs text-ink-2"><StatusBadge status={result.status} /> {result.model_id} · run #{result.run_id}{result.reason && <p className="mt-1">{result.reason}</p>}</div>)}</>}
    </div>
  </Disclosure>;
}
