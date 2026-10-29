import { useRef, useState } from "react";
import { Download, FileUp, Plus, UserPlus, X } from "lucide-react";
import { Button, Card, EmptyState, ErrorBlock, LoadingBlock, PageHeader, SelectInput, StatusBadge, Table, TextInput } from "../components/ui";
import { api, type PortalRecord } from "../services/api";
import { errorMessage, formatDate, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";

const PERSONAL_UPLOAD_ACCEPT = ".txt,.md,.csv,.json,.hl7,.pdf,.docx,.xlsx,.dcm,.nii,.gz,.nrrd,.mha,.png,.jpg,.jpeg,.bmp,.hea,.dat,.edf,.bdf";

function interval(result: PortalRecord["results"][number]): string {
  if (result.reference_low === null && result.reference_high === null) return "Not printed on the report";
  if (result.reference_low === null) return `up to ${formatNumber(result.reference_high, 3)}`;
  if (result.reference_high === null) return `${formatNumber(result.reference_low, 3)} or more`;
  return `${formatNumber(result.reference_low, 3)} – ${formatNumber(result.reference_high, 3)}`;
}

function Caregivers({ caseId }: { caseId: number }) {
  const list = useAsync(() => api.getPortalCaregivers(caseId), [caseId]);
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function add() {
    setError(null);
    try {
      await api.addPortalCaregiver(caseId, username.trim());
      setUsername("");
      list.reload();
    } catch (failure) {
      setError(errorMessage(failure));
    }
  }
  async function remove(userId: number) {
    setError(null);
    try {
      await api.removePortalCaregiver(caseId, userId);
      list.reload();
    } catch (failure) {
      setError(errorMessage(failure));
    }
  }
  return (
    <Card title="People who can see this record" eyebrow="You decide">
      <p className="mb-3 text-xs text-ink-2">A caregiver sees the same documents and reviewed results as you, and cannot add anyone else. You can remove access at any time.</p>
      {list.data && list.data.length > 0 ? (
        <ul className="mb-3 space-y-1 text-sm">
          {list.data.map((person) => (
            <li key={person.user_id} className="flex items-center justify-between gap-2">
              <span>{person.username} <span className="text-xs text-ink-3">since {formatDate(person.since)}</span></span>
              <button type="button" aria-label={`Remove ${person.username}`} onClick={() => void remove(person.user_id)} className="rounded p-1 text-ink-3 hover:text-critical-text"><X size={14} /></button>
            </li>
          ))}
        </ul>
      ) : <p className="mb-3 text-xs text-ink-3">No caregiver has access.</p>}
      <form className="flex items-end gap-2" onSubmit={(event) => { event.preventDefault(); void add(); }}>
        <label className="flex-1 text-xs text-ink-2">Caregiver's username<TextInput value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <Button size="sm" type="submit" icon={UserPlus} disabled={!username.trim()}>Give access</Button>
      </form>
      {error && <p role="alert" className="mt-2 text-xs text-critical-text">{error}</p>}
    </Card>
  );
}

/** Read-only view of one's own record for patients and caregivers. */
export default function PortalPage() {
  const cases = useAsync(() => api.getPortalCases(), []);
  const user = useWorkspace((state) => state.user);
  const [chosen, setChosen] = useState<number | null>(null);
  const active = cases.data?.find((item) => item.case_id === chosen) ?? cases.data?.[0] ?? null;
  const record = useAsync(() => (active ? api.getPortalRecord(active.case_id) : Promise.resolve(null)), [active?.case_id]);
  const inputRef = useRef<HTMLInputElement>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [deidentified, setDeidentified] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const hasPersonalRecord = cases.data?.some((item) => item.relationship === "PATIENT") ?? false;

  async function createPersonalRecord() {
    setCreating(true);
    setCreateError(null);
    try {
      const personalRecord = await api.createPersonalPortalRecord();
      setChosen(personalRecord.case_id);
      cases.reload();
    } catch (failure) {
      setCreateError(errorMessage(failure));
    } finally {
      setCreating(false);
    }
  }

  async function uploadDocument() {
    if (!active || active.relationship !== "PATIENT" || !selectedFile || !deidentified) return;
    setUploading(true);
    setUploadProgress(0);
    setUploadError(null);
    try {
      await api.uploadPortalDocumentWithProgress(active.case_id, selectedFile, setUploadProgress);
      setSelectedFile(null);
      setDeidentified(false);
      if (inputRef.current) inputRef.current.value = "";
      record.reload();
    } catch (failure) {
      setUploadError(errorMessage(failure));
    } finally {
      setUploading(false);
    }
  }

  async function download(documentId: number, filename: string) {
    if (!active) return;
    setDownloadError(null);
    try {
      const url = await api.downloadPortalDocument(active.case_id, documentId);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (failure) {
      setDownloadError(errorMessage(failure));
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="My record"
        title="Your health record"
        description="Your private documents and results reviewed by your care team. This page is not a diagnosis; ask your care team about anything you see here."
        actions={active && user?.role === "public" && !hasPersonalRecord ? <Button icon={Plus} loading={creating} onClick={() => void createPersonalRecord()}>Create private record</Button> : undefined}
      />
      {createError && <ErrorBlock message={createError} />}
      {cases.loading || cases.data === null ? <LoadingBlock label="Loading" /> : cases.error ? <ErrorBlock message={cases.error} onRetry={cases.reload} /> : !active ? (
        <EmptyState
          title="No personal health record yet"
          detail="Create a private record to store your own de-identified documents. Only this account can access it unless you explicitly share with a caregiver."
          action={user?.role === "public" ? <Button icon={Plus} loading={creating} onClick={() => void createPersonalRecord()}>Create private record</Button> : undefined}
        />
      ) : (
        <div className="space-y-4">
          {(cases.data?.length ?? 0) > 1 && (
            <div className="w-72">
              <SelectInput aria-label="Record" value={active.case_id} onChange={(event) => setChosen(Number(event.target.value))}>
                {cases.data?.map((item) => <option key={item.case_id} value={item.case_id}>{item.record} ({humanize(item.relationship)})</option>)}
              </SelectInput>
            </div>
          )}
          {record.loading && <LoadingBlock label="Loading your record" />}
          {record.error && <ErrorBlock message={record.error} onRetry={record.reload} />}
          {record.data && (
            <>
              <Card title="Reviewed results" eyebrow={record.data.relationship === "CAREGIVER" ? "Shared with you as a caregiver" : "Your results"} padded={false}>
                {record.data.results.length === 0 ? (
                  <p className="p-4 text-sm text-ink-2">No reviewed results yet. {record.data.notice}</p>
                ) : (
                  <>
                    <Table headers={["Test", "Result", "Range printed on the report", "Flag on the report", "Date"]}>
                      {record.data.results.map((result, index) => (
                        <tr key={index}>
                          <td>{result.name}</td>
                          <td className="tabular">{result.comparator !== "=" ? result.comparator : ""}{formatNumber(result.value, 4)} {result.unit}</td>
                          <td className="tabular">{interval(result)}{result.reference_low !== null || result.reference_high !== null ? ` ${result.unit}` : ""}</td>
                          <td>{result.documented_flag ? <StatusBadge status={result.documented_flag} label={humanize(result.documented_flag)} /> : "—"}</td>
                          <td>{result.documented_date ?? "Not documented"}</td>
                        </tr>
                      ))}
                    </Table>
                    <p className="p-4 text-xs text-ink-3">{record.data.notice}</p>
                  </>
                )}
              </Card>
              <Card title="Documents">
                {downloadError && <p role="alert" className="mb-2 text-xs text-critical-text">{downloadError}</p>}
                {uploadError && <ErrorBlock message={uploadError} />}
                {record.data.documents.length === 0 ? <p className="text-sm text-ink-2">No documents.</p> : (
                  <ul className="space-y-1 text-sm">
                    {record.data.documents.map((item) => (
                      <li key={item.id} className="flex items-center justify-between gap-2">
                        <span className="truncate">{item.filename}</span>
                        <Button size="sm" icon={Download} onClick={() => void download(item.id, item.filename)}>Download</Button>
                      </li>
                    ))}
                  </ul>
                )}
                {record.data.relationship === "PATIENT" && (
                  <div className="mt-4 border-t border-line pt-4">
                    <p className="text-sm font-medium text-ink">Add a document</p>
                    <p className="mt-1 text-xs leading-5 text-ink-3">Supported reports and medical files up to the server's upload limits. Remove names, dates of birth, addresses, and record numbers before uploading. Unreviewed uploads are not shown as clinical results.</p>
                    <input
                      ref={inputRef}
                      type="file"
                      accept={PERSONAL_UPLOAD_ACCEPT}
                      className="sr-only"
                      aria-label="Choose a de-identified document"
                      onChange={(event) => {
                        setSelectedFile(event.target.files?.[0] ?? null);
                        setDeidentified(false);
                        setUploadError(null);
                      }}
                    />
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Button type="button" variant="secondary" icon={FileUp} onClick={() => inputRef.current?.click()} disabled={uploading}>Choose file</Button>
                      {selectedFile && <span className="max-w-full truncate text-xs text-ink-2">{selectedFile.name}</span>}
                    </div>
                    <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-ink-2">
                      <input
                        type="checkbox"
                        checked={deidentified}
                        onChange={(event) => setDeidentified(event.target.checked)}
                        className="mt-1 accent-accent"
                      />
                      <span>I confirm this document has been de-identified and is appropriate to store in this research system.</span>
                    </label>
                    {uploading && (
                      <div className="mt-3" role="status" aria-label="Upload progress">
                        <div className="h-1.5 overflow-hidden rounded bg-surface-3">
                          <div className="h-full bg-accent transition-[width]" style={{ width: `${Math.round(uploadProgress * 100)}%` }} />
                        </div>
                        <p className="mt-1 text-[11px] tabular text-ink-3">{Math.round(uploadProgress * 100)}% uploaded</p>
                      </div>
                    )}
                    <Button type="button" className="mt-3" icon={FileUp} loading={uploading} disabled={!selectedFile || !deidentified} onClick={() => void uploadDocument()}>Upload document</Button>
                  </div>
                )}
              </Card>
              {record.data.relationship === "PATIENT" && <Caregivers caseId={active.case_id} />}
            </>
          )}
        </div>
      )}
    </>
  );
}
