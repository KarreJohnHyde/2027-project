import { useState } from "react";
import { HeartPulse } from "lucide-react";
import { Button, Card, ErrorBlock, LoadingBlock, SelectInput, Unavailable } from "./ui";
import { ResultView } from "./ResearchModelPanel";
import { api, type ResearchRun, type UploadedFile } from "../services/api";
import { errorMessage, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";

/** Ejection fraction from an apical-4-chamber echo video (research; EchoNet-format input only). */
export default function EchoEfPanel({ upload }: { upload: UploadedFile }) {
  const listing = useAsync(() => api.getResearchModels(), []);
  const models = (listing.data?.models ?? []).filter((model) => model.gate.allowed && model.inference_input === "echo_video");
  const [modelId, setModelId] = useState<string | null>(null);
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const model = models.find((item) => item.model_id === modelId) ?? models[0] ?? null;
  const evaluation = model?.held_out_evaluation ?? {};
  const mae = typeof evaluation.mae === "number" ? evaluation.mae : null;
  const interval = Array.isArray(evaluation.mae_95ci) ? evaluation.mae_95ci : null;

  async function execute() {
    if (!model) return;
    setBusy("Running");
    setError(null);
    try {
      setRun(await api.runResearchModel(upload.id, model.model_id, "ECHO", (job) => setBusy(`${humanize(job.status)}${job.message ? ` · ${job.message}` : ""}`)));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Echocardiography: ejection fraction" eyebrow="Research model · EchoNet-Dynamic">
      {listing.loading ? <LoadingBlock label="Reading model registry" /> : listing.error ? <ErrorBlock message={listing.error} onRetry={listing.reload} /> : !model ? (
        <Unavailable compact code="NO_RUNNABLE_ECHO_MODEL" reason="No echocardiography research model passes the gate (verified licence, held-out report, checkpoint hash, applicability reference)." />
      ) : (
        <div className="space-y-3">
          <p className="text-[11px] leading-4 text-ink-2">
            Only EchoNet-format videos are accepted: apical 4-chamber view, 112 × 112 pixels with the ultrasound sector cropped and everything outside it masked.
            Full-screen scanner exports, other views and Doppler are refused, never resized.
            {mae !== null ? ` Held-out test: mean absolute error ${formatNumber(mae, 2)} EF points${interval && interval[0] !== null ? ` (95% CI ${formatNumber(interval[0] as number, 2)}-${formatNumber(interval[1] as number, 2)})` : ""} on ${String(evaluation.test_n ?? "?")} videos from the same centre.` : ""}
          </p>
          {models.length > 1 && (
            <label className="block text-xs text-ink-2">
              Model
              <SelectInput aria-label="Echo research model" value={model.model_id} onChange={(event) => { setModelId(event.target.value); setRun(null); }}>
                {models.map((item) => <option key={item.model_id} value={item.model_id}>{item.display_name}</option>)}
              </SelectInput>
            </label>
          )}
          <label className="flex items-start gap-2 text-xs text-ink-2">
            <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-0.5 accent-[var(--mt-accent)]" />
            <span>I confirm this is an {listing.data?.input_types.ECHO ?? "apical-4-chamber echocardiography video in EchoNet format"}. The server checks the frame size, frame count, frame rate, colour and the model's applicability reference; it cannot verify the view.</span>
          </label>
          <Button variant="primary" icon={HeartPulse} disabled={!attested} loading={busy !== null} onClick={execute}>{busy ?? "Estimate ejection fraction"}</Button>
          {error && <ErrorBlock message={error} />}
          {run && <ResultView run={run} />}
        </div>
      )}
    </Card>
  );
}
