import { useMemo, useRef, useState, type DragEvent } from "react";
import { CheckCircle2, FileUp, Plus, Trash2, XCircle } from "lucide-react";
import { CreateExaminationDialog } from "../components/CaseDialogs";
import { Badge, Button, Card, Field, PageHeader, SelectInput, StatusBadge, Table } from "../components/ui";
import { api, type UploadedFile } from "../services/api";
import { errorMessage, formatBytes, formatDate, humanize } from "../lib/format";
import { Link } from "../lib/router";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

type Row = { id: string; file: File; status: "QUEUED" | "UPLOADING" | "STORED" | "PROCESSING" | "COMPLETED" | "ERROR"; progress: number; upload?: UploadedFile; jobStatus?: string; message?: string };

const ACCEPT = ".txt,.md,.csv,.json,.hl7,.pdf,.docx,.xlsx,.dcm,.nii,.gz,.nrrd,.mha,.png,.jpg,.jpeg,.bmp,.hea,.dat,.edf,.bdf";

export default function UploadCenterPage() {
  const selected = useSelectedCase()!;
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const modalities = useAsync(() => api.getModalities(), []);
  const inputRef = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [examinationId, setExaminationId] = useState<number | "">("");
  const [attested, setAttested] = useState(false);
  const [sameCase, setSameCase] = useState(false);
  const [process, setProcess] = useState(true);
  const [busy, setBusy] = useState(false);
  const [examDialog, setExamDialog] = useState(false);
  const examinations = useMemo(() => [...selected.examinations].sort((left, right) => left.exam_date.localeCompare(right.exam_date)), [selected.examinations]);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const next = [...list].map((file, index) => ({ id: `${Date.now()}-${index}-${file.name}`, file, status: "QUEUED" as const, progress: 0 }));
    setRows((current) => [...current, ...next]);
    setSameCase(false);
  }

  function update(id: string, patch: Partial<Row>) {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }

  async function run() {
    setBusy(true);
    for (const row of rows.filter((item) => item.status === "QUEUED" || item.status === "ERROR")) {
      update(row.id, { status: "UPLOADING", progress: 0, message: undefined });
      try {
        const upload = await api.uploadFileWithProgress(selected.id, row.file, {
          deidentified: true,
          isAssociated: true,
          ...(examinationId !== "" ? { examinationId } : {}),
          associationNotes: "Uploaded through the MedTwin upload center with case-match confirmation",
        }, (progress) => update(row.id, { progress }));
        update(row.id, { status: process ? "PROCESSING" : "STORED", upload, progress: 1 });
        if (process) {
          try {
            const job = await api.createAnalysisJob(upload.id, (queued) => update(row.id, { message: `Queued job #${queued.id}: ${humanize(queued.status)}${queued.message ? ` · ${queued.message}` : ""}` }));
            update(row.id, { status: "COMPLETED", jobStatus: job.status, message: job.error_message ?? undefined });
          } catch (error) {
            update(row.id, { status: "STORED", message: `Stored; processing reported: ${errorMessage(error)}` });
          }
        }
      } catch (error) {
        update(row.id, { status: "ERROR", message: errorMessage(error) });
      }
    }
    setBusy(false);
    await loadEvidence();
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  }

  const pending = rows.filter((row) => row.status === "QUEUED" || row.status === "ERROR").length;
  const accepted = (modalities.data?.modalities ?? []).flatMap((entry) => entry.supported_file_formats).filter((format) => format.upload_accepted && format.available);
  const formatNames = [...new Map(accepted.map((format) => [format.format, format])).values()];

  return (
    <>
      <PageHeader eyebrow="Upload center" title={`Add evidence to ${selected.pseudonymous_id}`} description="Files are validated by extension, MIME type and content signature, hashed with SHA-256 and bound to this case. Processing runs the transparent extractors and OCR for scanned pages; clinical imaging inference abstains without a validated model, and research-only image models are run separately from Medical Imaging." />
      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <Card title="Files">
          <div onDragOver={(event) => event.preventDefault()} onDrop={onDrop} className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line-strong bg-surface-2 px-4 py-8 text-center">
            <FileUp aria-hidden size={22} className="text-ink-3" />
            <p className="mt-2 text-sm font-medium text-ink">Drop de-identified files here</p>
            <p className="mt-1 text-xs text-ink-3">Reports up to 25 MB; images and volumes up to 512 MB. DICOM series are uploaded file by file.</p>
            <input ref={inputRef} type="file" multiple hidden accept={ACCEPT} data-testid="upload-file" onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }} />
            <Button className="mt-3" icon={Plus} onClick={() => inputRef.current?.click()}>Choose files</Button>
          </div>
          {rows.length > 0 && (
            <div className="mt-4">
              <Table headers={["File", "Size", "Status", "SHA-256 / message", ""]} dense>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="max-w-[14rem] truncate font-medium text-ink" title={row.file.name}>{row.file.name}</td>
                    <td className="whitespace-nowrap text-xs text-ink-2">{formatBytes(row.file.size)}</td>
                    <td>
                      {row.status === "UPLOADING" ? (
                        <div className="w-28"><div className="h-1.5 overflow-hidden rounded bg-surface-3"><div className="h-full bg-accent" style={{ width: `${Math.round(row.progress * 100)}%` }} /></div><span className="text-[11px] tabular text-ink-3">{Math.round(row.progress * 100)}%</span></div>
                      ) : <StatusBadge status={row.jobStatus && row.status === "COMPLETED" ? row.jobStatus : row.status} />}
                    </td>
                    <td className="max-w-[18rem] text-xs text-ink-2">
                      {row.upload && <code className="block truncate text-[11px]" title={row.upload.file_hash}>{row.upload.file_hash}</code>}
                      {row.message && <span className="block break-words">{row.message}</span>}
                      {row.upload?.modality === "IMAGE" && <Link to={`/imaging?upload=${row.upload.id}`} className="text-[11px] text-accent-text hover:underline">Review metadata</Link>}
                    </td>
                    <td>{row.status === "QUEUED" && <button type="button" aria-label={`Remove ${row.file.name}`} onClick={() => setRows((current) => current.filter((item) => item.id !== row.id))} className="rounded p-1 text-ink-3 hover:text-ink"><Trash2 size={14} /></button>}</td>
                  </tr>
                ))}
              </Table>
            </div>
          )}
        </Card>
        <div className="space-y-4">
          <Card title="Binding and attestation">
            <div className="space-y-4">
              <Field label="Examination" hint="A dated examination link is required for longitudinal comparison and trends.">
                <div className="flex gap-2">
                  <SelectInput value={examinationId} onChange={(event) => setExaminationId(event.target.value ? Number(event.target.value) : "")}>
                    <option value="">No dated examination</option>
                    {examinations.map((exam) => <option key={exam.id} value={exam.id}>{formatDate(exam.exam_date)} · {exam.modality}</option>)}
                  </SelectInput>
                  <Button icon={Plus} onClick={() => setExamDialog(true)} aria-label="Add examination" />
                </div>
              </Field>
              <label className="flex items-start gap-2.5 text-sm">
                <input type="checkbox" checked={sameCase} onChange={(event) => setSameCase(event.target.checked)} className="mt-1 accent-[var(--mt-accent)]" data-testid="same-case-confirmation" />
                <span><b className="font-medium text-ink">All selected files belong to {selected.pseudonymous_id}.</b><span className="block text-xs text-ink-2">MedTwin never merges evidence across cases; confirm before every batch.</span></span>
              </label>
              <label className="flex items-start gap-2.5 text-sm">
                <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-1 accent-[var(--mt-accent)]" data-testid="deidentified-attestation" />
                <span><b className="font-medium text-ink">These files are de-identified research data.</b><span className="block text-xs text-ink-2">The server rejects uploads without this attestation.</span></span>
              </label>
              <label className="flex items-center gap-2.5 text-sm text-ink">
                <input type="checkbox" checked={process} onChange={(event) => setProcess(event.target.checked)} className="accent-[var(--mt-accent)]" />
                Process after upload
              </label>
              <Button variant="primary" className="w-full" loading={busy} disabled={!pending || !attested || !sameCase} onClick={() => void run()} data-testid="upload-submit">
                {pending ? `Store ${pending} file${pending === 1 ? "" : "s"}` : "Choose files first"}
              </Button>
              {rows.some((row) => row.status === "COMPLETED") && <p className="flex items-center gap-1.5 text-xs text-good-text"><CheckCircle2 size={14} aria-hidden /> Stored evidence is available in Document Intelligence and Medical Imaging.</p>}
              {rows.some((row) => row.status === "ERROR") && <p className="flex items-center gap-1.5 text-xs text-critical-text"><XCircle size={14} aria-hidden /> Failed files stay queued; fix and retry.</p>}
            </div>
          </Card>
          <Card title="Accepted formats" eyebrow="Detected server readers">
            {modalities.data ? (
              <div className="flex flex-wrap gap-1.5">
                {formatNames.map((format) => <Badge key={format.format} tone="neutral" icon={false} title={format.note}>{humanize(format.format)} {format.extensions.filter((ext) => ext.startsWith(".")).join(" ")}</Badge>)}
              </div>
            ) : <p className="text-sm text-ink-2">{modalities.error ?? "Loading…"}</p>}
            <p className="mt-3 text-xs leading-5 text-ink-3">A readable file is not an interpretable one: see Medical Imaging for model coverage per modality.</p>
          </Card>
        </div>
      </div>
      {examDialog && <CreateExaminationDialog caseRecord={selected} onClose={() => setExamDialog(false)} />}
    </>
  );
}
