import { useId, useState, type FormEvent } from "react";
import { ClipboardPlus, FlaskConical, Trash2 } from "lucide-react";
import { Badge, Button, Card, Dialog, EmptyState, ErrorBlock, Field, LoadingBlock, SelectInput, StatusBadge, Table, TextArea, TextInput } from "./ui";
import { api, type LabReportRecord, type LabTestReference, type LabTestResult, type OrderedPackageRecord, type OrderStatus, type UploadedFile } from "../services/api";
import { errorMessage, formatDate, humanize, todayInputValue } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const NOT_DOCUMENTED = "NOT_DOCUMENTED";

/** Allowed next states, mirroring ORDER_TRANSITIONS in backend/app/routers/catalog.py. */
const NEXT_STATUS: Record<OrderStatus, Array<{ status: OrderStatus; label: string }>> = {
  ORDERED: [{ status: "IN_PROGRESS", label: "Start" }, { status: "CANCELLED", label: "Cancel" }],
  IN_PROGRESS: [{ status: "COMPLETED", label: "Complete" }, { status: "CANCELLED", label: "Cancel" }],
  COMPLETED: [],
  CANCELLED: [],
};

/** Flags are interval comparisons, so they are worded as positions, never as findings. */
const FLAG_LABEL: Record<LabTestResult["status"], string> = {
  NORMAL: "Within interval",
  LOW: "Below interval",
  HIGH: "Above interval",
  ABNORMAL: "Differs from expected",
  INFO: "Recorded",
  NO_REFERENCE: "No interval",
  INDETERMINATE: "Indeterminate",
};

const INTERVAL_SOURCE_LABEL: Record<string, string> = {
  REPORTING_LABORATORY: "Reporting laboratory",
  CATALOG_EXPECTED_RESULT: "Catalog expected result",
  NONE: "Not printed on report",
};

const CATALOG_DEFAULT_LABEL: Record<string, string> = {
  CATALOG_SEX_SPECIFIC_DEFAULT: "sex-specific catalog default",
  CATALOG_TYPICAL_ADULT_DEFAULT: "typical adult catalog default",
};

function documented(value: string | null | undefined): string {
  return !value || value === NOT_DOCUMENTED ? "Not documented" : value;
}

// ------------------------------------------------------------------ orders

function NewOrderDialog({ caseId, onClose, onCreated }: { caseId: number; onClose: () => void; onCreated: () => void }) {
  const formId = useId();
  const catalog = useAsync(() => Promise.all([api.getHealthPackages(), api.getImagingServices()]), []);
  const [itemId, setItemId] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createCaseOrder(caseId, itemId, notes.trim() || undefined);
      onCreated();
      onClose();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  const [packages, imaging] = catalog.data ?? [[], []];
  return (
    <Dialog
      title="Order an investigation"
      description="Records that an investigation was requested for this research case. An order produces no result; results enter the case only when uploaded or transcribed from the performing laboratory's report."
      onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button type="submit" form={formId} variant="primary" loading={busy} disabled={!itemId}>Place order</Button></>}
    >
      {catalog.loading && <LoadingBlock label="Loading catalog" />}
      {catalog.error && <ErrorBlock message={catalog.error} onRetry={catalog.reload} />}
      {catalog.data && (
        <form id={formId} onSubmit={submit} className="space-y-3">
          <Field label="Catalog item" htmlFor={`${formId}-item`}>
            <SelectInput id={`${formId}-item`} value={itemId} onChange={(event) => setItemId(event.target.value)} required>
              <option value="">Select a package or imaging study</option>
              <optgroup label="Laboratory packages">
                {packages.map((item) => <option key={item.id} value={item.id}>{item.name} ({humanize(item.kind)})</option>)}
              </optgroup>
              {imaging.map((category) => (
                <optgroup key={category.id} label={category.category}>
                  {category.modalities.map((modality) => <option key={modality.code} value={modality.code}>{modality.name}</option>)}
                </optgroup>
              ))}
            </SelectInput>
          </Field>
          <Field label="Clinical notes" hint="Optional. Do not enter names or other direct identifiers." htmlFor={`${formId}-notes`}>
            <TextArea id={`${formId}-notes`} rows={3} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </Field>
          {error && <ErrorBlock message={error} />}
        </form>
      )}
    </Dialog>
  );
}

export function OrdersCard({ caseId }: { caseId: number }) {
  const orders = useAsync(() => api.getCaseOrders(caseId), [caseId]);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function advance(order: OrderedPackageRecord, status: OrderStatus) {
    setBusy(order.id);
    setError(null);
    try {
      await api.updateCaseOrderStatus(caseId, order.id, status);
      orders.reload();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Investigation orders" eyebrow="Requested, not resulted" padded={false} actions={<Button size="sm" icon={ClipboardPlus} onClick={() => setCreating(true)}>New order</Button>}>
      {orders.error && <div className="p-3"><ErrorBlock message={orders.error} onRetry={orders.reload} /></div>}
      {error && <div className="p-3"><ErrorBlock message={error} /></div>}
      {orders.data && orders.data.length === 0 && <p className="p-4 text-sm text-ink-2">No investigations ordered for this case.</p>}
      {orders.data && orders.data.length > 0 && (
        <Table headers={["Item", "Status", "Ordered", "Notes", ""]} dense>
          {orders.data.map((order) => (
            <tr key={order.id}>
              <td><span className="font-medium text-ink">{order.package_name}</span><span className="block text-[11px] text-ink-3">{order.category} · {order.package_id}</span></td>
              <td><StatusBadge status={order.status} /></td>
              <td className="whitespace-nowrap text-xs text-ink-2">{formatDate(order.created_at)}</td>
              <td className="max-w-[14rem] text-xs text-ink-2">{order.clinical_notes || "—"}</td>
              <td className="whitespace-nowrap text-right">
                {NEXT_STATUS[order.status].map((next) => (
                  <Button key={next.status} size="sm" variant={next.status === "CANCELLED" ? "ghost" : "secondary"} loading={busy === order.id} onClick={() => void advance(order, next.status)} className="ml-1">{next.label}</Button>
                ))}
              </td>
            </tr>
          ))}
        </Table>
      )}
      {creating && <NewOrderDialog caseId={caseId} onClose={() => setCreating(false)} onCreated={orders.reload} />}
    </Card>
  );
}

// ------------------------------------------------------- laboratory results

type EntryRow = { code: string; operator: '=' | '<' | '>' | '<=' | '>='; value: string; refLow: string; refHigh: string };

function optionalNumber(value: string): number | undefined {
  return value.trim() === "" ? undefined : Number(value);
}

function RecordResultsDialog({ caseId, uploads, onClose, onRecorded }: { caseId: number; uploads: UploadedFile[]; onClose: () => void; onRecorded: () => void }) {
  const formId = useId();
  const catalog = useAsync(() => Promise.all([api.getLabTestCatalog(), api.getHealthPackages(), api.getCaseOrders(caseId)]), [caseId]);
  const [orderId, setOrderId] = useState("");
  const packageTests = useAsync(() => {
    const order = catalog.data?.[2].find((item) => String(item.id) === orderId);
    return order ? api.getHealthPackage(order.package_id) : null;
  }, [orderId, catalog.data]);
  const [rows, setRows] = useState<EntryRow[]>([]);
  const [meta, setMeta] = useState({ title: "", lab: "", specimen: "", method: "", date: "", sex: "", source: "", summary: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tests = catalog.data?.[0].tests ?? [];
  const panels = catalog.data?.[0].panels ?? {};
  const byCode = new Map(tests.map((test) => [test.code, test]));
  const packageIds = new Set((catalog.data?.[1] ?? []).map((item) => item.id));
  const labOrders = (catalog.data?.[2] ?? []).filter((order) => packageIds.has(order.package_id) && order.status !== "CANCELLED");
  const allowed = orderId && packageTests.data?.lab_test_codes ? new Set(packageTests.data.lab_test_codes) : null;
  const available = tests.filter((test) => (!allowed || allowed.has(test.code)) && !rows.some((row) => row.code === test.code));

  function add(codes: string[]) {
    setRows((current) => [...current, ...codes.filter((code) => !current.some((row) => row.code === code)).map((code): EntryRow => ({ code, operator: "=", value: "", refLow: "", refHigh: "" }))]);
  }
  function update(code: string, patch: Partial<EntryRow>) {
    setRows((current) => current.map((row) => (row.code === code ? { ...row, ...patch } : row)));
  }
  function selectOrder(value: string) {
    setOrderId(value);
    // Rows outside a newly linked package would be rejected by the server.
    if (value) setRows([]);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const filled = rows.filter((row) => row.value.trim() !== "");
    if (filled.length === 0) {
      setError("Enter at least one result exactly as printed on the report.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createCaseLabReport(caseId, {
        ordered_package_id: orderId ? Number(orderId) : undefined,
        source_file_id: meta.source ? Number(meta.source) : undefined,
        report_title: meta.title.trim() || undefined,
        lab_name: meta.lab.trim() || undefined,
        sample_type: meta.specimen.trim() || undefined,
        laboratory_method: meta.method.trim() || undefined,
        patient_sex: meta.sex === "M" || meta.sex === "F" ? meta.sex : undefined,
        collection_date: meta.date || undefined,
        clinical_summary: meta.summary.trim() || undefined,
        results: filled.map((row) => {
          const test = byCode.get(row.code);
          const quantitative = test?.kind === "QUANTITATIVE";
          return {
            code: row.code,
            result_operator: row.operator,
            value: quantitative ? Number(row.value) : row.value,
            ref_low: quantitative ? optionalNumber(row.refLow) : undefined,
            ref_high: quantitative ? optionalNumber(row.refHigh) : undefined,
          };
        }),
      });
      onRecorded();
      onClose();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      wide
      title="Transcribe laboratory results"
      description="Copy values exactly as printed on the performing laboratory's report. Fields left blank are stored as not documented; nothing is assumed or pre-filled."
      onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button type="submit" form={formId} variant="primary" loading={busy} disabled={rows.length === 0}>Record results</Button></>}
    >
      {catalog.loading && <LoadingBlock label="Loading test catalog" />}
      {catalog.error && <ErrorBlock message={catalog.error} onRetry={catalog.reload} />}
      {catalog.data && (
        <form id={formId} onSubmit={submit} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Source document" hint="The uploaded report these values come from." htmlFor={`${formId}-source`}>
              <SelectInput id={`${formId}-source`} value={meta.source} onChange={(event) => setMeta({ ...meta, source: event.target.value })}>
                <option value="">Not linked</option>
                {uploads.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename}</option>)}
              </SelectInput>
            </Field>
            <Field label="Sample collection date" hint="Needed for the result to join a longitudinal series." htmlFor={`${formId}-date`}>
              <TextInput id={`${formId}-date`} type="date" max={todayInputValue()} value={meta.date} onChange={(event) => setMeta({ ...meta, date: event.target.value })} />
            </Field>
            <Field label="Performing laboratory" htmlFor={`${formId}-lab`}>
              <TextInput id={`${formId}-lab`} maxLength={128} placeholder="Not documented" value={meta.lab} onChange={(event) => setMeta({ ...meta, lab: event.target.value })} />
            </Field>
            <Field label="Specimen" htmlFor={`${formId}-specimen`}>
              <TextInput id={`${formId}-specimen`} maxLength={64} placeholder="Not documented" value={meta.specimen} onChange={(event) => setMeta({ ...meta, specimen: event.target.value })} />
            </Field>
            <Field label="Assay / method" htmlFor={`${formId}-method`}>
              <TextInput id={`${formId}-method`} maxLength={128} placeholder="Not documented" value={meta.method} onChange={(event) => setMeta({ ...meta, method: event.target.value })} />
            </Field>
            <Field label="Report title" htmlFor={`${formId}-title`}>
              <TextInput id={`${formId}-title`} maxLength={128} placeholder="Laboratory Investigation Report" value={meta.title} onChange={(event) => setMeta({ ...meta, title: event.target.value })} />
            </Field>
            <Field label="Sex as documented on the report" hint="Selects which catalog default is shown for orientation." htmlFor={`${formId}-sex`}>
              <SelectInput id={`${formId}-sex`} value={meta.sex} onChange={(event) => setMeta({ ...meta, sex: event.target.value })}>
                <option value="">Not documented</option>
                <option value="F">Female</option>
                <option value="M">Male</option>
              </SelectInput>
            </Field>
            {labOrders.length > 0 && (
              <Field label="Linked order" hint="Restricts entry to the ordered package's tests." htmlFor={`${formId}-order`}>
                <SelectInput id={`${formId}-order`} value={orderId} onChange={(event) => selectOrder(event.target.value)}>
                  <option value="">None</option>
                  {labOrders.map((order) => <option key={order.id} value={order.id}>#{order.id} {order.package_name} ({humanize(order.status)})</option>)}
                </SelectInput>
              </Field>
            )}
          </div>

          <div className="flex flex-wrap items-end gap-2 border-t border-line pt-3">
            <div className="w-56">
              <SelectInput aria-label="Add a panel" value="" onChange={(event) => add(available.filter((test) => test.panel === event.target.value).map((test) => test.code))}>
                <option value="">Add a panel…</option>
                {Object.entries(panels).filter(([key]) => available.some((test) => test.panel === key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </SelectInput>
            </div>
            <div className="w-64">
              <SelectInput aria-label="Add a test" value="" onChange={(event) => event.target.value && add([event.target.value])}>
                <option value="">Add a single test…</option>
                {available.map((test) => <option key={test.code} value={test.code}>{test.name}</option>)}
              </SelectInput>
            </div>
            {orderId && packageTests.loading && <span className="text-xs text-ink-3">Loading package tests…</span>}
          </div>

          {rows.length === 0 ? (
            <EmptyState icon={FlaskConical} title="No tests added" detail="Add the panels or tests that appear on the report." />
          ) : (
            <Table headers={["Test", "Result as printed", "Laboratory interval (as printed)", ""]} dense>
              {rows.map((row) => {
                const test = byCode.get(row.code) as LabTestReference;
                const quantitative = test.kind === "QUANTITATIVE";
                return (
                  <tr key={row.code}>
                    <td className="text-xs"><span className="font-medium text-ink">{test.name}</span>{test.unit && <span className="block text-ink-3">{test.unit}</span>}</td>
                    <td className="w-40">
                      {quantitative ? (
                        <div className="flex gap-1">
                          <SelectInput aria-label={`${test.name} comparator`} value={row.operator} onChange={(event) => update(row.code, { operator: event.target.value as EntryRow["operator"] })} className="h-8 w-16 text-xs">
                            {(["=", "<", ">", "<=", ">="] as const).map((operator) => <option key={operator} value={operator}>{operator}</option>)}
                          </SelectInput>
                          <TextInput aria-label={`${test.name} value`} type="number" step="any" inputMode="decimal" value={row.value} onChange={(event) => update(row.code, { value: event.target.value })} className="h-8 text-xs" />
                        </div>
                      ) : (
                        <SelectInput aria-label={`${test.name} value`} value={row.value} onChange={(event) => update(row.code, { value: event.target.value })} className="h-8 text-xs">
                          <option value="">—</option>
                          {(test.options ?? []).map((option) => <option key={option} value={option}>{humanize(option)}</option>)}
                        </SelectInput>
                      )}
                    </td>
                    <td>
                      {quantitative ? (
                        <div className="flex items-center gap-1.5">
                          <TextInput aria-label={`${test.name} interval low`} type="number" step="any" placeholder="low" value={row.refLow} onChange={(event) => update(row.code, { refLow: event.target.value })} className="h-8 w-20 text-xs" />
                          <span className="text-ink-3">–</span>
                          <TextInput aria-label={`${test.name} interval high`} type="number" step="any" placeholder="high" value={row.refHigh} onChange={(event) => update(row.code, { refHigh: event.target.value })} className="h-8 w-20 text-xs" />
                        </div>
                      ) : <span className="text-xs text-ink-3">Expected: {humanize(test.expected ?? "—")}</span>}
                    </td>
                    <td className="text-right">
                      <button type="button" aria-label={`Remove ${test.name}`} onClick={() => setRows((current) => current.filter((item) => item.code !== row.code))} className="rounded p-1 text-ink-3 hover:text-critical-text"><Trash2 size={14} /></button>
                    </td>
                  </tr>
                );
              })}
            </Table>
          )}
          <p className="text-[11px] leading-4 text-ink-3">Leave the interval blank when the report prints none. The position is then recorded as indeterminate; a catalog default is shown for orientation only and is never used in place of the laboratory's interval.</p>
          <Field label="Comment" hint="Optional. No names or direct identifiers." htmlFor={`${formId}-summary`}>
            <TextArea id={`${formId}-summary`} rows={2} maxLength={4000} value={meta.summary} onChange={(event) => setMeta({ ...meta, summary: event.target.value })} />
          </Field>
          {error && <ErrorBlock message={error} />}
        </form>
      )}
    </Dialog>
  );
}

function ReportBlock({ report, uploads }: { report: LabReportRecord; uploads: UploadedFile[] }) {
  const source = uploads.find((upload) => upload.id === report.source_file_id);
  return (
    <div className="border-t border-line first:border-t-0">
      <div className="flex flex-wrap items-start justify-between gap-2 px-4 pt-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">{report.report_title}</p>
          <p className="text-[11px] leading-4 text-ink-3">
            {documented(report.lab_name)} · specimen {documented(report.sample_type).toLowerCase()} · method {documented(report.laboratory_method).toLowerCase()} · collected {report.collection_date ? formatDate(report.collection_date) : "date not documented"}
          </p>
          <p className="text-[11px] leading-4 text-ink-3">{source ? `Transcribed from ${source.filename}` : "No source document linked: transcription cannot be checked against a source"} · recorded {formatDate(report.created_at)}</p>
        </div>
        <div className="flex flex-wrap gap-1"><Badge tone="warning">{humanize(report.entry_method ?? "MANUAL_TRANSCRIPTION")}</Badge><StatusBadge status={report.review_status} /></div>
      </div>
      <Table headers={["Test", "Result", "Interval", "Interval source", "Position"]} dense>
        {report.results.map((result) => (
          <tr key={result.code}>
            <td className="text-xs text-ink">{result.test_name}</td>
            <td className="whitespace-nowrap text-xs tabular text-ink">{result.result_operator && result.result_operator !== "=" ? result.result_operator : ""}{typeof result.result_value === "number" ? result.result_value : humanize(result.result_value)} {result.unit}</td>
            <td className="whitespace-nowrap text-xs text-ink-2">{result.bio_ref_interval || "—"}</td>
            <td className="text-xs text-ink-2">
              {INTERVAL_SOURCE_LABEL[result.reference_source ?? ""] ?? "Not recorded"}
              {result.catalog_interval && <span className="block text-[11px] text-ink-3">For orientation only: {result.catalog_interval} ({CATALOG_DEFAULT_LABEL[result.catalog_interval_source ?? ""] ?? "catalog default"})</span>}
            </td>
            <td><StatusBadge status={result.status} label={FLAG_LABEL[result.status] ?? humanize(result.status)} /></td>
          </tr>
        ))}
      </Table>
    </div>
  );
}

export function LabReportsCard({ caseId, uploads, onChanged }: { caseId: number; uploads: UploadedFile[]; onChanged?: () => void }) {
  const reports = useAsync(() => api.getCaseLabReports(caseId), [caseId]);
  const [recording, setRecording] = useState(false);
  return (
    <Card
      title="Transcribed laboratory results"
      eyebrow="Manual entry against the test catalog"
      padded={false}
      actions={<Button size="sm" icon={FlaskConical} onClick={() => setRecording(true)}>Transcribe results</Button>}
    >
      {reports.error && <div className="p-3"><ErrorBlock message={reports.error} onRetry={reports.reload} /></div>}
      {reports.loading && !reports.data && <LoadingBlock label="Loading laboratory reports" />}
      {reports.data && reports.data.length === 0 && <p className="p-4 text-sm text-ink-2">No results transcribed. Values extracted from uploaded reports appear in the series above without manual entry.</p>}
      {(reports.data ?? []).map((report) => <ReportBlock key={report.id} report={report} uploads={uploads} />)}
      <p className="border-t border-line px-4 py-2.5 text-[11px] leading-4 text-ink-3">Positions compare a value with the interval the laboratory printed and are indeterminate without one; they are not diagnoses. Dated quantitative results join the matching series; a transcription that repeats an extracted value on the same date is excluded as a duplicate.</p>
      {recording && <RecordResultsDialog caseId={caseId} uploads={uploads} onClose={() => setRecording(false)} onRecorded={() => { reports.reload(); onChanged?.(); }} />}
    </Card>
  );
}
