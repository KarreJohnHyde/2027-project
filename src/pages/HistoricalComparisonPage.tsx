import { useMemo, useState } from "react";
import { GitCompareArrows } from "lucide-react";
import { Button, Card, EmptyState, ErrorBlock, Field, PageHeader, SelectInput, SourceExcerpt, StatusBadge, Table, Unavailable } from "../components/ui";
import { api, type LongitudinalComparisonResponse } from "../services/api";
import { errorMessage, formatDate, formatNumber, humanize } from "../lib/format";
import { useSelectedCase, useWorkspace } from "../state/workspace";

const IMAGE_CHECKS: Array<[string, string]> = [
  ["Same patient / case", "VERIFIED_BY_CASE_BINDING"],
  ["Same anatomy", "NOT_VERIFIED"],
  ["Comparable modality and sequence", "NOT_VERIFIED"],
  ["Acquisition protocol", "NOT_VERIFIED"],
  ["Orientation", "NOT_VERIFIED"],
  ["Resolution and spacing", "NOT_VERIFIED"],
  ["Acquisition timing", "NOT_VERIFIED"],
  ["Image quality", "NOT_VERIFIED"],
  ["Measurement reproducibility", "NOT_VERIFIED"],
];

export default function HistoricalComparisonPage() {
  const selected = useSelectedCase()!;
  const uploads = useWorkspace((state) => state.evidence.uploads);
  const loadEvidence = useWorkspace((state) => state.loadEvidence);
  const exams = useMemo(() => [...selected.examinations].sort((left, right) => left.exam_date.localeCompare(right.exam_date)), [selected.examinations]);
  const [priorId, setPriorId] = useState<number | null>(exams[0]?.id ?? null);
  const [currentId, setCurrentId] = useState<number | null>(exams.length > 1 ? exams[exams.length - 1].id : null);
  const [result, setResult] = useState<LongitudinalComparisonResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prior = exams.find((exam) => exam.id === priorId);
  const current = exams.find((exam) => exam.id === currentId);
  const chronological = Boolean(prior && current && prior.id !== current.id && prior.exam_date < current.exam_date);

  async function compare() {
    if (!priorId || !currentId) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.compareExaminations<LongitudinalComparisonResponse>(selected.id, priorId, currentId));
      await loadEvidence();
    } catch (requestError) {
      setResult(null);
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  const sourceName = (id: number) => uploads.find((upload) => upload.id === id)?.filename ?? `upload #${id}`;
  const intervalDays = result?.interval_days ?? null;

  return (
    <>
      <PageHeader eyebrow="Historical Comparison" title="Examination-pair comparison" description="Documented values with the same analyte and unit are compared source to source. Report wording changes are listed as documented. Nothing is interpreted as progression, improvement or causality." />
      <Card title="Select a chronological pair">
        {exams.length < 2 ? (
          <Unavailable code="INSUFFICIENT_EVIDENCE" reason="At least two dated examinations are needed. Add examinations in the Case Workspace and link uploads to them." />
        ) : (
          <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto] lg:items-end">
            <Field label="Prior examination">
              <SelectInput value={priorId ?? ""} onChange={(event) => { setPriorId(Number(event.target.value)); setResult(null); }}>{exams.map((exam) => <option key={exam.id} value={exam.id}>{formatDate(exam.exam_date)} · {humanize(exam.modality)}</option>)}</SelectInput>
            </Field>
            <GitCompareArrows aria-hidden size={17} className="mb-2.5 hidden text-ink-3 lg:block" />
            <Field label="Current examination">
              <SelectInput value={currentId ?? ""} onChange={(event) => { setCurrentId(Number(event.target.value)); setResult(null); }}>{exams.map((exam) => <option key={exam.id} value={exam.id}>{formatDate(exam.exam_date)} · {humanize(exam.modality)}</option>)}</SelectInput>
            </Field>
            <Button variant="primary" icon={GitCompareArrows} loading={busy} disabled={!chronological} onClick={() => void compare()}>Compare</Button>
          </div>
        )}
        {exams.length >= 2 && !chronological && <p className="mt-3 text-xs text-warning-text">Choose two distinct examinations with the prior date earlier than the current date.</p>}
        {error && <div className="mt-3"><ErrorBlock message={error} /></div>}
        {result && <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-ink-2"><StatusBadge status={result.status} /> {result.reason}{intervalDays !== null && <span className="text-ink-3">Interval {intervalDays} days.</span>}</p>}
      </Card>

      {result && (
        <>
          <Card title="Numeric differences" eyebrow={`${result.numeric_deltas?.length ?? 0} matched values`} className="mt-4" padded={false}>
            {(result.numeric_deltas?.length ?? 0) === 0 ? <p className="p-4 text-sm text-ink-2">No unit-compatible values documented in both examinations.</p> : (
              <Table headers={["Measurement", "Prior", "Current", "Δx", "Δx%", "Rate Δx/Δt", "Sources"]}>
                {result.numeric_deltas!.map((delta) => (
                  <tr key={`${delta.prior.measurement_id}-${delta.current.measurement_id}`}>
                    <td><span className="font-medium text-ink">{delta.display_name}</span><span className="block font-mono text-[11px] text-ink-3">{delta.name}</span>{delta.name.endsWith("_size") && <span className="mt-0.5 block text-[11px] text-warning-text">Lesion identity across reports not verified</span>}</td>
                    <td className="whitespace-nowrap tabular">{formatNumber(delta.prior.value, 4)} {delta.unit}</td>
                    <td className="whitespace-nowrap tabular">{formatNumber(delta.current.value, 4)} {delta.unit}</td>
                    <td className="whitespace-nowrap tabular font-medium text-ink">{formatNumber(delta.absolute_delta, 4)} {delta.unit}</td>
                    <td className="whitespace-nowrap tabular">{delta.percent_change === null ? "Undefined (zero baseline)" : `${formatNumber(delta.percent_change, 2)}%`}</td>
                    <td className="whitespace-nowrap tabular text-ink-2">{intervalDays ? `${formatNumber(delta.absolute_delta / intervalDays, 5)} ${delta.unit}/day` : "—"}</td>
                    <td className="min-w-[16rem] space-y-1.5 text-xs">
                      <SourceExcerpt text={delta.prior.source_span} />
                      <p className="text-[11px] text-ink-3">{sourceName(delta.prior.source_file_id)}</p>
                      <SourceExcerpt text={delta.current.source_span} />
                      <p className="text-[11px] text-ink-3">{sourceName(delta.current.source_file_id)}</p>
                    </td>
                  </tr>
                ))}
              </Table>
            )}
            {(result.numeric_comparison_blockers?.length ?? 0) > 0 && (
              <div className="border-t border-line p-4">
                <p className="text-xs font-medium text-ink">Values intentionally not compared</p>
                <ul className="mt-1 space-y-1 text-[11px] text-ink-3">
                  {result.numeric_comparison_blockers!.map((item, index) => (
                    <li key={`${item.name}-${item.unit}-${index}`}>{item.name} ({item.unit}): {humanize(item.reason)}{item.prior || item.current ? ` — prior ${item.prior ?? "not documented"}, current ${item.current ?? "not documented"}` : ""}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card title="Documented report changes" eyebrow="Statement-level differences" className="mt-4" padded={false}>
            {(result.semantic_report_diff?.length ?? 0) === 0 ? <p className="p-4 text-sm text-ink-2">No statement differences between the linked reports.</p> : (
              <Table headers={["Entity", "Change", "Prior statement", "Current statement"]}>
                {result.semantic_report_diff!.map((item, index) => (
                  <tr key={`${item.entity}-${item.identity.anatomical_site ?? "unspecified"}-${item.identity.laterality ?? "unspecified"}-${index}`}>
                    <td className="font-medium text-ink">{item.entity}<span className="block text-[11px] font-normal text-ink-3">{[item.identity.laterality, item.identity.anatomical_site].filter(Boolean).map((value) => humanize(value!)).join(" · ") || "No additional documented localization"}</span></td>
                    <td><StatusBadge status={item.change_type} /></td>
                    <td className="max-w-sm text-xs text-ink-2">{item.prior ? <>{humanize(item.prior.assertion)}, {humanize(item.prior.temporality)}, {humanize(item.prior.certainty ?? "NOT_DOCUMENTED")}<span className="block">“{item.prior.source_span}”</span></> : "—"}</td>
                    <td className="max-w-sm text-xs text-ink-2">{item.current ? <>{humanize(item.current.assertion)}, {humanize(item.current.temporality)}, {humanize(item.current.certainty ?? "NOT_DOCUMENTED")}<span className="block">“{item.current.source_span}”</span></> : "—"}</td>
                  </tr>
                ))}
              </Table>
            )}
            {(result.semantic_comparison_blockers?.length ?? 0) > 0 && (
              <div className="border-t border-line p-4">
                <p className="text-xs font-medium text-ink">Statements intentionally not paired</p>
                <ul className="mt-1 space-y-1 text-[11px] text-ink-3">
                  {result.semantic_comparison_blockers!.map((item, index) => (
                    <li key={`${item.entity}-${index}`}>{item.entity}: {humanize(item.reason)} ({item.prior.length} prior, {item.current.length} current). Explicit reviewer pairing is required.</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        </>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Imaging comparison" eyebrow="Registration-dependent">
          <Unavailable code="REGISTRATION_UNAVAILABLE" reason={result?.image_comparison?.reason ?? "Images are never subtracted or overlaid without validated registration."}>
            {result?.image_comparison && <p className="mt-1 text-xs text-ink-2">Prior images {result.image_comparison.prior_associated_image_count} · current images {result.image_comparison.current_associated_image_count}</p>}
          </Unavailable>
          <ul className="mt-3 space-y-1">
            {IMAGE_CHECKS.map(([label, status]) => <li key={label} className="flex items-center justify-between gap-2 text-xs"><span className="text-ink-2">{label}</span><StatusBadge status={status} /></li>)}
          </ul>
        </Card>
        <Card title="Anatomical change" eyebrow="3D twin state">
          <Unavailable code={result?.twin_state_delta?.status ?? "MAPPING_UNSUPPORTED"} reason={result?.twin_state_delta?.reason ?? "No held-out landmark registration supports an anatomical comparison."} />
          {!result && exams.length >= 2 && <div className="mt-3"><EmptyState title="Comparison not run" detail="Select a pair and compare to see documented differences." /></div>}
        </Card>
      </div>
    </>
  );
}
