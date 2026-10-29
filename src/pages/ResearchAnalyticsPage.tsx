import type { ReactNode } from "react";
import { BarList, ChartFrame, GroupedBars } from "../components/charts";
import { Card, ErrorBlock, LoadingBlock, PageHeader, StatusBadge, Table, Unavailable } from "../components/ui";
import { api, type AnalyticsChart } from "../services/api";
import { formatCount, formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";

function columnsOf(chart: AnalyticsChart): string[] {
  return chart.data.length ? Object.keys(chart.data[0]).filter((key) => typeof chart.data[0][key] !== "object") : [];
}

function rowsOf(chart: AnalyticsChart, columns: string[]): ReactNode[][] {
  return chart.data.map((row) => columns.map((column) => (typeof row[column] === "number" ? formatNumber(row[column] as number, 3) : String(row[column] ?? "—"))));
}

function SimpleBarChart({ chart, category, value, valueLabel }: { chart: AnalyticsChart; category: string; value: string; valueLabel: string }) {
  const columns = columnsOf(chart);
  return (
    <ChartFrame title={chart.title} status={chart.status} provenance={chart.provenance} columns={columns} rows={rowsOf(chart, columns)} height={Math.max(140, Math.min(chart.data.length, 18) * 26 + 30)}>
      <BarList data={chart.data} category={category} value={value} valueLabel={valueLabel} />
    </ChartFrame>
  );
}

const BAR_SPECS: Record<string, [string, string, string]> = {
  dataset_file_counts: ["dataset", "files", "Media files"],
  dataset_extensions: ["extension", "files", "Files"],
  dataset_readiness: ["state", "datasets", "Datasets"],
  dataset_licenses: ["license_status", "datasets", "Datasets"],
  anatomy_licenses: ["license_class", "assets", "Assets"],
  model_status: ["status", "models", "Models"],
  case_uploads: ["modality", "uploads", "Uploads"],
  case_statements: ["assertion", "statements", "Statements"],
  case_analytes: ["analyte", "measurements", "Measurements"],
  case_reference_positions: ["position", "measurements", "Measurements"],
};

function ChartFor({ chart }: { chart: AnalyticsChart }) {
  if (chart.status === "NOT_AVAILABLE" || chart.data.length === 0) {
    return <ChartFrame title={chart.title} status="NOT_AVAILABLE" provenance={chart.provenance} columns={[]} rows={[]}>{null}</ChartFrame>;
  }
  const spec = BAR_SPECS[chart.id];
  if (spec) return <SimpleBarChart chart={chart} category={spec[0]} value={spec[1]} valueLabel={spec[2]} />;
  if (chart.id === "annotation_pairing") {
    const columns = columnsOf(chart);
    return (
      <ChartFrame title={chart.title} status={chart.status} provenance={chart.provenance} columns={columns} rows={rowsOf(chart, columns)}>
        <GroupedBars data={chart.data} category="dataset" series={[{ key: "image_files", label: "Images" }, { key: "mask_files", label: "Masks" }, { key: "matching_stems", label: "Matched stems" }]} />
      </ChartFrame>
    );
  }
  if (chart.id === "software_benchmarks") {
    const kinds = [...new Set(chart.data.map((row) => String(row.kind)))];
    return (
      <div className="space-y-4">
        {kinds.map((kind) => {
          const rows: Array<Record<string, unknown>> = chart.data.filter((row) => row.kind === kind).map((row) => ({ ...row, label: `${row.concurrency}× · ${String(row.artifact).replace(/^.*benchmark-/, "").replace(/\.json$/, "")}` }));
          return (
            <ChartFrame key={kind} title={`${humanize(kind)} latency (ms)`} subtitle="Median across repeats" status={chart.status} provenance={chart.provenance}
              columns={["Run", "p50 ms", "p95 ms", "Throughput", "Attempted", "Failed", "Peak RSS MB"]}
              rows={rows.map((row) => [String(row.label), formatNumber(row.p50_ms as number), formatNumber(row.p95_ms as number), formatNumber(row.throughput as number), formatCount(row.attempted as number), formatCount(row.failed as number), formatNumber(row.peak_rss_mb as number)])}>
              <GroupedBars data={rows} category="label" series={[{ key: "p50_ms", label: "p50" }, { key: "p95_ms", label: "p95" }]} />
            </ChartFrame>
          );
        })}
      </div>
    );
  }
  if (chart.id === "anatomy_compression") {
    const rows: Array<Record<string, unknown> & { ratio: number }> = chart.data
      .map((row) => ({ ...row, ratio: Number(row.standard_mb) > 0 ? Number(row.source_mb) / Number(row.standard_mb) : 0 }))
      .sort((left, right) => right.ratio - left.ratio);
    return (
      <ChartFrame title="Standard-tier size reduction (source MB ÷ derived MB)" subtitle="Triangle count unchanged in the standard tier" status={chart.status} provenance={chart.provenance}
        columns={["Variant", "System", "Source MB", "Standard MB", "Preview MB", "Triangles", "Bounds deviation"]}
        rows={rows.map((row) => [String(row.variant), String(row.system), formatNumber(row.source_mb as number), formatNumber(row.standard_mb as number), row.preview_mb === null ? "—" : formatNumber(row.preview_mb as number), formatCount(row.triangles as number), formatNumber(row.bounds_deviation as number, 8)])}
        height={Math.min(rows.length, 18) * 26 + 30}>
        <BarList data={rows} category="variant" value="ratio" valueLabel="Reduction ×" />
      </ChartFrame>
    );
  }
  if (chart.id.startsWith("ocr_")) {
    // One group per engine, one bar per page condition (benchmarks/ocr_benchmark.py).
    const conditions = Object.keys(chart.data[0] ?? {}).filter((key) => key !== "engine");
    return (
      <ChartFrame title={chart.title} subtitle="Synthetic report pages; see limitations" status={chart.status} provenance={chart.provenance}
        columns={["Engine", ...conditions.map((condition) => humanize(condition))]}
        rows={chart.data.map((row) => [String(row.engine), ...conditions.map((condition) => (row[condition] == null ? "—" : formatNumber(row[condition] as number, 2)))])}>
        <GroupedBars data={chart.data} category="engine" series={conditions.map((condition) => ({ key: condition, label: humanize(condition) }))} />
      </ChartFrame>
    );
  }
  if (chart.id === "evaluation_runs") {
    return (
      <Card title={chart.title} padded={false}>
        <Table headers={["Run", "Task", "Dataset", "n", "Headline metrics", "Input SHA-256"]} dense>
          {chart.data.map((row) => <tr key={String(row.run_id)}><td>#{String(row.run_id)}</td><td>{humanize(String(row.task_type))}</td><td>{String(row.dataset ?? "—")}</td><td className="tabular">{formatCount(row.n as number)}</td><td className="text-xs">{Object.entries((row.headline ?? {}) as Record<string, number>).slice(0, 4).map(([key, value]) => `${key} ${formatNumber(value, 3)}`).join(" · ")}</td><td><code className="text-[11px]">{String(row.input_sha256).slice(0, 12)}…</code></td></tr>)}
        </Table>
      </Card>
    );
  }
  return null;
}

const SECTION_TITLES: Record<string, string> = {
  datasets: "Datasets",
  software: "Software performance",
  ocr: "OCR engine comparison",
  anatomy: "Anatomy asset pipeline",
  models: "Models and evaluation",
  cases: "Authorised case evidence",
};

export default function ResearchAnalyticsPage() {
  const analytics = useAsync(() => api.getResearchAnalytics(), []);
  if (analytics.error) return <ErrorBlock message={analytics.error} onRetry={analytics.reload} />;
  if (!analytics.data) return <LoadingBlock label="Computing analytics" />;
  return (
    <>
      <PageHeader eyebrow="Research Analytics" title="Workspace analytics" description="Every chart is computed from a real workspace artifact and states its source, sample count, population, time frame, model version, metric definition and limitations. Charts without data are shown as unavailable rather than illustrated." />
      {Object.entries(analytics.data.sections).map(([section, charts]) => (
        <section key={section} className="mb-6">
          <h2 className="mb-3 text-sm font-semibold text-ink">{SECTION_TITLES[section] ?? humanize(section)}</h2>
          <div className="grid gap-4 xl:grid-cols-2">{charts.map((chart) => <div key={chart.id} className={chart.id === "software_benchmarks" || chart.id === "anatomy_compression" ? "xl:col-span-2" : ""}><ChartFor chart={chart} /></div>)}</div>
        </section>
      ))}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-ink">Unavailable by design</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {analytics.data.unavailable_by_design.map((item) => <Unavailable key={item.chart} code="NOT_AVAILABLE" reason={<><b className="font-medium text-ink">{item.chart}.</b> {item.reason}</>} />)}
        </div>
      </section>
      <p className="mt-6 text-xs text-ink-3">Test evidence: <StatusBadge status={String(analytics.data.test_evidence.status ?? "AVAILABLE")} /></p>
    </>
  );
}
