import { useState } from "react";
import { ClipboardCheck, Database, FileCheck2, RefreshCw, ShieldAlert } from "lucide-react";
import { universalJson } from "../services/universal";
import { useAsync } from "../lib/useAsync";
import { ErrorBlock } from "./ui";
import { useWorkspace } from "../state/workspace";

type Metric = { metric_id: string; label: string; value: number | null; unit: string; scope: string };
type Source = { source_id: string; label: string; sha256: string | null; status: string };
type Readiness = {
  status: string; recorded_at: string | null; metrics: Metric[];
  live_model_counts: Record<string, number | null>;
  live_matched_cohort: { status: string; records: number | null; patients: number | null; snapshot_sha256: string | null };
  sources: Source[]; limitations: string[]; notice: string;
  independent_reports: { status: string; visibility: string; documents: number | null; pages: number | null; readable_pages: number | null; unreadable_pages: number | null; annotated_fields: number | null; annotated_entities: number | null; independent_real_documents: number | null; independent_real_pages: number | null; full_report_validation: string; metrics: Metric[]; sources: Source[]; notice: string };
};
const number = (value: number | null | undefined) => value == null ? "Not verified" : new Intl.NumberFormat().format(value);
const human = (value: string) => value.toLowerCase().replace(/_/g, " ");

function MetricTile({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: typeof Database }) {
  return <div className="min-w-0 rounded-lg border border-line bg-surface-2 p-3"><div className="flex items-center gap-2 text-xs text-ink-3"><Icon size={14} aria-hidden />{label}</div><p className="mt-2 break-words text-xl font-semibold tabular-nums text-ink">{value}</p><p className="mt-1 text-[11px] leading-4 text-ink-3">{detail}</p></div>;
}

function SourceList({ sources }: { sources: Source[] }) {
  const [copied, setCopied] = useState<string | null>(null);
  return <ul className="space-y-2" aria-label="Measured evidence source identities">{sources.map((source) => <li key={source.source_id} className="min-w-0 rounded border border-line p-2"><div className="flex flex-wrap items-start justify-between gap-2"><span className="text-xs font-medium text-ink">{source.label}</span>{source.sha256 && <button className="rounded border border-line px-2 py-1 text-[10px] text-ink-2 hover:bg-surface-2" aria-label={`${copied === source.source_id ? "Copied" : "Copy SHA-256"} for ${source.label}`} onClick={() => { void navigator.clipboard.writeText(source.sha256!).then(() => setCopied(source.source_id)).catch(() => setCopied(null)); }}>{copied === source.source_id ? "Copied" : "Copy SHA-256"}</button>}</div><p className="mt-1 text-[10px] text-ink-3">{human(source.status)}</p>{source.sha256 && <code className="mt-1 block break-all text-[10px] leading-4 text-ink-2">{source.sha256}</code>}</li>)}</ul>;
}

export default function ResearchReadinessPanel() {
  const account = useWorkspace((workspace) => `${workspace.user?.id ?? "none"}:${workspace.user?.role ?? "none"}:${workspace.user?.is_guest ?? false}`);
  const state = useAsync(async () => ({ account, payload: await universalJson<Readiness>("/universal/research/readiness") }), [account]);
  const data = state.data?.account === account ? state.data.payload : null;
  const value = (id: string) => data?.metrics.find((metric) => metric.metric_id === id)?.value;
  const independent = data?.independent_reports;
  const independentTitle = independent?.status === "PENDING_REFERENCE_IMPORT" ? "Pending reference import" : independent?.status === "PRIVATE_OPERATOR_EVALUATION" ? "Private operator evaluation" : independent?.status === "RECORDED_INDEPENDENT_EVALUATION" ? "Recorded independent run" : independent?.status === "SYNTHETIC_SOFTWARE_CONTROL" ? "Synthetic control only" : "Not verified";
  return <section className="min-w-0 space-y-3 rounded-xl border border-line bg-surface p-4" aria-labelledby="research-readiness-title" data-testid="research-readiness-panel">
    <div className="flex flex-wrap items-start justify-between gap-2"><div><h2 id="research-readiness-title" className="flex items-center gap-2 text-sm font-semibold text-ink"><ClipboardCheck size={16} aria-hidden />Measured results & readiness</h2><p className="mt-1 text-xs text-ink-3">Recorded engineering results, current source bindings and independent-report status.</p></div><button className="inline-flex items-center gap-1.5 rounded border border-line px-2 py-1.5 text-xs text-ink-2 hover:bg-surface-2 disabled:opacity-50" disabled={state.loading} onClick={state.reload}><RefreshCw size={12} aria-hidden className={state.loading ? "animate-spin" : ""} />Refresh evidence</button></div>
    {state.error && <ErrorBlock message={state.error} onRetry={state.reload} />}
    {state.loading && !data && <p role="status" className="text-xs text-ink-3">Verifying measured evidence and current capability gates…</p>}
    {data && <>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile label="Recorded backend run" value={`${number(value("backend_passed"))} passed`} detail={`${number(value("backend_skipped"))} skipped · committed run, not a fresh test execution`} icon={ClipboardCheck} />
        <MetricTile label="Current matched research cohort" value={data.live_matched_cohort.records != null ? `${number(data.live_matched_cohort.records)} records` : "Source binding unavailable"} detail={data.live_matched_cohort.patients != null ? `${number(data.live_matched_cohort.patients)} source-bound patients · no patient identifiers returned` : `${number(value("matched_records"))} records in committed evidence; not reverified here`} icon={Database} />
        <MetricTile label="Live research eligibility" value={`${number(data.live_model_counts.upload_runnable)} / ${number(data.live_model_counts.registry_models)}`} detail="Upload-runnable under current original-registry rights/checkpoint gates · no clinical activation" icon={ShieldAlert} />
        <MetricTile label="Independent full real reports" value={independentTitle} detail={independent?.independent_real_documents != null ? `${number(independent.independent_real_documents)} independent real documents · ${human(independent.full_report_validation)}` : "No accuracy is assigned before source and reference verification"} icon={FileCheck2} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-ink-3"><span>{number(value("anatomy_families"))} recorded anatomy families</span><span>{number(value("anatomy_nodes"))} source hierarchy entries</span><span className="rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-amber-800">Research evidence · clinical activation disabled</span></div>
      <p className="text-xs leading-5 text-ink-3">{data.notice}</p>
      <details className="rounded-lg border border-line p-3"><summary className="cursor-pointer text-xs font-medium text-ink">Measured checks & source identities</summary><p className="my-2 text-[11px] text-ink-3">Recorded evidence date: {data.recorded_at ? new Date(data.recorded_at).toLocaleString() : "Not available"}. Current gates and cohort bindings are checked separately on refresh.</p><dl className="mb-3 grid gap-x-4 gap-y-1 sm:grid-cols-2">{data.metrics.map((metric) => <div key={metric.metric_id} className="flex min-w-0 justify-between gap-3 text-xs"><dt className="text-ink-3">{metric.label}</dt><dd className="shrink-0 tabular-nums text-ink">{number(metric.value)} {metric.unit}</dd></div>)}</dl><SourceList sources={data.sources} /></details>
      <details className="rounded-lg border border-line p-3"><summary className="cursor-pointer text-xs font-medium text-ink">Independent-report evaluation & limitations</summary><p className="mt-2 text-xs leading-5 text-ink-2">{independent?.notice}</p>{independent?.documents != null && <p className="mt-2 text-[11px] text-ink-3">{number(independent.documents)} documents; {number(independent.pages)} pages; {number(independent.readable_pages)} readable; {number(independent.unreadable_pages)} unreadable. Annotated fields: {number(independent.annotated_fields)}. Annotated entities: {number(independent.annotated_entities)}.</p>}{independent?.metrics.length ? <div className="my-3 grid gap-2 sm:grid-cols-2">{independent.metrics.map((metric) => <div key={metric.metric_id} className="rounded border border-line p-2"><p className="text-[11px] text-ink-3">{metric.label}</p><p className="mt-1 font-mono text-sm text-ink">{metric.value == null ? "Not measured" : metric.value.toFixed(4)}</p></div>)}</div> : <p className="my-2 text-[11px] text-ink-3">No independent accuracy metric is disclosed in this view.</p>}{independent?.sources.length ? <SourceList sources={independent.sources} /> : null}<ul className="mt-3 space-y-2 text-xs leading-5 text-ink-3">{data.limitations.map((limitation) => <li className="flex gap-2" key={limitation}><span aria-hidden className="text-amber-700">•</span><span>{limitation}</span></li>)}</ul></details>
    </>}
  </section>;
}
