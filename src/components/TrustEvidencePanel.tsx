import { useAsync } from "../lib/useAsync";
import { universalJson } from "../services/universal";
import { humanize } from "../lib/format";
import { Card, ErrorBlock, StatusBadge } from "./ui";

type Evidence = { id: string; label: string; review_status?: string | null; source_file_id?: number | null; details: Record<string, unknown> };
type Capability = { model_id: string; capability_state: string; research_gate: { allowed: boolean; blockers: string[] }; limitations: string[] };

export default function TrustEvidencePanel({ selected, finding, run }: { selected?: Evidence; finding?: Evidence; run?: Evidence }) {
  const provenance = finding?.details.model_provenance && typeof finding.details.model_provenance === "object" ? finding.details.model_provenance as Record<string, unknown> : {};
  const modelId = typeof provenance.model_id === "string" ? provenance.model_id : null;
  const capabilities = useAsync(() => modelId ? universalJson<{ items: Capability[] }>("/universal/capabilities") : null, [modelId]);
  const capability = !capabilities.loading ? capabilities.data?.items.find((item) => item.model_id === modelId) : undefined;
  const score = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value.toFixed(5) : "Not recorded";
  return <Card title="Trust & refusal center" eyebrow="Recorded outcome and current eligibility are separate">
    {!selected ? <p className="text-xs text-ink-3">Select an observation to inspect its source, original computation, review decision and current model gate.</p> : <div className="space-y-3 text-xs">
      <p className="font-medium">{selected.label}</p>
      <div className="flex flex-wrap gap-2"><StatusBadge status={finding?.review_status ?? selected.review_status} /><StatusBadge status={finding?.details.active_evidence === false ? "NOT_CURRENT_EVIDENCE" : finding ? "RECORDED_EVIDENCE" : "SOURCE_CONTEXT"} /><StatusBadge status="CLINICALLY_UNVALIDATED" /></div>
      {typeof finding?.details.failure_reason === "string" && <p className="rounded border border-warning p-2 text-warning-text">Recorded refusal or failure: {finding.details.failure_reason}</p>}
      <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)] gap-x-3 gap-y-2">
        <dt className="text-ink-3">Source / finding</dt><dd className="break-all">Upload #{selected.source_file_id ?? finding?.source_file_id ?? "unlinked"} / {finding?.id ?? "not selected"}</dd>
        <dt className="text-ink-3">Original run</dt><dd>{run?.id ?? "Not recorded"} {run ? `· ${humanize(String(run.details.status ?? "UNKNOWN"))}` : ""}</dd>
        <dt className="text-ink-3">Preprocessing</dt><dd className="break-words">{typeof run?.details.preprocessing_version === "string" ? run.details.preprocessing_version : "Not recorded"}</dd>
        <dt className="text-ink-3">Raw model score</dt><dd>{score(finding?.details.raw_confidence)}</dd>
        <dt className="text-ink-3">Calibrated score</dt><dd>{score(finding?.details.calibrated_confidence)} · {humanize(String(finding?.details.calibration_status ?? "NOT_RECORDED"))}</dd>
      </dl>
      <p className="text-ink-3">A model score is not a confirmed probability of disease. Reviewer confirmation does not confer clinical validation or override an input or rights gate.</p>
      {modelId && <div className="space-y-2 border-t border-line pt-2"><p className="break-all font-mono">Model: {modelId}</p>{capabilities.error && <ErrorBlock message={capabilities.error} />}{capability ? <><StatusBadge status={capability.capability_state} /><p>New execution: {capability.research_gate.allowed ? "Eligible subject to this model's per-input checks" : "Blocked by the current model gate"}</p>{capability.research_gate.blockers.map((reason) => <p key={reason} className="break-words text-warning-text">{reason}</p>)}</> : <p className="text-ink-3">{capabilities.loading ? "Resolving the current gate…" : "No current eligibility record resolved; a saved result does not authorize a new run."}</p>}</div>}
      <details><summary className="cursor-pointer text-accent-text">Checkpoint and source identities</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all text-[10px]">{JSON.stringify({ source_sha256: finding?.details.source_file_sha256 ?? null, model: provenance, run: run?.details ?? null }, null, 2)}</pre></details>
    </div>}
  </Card>;
}
