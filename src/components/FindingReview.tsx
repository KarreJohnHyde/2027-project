import { useState, type FormEvent } from "react";
import {
  api,
  type AnalysisJob,
  type Finding,
  type HumanReviewCorrectionPayload,
  type HumanReviewDecision,
  type MedicalMeasurement,
  type UploadedFile,
} from "../services/api";
import { errorMessage, formatDate } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";
import { Button, Disclosure, ErrorBlock, Field, KeyValue, SelectInput, StatusBadge, TextArea, TextInput } from "./ui";

export function FindingCard({ finding, uploads, jobs, measurements }: { finding: Finding; uploads: UploadedFile[]; jobs: AnalysisJob[]; measurements: MedicalMeasurement[] }) {
  const user = useWorkspace((state) => state.user);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const setNotice = useWorkspace((state) => state.setNotice);
  const job = jobs.find((item) => item.id === finding.inference_run_id);
  const upload = uploads.find((item) => item.id === job?.upload_id);
  const calibrated = finding.calibration_status.toUpperCase().startsWith("CALIBRATED") && finding.calibrated_confidence !== null;
  const canReview = user?.role === "clinician" || user?.role === "admin";
  const [decision, setDecision] = useState<HumanReviewDecision>("CONFIRMED");
  const [comments, setComments] = useState("");
  const [correctionKind, setCorrectionKind] = useState<"ENTITY" | "MEASUREMENT">(finding.report_statements.length ? "ENTITY" : "MEASUREMENT");
  const [correctionTargetId, setCorrectionTargetId] = useState("");
  const [correctionAction, setCorrectionAction] = useState<"AMEND" | "REMOVE">("AMEND");
  const [correctedEntity, setCorrectedEntity] = useState("");
  const [correctedValue, setCorrectedValue] = useState("");
  const [correctedOperator, setCorrectedOperator] = useState<"=" | "<" | ">" | "<=" | ">=">("=");
  const [correctedUnit, setCorrectedUnit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reviews = useAsync(() => api.getFindingReviews(finding.id), [finding.id]);
  const findingMeasurements = measurements.filter((item) => item.finding_id === finding.id);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let correctionPayload: HumanReviewCorrectionPayload | undefined;
      if (decision === "MODIFIED") {
        const targetId = Number(correctionTargetId);
        if (!Number.isInteger(targetId) || targetId <= 0) throw new Error("Select the extracted evidence being corrected.");
        if (correctionKind === "ENTITY") {
          if (correctionAction === "AMEND" && !correctedEntity.trim()) throw new Error("Enter the proposed corrected entity text.");
          correctionPayload = {
            schema_version: "1.0",
            status: "PROPOSED_NOT_APPLIED",
            entity_corrections: [{
              target_statement_id: targetId,
              action: correctionAction,
              ...(correctionAction === "AMEND" ? { corrected_entity: correctedEntity.trim() } : {}),
            }],
            measurement_corrections: [],
          };
        } else {
          const numericValue = Number(correctedValue);
          if (correctionAction === "AMEND" && (correctedValue.trim() === "" || !Number.isFinite(numericValue))) {
            throw new Error("Enter a finite proposed measurement value.");
          }
          correctionPayload = {
            schema_version: "1.0",
            status: "PROPOSED_NOT_APPLIED",
            entity_corrections: [],
            measurement_corrections: [{
              target_measurement_id: targetId,
              action: correctionAction,
              ...(correctionAction === "AMEND" ? {
                corrected_value: numericValue,
                corrected_result_operator: correctedOperator,
                ...(correctedUnit.trim() ? { corrected_unit: correctedUnit.trim() } : {}),
              } : {}),
            }],
          };
        }
      }
      const review = await api.submitFindingReview(finding.id, decision, comments, correctionPayload);
      await loadEvidence();
      reviews.reload();
      setNotice({ tone: "success", text: `Review #${review.id} recorded as ${review.review_status}; the original output was preserved.` });
      setComments("");
      setCorrectionTargetId("");
      setCorrectedEntity("");
      setCorrectedValue("");
      setCorrectedUnit("");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article data-testid="finding-record" className="rounded-xl border border-line bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge status={finding.modality} />
            <StatusBadge status={finding.review_status} />
          </div>
          <h3 className="mt-2 text-sm font-semibold text-ink">{finding.label}</h3>
          <p className="mt-0.5 text-xs text-ink-2">{finding.category}</p>
        </div>
        <div className="rounded-lg bg-surface-2 px-3 py-2 text-right">
          <p className="text-[11px] text-ink-3">Confidence</p>
          <p className="text-xs font-medium text-ink">{calibrated ? `${((finding.calibrated_confidence ?? 0) * 100).toFixed(1)}% calibrated` : "Withheld — no calibrated model"}</p>
        </div>
      </div>
      {finding.failure_reason && <p className="mt-3 rounded-lg border border-line bg-surface-2 p-2.5 text-xs text-ink-2">{finding.failure_reason}</p>}
      <div className="mt-3">
        <KeyValue
          items={[
            { label: "Source", value: upload?.filename ?? `Inference run #${finding.inference_run_id ?? "n/a"}` },
            { label: "Created", value: formatDate(finding.created_at, true) },
            { label: "Processor", value: job ? `${job.model_name} · ${job.model_version}` : "—" },
            { label: "Anatomical level", value: `${finding.representation_level} · ${finding.mapping_status}` },
          ]}
        />
      </div>
      {finding.evidence_provenance && (
        <div className="mt-3">
          <Disclosure summary="Processing provenance">
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-ink-2">{JSON.stringify(finding.evidence_provenance, null, 2)}</pre>
          </Disclosure>
        </div>
      )}
      {canReview && (
        <div className="mt-3">
          <Disclosure summary="Record clinician review">
            <form onSubmit={submit} className="space-y-2.5">
              <p className="text-[11px] leading-4 text-ink-3">Reviews are appended to the audit trail. The extracted output, source evidence and provenance are never overwritten. A confirmed report finding allows its documented regions to be shown as verified anatomical regions.</p>
              <SelectInput value={decision} onChange={(event) => setDecision(event.target.value as HumanReviewDecision)}>
                <option value="CONFIRMED">Confirm extraction</option>
                <option value="REJECTED">Reject extraction</option>
                <option value="MODIFIED">Correction required</option>
                <option value="REQUIRES_FURTHER_WORKUP">Further work-up required</option>
              </SelectInput>
              {decision === "MODIFIED" && (
                <div className="space-y-2 rounded-lg border border-line bg-surface-2 p-3">
                  <div className="flex flex-wrap gap-2">
                    <div className="min-w-44 flex-1">
                      <Field label="Evidence type">
                        <SelectInput value={correctionKind} onChange={(event) => { setCorrectionKind(event.target.value as "ENTITY" | "MEASUREMENT"); setCorrectionTargetId(""); }}>
                          <option value="ENTITY" disabled={!finding.report_statements.length}>Extracted entity</option>
                          <option value="MEASUREMENT" disabled={!findingMeasurements.length}>Extracted measurement</option>
                        </SelectInput>
                      </Field>
                    </div>
                    <div className="min-w-44 flex-1">
                      <Field label="Correction action">
                        <SelectInput value={correctionAction} onChange={(event) => setCorrectionAction(event.target.value as "AMEND" | "REMOVE")}>
                          <option value="AMEND">Propose amendment</option>
                          <option value="REMOVE">Propose removal</option>
                        </SelectInput>
                      </Field>
                    </div>
                  </div>
                  <Field label="Original extracted evidence">
                    <SelectInput value={correctionTargetId} onChange={(event) => setCorrectionTargetId(event.target.value)}>
                      <option value="">Select an item</option>
                      {correctionKind === "ENTITY" ? finding.report_statements.map((statement) => (
                        <option key={statement.id} value={statement.id}>#{statement.id} {statement.entity} · {statement.negation}</option>
                      )) : findingMeasurements.map((measurement) => (
                        <option key={measurement.id} value={measurement.id}>#{measurement.id} {measurement.display_name}: {measurement.result_operator}{measurement.value} {measurement.unit}</option>
                      ))}
                    </SelectInput>
                  </Field>
                  {correctionAction === "AMEND" && correctionKind === "ENTITY" && (
                    <Field label="Proposed entity text" hint="This proposal is stored beside the source extraction; it does not replace it.">
                      <TextInput maxLength={128} value={correctedEntity} onChange={(event) => setCorrectedEntity(event.target.value)} />
                    </Field>
                  )}
                  {correctionAction === "AMEND" && correctionKind === "MEASUREMENT" && (
                    <div className="grid gap-2 sm:grid-cols-[6rem_1fr_1fr]">
                      <Field label="Operator">
                        <SelectInput value={correctedOperator} onChange={(event) => setCorrectedOperator(event.target.value as "=" | "<" | ">" | "<=" | ">=")}>
                          {["=", "<", ">", "<=", ">="].map((operator) => <option key={operator} value={operator}>{operator}</option>)}
                        </SelectInput>
                      </Field>
                      <Field label="Proposed value">
                        <TextInput inputMode="decimal" value={correctedValue} onChange={(event) => setCorrectedValue(event.target.value)} />
                      </Field>
                      <Field label="Proposed unit (optional)">
                        <TextInput maxLength={32} value={correctedUnit} onChange={(event) => setCorrectedUnit(event.target.value)} />
                      </Field>
                    </div>
                  )}
                  <p className="text-[11px] leading-4 text-ink-3">Proposed corrections remain unvalidated review annotations. They are not applied to the extracted evidence and are never promoted to ground truth automatically.</p>
                </div>
              )}
              <TextArea maxLength={2000} rows={2} value={comments} onChange={(event) => setComments(event.target.value)} required={decision === "MODIFIED"} placeholder="Rationale (required for a correction)" />
              {error && <ErrorBlock message={error} />}
              <Button type="submit" size="sm" variant="primary" loading={busy} disabled={decision === "MODIFIED" && (!comments.trim() || !correctionTargetId)}>Submit review</Button>
            </form>
          </Disclosure>
        </div>
      )}
      {(reviews.data ?? []).some((review) => review.correction_payload) && (
        <div className="mt-3">
          <Disclosure summary="Proposed correction history">
            <div className="space-y-3">
              {(reviews.data ?? []).filter((review) => review.correction_payload).map((review) => (
                <div key={review.id} className="rounded-lg border border-line bg-surface-2 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-medium text-ink">Review #{review.id} · {formatDate(review.reviewed_at, true)}</p>
                    <StatusBadge status={review.correction_payload?.status} />
                  </div>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    <div className="rounded-md border border-line bg-surface p-2.5">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">Original evidence · preserved</p>
                      <p className="mt-1 text-xs text-ink">Finding: {finding.label}</p>
                      {review.correction_payload?.entity_corrections.map((correction) => {
                        const original = finding.report_statements.find((statement) => statement.id === correction.target_statement_id);
                        return <p key={`entity-${correction.target_statement_id}`} className="mt-1 text-xs text-ink-2">Entity #{correction.target_statement_id}: {original ? `${original.entity} · ${original.negation} · “${original.source_span}”` : "source item unavailable"}</p>;
                      })}
                      {review.correction_payload?.measurement_corrections.map((correction) => {
                        const original = findingMeasurements.find((measurement) => measurement.id === correction.target_measurement_id);
                        return <p key={`measurement-${correction.target_measurement_id}`} className="mt-1 text-xs text-ink-2">Measurement #{correction.target_measurement_id}: {original ? `${original.result_operator}${original.value} ${original.unit} · “${original.source_span}”` : "source item unavailable"}</p>;
                      })}
                    </div>
                    <div className="rounded-md border border-line bg-surface p-2.5">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">Proposed correction · not applied</p>
                      <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-ink-2">{JSON.stringify(review.correction_payload, null, 2)}</pre>
                    </div>
                  </div>
                  {review.reviewer_comments && <p className="mt-2 text-xs text-ink-2">Rationale: {review.reviewer_comments}</p>}
                </div>
              ))}
            </div>
          </Disclosure>
        </div>
      )}
      {reviews.error && <div className="mt-3"><ErrorBlock message={reviews.error} /></div>}
    </article>
  );
}
