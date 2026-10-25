import { useState } from "react";
import { Download, Printer } from "lucide-react";
import { Button, Card, ErrorBlock, PageHeader, StatusBadge, Table } from "../components/ui";
import { api } from "../services/api";
import { errorMessage, formatDate, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export default function ReportsPage() {
  const selected = useSelectedCase()!;
  const evidence = useWorkspace((state) => state.evidence);
  const evidenceVersion = useWorkspace((state) => state.evidenceVersion);
  const capabilities = useWorkspace((state) => state.capabilities);
  const health = useWorkspace((state) => state.health);
  const trends = useAsync(() => api.getBiomarkerTrends(selected.id), [selected.id, evidenceVersion]);
  const anatomy = useAsync(() => api.getAnatomyEvidence(selected.id), [selected.id, evidenceVersion]);
  const egfr = useAsync(() => api.getEgfr(selected.id), [selected.id, evidenceVersion]);
  const prognosis = useAsync(() => api.getPrognosisEvaluations(selected.id), [selected.id, evidenceVersion]);
  const [exportHash, setExportHash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generatedAt] = useState(() => new Date().toISOString());

  async function exportJson() {
    try {
      const payload = {
        schema_version: "medtwin-evidence-export-2.0.0",
        exported_at: new Date().toISOString(),
        api_version: health?.version ?? null,
        research_notice: "Research evidence export only. Not a diagnosis, treatment recommendation or clinically validated report.",
        case: selected,
        uploads: evidence.uploads,
        analysis_jobs: evidence.jobs,
        findings: evidence.findings,
        report_statements: evidence.statements,
        measurements: evidence.measurements,
        documented_attributes: evidence.attributes,
        biomarker_trends: trends.data?.series ?? null,
        egfr: egfr.data ?? null,
        anatomy_evidence: anatomy.data ?? null,
        prognosis_evaluations: prognosis.data ?? null,
        provenance: evidence.provenance,
        capability_snapshot: capabilities,
      };
      const text = JSON.stringify(payload, null, 2);
      const hash = await sha256Hex(text);
      setExportHash(hash);
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

  const affirmed = evidence.statements.filter((item) => item.negation === "AFFIRMED" && item.certainty === "CERTAIN" && item.experiencer === "PATIENT");
  const qualified = evidence.statements.filter((item) => !affirmed.includes(item));
  return (
    <>
      <div className="print:hidden">
        <PageHeader
          eyebrow="Reports"
          title="Evidence-linked research report"
          description="Every statement below traces to an uploaded source and a recorded computation. Print to PDF from the browser, or export the full evidence as versioned JSON with its SHA-256."
          actions={<><Button icon={Download} onClick={() => void exportJson()}>Export JSON</Button><Button variant="primary" icon={Printer} onClick={() => window.print()}>Print / save PDF</Button></>}
        />
        {exportHash && <p className="mb-4 text-xs text-ink-2">Last export SHA-256 <code>{exportHash}</code></p>}
        {error && <ErrorBlock message={error} />}
      </div>

      <article className="space-y-4 print:space-y-3 print:text-[11px]">
        <Card>
          <h1 className="text-lg font-semibold text-ink">MedTwin research evidence report — {selected.pseudonymous_id}</h1>
          <p className="mt-1 text-xs text-ink-2">Generated {formatDate(generatedAt, true)} · API {health?.version ?? "—"} · case #{selected.id} · {selected.examinations.length} examination(s)</p>
          <p className="mt-2 rounded-md border border-line bg-surface-2 p-2 text-xs leading-5 text-ink-2">Research output only. Not a diagnosis, prognosis or treatment recommendation. Extraction is a transparent rules baseline that has not been evaluated on an annotated corpus; every item awaits clinician review.</p>
        </Card>

        <Card title="Source documents" padded={false}>
          <Table headers={["File", "Modality", "SHA-256", "Examination"]} dense>
            {evidence.uploads.map((upload) => <tr key={upload.id}><td>{upload.filename}</td><td>{humanize(upload.modality)}</td><td className="font-mono text-[11px]">{upload.file_hash}</td><td>{formatDate(selected.examinations.find((exam) => exam.id === upload.examination_id)?.exam_date)}</td></tr>)}
          </Table>
        </Card>

        <Card title="Processing" padded={false}>
          <Table headers={["Job", "Processor", "Version", "Preprocessing", "Status"]} dense>
            {evidence.jobs.map((job) => <tr key={job.id}><td>#{job.id}</td><td>{job.model_name}</td><td className="font-mono text-[11px]">{job.model_version}</td><td className="font-mono text-[11px]">{job.preprocessing_version}</td><td><StatusBadge status={job.status} /></td></tr>)}
          </Table>
          <div className="border-t border-line p-3 text-xs text-ink-2">Findings: {evidence.findings.map((finding) => `${finding.label} (${humanize(finding.review_status)})`).join("; ") || "none"}</div>
        </Card>

        <Card title={`Documented statements (${affirmed.length} affirmed, ${qualified.length} negated or qualified)`} padded={false}>
          <Table headers={["Entity", "Assertion", "Certainty", "Time", "Who", "Source span"]} dense>
            {evidence.statements.map((statement) => <tr key={statement.id}><td>{statement.entity}</td><td>{humanize(statement.negation)}</td><td>{humanize(statement.certainty)}</td><td>{humanize(statement.temporality)}</td><td>{humanize(statement.experiencer)}</td><td className="max-w-md">“{statement.source_span}”</td></tr>)}
          </Table>
        </Card>

        <Card title="Documented measurements" padded={false}>
          <Table headers={["Measurement", "Value", "Documented interval", "Date", "Source span"]} dense>
            {evidence.measurements.map((measurement) => <tr key={measurement.id}><td>{measurement.display_name}</td><td className="whitespace-nowrap">{formatNumber(measurement.value, 4)} {measurement.unit}</td><td>{measurement.reference_text ?? "—"}</td><td>{measurement.documented_date ? formatDate(measurement.documented_date) : "—"}</td><td className="max-w-md">“{measurement.source_span}”</td></tr>)}
          </Table>
        </Card>

        <Card title="Longitudinal summary (descriptive)" padded={false}>
          <Table headers={["Analyte", "n", "First → last", "Δx", "Rate / yr", "Trend estimate"]} dense>
            {(trends.data?.series ?? []).map((series) => (
              <tr key={series.name}>
                <td>{series.display_name} ({series.unit})</td><td>{series.analysis.n}</td>
                <td>{series.analysis.first ? `${formatNumber(series.analysis.first.value, 4)} → ${formatNumber(series.analysis.last?.value, 4)}` : "—"}</td>
                <td>{formatNumber(series.analysis.absolute_change, 4)}</td><td>{formatNumber(series.analysis.rate_per_year, 4)}</td>
                <td>{series.analysis.ols?.status === "COMPUTED" ? `${formatNumber(series.analysis.ols.slope_per_year, 4)}/yr (95% CI ${formatNumber(series.analysis.ols.slope_95ci_per_year?.[0], 4)} to ${formatNumber(series.analysis.ols.slope_95ci_per_year?.[1], 4)})` : humanize(series.analysis.ols?.status ?? series.analysis.status)}</td>
              </tr>
            ))}
          </Table>
          {egfr.data && <p className="border-t border-line p-3 text-xs text-ink-2">eGFR ({egfr.data.equation.display}): {egfr.data.results.map((result) => (result.value !== null ? `${formatNumber(result.value, 1)} ${result.unit}` : humanize(result.status))).join("; ") || humanize(egfr.data.status)}</p>}
        </Card>

        <div className="grid gap-4 md:grid-cols-2 print:grid-cols-2">
          <Card title="Anatomical mapping">
            {anatomy.data ? (
              <ul className="space-y-1 text-xs text-ink-2">
                {Object.values(anatomy.data.systems).filter((system) => system.system_id !== "hybrid" && system.items.length > 0).map((system) => (
                  <li key={system.system_id}>{system.label}: {system.state_counts.REGION_VERIFIED} verified region(s), {system.state_counts.SCHEMATIC_ORGAN_ONLY} schematic organ association(s)</li>
                ))}
                <li>Spatial registration: {humanize(anatomy.data.spatial_registration.status)}</li>
              </ul>
            ) : <p className="text-xs text-ink-2">—</p>}
          </Card>
          <Card title="Prognosis and risk">
            <p className="text-xs leading-5 text-ink-2">No validated prognostic or risk model is registered; no forecast, risk score or treatment effect is reported. {prognosis.data?.length ? `${prognosis.data.length} scenario evaluation request(s) were recorded, each returning ${[...new Set(prognosis.data.map((row) => humanize(row.status)))].join(", ")}.` : ""}</p>
          </Card>
        </div>

        <Card title="Limitations">
          <ul className="list-disc space-y-0.5 pl-4 text-xs leading-5 text-ink-2">
            {capabilities.filter((capability) => !capability.operational || capability.verification_status !== "IMPLEMENTED_AND_TESTED").map((capability) => <li key={capability.capability_id}>{capability.label}: {capability.limitations[0] ?? humanize(capability.verification_status)}</li>)}
            <li>3D anatomy is generic reference geometry and is not the patient's anatomy.</li>
          </ul>
        </Card>
      </article>
    </>
  );
}
