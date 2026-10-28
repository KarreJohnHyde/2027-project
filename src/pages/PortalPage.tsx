import { useState } from "react";
import { Download, UserPlus, X } from "lucide-react";
import { Button, Card, EmptyState, ErrorBlock, LoadingBlock, PageHeader, SelectInput, StatusBadge, Table, TextInput } from "../components/ui";
import { api, type PortalRecord } from "../services/api";
import { errorMessage, formatDate, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";

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
  const [chosen, setChosen] = useState<number | null>(null);
  const active = cases.data?.find((item) => item.case_id === chosen) ?? cases.data?.[0] ?? null;
  const record = useAsync(() => (active ? api.getPortalRecord(active.case_id) : Promise.resolve(null)), [active?.case_id]);
  const [downloadError, setDownloadError] = useState<string | null>(null);

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
      <PageHeader eyebrow="My record" title="Your health record" description="Documents from your care team and results they have reviewed. This page is not a diagnosis; ask your care team about anything you see here." />
      {cases.loading ? <LoadingBlock label="Loading" /> : cases.error ? <ErrorBlock message={cases.error} onRetry={cases.reload} /> : !active ? (
        <EmptyState title="No record is shared with you yet" detail="Your clinician links your account to your record. Give them your username, shown under Settings." />
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
              </Card>
              {record.data.relationship === "PATIENT" && <Caregivers caseId={active.case_id} />}
            </>
          )}
        </div>
      )}
    </>
  );
}
