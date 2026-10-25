import { useState } from "react";
import { BiomarkerTrendChart, ChartFrame } from "../components/charts";
import { Card, EmptyState, ErrorBlock, KeyValue, LoadingBlock, Metric, PageHeader, SelectInput, StatusBadge, Table, Unavailable } from "../components/ui";
import { LabReportsCard } from "../components/LabEntry";
import { api, type BiomarkerSeries, type TrendPoint, type TrendStatistic } from "../services/api";
import { formatDate, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

function Statistic({ label, value }: { label: string; value: TrendStatistic | undefined }) {
  if (!value) return null;
  if (value.status !== "COMPUTED") {
    return <tr><td className="text-ink-2">{label}</td><td colSpan={2}><StatusBadge status={value.status} />{value.required && <span className="ml-2 text-[11px] text-ink-3">needs n ≥ {value.required}</span>}</td></tr>;
  }
  const interval = value.slope_95ci_per_year;
  return (
    <tr>
      <td className="text-ink-2">{label}</td>
      <td className="tabular text-ink">
        {value.slope_per_year !== undefined && <>{formatNumber(value.slope_per_year, 3)} / yr{interval && <span className="text-ink-3"> (95% CI {formatNumber(interval[0], 3)} to {formatNumber(interval[1], 3)})</span>}</>}
        {value.kendall_tau !== undefined && <>τ {formatNumber(value.kendall_tau, 3)}, p {formatNumber(value.p_value_two_sided, 3)}</>}
        {value.r_squared !== undefined && <span className="block text-[11px] text-ink-3">R² {formatNumber(value.r_squared, 3)} · p(slope=0) {formatNumber(value.p_value_slope_zero, 3)}</span>}
      </td>
      <td className="max-w-xs text-[11px] leading-4 text-ink-3">{value.assumptions}</td>
    </tr>
  );
}

function pointSource(point: TrendPoint): string {
  if (point.source_type === "MANUAL_TRANSCRIPTION") return `lab report #${point.lab_report_id} (transcribed${point.source_file_id ? `, upload #${point.source_file_id}` : ", no source linked"})`;
  return `upload #${point.source_file_id}`;
}

function SeriesCard({ series }: { series: BiomarkerSeries }) {
  const analysis = series.analysis;
  const dates = series.points.map((point) => point.date);
  const transcribed = series.points.filter((point) => point.source_type === "MANUAL_TRANSCRIPTION").length;
  return (
    <div className="space-y-3">
      <ChartFrame
        title={`${series.display_name} (${series.unit})`}
        subtitle={series.canonical_code ? `LOINC ${series.canonical_code} · ${humanize(series.association)}` : humanize(series.association)}
        status={series.points.length ? "OBSERVED" : "NOT_AVAILABLE"}
        provenance={{
          source: transcribed ? "Source-linked case measurements and clinician transcriptions" : "Source-linked case measurements",
          sample_count: series.points.length,
          sample_count_semantics: "dated observations",
          analysis_population: "This case only",
          time_frame: dates.length ? `${formatDate(dates[0])} – ${formatDate(dates[dates.length - 1])}` : null,
          model_version: null,
          metric_definition: "Documented value per dated observation; dates from the source when documented, otherwise the examination date.",
          limitations: [
            ...(series.identity_review_required ? ["Sizes from different reports may describe different lesions; identity across reports is not verified."] : []),
            ...(series.conversions.length ? [`Converted ${series.conversions.join(", ")} using ${series.conversion_source}`] : []),
            ...(transcribed ? [`${transcribed} value(s) were transcribed manually; transcription is not verified against the source document.`] : []),
            "Descriptive only: no forecast, trend interpretation or reference-range judgement.",
          ],
        }}
        columns={["Date", "Value", "Documented", "Flag", "Source"]}
        rows={series.points.map((point) => [formatDate(point.date), `${formatNumber(point.value, 4)} ${series.unit}`, `${point.result_operator === "=" ? "" : point.result_operator}${point.documented_value} ${point.documented_unit}`, point.documented_flag ?? "—", pointSource(point)])}
        height={220}
      >
        <BiomarkerTrendChart series={series} height={220} />
      </ChartFrame>
      <Card title="Change statistics" eyebrow={humanize(analysis.status)}>
        {analysis.status !== "COMPUTED" ? (
          <Unavailable compact code={analysis.status} reason={analysis.reason} />
        ) : (
          <>
            <KeyValue columns={3} items={[
              { label: "First → last", value: `${formatNumber(analysis.first?.value, 4)} → ${formatNumber(analysis.last?.value, 4)} ${series.unit}` },
              { label: "Absolute change (Δx)", value: `${formatNumber(analysis.absolute_change, 4)} ${series.unit}` },
              { label: "Percent change (Δx%)", value: analysis.percent_change === null || analysis.percent_change === undefined ? humanize(analysis.percent_change_status) : `${formatNumber(analysis.percent_change, 2)}%` },
              { label: "Interval (Δt)", value: `${analysis.interval_days} days` },
              { label: "Rate (Δx/Δt)", value: analysis.rate_per_year === null || analysis.rate_per_year === undefined ? "—" : `${formatNumber(analysis.rate_per_year, 4)} ${series.unit}/yr` },
              { label: "Observations", value: `${analysis.n} on ${analysis.distinct_dates} dates` },
            ]} />
            <div className="mt-3">
              <Table headers={["Trend estimator", "Estimate", "Assumptions"]} dense>
                <Statistic label="Ordinary least squares" value={analysis.ols} />
                <Statistic label="Theil–Sen (robust)" value={analysis.theil_sen} />
                <Statistic label="Mann–Kendall" value={analysis.mann_kendall} />
              </Table>
            </div>
          </>
        )}
        {series.excluded.length > 0 && <p className="mt-2 text-[11px] text-ink-3">Excluded: {series.excluded.map((item) => `${item.measurement_id !== null ? `measurement #${item.measurement_id}` : `lab report #${item.lab_report_id}`} ${humanize(item.reason)}`).join("; ")}</p>}
      </Card>
    </div>
  );
}

export default function BiomarkerAnalyticsPage() {
  const selected = useSelectedCase()!;
  const evidenceVersion = useWorkspace((state) => state.evidenceVersion);
  const uploads = useWorkspace((state) => state.evidence.uploads);
  const trends = useAsync(() => api.getBiomarkerTrends(selected.id), [selected.id, evidenceVersion]);
  const egfr = useAsync(() => api.getEgfr(selected.id), [selected.id, evidenceVersion]);
  const [system, setSystem] = useState("ALL");
  const series = trends.data?.series ?? [];
  const systems = [...new Set(series.map((item) => item.anatomy_system ?? "systemic"))].sort();
  const shown = series.filter((item) => system === "ALL" || (item.anatomy_system ?? "systemic") === system);

  return (
    <>
      <PageHeader
        eyebrow="Biomarker Analytics"
        title="Documented measurements over time"
        description="Series contain only documented values. Units are converted only through registered SI factors, and statistics are tiered by the number of dated observations."
        actions={systems.length > 1 && <div className="w-48"><SelectInput aria-label="System filter" value={system} onChange={(event) => setSystem(event.target.value)}><option value="ALL">All systems</option>{systems.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</SelectInput></div>}
      />
      {trends.error && <ErrorBlock message={trends.error} onRetry={trends.reload} />}
      {trends.loading && !trends.data && <LoadingBlock label="Building series" />}
      {trends.data && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Metric label="Measured analytes" value={series.length} />
          <Metric label="Dated observations" value={series.reduce((sum, item) => sum + item.points.length, 0)} />
          <Metric label="Series with trend estimates" value={series.filter((item) => item.analysis.ols?.status === "COMPUTED").length} note="Require ≥ 3 dated observations" />
        </div>
      )}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          {trends.data && shown.length === 0 && <EmptyState title="No measurements" detail="Process reports linked to dated examinations, or transcribe dated laboratory results, to build series." />}
          {shown.map((item) => <SeriesCard key={item.name} series={item} />)}
          <LabReportsCard caseId={selected.id} uploads={uploads} onChanged={trends.reload} />
        </div>
        <div className="min-w-0 space-y-4">
          <Card title="eGFR (CKD-EPI 2021)" eyebrow="Calculated from documented inputs">
            {egfr.data ? (
              <div className="space-y-3">
                <p className="text-xs leading-5 text-ink-2">{egfr.data.equation.display}. {egfr.data.equation.citation}</p>
                {egfr.data.results.length === 0 ? <Unavailable compact code="NO_CREATININE_DOCUMENTED" reason="No creatinine value is documented in this case." /> : egfr.data.results.map((result) => (
                  <div key={result.creatinine_measurement_id} className="rounded-lg border border-line p-2.5">
                    <p className="text-xs text-ink-2">Creatinine {result.documented_creatinine.value} {result.documented_creatinine.unit}{result.documented_date ? ` · ${formatDate(result.documented_date)}` : ""}</p>
                    {result.value !== null ? (
                      <p className="mt-1 text-lg font-semibold text-ink">{formatNumber(result.value, 1)} <span className="text-xs font-normal text-ink-2">{result.unit}</span></p>
                    ) : (
                      <div className="mt-1.5"><Unavailable compact code={result.status} reason={(result.missing_or_invalid_inputs ?? []).map(humanize).join("; ")} /></div>
                    )}
                    {result.inputs && <p className="mt-1 text-[11px] text-ink-3">Age {result.inputs.age_years} ({result.inputs.age_source.same_source_as_creatinine ? "same report" : "another case report"}), sex {result.inputs.sex}</p>}
                  </div>
                ))}
                <ul className="list-disc space-y-0.5 pl-4 text-[11px] leading-4 text-ink-3">{egfr.data.equation.caveats.map((caveat) => <li key={caveat}>{caveat}</li>)}</ul>
              </div>
            ) : <p className="text-sm text-ink-2">{egfr.error ?? "Loading…"}</p>}
          </Card>
          <Card title="Method">
            <ul className="space-y-1.5 text-xs leading-5 text-ink-2">
              <li>Δx = x<sub>last</sub> − x<sub>first</sub>; Δx% = 100·Δx/|x<sub>first</sub>| only for a non-zero baseline; rate = Δx/Δt.</li>
              <li>OLS slope with a t-based 95% interval and Theil–Sen slope from n ≥ 3; Mann–Kendall from n ≥ 4.</li>
              <li>ARIMA, state-space and change-point models are not fitted to single-patient series this short.</li>
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
