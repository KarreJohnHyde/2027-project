import { useEffect, useState, type ReactNode } from "react";
import { Check, FileCheck2, X } from "lucide-react";
import { Badge, Button, Card, EmptyState, ErrorBlock, LoadingBlock, PageHeader, SelectInput, StatusBadge, TextInput, Unavailable } from "../components/ui";
import {
  api,
  type EntityCorrection,
  type HumanReviewCorrectionPayload,
  type MeasurementCorrection,
  type MedicalMeasurement,
  type ReportPage,
  type ReportPageImage,
  type ReportStatement,
  type UploadedFile,
} from "../services/api";
import { errorMessage, formatNumber, humanize } from "../lib/format";
import { documentedValue, intervalText } from "../lib/measurements";
import { pageOf, pageTypeLabel } from "../lib/reportPages";
import { Link, useLocation } from "../lib/router";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";

type Box = [number, number, number, number];
type Item =
  | { kind: "measurement"; id: string; measurement: MedicalMeasurement; box: Box | null }
  | { kind: "statement"; id: string; statement: ReportStatement; box: Box | null };
type Check = { verdict: "MATCHES" | "DIFFERS"; remove?: boolean; value?: string; unit?: string; specimen?: string; assertion?: "AFFIRMED" | "NEGATED" };

/** The OCR line boxes a page-relative text range falls on, as one box (OCR render pixels). */
function boxOf(page: ReportPage | undefined, start: number, end: number): Box | null {
  const lines = (page?.lines ?? []).filter((line) => start < line.text_end && end > line.text_start);
  if (!lines.length) return null;
  return [
    Math.min(...lines.map((line) => line.bbox_xyxy[0])), Math.min(...lines.map((line) => line.bbox_xyxy[1])),
    Math.max(...lines.map((line) => line.bbox_xyxy[2])), Math.max(...lines.map((line) => line.bbox_xyxy[3])),
  ];
}

const MAX_CORRECTIONS = 20; // per review, as the API enforces

export default function DocumentVerificationPage() {
  const { search } = useLocation();
  const reports = useWorkspace((state) => state.evidence.uploads).filter((upload) => upload.modality === "REPORT");
  const [uploadId, setUploadId] = useState<number | null>(Number(search.get("upload")) || reports[0]?.id || null);
  const activeUpload = reports.find((upload) => upload.id === uploadId) ?? reports[0] ?? null;
  if (!activeUpload) {
    return (
      <>
        <PageHeader eyebrow="Document Verification" title="Check extracted values against the source" />
        <EmptyState title="No report uploads" detail="Upload a report and run its analysis first." action={<Link to="/upload" className="text-sm text-accent-text hover:underline">Open the upload center</Link>} />
      </>
    );
  }
  const reportSelect = (
    <div className="w-72">
      <SelectInput aria-label="Report" value={activeUpload.id} onChange={(event) => setUploadId(Number(event.target.value))}>
        {reports.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename}</option>)}
      </SelectInput>
    </div>
  );
  // Keyed by upload: page, checks and the draft review start fresh for another report.
  return <VerificationWorkspace key={activeUpload.id} upload={activeUpload} reportSelect={reportSelect} />;
}

function VerificationWorkspace({ upload: activeUpload, reportSelect }: { upload: UploadedFile; reportSelect: ReactNode }) {
  const evidence = useWorkspace((state) => state.evidence);
  const user = useWorkspace((state) => state.user);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const text = useAsync(() => api.getReportText(activeUpload.id), [activeUpload.id]);
  const [pageNumber, setPageNumber] = useState(1);
  const isPdf = activeUpload.filename.toLowerCase().endsWith(".pdf");
  const image = useAsync<ReportPageImage>(() => (isPdf ? api.getReportPageImage(activeUpload.id, pageNumber) : null), [activeUpload.id, pageNumber, isPdf]);
  const [checks, setChecks] = useState<Record<string, Check>>({});
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const [rationale, setRationale] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => () => { if (image.data) URL.revokeObjectURL(image.data.url); }, [image.data]);

  const pages = text.data?.pages ?? [];
  const starts = text.data?.page_starts ?? [0];
  const page = pages[pageNumber - 1];
  const allItems: Item[] = (() => {
    if (!text.data) return [];
    const measurements = evidence.measurements.filter((measurement) => measurement.source_file_id === activeUpload.id && measurement.duplicate_of_measurement_id == null);
    const statements = evidence.statements.filter((statement) => statement.source_file_id === String(activeUpload.id) && statement.extraction_method === "TRANSPARENT_RULE_BASELINE");
    const relative = (offset: number) => offset - starts[pageOf(starts, offset) - 1];
    return [
      ...measurements.map((measurement): Item => ({
        kind: "measurement", id: `m${measurement.id}`, measurement,
        box: measurement.source_bbox ?? boxOf(pages[pageOf(starts, measurement.source_span_start) - 1], relative(measurement.source_span_start), relative(measurement.source_span_end)),
      })),
      ...statements.map((statement): Item => {
        const start = statement.source_span_start ?? statement.char_start;
        const end = statement.source_span_end ?? statement.char_end;
        return { kind: "statement", id: `s${statement.id}`, statement, box: boxOf(pages[pageOf(starts, start) - 1], relative(start), relative(end)) };
      }),
    ];
  })();
  const pageOfItem = (item: Item) => item.kind === "measurement"
    ? item.measurement.source_page ?? pageOf(starts, item.measurement.source_span_start)
    : pageOf(starts, item.statement.source_span_start ?? item.statement.char_start);
  const items = allItems.filter((item) => pageOfItem(item) === pageNumber);
  const checked = allItems.filter((item) => checks[item.id]);
  const differing = allItems.filter((item) => checks[item.id]?.verdict === "DIFFERS");
  const findingIds = [...new Set(allItems.map((item) => Number(item.kind === "measurement" ? item.measurement.finding_id : item.statement.finding_id)))];
  const canReview = user?.role === "clinician" || user?.role === "admin";

  function setCheck(id: string, check: Check | null) {
    setChecks((current) => {
      const next = { ...current };
      if (check) next[id] = check;
      else delete next[id];
      return next;
    });
    setSubmitted(null);
  }

  function payload(): HumanReviewCorrectionPayload {
    const measurement_corrections: MeasurementCorrection[] = [];
    const entity_corrections: EntityCorrection[] = [];
    for (const item of differing) {
      const check = checks[item.id];
      if (item.kind === "measurement") {
        const value = check.value?.trim() ? Number(check.value) : undefined;
        measurement_corrections.push(check.remove
          ? { target_measurement_id: item.measurement.id, action: "REMOVE" }
          : { target_measurement_id: item.measurement.id, action: "AMEND", ...(value !== undefined && Number.isFinite(value) ? { corrected_value: value } : {}),
              ...(check.unit?.trim() ? { corrected_unit: check.unit.trim() } : {}), ...(check.specimen?.trim() ? { corrected_specimen: check.specimen.trim() } : {}) });
      } else {
        entity_corrections.push(check.remove
          ? { target_statement_id: Number(item.statement.id), action: "REMOVE" }
          : { target_statement_id: Number(item.statement.id), action: "AMEND", corrected_assertion: check.assertion });
      }
    }
    return { schema_version: "1.0", status: "PROPOSED_NOT_APPLIED", entity_corrections, measurement_corrections };
  }

  const amendIncomplete = differing.some((item) => {
    const check = checks[item.id];
    if (check.remove) return false;
    return item.kind === "measurement" ? !(check.value?.trim() || check.unit?.trim() || check.specimen?.trim()) : !check.assertion;
  });

  async function submit() {
    if (findingIds.length !== 1) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const pagesChecked = [...new Set(checked.map(pageOfItem))].sort((left, right) => left - right).join(", ");
      const review = differing.length
        ? await api.submitFindingReview(findingIds[0], "MODIFIED", rationale, payload())
        : await api.submitFindingReview(findingIds[0], "CONFIRMED", `Checked ${checked.length} extracted items against the source page images (pages ${pagesChecked}).`);
      setSubmitted(differing.length
        ? `Review #${review.id} proposes ${differing.length} correction${differing.length === 1 ? "" : "s"}; a second reviewer must approve them before they change any result.`
        : `Review #${review.id} confirms the finding; the original extraction is preserved.`);
      void loadEvidence();
    } catch (failure) {
      setSubmitError(errorMessage(failure));
    } finally {
      setSubmitting(false);
    }
  }

  const imageWidth = page?.image_width ?? image.data?.source_image_width ?? null;
  const imageHeight = page?.image_height ?? image.data?.source_image_height ?? null;

  return (
    <>
      <PageHeader
        eyebrow="Document Verification"
        title="Check extracted values against the source"
        description="Each page is shown beside what was extracted from it. Mark every value and statement as matching the page or differing from it; differences become a correction proposal that a second reviewer must approve, and the original extraction is never overwritten."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {reportSelect}
            <div className="w-64">
              <SelectInput aria-label="Page" value={pageNumber} onChange={(event) => setPageNumber(Number(event.target.value))}>
                {(pages.length ? pages : [{ page: 1 } as ReportPage]).map((item) => <option key={item.page} value={item.page}>Page {item.page} · {pageTypeLabel(item)}</option>)}
              </SelectInput>
            </div>
          </div>
        }
      />
      {text.loading && <LoadingBlock label="Loading the parsed document" />}
      {text.error && <ErrorBlock message={text.error} onRetry={text.reload} />}
      {text.data && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
          <Card
            title={`Page ${pageNumber} of ${pages.length || 1}`}
            eyebrow={pageTypeLabel(page)}
            actions={image.data && <StatusBadge status={image.data.masking === "UNAVAILABLE_EMBEDDED_TEXT" ? "INSUFFICIENT_EVIDENCE" : "CONSISTENT"} label={image.data.masking === "APPLIED" ? `${image.data.masked_lines} identifier lines painted out` : image.data.masking === "NO_IDENTIFIER_LINES" ? "No identifier lines found" : "Embedded text: not masked"} />}
          >
            {!isPdf ? (
              <Unavailable compact code="NO_PAGE_IMAGE" reason="Only PDF reports have page images; check this report against its text in Document Intelligence." />
            ) : image.loading ? <LoadingBlock label="Rendering page" /> : image.error ? <ErrorBlock message={image.error} onRetry={image.reload} /> : image.data && (
              <div className="relative overflow-hidden rounded-lg border border-line bg-surface-2">
                <img src={image.data.url} alt={`Page ${pageNumber} of the report, identifier lines painted out`} className="block w-full" />
                {imageWidth && imageHeight && (
                  <svg aria-label="Extracted items on this page" className="absolute inset-0 h-full w-full" viewBox={`0 0 ${imageWidth} ${imageHeight}`} preserveAspectRatio="none">
                    {items.filter((item) => item.box).map((item) => {
                      const [x0, y0, x1, y1] = item.box!;
                      const verdict = checks[item.id]?.verdict;
                      const stroke = verdict === "DIFFERS" ? "var(--mt-critical)" : verdict === "MATCHES" ? "var(--mt-good)" : item.kind === "measurement" ? "var(--mt-series-1)" : "var(--mt-warning)";
                      return (
                        <rect key={item.id} x={x0 - 6} y={y0 - 6} width={x1 - x0 + 12} height={y1 - y0 + 12} rx={6} fill={activeItem === item.id ? "color-mix(in srgb, var(--mt-focus) 18%, transparent)" : "transparent"}
                          stroke={stroke} strokeWidth={activeItem === item.id ? 9 : 5} onMouseEnter={() => setActiveItem(item.id)} className="cursor-pointer" />
                      );
                    })}
                  </svg>
                )}
              </div>
            )}
            <p className="mt-2 text-[11px] leading-4 text-ink-3">
              Lines in which the identifier masks found a name, number or address are painted out; logos, signatures and unlabelled names can remain, so this view is limited to people with access to the case.
              Boxes: blue values, amber statements, green checked as matching, red marked as differing.
            </p>
          </Card>

          <div className="space-y-4">
            <Card title="Extracted from this page" eyebrow={`${items.length} items · ${checked.length} of ${allItems.length} checked in this report`}>
              {items.length === 0 ? <p className="text-xs text-ink-2">Nothing was extracted from this page.</p> : (
                <ul className="space-y-2">
                  {items.map((item) => {
                    const check = checks[item.id];
                    return (
                      <li key={item.id} onMouseEnter={() => setActiveItem(item.id)} className={`rounded-lg border p-2.5 ${activeItem === item.id ? "border-[var(--mt-focus)]" : "border-line"}`}>
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            {item.kind === "measurement" ? (
                              <>
                                <p className="text-xs font-medium text-ink">{item.measurement.display_name} <span className="tabular">{documentedValue(item.measurement, 3)}</span></p>
                                <p className="text-[11px] text-ink-3">Interval {intervalText(item.measurement)} · specimen {item.measurement.specimen === "NOT_DOCUMENTED" ? "not printed" : item.measurement.specimen}</p>
                                <p className="text-[11px] text-ink-2">“{item.measurement.source_span}”</p>
                              </>
                            ) : (
                              <>
                                <p className="text-xs font-medium text-ink">{item.statement.entity} <span className="font-normal text-ink-3">· {humanize(item.statement.negation)} · {humanize(item.statement.certainty)}</span></p>
                                <p className="text-[11px] text-ink-2">“{item.statement.source_span}”</p>
                              </>
                            )}
                            {!item.box && <p className="text-[11px] text-ink-3">No box on the page image (embedded text or a value read across lines).</p>}
                          </div>
                          <div className="flex shrink-0 gap-1">
                            <Button size="sm" variant={check?.verdict === "MATCHES" ? "primary" : "secondary"} icon={Check} onClick={() => setCheck(item.id, check?.verdict === "MATCHES" ? null : { verdict: "MATCHES" })}>Matches</Button>
                            <Button size="sm" variant={check?.verdict === "DIFFERS" ? "primary" : "secondary"} icon={X} onClick={() => setCheck(item.id, check?.verdict === "DIFFERS" ? null : { verdict: "DIFFERS" })}>Differs</Button>
                          </div>
                        </div>
                        {check?.verdict === "DIFFERS" && (
                          <div className="mt-2 grid gap-2 border-t border-line pt-2 sm:grid-cols-3">
                            <label className="flex items-center gap-1.5 text-[11px] text-ink-2 sm:col-span-3">
                              <input type="checkbox" checked={Boolean(check.remove)} onChange={(event) => setCheck(item.id, { ...check, remove: event.target.checked })} />
                              Not on the page: propose removing it
                            </label>
                            {!check.remove && item.kind === "measurement" && (
                              <>
                                <TextInput aria-label="Value on the page" placeholder={`Value (${formatNumber(item.measurement.value)})`} inputMode="decimal" value={check.value ?? ""} onChange={(event) => setCheck(item.id, { ...check, value: event.target.value })} />
                                <TextInput aria-label="Unit on the page" placeholder={`Unit (${item.measurement.unit})`} value={check.unit ?? ""} onChange={(event) => setCheck(item.id, { ...check, unit: event.target.value })} />
                                <TextInput aria-label="Specimen on the page" placeholder="Specimen" value={check.specimen ?? ""} onChange={(event) => setCheck(item.id, { ...check, specimen: event.target.value })} />
                              </>
                            )}
                            {!check.remove && item.kind === "statement" && (
                              <SelectInput aria-label="Assertion on the page" value={check.assertion ?? ""} onChange={(event) => setCheck(item.id, { ...check, assertion: (event.target.value || undefined) as Check["assertion"] })}>
                                <option value="">Assertion on the page…</option>
                                <option value="AFFIRMED">Affirmed</option>
                                <option value="NEGATED">Negated</option>
                              </SelectInput>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>

            <Card title="Record the check" eyebrow="Finding-level human review">
              <ul className="space-y-1 text-xs text-ink-2">
                <li>{checked.length} of {allItems.length} items checked across {pages.length || 1} page{pages.length === 1 ? "" : "s"}; {differing.length} differ from the source.</li>
                <li>{differing.length ? "Differences are submitted as one correction proposal (MODIFIED review)." : "With every item checked and none differing, the finding can be confirmed (CONFIRMED review)."}</li>
              </ul>
              {differing.length > 0 && (
                <TextInput className="mt-2" aria-label="Reason for the corrections" placeholder="Reason for the corrections (required)" value={rationale} onChange={(event) => setRationale(event.target.value)} />
              )}
              {!canReview && <p className="mt-2 text-[11px] text-ink-3">Only clinician or administrator accounts can record reviews; the check above is not saved.</p>}
              {findingIds.length > 1 && <p className="mt-2 text-[11px] text-ink-3">This report was analysed more than once; record the review from the Case Workspace.</p>}
              {differing.length > MAX_CORRECTIONS && <p className="mt-2 text-[11px] text-ink-3">At most {MAX_CORRECTIONS} corrections fit in one review.</p>}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button
                  variant="primary"
                  icon={FileCheck2}
                  loading={submitting}
                  disabled={!canReview || findingIds.length !== 1 || (differing.length
                    ? !rationale.trim() || amendIncomplete || differing.length > MAX_CORRECTIONS
                    : checked.length !== allItems.length || allItems.length === 0)}
                  onClick={() => void submit()}
                >
                  {differing.length ? "Propose corrections" : "Confirm finding"}
                </Button>
                {submitted && <Badge tone="good">{submitted}</Badge>}
              </div>
              {submitError && <div className="mt-2"><ErrorBlock message={submitError} /></div>}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
