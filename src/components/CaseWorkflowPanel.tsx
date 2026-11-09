import { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { api } from "../services/api";
import { errorMessage, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { Link } from "../lib/router";
import { useWorkspace } from "../state/workspace";
import { Button, Card, ErrorBlock, LoadingBlock, StatusBadge } from "./ui";

export default function CaseWorkflowPanel({ caseId }: { caseId: number }) {
  const revision = useWorkspace((state) => state.evidenceVersion);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const workflow = useAsync(() => api.getCaseWorkflow(caseId), [caseId, revision]);
  const data = !workflow.loading && workflow.data?.case_id === caseId ? workflow.data : null;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);
  const processing = Boolean(workflow.data?.active_report_job_ids.length);
  const reloadWorkflow = workflow.reload;
  useEffect(() => {
    if (!processing) return;
    const timer = window.setTimeout(() => { reloadWorkflow(); void loadEvidence(); }, 2500);
    return () => window.clearTimeout(timer);
  }, [processing, workflow.data, reloadWorkflow, loadEvidence]);

  async function process() {
    setBusy(true); setError(null); setOutcome(null);
    try {
      const result = await api.processPendingReports(caseId);
      setOutcome(result.results.length ? result.results.map((row) => `Upload #${row.upload_id}: ${humanize(row.status)}${row.reason ? ` — ${row.reason}` : ""}`).join(" · ") : "No unprocessed report sources remain.");
      await loadEvidence(); workflow.reload();
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <Card title="Integrated case workflow" eyebrow="One case · shared source and review boundaries" className="mb-4"
    actions={<><Button size="sm" icon={RefreshCw} onClick={workflow.reload}>Refresh status</Button><Button size="sm" icon={Play} loading={busy} disabled={!data?.pending_report_upload_ids.length || processing} onClick={() => void process()}>Process pending reports</Button></>}>
    {error && <ErrorBlock message={error} />}
    {workflow.error && <ErrorBlock message={workflow.error} onRetry={workflow.reload} />}
    {outcome && <p role="status" className="mb-3 text-xs text-ink-2">{outcome}</p>}
    {workflow.loading ? <LoadingBlock label="Reading current case workflow" /> : data && <>
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-ink-2"><StatusBadge status={data.mode === "EMPTY" ? "NO_EVIDENCE" : "AVAILABLE"} label={data.mode === "SCAN_ONLY" ? "Scan / signal only" : humanize(data.mode)} /><span>{data.sources.length} active sources</span><span>{data.examinations.length} dated examinations</span><span>{data.unlinked_upload_ids.length} sources need examination links</span></div>
      <p className="mb-4 text-xs text-ink-2">Mode follows the current uploads. Each request processes up to 10 unique pending reports through the existing processor and queue. Imaging model selection, source review and examination identity remain explicit steps.</p>
      <ol className="grid gap-3 lg:grid-cols-2">{data.stages.map((stage, index) => <li key={stage.id} className="rounded-lg border border-line p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><Link to={stage.path} className="text-sm font-medium text-accent-text hover:underline">{index + 1}. {stage.title}</Link><StatusBadge status={stage.status} /></div>
        <p className="mt-2 text-xs leading-5 text-ink-2">{stage.detail}</p>
      </li>)}</ol>
      <p className="mt-3 text-[11px] text-ink-3">{data.version} · Workflow status is a live evidence inventory. It is not clinical validation or a disease probability.</p>
    </>}
  </Card>;
}
