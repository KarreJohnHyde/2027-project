import { useState } from "react";
import { api } from "../services/api";
import { useAsync } from "../lib/useAsync";
import { errorMessage, formatDate } from "../lib/format";
import { useSelectedCase, useWorkspace } from "../state/workspace";
import { Button, Card, ErrorBlock, SelectInput } from "./ui";
import { CreateExaminationDialog } from "./CaseDialogs";

export default function ExaminationEvidenceLinker() {
  const selected = useSelectedCase()!;
  const uploads = useWorkspace((state) => state.evidence.uploads);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const version = useWorkspace((state) => state.evidenceVersion);
  const attributes = useAsync(() => api.getDocumentedAttributes(selected.id), [selected.id, version]);
  const [fileId, setFileId] = useState("");
  const [examId, setExamId] = useState("");
  const [dateId, setDateId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createDate, setCreateDate] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const exam = selected.examinations.find((item) => item.id === Number(examId));
  const dates = (attributes.data ?? []).filter((item) => ["study_date", "report_date", "document_date"].includes(item.name) && item.value_text);
  const uniqueDates = [...new Map(dates.map((item) => [`${item.source_file_id}:${item.value_text}`, item])).values()];
  async function link() {
    if (!confirmed || !fileId || !examId) return;
    setBusy(true); setError(null);
    try { await api.linkUploadExamination(Number(fileId), Number(examId), dateId ? Number(dateId) : undefined); await loadEvidence(); setSaved(true); setConfirmed(false); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }
  return <Card title="Link evidence to an examination" eyebrow="Identity and date review" className="mt-4">
    <p className="mb-3 text-xs text-ink-2">Create an examination with its actual study date, then link the report and images here. Upload dates are never used as examination dates.</p>
    {attributes.error && <ErrorBlock message={attributes.error} onRetry={attributes.reload} />}
    {uniqueDates.map((item) => <div key={item.id} className="mb-3 rounded border border-line p-3 text-xs text-ink-2"><p>Date candidate {item.value_text} · upload #{item.source_file_id} · “{item.source_span}”</p><p className="my-2">Requires source review; a document date may differ from the study date.</p><Button size="sm" onClick={() => setCreateDate(item.value_text!)}>Create examination using this date</Button></div>)}
    <div className="mb-3"><Button size="sm" onClick={() => setCreateDate("")}>Create a dated examination</Button></div>
    {createDate !== null && <CreateExaminationDialog caseRecord={selected} initialDate={createDate} onClose={() => setCreateDate(null)} />}
    <div className="grid gap-2 md:grid-cols-3">
      <SelectInput aria-label="Evidence to link" value={fileId} onChange={(event) => { setFileId(event.target.value); setDateId(""); setConfirmed(false); setSaved(false); }}><option value="">Select evidence</option>{uploads.filter((u) => u.is_associated && !u.withdrawn_at && !u.superseded_by_file_id).map((u) => <option key={u.id} value={u.id}>#{u.id} · {u.filename}</option>)}</SelectInput>
      <SelectInput aria-label="Target examination" value={examId} onChange={(event) => { setExamId(event.target.value); setDateId(""); setConfirmed(false); setSaved(false); }}><option value="">Select examination</option>{selected.examinations.map((item) => <option key={item.id} value={item.id}>#{item.id} · {formatDate(item.exam_date)}</option>)}</SelectInput>
      <SelectInput aria-label="Reviewed date source" value={dateId} onChange={(event) => { setDateId(event.target.value); setConfirmed(false); setSaved(false); }}><option value="">Date checked manually against source</option>{uniqueDates.filter((item) => item.source_file_id === Number(fileId) && exam?.exam_date.slice(0, 10) === item.value_text).map((item) => <option key={item.id} value={item.id}>Use reviewed date from upload #{item.source_file_id}</option>)}</SelectInput>
    </div>
    <label className="my-3 flex items-start gap-2 text-xs text-ink-2"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I checked the source: the selected evidence belongs to this patient and examination, and the examination date is correct.</label>
    <Button loading={busy} disabled={!confirmed || !fileId || !examId} onClick={() => void link()}>Save examination link</Button>
    {saved && <p role="status" className="mt-2 text-xs text-accent-text">Examination link saved. Select the next evidence file to link it to the same examination.</p>}
    {error && <div className="mt-3"><ErrorBlock message={error} /></div>}
  </Card>;
}
