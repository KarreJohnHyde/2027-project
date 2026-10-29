import { useId, useState, type FormEvent } from "react";
import { api, type ReviewedDemographics, type UploadedFile } from "../services/api";
import { errorMessage, formatDate, todayInputValue } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { Button, Card, ErrorBlock, Field, LoadingBlock, SelectInput, TextArea, TextInput } from "./ui";

function ContextEditor({ caseId, current, uploads, onSaved }: {
  caseId: number; current: ReviewedDemographics | null; uploads: UploadedFile[]; onSaved: () => void;
}) {
  const id = useId();
  const [sex, setSex] = useState<ReviewedDemographics["sex"]>(current?.sex ?? "UNKNOWN");
  const [dob, setDob] = useState(current?.date_of_birth ?? "");
  const [source, setSource] = useState(current?.source_reference_id ? String(current.source_reference_id) : current?.source_file_id ? String(current.source_file_id) : "");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = uploads.filter(file => file.is_associated && !file.withdrawn_at && !file.superseded_by_file_id);
  const sourceUnavailable = source !== "" && !active.some(file => String(file.id) === source);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!confirmed || sourceUnavailable || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.recordReviewedDemographics(caseId, {
        expected_revision: current?.revision ?? 0, sex, date_of_birth: dob || null,
        source_file_id: source ? Number(source) : null, reason: reason.trim(),
      });
      onSaved();
    } catch (requestError) { setError(errorMessage(requestError)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={save} className="mt-4 space-y-3 border-t border-line pt-4">
    <p className="text-xs text-ink-2">Use only when authorised to record this context. Do not infer sex or date of birth from a name or image. A new revision preserves earlier entries; Unknown and an empty date explicitly clear incorrect context.</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Reviewed sex (context only)" htmlFor={`${id}-sex`} hint="Not gender identity or an automatic laboratory-range selection; leave unknown when unconfirmed.">
        <SelectInput id={`${id}-sex`} value={sex} onChange={event => setSex(event.target.value as ReviewedDemographics["sex"])}>
          <option value="UNKNOWN">Unknown / not confirmed</option><option value="F">Female (source-confirmed)</option><option value="M">Male (source-confirmed)</option>
        </SelectInput>
      </Field>
      <Field label="Date of birth" htmlFor={`${id}-dob`} hint="Optional sensitive data. Leave empty if not reliably confirmed.">
        <TextInput id={`${id}-dob`} type="date" max={todayInputValue()} value={dob} onChange={event => setDob(event.target.value)} />
      </Field>
    </div>
    <Field label="Supporting source" htmlFor={`${id}-source`}>
      <SelectInput id={`${id}-source`} value={source} onChange={event => setSource(event.target.value)}>
        {sourceUnavailable && <option value={source} disabled>Previous source is unavailable — select a new basis</option>}
        <option value="">Reviewer attestation — explain the basis below</option>
        {active.map(file => <option key={file.id} value={file.id}>#{file.id} · {file.filename}</option>)}
      </SelectInput>
    </Field>
    <Field label="Verification basis / reason for revision" htmlFor={`${id}-reason`} hint="Explain the evidence and any conflict. Do not repeat names or other identifiers.">
      <TextArea id={`${id}-reason`} minLength={5} maxLength={500} required rows={2} value={reason} onChange={event => setReason(event.target.value)} />
    </Field>
    <label className="flex items-start gap-2 text-xs text-ink-2"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />I checked the case identity and the supporting evidence. This entry does not alter extracted results or authorise an automatic diagnosis.</label>
    {error && <ErrorBlock message={error} onRetry={onSaved} />}
    <Button type="submit" loading={busy} disabled={!confirmed || sourceUnavailable || reason.trim().length < 5}>Record revision {(current?.revision ?? 0) + 1}</Button>
  </form>;
}

export default function ReviewedDemographicsCard({ caseId, uploads }: { caseId: number; uploads: UploadedFile[] }) {
  // Source withdrawals, reassociation and version replacement must refresh the
  // provenance warning even when the demographic revision itself is unchanged.
  const sourceVersions = uploads.map(file => `${file.id}:${file.is_associated}:${file.withdrawn_at ?? ""}:${file.superseded_by_file_id ?? ""}`).join("|");
  const context = useAsync(() => api.getReviewedDemographics(caseId), [caseId, sourceVersions]);
  return <Card title="Reviewed demographic context" eyebrow="Audited human entry, separate from OCR">
    {context.loading && <LoadingBlock label="Loading reviewed context" />}
    {context.error && <ErrorBlock message={context.error} onRetry={context.reload} />}
    {context.data && <>
      <p className="text-xs text-ink-2">{context.data.notice}</p>
      {context.data.current ? <div className="mt-3 rounded border border-line bg-page p-3 text-sm">
        <p>Revision {context.data.current.revision} · sex: {context.data.current.sex} · date of birth: {context.data.current.date_of_birth ?? "Not recorded"}</p>
        <p className="mt-1 text-xs text-ink-3">Reviewer #{context.data.current.reviewed_by_id ?? "unavailable"} · {formatDate(context.data.current.created_at)} · {context.data.current.source_reference_id ? `source #${context.data.current.source_reference_id}` : context.data.current.source_state === "REVIEWER_ATTESTATION" ? "Reviewer attestation" : "Original source provenance unavailable"}</p>
        <p className="mt-1 text-xs text-ink-2">{context.data.current.reason}</p>
        {!["ACTIVE", "REVIEWER_ATTESTATION"].includes(context.data.current.source_state) && <p role="alert" className="mt-2 text-xs text-critical-text">Supporting source is inactive, deleted or its provenance is unavailable. Re-review this context before use.</p>}
      </div> : <p className="mt-3 text-sm text-ink-2">No reviewed context. Missing demographic information remains unknown.</p>}
      {context.data.history.length > 1 && <details className="mt-3 text-xs text-ink-2"><summary className="cursor-pointer">Earlier revisions ({context.data.history.length - 1})</summary><ol className="mt-2 space-y-2">{context.data.history.slice(1).map(row => <li key={row.id}>Revision {row.revision}: {row.sex}; {row.date_of_birth ?? "date not recorded"} · reviewer #{row.reviewed_by_id ?? "unavailable"}. {row.reason}{!["ACTIVE", "REVIEWER_ATTESTATION"].includes(row.source_state) && <span className="text-critical-text"> Supporting source inactive, deleted or unavailable.</span>}</li>)}</ol></details>}
      {context.data.can_record && !context.loading ? <ContextEditor key={`${caseId}:${context.data.current?.revision ?? 0}`} caseId={caseId} current={context.data.current} uploads={uploads} onSaved={context.reload} /> : <p className="mt-3 text-xs text-ink-3">Only a verified professional with case-edit permission can record a revision.</p>}
      <p className="mt-3 text-xs text-ink-3">No automatic range selection, recalculated eGFR, age inference or risk estimate is performed from this context. Printed laboratory intervals take priority; review any selection against the specimen date.</p>
    </>}
  </Card>;
}
