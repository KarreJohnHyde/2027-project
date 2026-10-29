import { useState } from "react";
import { Download, Printer, RefreshCw } from "lucide-react";
import { Button, Card, ErrorBlock, LoadingBlock, PageHeader, StatusBadge, Table } from "../components/ui";
import { api, type EvidenceCorrection, type EntityCorrection, type MeasurementCorrection } from "../services/api";
import { errorMessage, formatDate, formatNumber, humanize } from "../lib/format";
import { documentedValue, intervalText, occurrenceNote } from "../lib/measurements";
import { assertReportTrendConsistency, buildReportEvidence, reportDerivedAvailability, reportEvidenceExport } from "../lib/reportEvidence";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function CorrectionHistory({ corrections, appliedReviewId }: {
  corrections: EvidenceCorrection<EntityCorrection | MeasurementCorrection>[];
  appliedReviewId: number | null;
}) {
  if (corrections.length === 0) return <span className="text-ink-3">Original extraction; no correction decision</span>;
  return <ul className="space-y-1 text-[11px]">
    {corrections.map((entry) => <li key={entry.review_id}>
      <strong>Review #{entry.review_id}</strong>: {entry.state === "CORRECTION_PROPOSED" ? "Pending — not applied" : entry.state === "CORRECTION_REJECTED" ? "Rejected — not applied" : entry.review_id === appliedReviewId ? "Approved — applied" : "Approved — superseded"}
      {entry.decided_at ? ` · reviewer #${entry.decided_by_id ?? "unavailable"} · ${formatDate(entry.decided_at, true)}` : ` · proposed ${formatDate(entry.proposed_at, true)}`}
    </li>)}
  </ul>;
}

export default function ReportsPage() {
  const selected = useSelectedCase()!;
  const evidence = useWorkspace((state) => state.evidence);
  const evidenceVersion = useWorkspace((state) => state.evidenceVersion);
  const loadingEvidence = useWorkspace((state) => state.loadingEvidence);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const capabilities = useWorkspace((state) => state.capabilities);
  const health = useWorkspace((state) => state.health);
  const report = useAsync(() => loadingEvidence ? null : (async () => {
    const [reviewed, trends, anatomy, egfr, prognosis] = await Promise.all([
      api.getEffectiveEvidence(selected.id), api.getBiomarkerTrends(selected.id),
      api.getAnatomyEvidence(selected.id), api.getEgfr(selected.id), api.getPrognosisEvaluations(selected.id),
    ]);
    const view = buildReportEvidence(selected.id, evidence.statements, evidence.measurements, reviewed, evidence.uploads);
    assertReportTrendConsistency(view, trends.series);
    return {
      caseId: selected.id, evidenceVersion, source: evidence, reviewed,
      view,
      trends, anatomy, egfr, prognosis, generatedAt: new Date().toISOString(),
    };
  })(), [selected.id, evidenceVersion, loadingEvidence]);
  // useAsync retains previous data during reload; never render/export it for a new case or revision.
  const snapshot = !loadingEvidence && !report.loading && report.data?.caseId === selected.id
    && report.data.evidenceVersion === evidenceVersion ? report.data : null;
  const availability = snapshot ? reportDerivedAvailability(snapshot.view) : null;
  const [exportHash, setExportHash] = useState<{ caseId: number; hash: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function exportJson() {
    if (!snapshot || !availability) return;
    setError(null);
    try {
      const payload = {
        schema_version: "medtwin-evidence-export-3.0.0",
        exported_at: new Date().toISOString(),
        evidence_loaded_at: snapshot.generatedAt,
        api_version: health?.version ?? null,
        research_notice: "Research evidence export only. Approved corrections are not clinical validation. Not a diagnosis or treatment recommendation.",
        case: selected,
        uploads: snapshot.source.uploads,
        analysis_jobs: snapshot.source.jobs,
        original_findings: snapshot.source.findings,
        ...reportEvidenceExport(snapshot.view),
        documented_attributes: snapshot.source.attributes,
        biomarker_trends: snapshot.trends.series,
        egfr: availability.egfrWithheld ? null : snapshot.egfr,
        anatomy_evidence: availability.anatomyWithheld ? null : snapshot.anatomy,
        derived_evidence_policy: {
          egfr: availability.egfrWithheld ? "WITHHELD_PENDING_EFFECTIVE_EVIDENCE_CALCULATION" : "CALCULATED_FROM_ORIGINAL_DOCUMENTED_INPUTS",
          anatomy: availability.anatomyWithheld ? "WITHHELD_PENDING_EFFECTIVE_EVIDENCE_MAPPING" : "MAPPED_FROM_ORIGINAL_EXTRACTION",
        },
        prognosis_evaluations: snapshot.prognosis,
        provenance: snapshot.source.provenance,
        capability_snapshot: capabilities,
      };
      const text = JSON.stringify(payload, null, 2);
      const hash = await sha256Hex(text);
      setExportHash({ caseId: snapshot.caseId, hash });
      const href = URL.createObjectURL(new Blob([text], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `${selected.pseudonymous_id}-medtwin-evidence-${hash.slice(0, 8)}.json`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(href), 1000);
    } catch (exportError) {
      setError(errorMessage(exportError));
    }
  }

  const affirmed = snapshot?.view.activeStatements.filter(({ original, effective }) => effective.negation === "AFFIRMED" && effective.certainty === "CERTAIN" && original.experiencer === "PATIENT").length ?? 0;
  return (
    <>
      <div className="print:hidden">
        <PageHeader
          eyebrow="Reports"
          title="Evidence-linked research report"
          description="Approved corrections appear in the reviewed report. Original extraction, source spans and every pending, rejected or approved correction remain in the audit trail."
          actions={<><Button icon={RefreshCw} loading={loadingEvidence || report.loading} onClick={() => void loadEvidence()}>Refresh report</Button><Button icon={Download} disabled={!snapshot} onClick={() => void exportJson()}>Export JSON</Button><Button variant="primary" icon={Printer} disabled={!snapshot} onClick={() => window.print()}>Print / save PDF</Button></>}
        />
        {exportHash?.caseId === selected.id && <p className="mb-4 text-xs text-ink-2">Last export SHA-256 <code>{exportHash.hash}</code></p>}
        {error && <ErrorBlock message={error} />}
      </div>

      {!snapshot ? <Card title="Reviewed report unavailable">
        {report.error ? <ErrorBlock message={`${report.error} No unreviewed fallback has been exported. Refresh the report to retry.`} /> : <LoadingBlock label="Loading source evidence and correction decisions" />}
        <p className="mt-2 text-xs text-ink-2">Printing and export are unavailable until source records and reviewed evidence agree for this case.</p>
      </Card> : <article className="space-y-4 print:space-y-3 print:text-[11px]">
        <Card>
          <h1 className="text-lg font-semibold text-ink">MedTwin research evidence report — {selected.pseudonymous_id}</h1>
          <p className="mt-1 text-xs text-ink-2">Evidence loaded {formatDate(snapshot.generatedAt, true)} · API {health?.version ?? "—"} · case #{selected.id} · {selected.examinations.length} examination(s)</p>
          <p className="mt-2 rounded-md border border-line bg-surface-2 p-2 text-xs leading-5 text-ink-2">Research output only. Not a diagnosis, prognosis or treatment recommendation. Extraction accuracy remains unvalidated. Only independently approved corrections change this reviewed view; approval of an item is not validation of the NLP system.</p>
          <p className="mt-2 text-xs text-ink-2">{snapshot.reviewed.notice} Removed items and inactive sources are excluded from the reviewed tables and retained below. Pending proposals do not change the values shown. Refresh before sharing to load newer decisions.</p>
        </Card>

        <Card title="Source documents" padded={false}>
          <Table headers={["File", "Modality", "SHA-256", "Examination", "Source state"]} dense>
            {snapshot.source.uploads.map((upload) => <tr key={upload.id}><td>{upload.filename}</td><td>{humanize(upload.modality)}</td><td className="font-mono text-[11px]">{upload.file_hash}</td><td>{formatDate(selected.examinations.find((exam) => exam.id === upload.examination_id)?.exam_date)}</td><td>{upload.withdrawn_at ? "Withdrawn — audit only" : upload.superseded_by_file_id != null ? `Superseded by file #${upload.superseded_by_file_id}` : !upload.is_associated ? "Not associated — audit only" : "Active source"}</td></tr>)}
          </Table>
        </Card>

        <Card title="Original processing record" padded={false}>
          <Table headers={["Job", "Processor", "Version", "Preprocessing", "Status"]} dense>
            {snapshot.source.jobs.map((job) => <tr key={job.id}><td>#{job.id}</td><td>{job.model_name}</td><td className="font-mono text-[11px]">{job.model_version}</td><td className="font-mono text-[11px]">{job.preprocessing_version}</td><td><StatusBadge status={job.status} /></td></tr>)}
          </Table>
          <div className="border-t border-line p-3 text-xs text-ink-2">Original finding labels (not rewritten by corrections): {snapshot.source.findings.map((finding) => `${finding.label} (${humanize(finding.review_status)})`).join("; ") || "none"}</div>
        </Card>

        <Card title={`Reviewed statements (${affirmed} affirmed, ${snapshot.view.activeStatements.length - affirmed} negated or qualified)`} padded={false}>
          <Table headers={["Entity / site", "Assertion / certainty", "Time / who", "Original source span", "Correction review"]} dense>
            {snapshot.view.activeStatements.map(({ original, effective, review }) => <tr key={original.id}>
              <td>{effective.entity}<span className="block text-[11px] text-ink-3">{[effective.anatomical_site, effective.laterality].filter(Boolean).join(" · ")}</span></td>
              <td>{humanize(effective.negation)} · {humanize(effective.certainty)}</td>
              <td>{humanize(effective.temporality)} · {humanize(original.experiencer)}</td>
              <td className="max-w-md">“{original.source_span}”<span className="block text-[11px] text-ink-3">Statement #{original.id} · file #{original.source_file_id ?? "unavailable"}</span>
                {review.applied_review_id !== null && <span className="block text-[11px] text-ink-3">Original: {original.entity} · {humanize(original.negation)} · {humanize(original.certainty)} · {humanize(original.temporality)} · {[original.anatomical_site, original.laterality].filter(Boolean).join(" / ") || "no site recorded"}</span>}
              </td>
              <td><CorrectionHistory corrections={review.corrections} appliedReviewId={review.applied_review_id} /></td>
            </tr>)}
          </Table>
        </Card>

        <Card title="Reviewed measurements (distinct observations)" padded={false}>
          <Table headers={["Measurement", "Reviewed value", "Reference interval", "Date / source", "Correction review"]} dense>
            {snapshot.view.activeMeasurements.map(({ original, effective, review }) => <tr key={original.id}>
              <td>{effective.display_name}<span className="block text-[11px] text-ink-3">Specimen: {effective.specimen || "not documented"} · method: {effective.laboratory_method || "not documented"}</span></td>
              <td className="whitespace-nowrap">{documentedValue({ ...original, ...effective })}
                {review.applied_review_id !== null && <span className="block text-[11px] text-ink-3">Original: {original.display_name} · {documentedValue(original)}</span>}
                {original.documented_category && <span className="block text-[11px] text-ink-3">Originally printed category: {original.documented_category} (not recalculated)</span>}
              </td>
              <td className="max-w-xs">
                {(effective.reference_low !== original.reference_low || effective.reference_high !== original.reference_high) && <span className="block">Reviewed bounds: {effective.reference_low ?? "no lower bound"} to {effective.reference_high ?? "no upper bound"} {effective.unit}</span>}
                <span className="block text-[11px] text-ink-3">Printed interval (original): {intervalText(original)}</span>
              </td>
              <td className="max-w-md">{original.documented_date ? formatDate(original.documented_date) : "Undated"}<span className="block">“{original.source_span}”</span>
                <span className="block text-[11px] text-ink-3">Measurement #{original.id} · file #{original.source_file_id}{original.source_page ? ` · page ${original.source_page}` : ""}</span>
                {occurrenceNote(original) && <span className="block text-[11px] text-ink-3">{occurrenceNote(original)}</span>}
              </td>
              <td><CorrectionHistory corrections={review.corrections} appliedReviewId={review.applied_review_id} /></td>
            </tr>)}
          </Table>
          <p className="border-t border-line p-3 text-xs text-ink-2">Printed categories and intervals remain attributed to the original source; no new clinical interpretation is inferred from a correction. All original rows, including duplicate occurrences, remain in the JSON audit.</p>
        </Card>

        {(snapshot.view.removedStatements.length > 0 || snapshot.view.removedMeasurements.length > 0) && <Card title="Approved removals — retained for audit, excluded from reviewed tables" padded={false}>
          <Table headers={["Original item", "Original source span", "Correction review"]} dense>
            {snapshot.view.removedStatements.map(({ original, review }) => <tr key={`s${original.id}`}><td>Statement #{original.id}: {original.entity} · {humanize(original.negation)}</td><td>“{original.source_span}” · file #{original.source_file_id}</td><td><CorrectionHistory corrections={review.corrections} appliedReviewId={review.applied_review_id} /></td></tr>)}
            {snapshot.view.removedMeasurements.map(({ original, review }) => <tr key={`m${original.id}`}><td>Measurement #{original.id}: {original.display_name} · {documentedValue(original)}</td><td>“{original.source_span}” · file #{original.source_file_id}</td><td><CorrectionHistory corrections={review.corrections} appliedReviewId={review.applied_review_id} /></td></tr>)}
          </Table>
        </Card>}

        {(snapshot.view.inactiveStatements.length > 0 || snapshot.view.inactiveMeasurements.length > 0) && <Card title="Inactive-source evidence — retained for audit, excluded from reviewed tables" padded={false}>
          <Table headers={["Original item", "Original source span", "Exclusion"]} dense>
            {snapshot.view.inactiveStatements.map(({ original, sourceExclusion }) => <tr key={`s${original.id}`}><td>Statement #{original.id}: {original.entity}</td><td>“{original.source_span}” · file #{original.source_file_id}</td><td>{humanize(sourceExclusion)}</td></tr>)}
            {snapshot.view.inactiveMeasurements.map(({ original, sourceExclusion }) => <tr key={`m${original.id}`}><td>Measurement #{original.id}: {original.display_name} · {documentedValue(original)}</td><td>“{original.source_span}” · file #{original.source_file_id}</td><td>{humanize(sourceExclusion)}</td></tr>)}
          </Table>
        </Card>}

        <Card title="Longitudinal summary (descriptive, approved corrections applied)" padded={false}>
          <Table headers={["Analyte", "n", "First → last", "Δx", "Rate / yr", "Trend estimate"]} dense>
            {snapshot.trends.series.map((series) => (
              <tr key={series.name}>
                <td>{series.display_name} ({series.unit})</td><td>{series.analysis.n}</td>
                <td>{series.analysis.first ? `${formatNumber(series.analysis.first.value, 4)} → ${formatNumber(series.analysis.last?.value, 4)}` : "—"}</td>
                <td>{formatNumber(series.analysis.absolute_change, 4)}</td><td>{formatNumber(series.analysis.rate_per_year, 4)}</td>
                <td>{series.analysis.ols?.status === "COMPUTED" ? `${formatNumber(series.analysis.ols.slope_per_year, 4)}/yr (95% CI ${formatNumber(series.analysis.ols.slope_95ci_per_year?.[0], 4)} to ${formatNumber(series.analysis.ols.slope_95ci_per_year?.[1], 4)})` : humanize(series.analysis.ols?.status ?? series.analysis.status)}</td>
              </tr>
            ))}
          </Table>
          <p className="border-t border-line p-3 text-xs text-ink-2">{availability?.egfrWithheld ? "Calculated eGFR withheld from this report: creatinine or documented-eGFR evidence has an approved correction or inactive source, but this calculator still uses original extraction. Effective-evidence recalculation is required." : `eGFR from original documented inputs (${snapshot.egfr.equation.display}): ${snapshot.egfr.results.map((result) => result.value !== null ? `${formatNumber(result.value, 1)} ${result.unit}` : humanize(result.status)).join("; ") || humanize(snapshot.egfr.status)}`}</p>
        </Card>

        <div className="grid gap-4 md:grid-cols-2 print:grid-cols-2">
          <Card title="Anatomical mapping">
            {!availability?.anatomyWithheld ? (
              <ul className="space-y-1 text-xs text-ink-2">
                {Object.values(snapshot.anatomy.systems).filter((system) => system.system_id !== "hybrid" && system.items.length > 0).map((system) => (
                  <li key={system.system_id}>{system.label}: {system.state_counts.REGION_VERIFIED} reviewed region association(s), {system.state_counts.SCHEMATIC_ORGAN_ONLY} schematic organ association(s)</li>
                ))}
                <li>Source: original extraction. Spatial registration: {humanize(snapshot.anatomy.spatial_registration.status)}</li>
              </ul>
            ) : <p className="text-xs text-ink-2">Mapping summary withheld: approved corrections or inactive sources exist, but anatomical associations still use original extraction. Effective-evidence remapping is required before including this summary.</p>}
          </Card>
          <Card title="Prognosis and risk">
            <p className="text-xs leading-5 text-ink-2">No validated prognostic or risk model is registered; no forecast, risk score or treatment effect is reported. {snapshot.prognosis.length ? `${snapshot.prognosis.length} scenario evaluation request(s) were recorded, returning ${[...new Set(snapshot.prognosis.map((row) => humanize(row.status)))].join(", ")}.` : ""}</p>
          </Card>
        </div>

        <Card title="Limitations">
          <ul className="list-disc space-y-0.5 pl-4 text-xs leading-5 text-ink-2">
            {capabilities.filter((capability) => !capability.operational || capability.verification_status !== "IMPLEMENTED_AND_TESTED").map((capability) => <li key={capability.capability_id}>{capability.label}: {capability.limitations[0] ?? humanize(capability.verification_status)}</li>)}
            <li>3D anatomy is generic reference geometry and is not the patient's anatomy.</li>
            <li>Review decisions are a loaded snapshot, not a live subscription or an independent accuracy evaluation.</li>
          </ul>
        </Card>
      </article>}
    </>
  );
}
