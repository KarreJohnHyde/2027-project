import { lazy, Suspense, useRef, useState } from "react";
import { BarChart3 } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Card, ErrorBlock, LoadingBlock, PageHeader, SelectInput, StatusBadge } from "../components/ui";
import { useAsync } from "../lib/useAsync";
import { errorMessage, humanize } from "../lib/format";
import { universalJson } from "../services/universal";
import { Link } from "../lib/router";

type Model = { model_id: string; display_name: string; task: string; labels: string[]; dataset_version: string | null; checkpoint_sha256: string | null; preprocessing_version: string | null; calibration: unknown; decision_thresholds: unknown; gate: { allowed: boolean; blockers: string[] }; evaluation_state: string; evaluation_sha256: string | null; metrics: Record<string, unknown>; test_n: number | null; test_patients: number | null; confidence_intervals_95: Record<string, unknown>; available_diagnostics?: string[]; report_binding: {status: string; reasons: string[]; scope?: string} };
type Comparison = { status: string; reasons: string[]; left: Model; right: Model; cohorts: { left: { digest: string | null; n: number }; right: { digest: string | null; n: number } }; right_minus_left: Record<string, number>; significance: string; notice: string };
const numeric = (entries: Record<string, unknown>) => Object.entries(entries).filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1]));
const Diagnostics = lazy(() => import("../components/ArenaDiagnostics"));
const MatchedRecords = lazy(() => import("../components/MatchedModelExplorer"));

function EvaluationCard({ model }: { model: Model }) {
  const [diagnostics, setDiagnostics] = useState(false);
  return <Card title={model.display_name} eyebrow={humanize(model.task)}>
    <div className="mb-3 flex flex-wrap gap-2"><StatusBadge status={model.evaluation_state} /><StatusBadge status={model.report_binding.status} /><StatusBadge status={model.gate.allowed ? "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED" : "RESEARCH_MODEL_BLOCKED"} /></div>
    {model.report_binding.reasons.length > 0 && <p className="mb-2 text-xs text-ink-2">Evaluation binding limits: {model.report_binding.reasons.join(" · ")}</p>}
    {model.gate.blockers.length > 0 && <p className="mb-3 text-xs text-ink-2">Serving blockers: {model.gate.blockers.join(" · ")}</p>}
    <dl className="grid grid-cols-2 gap-3 text-xs"><div><dt className="text-ink-3">Recorded test units</dt><dd className="mt-1 font-semibold">{model.test_n ?? "Not recorded"}</dd></div><div><dt className="text-ink-3">Recorded test patients</dt><dd className="mt-1 font-semibold">{model.test_patients ?? "Not recorded"}</dd></div></dl>
    <table className="mt-4 w-full text-left text-xs"><caption className="sr-only">Saved evaluation metrics</caption><thead><tr className="border-b border-line text-ink-3"><th className="py-2">Metric / count</th><th>Recorded value</th></tr></thead><tbody>{numeric(model.metrics).map(([key, value]) => <tr key={key} className="border-b border-line"><td className="py-2">{humanize(key)}</td><td className="font-mono">{Number.isInteger(value) ? value : value.toFixed(5)}</td></tr>)}</tbody></table>
    <details className="mt-3 text-xs"><summary className="cursor-pointer text-accent-text">Artifact identity, thresholds & uncertainty</summary><dl className="mt-2 space-y-2">{[["Checkpoint SHA-256", model.checkpoint_sha256], ["Evaluation SHA-256", model.evaluation_sha256], ["Dataset version", model.dataset_version], ["Preprocessing", model.preprocessing_version]].map(([key, value]) => <div key={key}><dt className="text-ink-3">{key}</dt><dd className="break-all font-mono text-[10px]">{value ?? "Unavailable"}</dd></div>)}</dl><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-[10px]">{JSON.stringify({ calibration: model.calibration, thresholds: model.decision_thresholds, confidence_intervals_95: model.confidence_intervals_95, diagnostics_present: model.available_diagnostics ?? [] }, null, 2)}</pre></details>
    <Link to={`/validation?model=${encodeURIComponent(model.model_id)}`} className="mt-3 inline-block text-xs text-accent-text">Open task-specific evaluation figures →</Link>
    <div className="mt-3"><Button size="sm" aria-expanded={diagnostics} onClick={() => setDiagnostics(!diagnostics)}>{diagnostics ? "Hide" : "Show"} computed diagnostics</Button>{diagnostics && <Suspense fallback={<LoadingBlock label="Loading diagnostics" />}><Diagnostics key={model.model_id} modelId={model.model_id} /></Suspense>}</div>
  </Card>;
}

export default function ModelArenaPage() {
  const data = useAsync(() => universalJson<{ models: Model[]; notice: string }>("/universal/arena/models"), []);
  const [leftId, setLeft] = useState("ptbxl_ecg_baseline");
  const [rightId, setRight] = useState("ptbxl_ecg_demographic_fusion");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestTicket = useRef(0);
  const models = data.data?.models ?? [];
  const left = models.find((m) => m.model_id === leftId);
  const right = models.find((m) => m.model_id === rightId);
  const update = (side: "left" | "right", value: string) => { requestTicket.current += 1; (side === "left" ? setLeft : setRight)(value); setComparison(null); setError(null); setBusy(false); };
  async function compare() {
    const ticket = ++requestTicket.current;
    setBusy(true); setError(null); setComparison(null);
    try { const response = await universalJson<Comparison>("/universal/arena/compare", { method: "POST", body: JSON.stringify({ left_id: leftId, right_id: rightId }) }); if (ticket === requestTicket.current) setComparison(response); }
    catch (failure) { if (ticket === requestTicket.current) setError(errorMessage(failure)); } finally { if (ticket === requestTicket.current) setBusy(false); }
  }
  const chart = comparison ? Object.entries(comparison.right_minus_left).filter(([key]) => !/n$|patients|positives/.test(key)).map(([key, delta]) => ({ metric: humanize(key), delta })) : [];
  return <>
    <PageHeader eyebrow="AI research laboratory" title="Model Arena" description="Compare checkpoint-specific research evidence with explicit cohort checks. Saved evaluation results remain separate from current inference and clinical validation." actions={<Link to="/universal" className="text-sm text-accent-text">Return to Command Center →</Link>} />
    <div className="mb-4 flex flex-wrap gap-2"><Badge tone="accent"><BarChart3 size={12} /> Artifact-backed results</Badge><Badge>Read only</Badge><Badge>No test-set tuning</Badge></div>
    {data.loading && <LoadingBlock label="Inspecting registered evaluations" />}{data.error && <ErrorBlock message={data.error} onRetry={data.reload} />}
    <Card title="Choose a baseline and candidate" eyebrow="Common task · labels · dataset · labelled patient records">
      <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">{([["left", leftId], ["right", rightId]] as const).map(([side, value]) => <label key={side} className="text-xs text-ink-2">{side === "left" ? "Baseline" : "Candidate"}<SelectInput aria-label={side === "left" ? "Baseline model" : "Candidate model"} value={value} onChange={(e) => update(side, e.target.value)}>{models.map((model) => <option key={model.model_id} value={model.model_id}>{model.display_name}</option>)}</SelectInput></label>)}<Button variant="primary" className="self-end" disabled={!left || !right} loading={busy} onClick={() => void compare()}>Check comparability</Button></div>
      <p className="mt-3 text-xs leading-5 text-ink-3">A difference is displayed only for the same dataset version, task, ordered labels and identical held-out record/patient/ground-truth tuples. This check does not prove statistical significance or remove dataset bias. Rights and serving eligibility are displayed separately.</p>
    </Card>
    {error && <div className="mt-4"><ErrorBlock message={error} /></div>}
    {comparison && <Card className="mt-4" title="Comparison verdict"><StatusBadge status={comparison.status} />{comparison.reasons.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-ink-2">{comparison.reasons.map((reason) => <li key={reason}>{humanize(reason)}</li>)}</ul>}
      {chart.length > 0 && <><p className="mt-3 text-xs text-ink-2">Candidate minus baseline on {comparison.cohorts.left.n} matched labelled records. Metric direction depends on the task.</p><div className="mt-3 h-64" role="img" aria-label="Recorded metric differences, candidate minus baseline"><ResponsiveContainer width="100%" height="100%"><BarChart data={chart} layout="vertical" margin={{ left: 20, right: 20 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" /><YAxis type="category" dataKey="metric" width={170} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="delta" fill="var(--mt-accent)" /></BarChart></ResponsiveContainer></div><table className="mt-2 w-full text-left text-xs"><caption className="sr-only">Metric difference values</caption><tbody>{chart.map((row) => <tr key={row.metric}><th className="py-1 font-normal">{row.metric}</th><td className="font-mono">{row.delta.toFixed(6)}</td></tr>)}</tbody></table></>}
      <p className="mt-3 text-xs text-ink-3">{humanize(comparison.significance)}. The previously recorded paired ECG fusion experiment does not establish superiority; its difference interval includes zero. Inspect that experiment in Validation Center.</p>
    </Card>}
    {comparison && "paired_statistics" in comparison && <Card className="mt-4" title="Patient-cluster paired comparison"><pre className="overflow-auto whitespace-pre-wrap break-all text-xs text-ink-2">{JSON.stringify(comparison.paired_statistics, null, 2)}</pre></Card>}
    <div className="mt-4 grid items-start gap-4 xl:grid-cols-2">{left && <EvaluationCard key={`left:${left.model_id}`} model={left} />}{right && <EvaluationCard key={`right:${right.model_id}`} model={right} />}</div>
    <div className="mt-4"><Suspense fallback={<LoadingBlock label="Loading matched record explorer" />}><MatchedRecords /></Suspense></div>
    <p className="mt-4 text-xs leading-5 text-ink-3">{data.data?.notice} ROC, precision–recall, confusion and reliability figures are shown in the task-specific evaluator only when supported by actual saved data. Missing curves are not interpolated from a headline score.</p>
  </>;
}
