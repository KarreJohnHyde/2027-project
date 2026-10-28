import { useState, type ReactNode } from "react";
import { Box } from "lucide-react";
import { Badge, Card, EmptyState, ErrorBlock, LoadingBlock, PageHeader, SelectInput, StatusBadge, Table, Unavailable } from "../components/ui";
import { api, type MedicalMeasurement, type ReportStatement } from "../services/api";
import { formatDate, formatNumber, humanize } from "../lib/format";
import { documentedValue, intervalText, occurrenceNote } from "../lib/measurements";
import { Link } from "../lib/router";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";

type Span = { start: number; end: number; kind: "statement" | "measurement"; id: string; label: string; tone: string };

const STATEMENT_TONE = (statement: ReportStatement) =>
  statement.experiencer === "FAMILY" ? "bg-surface-3"
    : statement.negation === "NEGATED" ? "bg-[color-mix(in_srgb,var(--mt-ink-3)_22%,transparent)] line-through decoration-ink-3"
      : statement.certainty === "HYPOTHETICAL" ? "bg-[color-mix(in_srgb,var(--mt-map-verified)_18%,transparent)]"
        : statement.certainty === "UNCERTAIN" ? "bg-[color-mix(in_srgb,var(--mt-warning)_28%,transparent)]"
          : "bg-[color-mix(in_srgb,var(--mt-accent)_24%,transparent)]";

function HighlightedText({ text, spans, activeId, onActivate }: { text: string; spans: Span[]; activeId: string | null; onActivate: (id: string) => void }) {
  const ordered = [...spans].sort((left, right) => left.start - right.start || right.end - left.end);
  const pieces: ReactNode[] = [];
  let cursor = 0;
  for (const span of ordered) {
    if (span.start < cursor || span.end > text.length) continue;
    if (span.start > cursor) pieces.push(text.slice(cursor, span.start));
    pieces.push(
      <mark
        key={`${span.kind}-${span.id}`}
        tabIndex={0}
        title={span.label}
        onClick={() => onActivate(span.id)}
        onKeyDown={(event) => event.key === "Enter" && onActivate(span.id)}
        className={`cursor-pointer rounded-sm px-0.5 text-ink ${span.kind === "measurement" ? "bg-transparent underline decoration-[var(--mt-series-1)] decoration-2 underline-offset-2" : span.tone} ${activeId === span.id ? "ring-2 ring-[var(--mt-focus)]" : ""}`}
      >
        {text.slice(span.start, span.end)}
      </mark>,
    );
    cursor = span.end;
  }
  pieces.push(text.slice(cursor));
  return <pre className="max-h-[30rem] overflow-auto whitespace-pre-wrap break-words font-sans text-sm leading-7 text-ink-2">{pieces}</pre>;
}

function filterOptions(values: string[]) {
  return ["ALL", ...[...new Set(values)].sort()];
}

export default function DocumentIntelligencePage() {
  const evidence = useWorkspace((state) => state.evidence);
  const reports = evidence.uploads.filter((upload) => upload.modality === "REPORT");
  const [uploadId, setUploadId] = useState<number | null>(reports[0]?.id ?? null);
  const activeUpload = reports.find((upload) => upload.id === uploadId) ?? reports[0] ?? null;
  const text = useAsync(() => (activeUpload ? api.getReportText(activeUpload.id) : null), [activeUpload?.id]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [filters, setFilters] = useState({ negation: "ALL", certainty: "ALL", temporality: "ALL", experiencer: "ALL", system: "ALL" });

  const statements = evidence.statements.filter((statement) => !activeUpload || statement.source_file_id === String(activeUpload.id));
  const measurements = evidence.measurements.filter((measurement) => !activeUpload || measurement.source_file_id === activeUpload.id);
  const attributes = evidence.attributes.filter((attribute) => !activeUpload || attribute.source_file_id === activeUpload.id);
  const identityAttributes = evidence.attributes.filter((attribute) => attribute.name === "age_years" || attribute.name === "sex");
  const documentedSexes = new Set(identityAttributes.filter((attribute) => attribute.name === "sex" && attribute.value_text).map((attribute) => attribute.value_text!.toLowerCase()));
  const documentedAges = identityAttributes
    .filter((attribute) => attribute.name === "age_years" && attribute.value_number !== null)
    .map((attribute) => attribute.value_number!);
  const ageSpread = documentedAges.length > 1 ? Math.max(...documentedAges) - Math.min(...documentedAges) : 0;
  const identityReviewRequired = documentedSexes.size > 1 || ageSpread > 2;
  const visible = statements.filter((statement) =>
    (filters.negation === "ALL" || statement.negation === filters.negation) &&
    (filters.certainty === "ALL" || statement.certainty === filters.certainty) &&
    (filters.temporality === "ALL" || statement.temporality === filters.temporality) &&
    (filters.experiencer === "ALL" || statement.experiencer === filters.experiencer) &&
    (filters.system === "ALL" || (statement.anatomy_system ?? "NONE") === filters.system));

  const spans: Span[] = [
    ...statements.filter((statement) => statement.entity_start !== null && statement.entity_end !== null).map((statement) => ({
      start: statement.entity_start!, end: statement.entity_end!, kind: "statement" as const, id: `s${statement.id}`,
      label: `${statement.entity}: ${statement.negation}, ${statement.certainty}, ${statement.temporality}`, tone: STATEMENT_TONE(statement),
    })),
    ...measurements.map((measurement: MedicalMeasurement) => ({
      start: measurement.source_span_start, end: measurement.source_span_end, kind: "measurement" as const, id: `m${measurement.id}`,
      label: `${measurement.display_name}: ${measurement.result_operator === "=" ? "" : measurement.result_operator}${measurement.value} ${measurement.unit}`, tone: "",
    })),
  ];

  if (reports.length === 0) {
    return (
      <>
        <PageHeader eyebrow="Document Intelligence" title="Clinical document analysis" />
        <EmptyState title="No report uploads" detail="Upload a de-identified PDF (embedded text or scanned), DOCX, XLSX, TXT, CSV, FHIR JSON or HL7 v2 result message to extract source-linked statements and measurements." action={<Link to="/upload" className="text-sm text-accent-text hover:underline">Open the upload center</Link>} />
      </>
    );
  }

  const filterSelect = (key: keyof typeof filters, label: string, values: string[]) => (
    <label className="text-[11px] text-ink-3">
      {label}
      <SelectInput value={filters[key]} onChange={(event) => setFilters((current) => ({ ...current, [key]: event.target.value }))} className="mt-0.5 h-8 text-xs">
        {filterOptions(values).map((value) => <option key={value} value={value}>{value === "ALL" ? "All" : humanize(value)}</option>)}
      </SelectInput>
    </label>
  );

  return (
    <>
      <PageHeader
        eyebrow="Document Intelligence"
        title="Source-linked clinical text"
        description="A transparent rules extractor (rules-v2) records what each report states, with assertion, certainty, temporality and experiencer. Hedged or negated statements are never treated as confirmed diagnoses. Outputs are unvalidated and await clinician review."
        actions={
          <div className="w-72">
            <SelectInput aria-label="Report" value={activeUpload?.id ?? ""} onChange={(event) => setUploadId(Number(event.target.value))}>
              {reports.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename}</option>)}
            </SelectInput>
          </div>
        }
      />
      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card title="Document text" eyebrow={text.data ? `${text.data.extractor_version} · de-identified · text SHA-256 ${text.data.text_sha256.slice(0, 10)}…` : "Parsed text"}>
          {text.loading && <LoadingBlock label="Parsing document" />}
          {text.error && <ErrorBlock message={text.error} onRetry={text.reload} />}
          {text.data && <HighlightedText text={text.data.text} spans={spans} activeId={activeId} onActivate={setActiveId} />}
          <div className="mt-3 flex flex-wrap gap-3 border-t border-line pt-3 text-[11px] text-ink-2">
            <span className="flex items-center gap-1"><span aria-hidden className="h-3 w-5 rounded-sm bg-[color-mix(in_srgb,var(--mt-accent)_24%,transparent)]" /> Affirmed, certain</span>
            <span className="flex items-center gap-1"><span aria-hidden className="h-3 w-5 rounded-sm bg-[color-mix(in_srgb,var(--mt-warning)_28%,transparent)]" /> Uncertain</span>
            <span className="flex items-center gap-1"><span aria-hidden className="h-3 w-5 rounded-sm bg-[color-mix(in_srgb,var(--mt-map-verified)_18%,transparent)]" /> Hypothetical</span>
            <span className="flex items-center gap-1"><span aria-hidden className="h-3 w-5 rounded-sm bg-[color-mix(in_srgb,var(--mt-ink-3)_22%,transparent)]" /> <s>Negated</s></span>
            <span className="flex items-center gap-1"><span aria-hidden className="h-3 w-5 rounded-sm bg-surface-3" /> Family history</span>
            <span className="flex items-center gap-1"><span aria-hidden className="h-0.5 w-5 bg-[var(--mt-series-1)]" /> Measurement</span>
          </div>
        </Card>
        <div className="space-y-4">
          <Card
            title="Identity consistency"
            eyebrow="Case-level document check"
            actions={
              <StatusBadge
                status={identityAttributes.length === 0 ? "INSUFFICIENT_EVIDENCE" : identityReviewRequired ? "IDENTITY_REVIEW_REQUIRED" : "CONSISTENT"}
                label={identityAttributes.length === 0 ? "No attributes" : identityReviewRequired ? "Review required" : "No conflict observed"}
              />
            }
          >
            {identityReviewRequired ? (
              <Unavailable
                compact
                code="IDENTITY_REVIEW_REQUIRED"
                reason="Documents assigned to this case contain materially different age or sex values. MedTwin will not reconcile or merge them automatically; verify the source patient and case association."
              />
            ) : (
              <p className="text-xs leading-5 text-ink-2">
                {identityAttributes.length === 0
                  ? "No documented age or sex was extracted, so patient consistency cannot be assessed."
                  : "No material age or sex conflict was detected in the currently extracted case documents. This is not proof of identity."}
              </p>
            )}
            {identityAttributes.length > 0 && (
              <p className="mt-2 text-[11px] leading-5 text-ink-3">
                Review heuristic: documented sex values differ or documented ages span more than two years. A clean result is not identity proof.
              </p>
            )}
            {identityAttributes.length > 0 && (
              <ul className="mt-3 space-y-1.5 border-t border-line pt-3 text-xs text-ink-2">
                {identityAttributes.map((attribute) => {
                  const source = reports.find((report) => report.id === attribute.source_file_id);
                  return (
                    <li key={attribute.id} className="flex items-start justify-between gap-3">
                      <span className="min-w-0 truncate" title={source?.filename}>{source?.filename ?? `Report #${attribute.source_file_id}`}</span>
                      <span className="shrink-0 font-medium text-ink">
                        {humanize(attribute.name)}: {attribute.value_text ?? (attribute.value_number !== null ? formatNumber(attribute.value_number, 1) : "Unparsed")}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          <Card title="Documented attributes" eyebrow="Dates, age and sex as written">
            {attributes.length === 0 ? <p className="text-sm text-ink-2">No dates, age or sex documented in this report.</p> : (
              <ul className="space-y-1.5 text-sm">
                {attributes.map((attribute) => (
                  <li key={attribute.id} className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-medium text-ink">{humanize(attribute.name)}</span>
                    <span className="text-ink-2">{attribute.value_text ?? <StatusBadge status={attribute.parse_status} />} <span className="text-[11px] text-ink-3">“{attribute.source_span}”</span></span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Extraction boundary">
            <ul className="space-y-1.5 text-xs leading-5 text-ink-2">
              <li>Negation, uncertainty ("suspected", "consistent with", "cannot be excluded"), hypothetical ("rule out", "evaluate for"), historical and family contexts are scoped per clause.</li>
              <li>Anatomical sites resolve to reference-atlas structure terms; they become verified regions only after clinician confirmation.</li>
              <li>Reference intervals and flags are taken only from the report itself; no population ranges are applied.</li>
              <li>LOINC codes are curated and not yet verified against a licensed LOINC release.</li>
            </ul>
            <div className="mt-3"><Unavailable compact code="MODEL_NOT_VALIDATED" reason="A secondary biomedical entity model (diseases and chemicals) can add model-derived statements when enabled on the server; they are marked as model inference and have no evaluation on an annotated clinical corpus. Concept-linking, clinical-transformer and radiology-relation extractors are not installed." /></div>
          </Card>
        </div>
      </div>

      <Card title="Statements" eyebrow={`${visible.length} of ${statements.length}`} className="mt-4" padded={false}>
        <div className="grid grid-cols-2 gap-2 border-b border-line p-3 sm:grid-cols-5">
          {filterSelect("negation", "Assertion", statements.map((item) => item.negation))}
          {filterSelect("certainty", "Certainty", statements.map((item) => item.certainty))}
          {filterSelect("temporality", "Temporality", statements.map((item) => item.temporality))}
          {filterSelect("experiencer", "Experiencer", statements.map((item) => item.experiencer))}
          {filterSelect("system", "System", statements.map((item) => item.anatomy_system ?? "NONE"))}
        </div>
        {visible.length === 0 ? <p className="p-4 text-sm text-ink-2">No statements match.</p> : (
          <Table headers={["Entity", "Assertion", "Certainty", "Time", "Who", "Change", "Site", "Cues", "Source"]} dense>
            {visible.map((statement) => (
              <tr key={statement.id} data-testid="source-statement" className={activeId === `s${statement.id}` ? "bg-accent-soft" : ""} onClick={() => setActiveId(`s${statement.id}`)}>
                <td>
                  <span className="font-medium text-ink">{statement.entity}</span>
                  <span className="block text-[11px] text-ink-3">{humanize(statement.category)}{statement.section ? ` · ${statement.section}` : ""}</span>
                  {statement.extractor_version.startsWith("scispacy:") && <span className="mt-0.5 block"><Badge tone="warning" title="Secondary biomedical entity model">Model inference · unvalidated</Badge></span>}
                </td>
                <td><StatusBadge status={statement.negation} /></td>
                <td><StatusBadge status={statement.certainty} /></td>
                <td className="text-xs text-ink-2">{humanize(statement.temporality)}</td>
                <td className="text-xs text-ink-2">{humanize(statement.experiencer)}</td>
                <td className="text-xs text-ink-2">{statement.comparison ? humanize(statement.comparison) : "—"}</td>
                <td className="text-xs text-ink-2">
                  {statement.anatomical_site ?? "—"}
                  {statement.anatomy_system && (
                    <Link to={`/anatomy-studio?system=${statement.anatomy_system}${statement.atlas_structure_id ? `&variant=atlas-${statement.anatomy_system}` : ""}`} className="mt-0.5 flex items-center gap-1 text-[11px] text-accent-text hover:underline"><Box size={11} aria-hidden /> {humanize(statement.anatomy_system)}</Link>
                  )}
                </td>
                <td className="max-w-[12rem]"><div className="flex flex-wrap gap-1">{statement.cues.map((cue, index) => <Badge key={index} tone="neutral" icon={false} title={cue.type}>{cue.text}</Badge>)}</div></td>
                <td className="max-w-xs text-xs text-ink-2">“{statement.source_span}”</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Measurements" eyebrow={`${measurements.length} source-linked values`} className="mt-4" padded={false}>
        {measurements.length === 0 ? <p className="p-4 text-sm text-ink-2">No explicit name/value/unit triples in this report.</p> : (
          <Table headers={["Measurement", "Value", "Documented interval", "Position", "Code", "Date", "Source"]} dense>
            {measurements.map((measurement) => (
              <tr key={measurement.id} className={activeId === `m${measurement.id}` ? "bg-accent-soft" : ""} onClick={() => setActiveId(`m${measurement.id}`)}>
                <td><span className="font-medium text-ink">{measurement.display_name}</span><span className="block font-mono text-[11px] text-ink-3">{measurement.name}</span></td>
                <td className="whitespace-nowrap tabular text-ink">{documentedValue(measurement, 3)}{measurement.conversion_status !== "AS_DOCUMENTED" && <span className="block text-[11px] text-ink-3">{humanize(measurement.conversion_status)}</span>}{measurement.documented_category && <span className="block text-[11px] text-ink-3">Printed category: {measurement.documented_category}</span>}</td>
                <td className="max-w-xs text-xs text-ink-2">{intervalText(measurement)}{measurement.documented_flag && <span className="block"><StatusBadge status={measurement.documented_flag} label={`Flag: ${humanize(measurement.documented_flag)}`} /></span>}{occurrenceNote(measurement) && <span className="block text-[11px] text-ink-3">{occurrenceNote(measurement)}</span>}</td>
                <td><StatusBadge status={measurement.documented_range_position} /></td>
                <td className="text-xs text-ink-2">{measurement.canonical_code ? <span title={measurement.code_mapping_status ?? undefined}>LOINC {measurement.canonical_code}</span> : "—"}</td>
                <td className="whitespace-nowrap text-xs text-ink-2">{measurement.documented_date ? formatDate(measurement.documented_date) : "—"}{measurement.source_page ? ` · p.${measurement.source_page}` : ""}</td>
                <td className="max-w-xs text-xs text-ink-2">“{measurement.source_span}”</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}
