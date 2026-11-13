import { useEffect } from "react";
import { api, type User } from "../services/api";
import { formatBytes, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";
import { Card, StatusBadge } from "./ui";

/** The server shows workstation research jobs to verified administrators, clinicians and researchers only. */
function mayViewResearchJobs(user: User | null): boolean {
  return user !== null && ["admin", "clinician", "researcher"].includes(user.role) && user.verification_status === "VERIFIED";
}

export default function ResearchJobProgress() {
  const permitted = useWorkspace((state) => mayViewResearchJobs(state.user));
  // Other accounts do not ask for it at all (the request would only be refused).
  return permitted ? <ResearchJobList /> : null;
}

function ResearchJobList() {
  const { data, error, reload } = useAsync(() => api.getResearchJobs(), []);
  useEffect(() => {
    if (error) return;
    const timer = window.setInterval(reload, 10_000);
    return () => window.clearInterval(timer);
  }, [reload, error]);
  if (error || !data?.available) return null;
  return <Card title="Research job progress" eyebrow="Recorded events · refreshes every 10 seconds" className="mb-4">
    <p className="mb-3 text-xs text-ink-2">{data.scope}</p>
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{data.jobs.map((job) => <div key={job.id} className="rounded-lg border border-line p-3">
      <p className="mb-2 text-xs font-medium text-ink">{job.label}</p>
      <StatusBadge status={job.status} label={humanize(job.status)} />
      {job.expected != null && <p className="mt-2 text-xs text-ink-2">{job.completed ?? 0} / {job.expected} verified{job.failed ? ` · ${job.failed} need review` : ""}</p>}
      {job.transfer && <p className="mt-2 text-xs text-ink-2">{formatBytes(job.transfer.received_bytes)} / {formatBytes(job.transfer.expected_bytes)} received; verification pending</p>}
      {job.last_event_at && <p className="mt-1 text-[11px] text-ink-3">Last event: {new Date(job.last_event_at).toLocaleString()}</p>}
    </div>)}</div>
    <p className="mt-3 text-[11px] text-ink-3">{data.notice}</p>
  </Card>;
}
