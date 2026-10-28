import { useState, type FormEvent } from "react";
import { CalendarPlus, Play, Trash2, Upload, UserPlus } from "lucide-react";
import { CreateExaminationDialog } from "../components/CaseDialogs";
import { FindingCard } from "../components/FindingReview";
import { OrdersCard } from "../components/LabEntry";
import { Button, Card, ErrorBlock, Hash, PageHeader, SelectInput, StatusBadge, Table, TextInput } from "../components/ui";
import { api, type CaseMemberRole } from "../services/api";
import { errorMessage, formatBytes, formatDate, humanize } from "../lib/format";
import { navigate } from "../lib/router";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

function Members({ caseId, canManage }: { caseId: number; canManage: boolean }) {
  const members = useAsync(() => api.getCaseMembers(caseId), [caseId]);
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<CaseMemberRole>("VIEWER");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.addCaseMember(caseId, username.trim(), role);
      setUsername("");
      members.reload();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }
  async function remove(userId: number) {
    try {
      await api.removeCaseMember(caseId, userId);
      members.reload();
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  return (
    <div className="space-y-3">
      {(members.data ?? []).length === 0 ? <p className="text-sm text-ink-2">Only the creator (and administrators) can access this case.</p> : (
        <ul className="divide-y divide-line">
          {members.data!.map((member) => (
            <li key={member.user_id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <span className="min-w-0"><span className="font-medium text-ink">{member.full_name || member.username}</span> <span className="text-xs text-ink-3">@{member.username}</span></span>
              <span className="flex items-center gap-2"><StatusBadge status={member.role} label={humanize(member.role)} />{canManage && <button type="button" aria-label={`Revoke ${member.username}`} onClick={() => void remove(member.user_id)} className="rounded p-1 text-ink-3 hover:text-critical-text"><Trash2 size={14} /></button>}</span>
            </li>
          ))}
        </ul>
      )}
      {canManage && (
        <form onSubmit={add} className="flex flex-wrap gap-2">
          <TextInput aria-label="Username to share with" placeholder="Username" value={username} onChange={(event) => setUsername(event.target.value)} required className="min-w-0 flex-1" />
          <div className="w-36"><SelectInput aria-label="Role" value={role} onChange={(event) => setRole(event.target.value as CaseMemberRole)}><option value="VIEWER">Viewer</option><option value="EDITOR">Editor</option><option value="PATIENT">Patient (portal)</option><option value="CAREGIVER">Caregiver (portal)</option></SelectInput></div>
          <Button type="submit" icon={UserPlus} loading={busy}>Share</Button>
        </form>
      )}
      {error && <ErrorBlock message={error} />}
      <p className="text-[11px] leading-4 text-ink-3">Viewers can read evidence; editors can also upload, process and review. Every grant and revocation is audited.</p>
    </div>
  );
}

export default function CaseWorkspacePage() {
  const selected = useSelectedCase()!;
  const user = useWorkspace((state) => state.user);
  const evidence = useWorkspace((state) => state.evidence);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const setNotice = useWorkspace((state) => state.setNotice);
  const [examDialog, setExamDialog] = useState(false);
  const [busyUpload, setBusyUpload] = useState<number | null>(null);
  const [versionTarget, setVersionTarget] = useState<number | null>(null);
  const [versionReason, setVersionReason] = useState("");
  const [withdrawTarget, setWithdrawTarget] = useState<number | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const examinations = [...selected.examinations].sort((left, right) => left.exam_date.localeCompare(right.exam_date));
  const jobsByUpload = new Map<number, number>();
  evidence.jobs.forEach((job) => jobsByUpload.set(job.upload_id, (jobsByUpload.get(job.upload_id) ?? 0) + 1));
  const modelVersions = [...new Map(evidence.jobs.map((job) => [`${job.model_name}|${job.model_version}|${job.preprocessing_version}`, job])).values()];
  const canManage = user?.role === "admin" || selected.created_by_id === user?.id;

  async function toggleAssociation(uploadId: number, associated: boolean) {
    try {
      await api.updateFileAssociation(uploadId, associated, associated ? "Re-associated by reviewer" : "Marked unassociated by reviewer");
      await loadEvidence();
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    }
  }

  async function replaceVersion(uploadId: number, file: File | undefined) {
    const reason = versionReason.trim();
    if (!file || reason.length < 3) return;
    try {
      const replacement = await api.uploadFileVersion(uploadId, file, reason);
      setNotice({ tone: "success", text: `Version ${replacement.version_number ?? 2} recorded; the earlier version is kept and marked superseded.` });
      setVersionTarget(null);
      setVersionReason("");
      await loadEvidence();
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    }
  }

  async function withdraw(uploadId: number) {
    const reason = withdrawReason.trim();
    if (reason.length < 3) return;
    try {
      await api.withdrawFile(uploadId, reason);
      setNotice({ tone: "success", text: "File withdrawn. Its record and derived evidence stay for provenance; its content is no longer served." });
      setWithdrawTarget(null);
      setWithdrawReason("");
      await loadEvidence();
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    }
  }

  async function process(uploadId: number) {
    setBusyUpload(uploadId);
    try {
      const job = await api.createAnalysisJob(uploadId);
      setNotice({ tone: "success", text: `Job #${job.id} recorded as ${humanize(job.status)}.` });
      await loadEvidence();
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setBusyUpload(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Case Workspace"
        title={selected.pseudonymous_id}
        description={selected.description || "Pseudonymous research case. Clinical records, model interpretation and unsupported information are kept visibly distinct."}
        actions={<><Button icon={CalendarPlus} onClick={() => setExamDialog(true)}>Add examination</Button><Button variant="primary" icon={Upload} onClick={() => navigate("/upload")}>Add evidence</Button></>}
      />
      <div className="grid gap-4 xl:grid-cols-[1fr_1.6fr]">
        <Card title="Examination timeline" eyebrow={`${examinations.length} dated`}>
          {examinations.length === 0 ? <p className="text-sm text-ink-2">No examinations. Add one to enable longitudinal comparison.</p> : (
            <ol className="relative space-y-3 border-l border-line pl-4">
              {examinations.map((exam) => {
                const linked = evidence.uploads.filter((upload) => upload.examination_id === exam.id).length;
                return (
                  <li key={exam.id} className="relative">
                    <span aria-hidden className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-surface bg-accent" />
                    <p className="text-sm font-medium text-ink">{formatDate(exam.exam_date)} · {humanize(exam.modality)}</p>
                    <p className="text-xs text-ink-2">{exam.clinical_indication || "No indication recorded"} · {linked} linked upload{linked === 1 ? "" : "s"}</p>
                  </li>
                );
              })}
            </ol>
          )}
        </Card>
        <Card title="Uploads" eyebrow="Content-addressed storage" padded={false}>
          {evidence.uploads.length === 0 ? <p className="p-4 text-sm text-ink-2">No uploads yet.</p> : (
            <Table headers={["File", "Modality", "SHA-256", "Examination", "Association", ""]}>
              {evidence.uploads.map((upload) => {
                const exam = selected.examinations.find((item) => item.id === upload.examination_id);
                return (
                  <tr key={upload.id} data-testid="upload-record">
                    <td className="max-w-[12rem]">
                      <p className="truncate font-medium text-ink" title={upload.filename}>{upload.filename}</p>
                      <p className="text-[11px] text-ink-3">{formatBytes(upload.file_size_bytes)} · {formatDate(upload.created_at)}{(upload.version_number ?? 1) > 1 ? ` · v${upload.version_number} of #${upload.supersedes_file_id}` : ""}</p>
                      {upload.superseded_by_file_id && <p className="text-[11px] text-ink-3">Superseded by #{upload.superseded_by_file_id}; kept for provenance</p>}
                      {upload.withdrawn_at && <p className="text-[11px] text-ink-3">Withdrawn {formatDate(upload.withdrawn_at)}: {upload.withdrawal_reason}</p>}
                    </td>
                    <td><StatusBadge status={upload.modality} /></td>
                    <td><Hash value={upload.file_hash} /></td>
                    <td className="text-xs text-ink-2">{exam ? formatDate(exam.exam_date) : "—"}</td>
                    <td>
                      <SelectInput aria-label={`Association for ${upload.filename}`} value={upload.is_associated ? "1" : "0"} onChange={(event) => void toggleAssociation(upload.id, event.target.value === "1")} className="h-8 text-xs">
                        <option value="1">Case-bound</option>
                        <option value="0">Unassociated</option>
                      </SelectInput>
                    </td>
                    <td className="space-y-1.5">
                      <Button size="sm" icon={Play} loading={busyUpload === upload.id} disabled={!upload.is_associated} onClick={() => void process(upload.id)}>{jobsByUpload.get(upload.id) ? "Re-run" : "Process"}</Button>
                      {!upload.withdrawn_at && !upload.superseded_by_file_id && (
                        <div className="flex flex-wrap gap-1.5">
                          <Button size="sm" variant="ghost" onClick={() => { setVersionTarget(versionTarget === upload.id ? null : upload.id); setWithdrawTarget(null); }}>New version</Button>
                          <Button size="sm" variant="ghost" onClick={() => { setWithdrawTarget(withdrawTarget === upload.id ? null : upload.id); setVersionTarget(null); }}>Withdraw</Button>
                        </div>
                      )}
                      {versionTarget === upload.id && (
                        <div className="space-y-1.5">
                          <TextInput aria-label={`Reason for a new version of ${upload.filename}`} placeholder="Reason (required)" value={versionReason} onChange={(event) => setVersionReason(event.target.value)} className="h-8 text-xs" />
                          <input aria-label={`New version file for ${upload.filename}`} type="file" disabled={versionReason.trim().length < 3} className="block w-full text-xs" onChange={(event) => void replaceVersion(upload.id, event.target.files?.[0])} />
                        </div>
                      )}
                      {withdrawTarget === upload.id && (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <TextInput aria-label={`Reason for withdrawing ${upload.filename}`} placeholder="Reason (required)" value={withdrawReason} onChange={(event) => setWithdrawReason(event.target.value)} className="h-8 text-xs" />
                          <Button size="sm" variant="danger" disabled={withdrawReason.trim().length < 3} onClick={() => void withdraw(upload.id)}>Confirm withdrawal</Button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </Table>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Card title="Processing history" eyebrow="Persisted jobs" padded={false}>
          {evidence.jobs.length === 0 ? <p className="p-4 text-sm text-ink-2">No jobs recorded.</p> : (
            <Table headers={["Job", "Status", "Processor", "Preprocessing", "Time", "Message"]} dense>
              {evidence.jobs.map((job) => (
                <tr key={job.id}>
                  <td className="tabular">#{job.id}</td>
                  <td><StatusBadge status={job.status} /></td>
                  <td className="text-xs"><span className="font-medium text-ink">{job.model_name}</span><span className="block font-mono text-[11px] text-ink-3">{job.model_version}</span></td>
                  <td className="max-w-[12rem] font-mono text-[11px] text-ink-2">{job.preprocessing_version}</td>
                  <td className="whitespace-nowrap text-xs text-ink-2">{job.execution_time_ms === null ? "—" : `${job.execution_time_ms} ms`}</td>
                  <td className="max-w-[16rem] text-xs text-ink-2">{job.error_message ?? "—"}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <div className="space-y-4">
          <Card title="Processor versions used">
            {modelVersions.length === 0 ? <p className="text-sm text-ink-2">None yet.</p> : (
              <ul className="space-y-1.5 text-xs">{modelVersions.map((job) => <li key={job.id}><span className="font-medium text-ink">{job.model_name}</span> <code className="text-ink-2">{job.model_version}</code><span className="block text-ink-3">{job.preprocessing_version}</span></li>)}</ul>
            )}
          </Card>
          <Card title="Case sharing"><Members caseId={selected.id} canManage={canManage} /></Card>
        </div>
      </div>

      <div className="mt-4"><OrdersCard caseId={selected.id} /></div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Findings and review" eyebrow="Append-only clinician review">
          {evidence.findings.length === 0 ? <p className="text-sm text-ink-2">No findings. Process an upload to create one.</p> : (
            <div className="space-y-3">{evidence.findings.map((finding) => <FindingCard key={finding.id} finding={finding} uploads={evidence.uploads} jobs={evidence.jobs} measurements={evidence.measurements} />)}</div>
          )}
        </Card>
        <Card title="Audit trail" eyebrow="Metadata only" padded={false}>
          {evidence.provenance.length === 0 ? <p className="p-4 text-sm text-ink-2">No events.</p> : (
            <div className="max-h-[36rem] overflow-y-auto">
              <Table headers={["Event", "Resource", "Time"]} dense>
                {evidence.provenance.map((event) => (
                  <tr key={event.id} data-testid="audit-event">
                    <td><span className="font-medium text-ink">{humanize(event.action)}</span>{event.details && <code className="mt-0.5 block max-w-md truncate text-[11px] text-ink-3" title={JSON.stringify(event.details)}>{JSON.stringify(event.details)}</code>}</td>
                    <td className="whitespace-nowrap text-xs text-ink-2">{event.resource_type} #{event.resource_id ?? "—"}</td>
                    <td className="whitespace-nowrap text-xs text-ink-2">{formatDate(event.timestamp, true)}</td>
                  </tr>
                ))}
              </Table>
            </div>
          )}
        </Card>
      </div>
      {examDialog && <CreateExaminationDialog caseRecord={selected} onClose={() => setExamDialog(false)} />}
    </>
  );
}
