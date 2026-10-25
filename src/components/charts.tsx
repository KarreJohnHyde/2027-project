import { useId, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { Table2 } from "lucide-react";
import type { BiomarkerSeries, ChartProvenance } from "../services/api";
import { formatCount, formatDate, formatNumber, humanize } from "../lib/format";
import { IconButton, StatusBadge, Table, Unavailable } from "./ui";

type ChartColors = { series: string[]; ink: string; ink2: string; ink3: string; grid: string; axis: string; surface: string; ramp: string[] };

function subscribeTheme(callback: () => void) {
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
  return () => observer.disconnect();
}

/** Resolve chart tokens for the active theme (SVG attributes need concrete colours). */
export function useChartColors(): ChartColors {
  const theme = useSyncExternalStore(subscribeTheme, () => document.documentElement.dataset.theme ?? "light", () => "light");
  return useMemo(() => {
    const styles = getComputedStyle(document.documentElement);
    const value = (name: string) => styles.getPropertyValue(name).trim();
    return {
      series: [value("--mt-series-1"), value("--mt-series-2"), value("--mt-series-3"), value("--mt-series-4")],
      ink: value("--mt-ink"),
      ink2: value("--mt-ink-2"),
      ink3: value("--mt-ink-3"),
      grid: value("--mt-grid"),
      axis: value("--mt-axis"),
      surface: value("--mt-surface"),
      ramp: theme === "dark" ? ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"] : ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
    };
  }, [theme]);
}

const AXIS_TICK = { fontSize: 11 };

export function ProvenanceFooter({ provenance, status }: { provenance: ChartProvenance; status?: string }) {
  return (
    <footer className="mt-3 border-t border-line pt-3 text-[11px] leading-5 text-ink-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {status && <StatusBadge status={status} />}
        <span><b className="font-medium text-ink-2">Source</b> {provenance.source}</span>
        <span><b className="font-medium text-ink-2">n</b> {provenance.sample_count === null ? "—" : formatCount(provenance.sample_count)} {provenance.sample_count_semantics}</span>
        <span><b className="font-medium text-ink-2">Population</b> {provenance.analysis_population}</span>
        {provenance.time_frame && <span><b className="font-medium text-ink-2">Time frame</b> {provenance.time_frame}</span>}
        <span><b className="font-medium text-ink-2">Model</b> {provenance.model_version ?? "None (descriptive)"}</span>
      </div>
      <p className="mt-1"><b className="font-medium text-ink-2">Metric</b> {provenance.metric_definition}</p>
      {provenance.limitations.length > 0 && <p className="mt-1"><b className="font-medium text-ink-2">Limitations</b> {provenance.limitations.join(" ")}</p>}
    </footer>
  );
}

/** Every chart ships with a table view (the accessibility relief for low-contrast hues). */
export function ChartFrame({ title, subtitle, status, provenance, columns, rows, children, height = 260 }: {
  title: string;
  subtitle?: ReactNode;
  status: string;
  provenance?: ChartProvenance;
  columns: string[];
  rows: Array<Array<ReactNode>>;
  children: ReactNode;
  height?: number;
}) {
  const [tableView, setTableView] = useState(false);
  const unavailable = status === "NOT_AVAILABLE" || rows.length === 0;
  return (
    <figure className="min-w-0 rounded-xl border border-line bg-surface p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <figcaption className="min-w-0">
          <p className="text-sm font-semibold text-ink">{title}</p>
          {subtitle && <p className="mt-0.5 text-xs text-ink-2">{subtitle}</p>}
        </figcaption>
        {!unavailable && <IconButton label={tableView ? "Show chart" : "Show data table"} icon={Table2} active={tableView} onClick={() => setTableView((value) => !value)} />}
      </div>
      <div className="mt-3">
        {unavailable ? (
          <Unavailable code="NOT_AVAILABLE" reason={provenance?.limitations[0] ?? "No data exist for this chart."} />
        ) : tableView ? (
          <div className="max-h-80 overflow-auto">
            <Table headers={columns} dense>
              {rows.map((row, index) => (
                <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
              ))}
            </Table>
          </div>
        ) : (
          <div style={{ height }} className="min-w-0">{children}</div>
        )}
      </div>
      {provenance && <ProvenanceFooter provenance={provenance} status={status} />}
    </figure>
  );
}

function TooltipCard({ title, lines }: { title: ReactNode; lines: Array<[string, ReactNode]> }) {
  return (
    <div className="max-w-xs rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-card">
      <p className="font-medium text-ink">{title}</p>
      {lines.map(([label, value]) => (
        <p key={label} className="mt-0.5 text-ink-2"><span className="text-ink-3">{label}:</span> {value}</p>
      ))}
    </div>
  );
}

/** Horizontal bars for one categorical measure (single series: no legend; the title names it). */
export function BarList({ data, category, value, valueLabel, height }: { data: Array<Record<string, unknown>>; category: string; value: string; valueLabel: string; height?: number }) {
  const colors = useChartColors();
  const rows = data.slice(0, 18);
  return (
    <ResponsiveContainer width="100%" height={height ?? Math.max(140, rows.length * 26 + 30)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }} barCategoryGap={2}>
        <CartesianGrid horizontal={false} stroke={colors.grid} />
        <XAxis type="number" tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} tickFormatter={(tick: number) => formatNumber(tick, 1)} />
        <YAxis type="category" dataKey={category} width={150} tick={{ ...AXIS_TICK, fill: colors.ink2 }} stroke={colors.axis} interval={0} />
        <Tooltip
          cursor={{ fill: colors.grid, opacity: 0.4 }}
          content={({ active, payload }) => active && payload?.length ? <TooltipCard title={String(payload[0].payload[category])} lines={[[valueLabel, formatNumber(Number(payload[0].value))]]} /> : null}
        />
        <Bar dataKey={value} fill={colors.series[0]} radius={[0, 4, 4, 0]} maxBarSize={16} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Grouped bars for two measures in the same unit (legend + direct identity). */
export function GroupedBars({ data, category, series }: { data: Array<Record<string, unknown>>; category: string; series: Array<{ key: string; label: string }> }) {
  const colors = useChartColors();
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }} barGap={2}>
        <CartesianGrid vertical={false} stroke={colors.grid} />
        <XAxis dataKey={category} tick={{ ...AXIS_TICK, fill: colors.ink2 }} stroke={colors.axis} />
        <YAxis tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} width={48} />
        <Tooltip cursor={{ fill: colors.grid, opacity: 0.4 }} content={({ active, payload, label }) => active && payload?.length ? <TooltipCard title={String(label)} lines={payload.map((item) => [String(item.name), formatNumber(Number(item.value))])} /> : null} />
        <Legend wrapperStyle={{ fontSize: 11, color: colors.ink2 }} iconType="square" />
        {series.map((item, index) => <Bar key={item.key} dataKey={item.key} name={item.label} fill={colors.series[index]} radius={[4, 4, 0, 0]} maxBarSize={28} />)}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Observed biomarker values over time. Never extended beyond the last observation. */
export function BiomarkerTrendChart({ series, height = 240 }: { series: BiomarkerSeries; height?: number }) {
  const colors = useChartColors();
  // Use a timezone-neutral timestamp for date-only clinical observations. Creating
  // local midnight and then formatting through ISO shifts the label back one day in
  // positive UTC offsets (for example, 24 Oct appeared as 23 Oct in IST).
  const data = series.points.map((point) => ({ ...point, t: new Date(`${point.date}T00:00:00Z`).getTime() }));
  // Recharts generates repeated automatic ticks (and therefore duplicate React
  // keys) when several observations share a date and the numeric domain collapses
  // to one timestamp. Axis ticks represent observed dates, not observations, so
  // supply the unique timestamps while retaining every point in the line series.
  const observedDateTicks = [...new Set(data.map((point) => point.t))].sort((left, right) => left - right);
  const intervals = new Set(series.points.map((point) => `${point.reference_low}|${point.reference_high}`));
  const sharedInterval = intervals.size === 1 && (series.points[0]?.reference_low !== null || series.points[0]?.reference_high !== null) ? series.points[0] : null;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 10, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid stroke={colors.grid} vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} ticks={observedDateTicks} padding={{ left: 16, right: 16 }} tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} tickFormatter={(tick: number) => formatDate(new Date(tick).toISOString().slice(0, 10))} />
        <YAxis tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} width={48} domain={["auto", "auto"]} />
        {sharedInterval && (
          <ReferenceArea y1={sharedInterval.reference_low ?? undefined} y2={sharedInterval.reference_high ?? undefined} fill={colors.series[2]} fillOpacity={0.08} stroke={colors.series[2]} strokeOpacity={0.35} strokeDasharray="3 3" label={{ value: "Documented interval", position: "insideTopRight", fontSize: 10, fill: colors.ink3 }} />
        )}
        <Tooltip
          content={({ active, payload }) => {
            const point = active && payload?.length ? (payload[0].payload as (typeof data)[number]) : null;
            return point ? (
              <TooltipCard
                title={`${formatNumber(point.value, 3)} ${series.unit} · ${formatDate(point.date)}`}
                lines={[
                  ["Documented", `${point.documented_value} ${point.documented_unit}${point.unit_converted ? " (converted)" : ""}`],
                  ["Date source", humanize(point.date_source)],
                  ["Source", `upload #${point.source_file_id}: “${point.source_span}”`],
                  ...(point.documented_flag ? ([["Flag in source", point.documented_flag]] as Array<[string, ReactNode]>) : []),
                ]}
              />
            ) : null;
          }}
        />
        <Line type="linear" dataKey="value" name={series.display_name} stroke={colors.series[0]} strokeWidth={2} dot={{ r: 4, fill: colors.series[0], stroke: colors.surface, strokeWidth: 2 }} activeDot={{ r: 6 }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/**
 * Observed values followed by the requested horizon drawn as a hatched,
 * explicitly labelled UNAVAILABLE region. No value is placed in that region.
 */
export function ObservedHorizonChart({ series, horizonDays, height = 180 }: { series: BiomarkerSeries; horizonDays: number; height?: number }) {
  const colors = useChartColors();
  const patternId = `hatch-${useId().replace(/:/g, "")}`;
  const data = series.points.map((point) => ({ ...point, t: new Date(`${point.date}T00:00:00Z`).getTime() }));
  if (data.length === 0) return null;
  const first = data[0].t;
  const last = data[data.length - 1].t;
  const horizonEnd = last + horizonDays * 86_400_000;
  // Explicit, unique domain landmarks prevent Recharts from generating repeated
  // ticks (and duplicate React keys) when many observations share one date.
  const horizonTicks = [...new Set([first, last, horizonEnd])].sort((left, right) => left - right);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 10, right: 12, bottom: 4, left: 0 }}>
        <defs>
          <pattern id={patternId} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke={colors.ink3} strokeOpacity={0.5} strokeWidth={1.5} />
          </pattern>
        </defs>
        <CartesianGrid stroke={colors.grid} vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={[first, horizonEnd]} ticks={horizonTicks} tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} tickFormatter={(tick: number) => formatDate(new Date(tick).toISOString().slice(0, 10))} />
        <YAxis tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} width={44} domain={["auto", "auto"]} />
        <ReferenceArea x1={last} x2={horizonEnd} fill={`url(#${patternId})`} stroke={colors.axis} strokeDasharray="3 3" label={{ value: "Forecast unavailable", position: "insideTop", fontSize: 10, fill: colors.ink2 }} />
        <Tooltip content={({ active, payload }) => active && payload?.length ? <TooltipCard title={`${formatNumber(Number(payload[0].payload.value), 3)} ${series.unit}`} lines={[["Observed", formatDate(String(payload[0].payload.date))], ["Source", `upload #${payload[0].payload.source_file_id}`]]} /> : null} />
        <Line type="linear" dataKey="value" stroke={colors.series[0]} strokeWidth={2} dot={{ r: 4, fill: colors.series[0], stroke: colors.surface, strokeWidth: 2 }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** ROC or PR curve from uploaded held-out predictions, with the chance reference. */
export function CurveChart({ points, x, y, xLabel, yLabel, chance }: { points: Array<Record<string, number | null>>; x: string; y: string; xLabel: string; yLabel: string; chance?: "diagonal" | number }) {
  const colors = useChartColors();
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 18, left: 4 }}>
        <CartesianGrid stroke={colors.grid} />
        <XAxis dataKey={x} type="number" domain={[0, 1]} tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} label={{ value: xLabel, position: "insideBottom", offset: -10, fontSize: 11, fill: colors.ink2 }} />
        <YAxis type="number" domain={[0, 1]} tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} width={40} label={{ value: yLabel, angle: -90, position: "insideLeft", fontSize: 11, fill: colors.ink2 }} />
        {chance === "diagonal" && <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={colors.axis} strokeDasharray="4 4" />}
        {typeof chance === "number" && <ReferenceLine y={chance} stroke={colors.axis} strokeDasharray="4 4" label={{ value: "Prevalence", fontSize: 10, fill: colors.ink3, position: "insideTopLeft" }} />}
        <Tooltip content={({ active, payload }) => active && payload?.length ? <TooltipCard title="Operating point" lines={[[xLabel, formatNumber(Number(payload[0].payload[x]), 3)], [yLabel, formatNumber(Number(payload[0].payload[y]), 3)], ["Threshold", formatNumber(payload[0].payload.threshold as number | null, 3)]]} /> : null} />
        <Line type="stepAfter" dataKey={y} stroke={colors.series[0]} strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Reliability diagram: observed fraction against mean predicted probability per bin. */
export function CalibrationChart({ bins }: { bins: Array<{ mean_predicted: number; observed_fraction: number; count: number }> }) {
  const colors = useChartColors();
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 8, right: 16, bottom: 18, left: 4 }}>
        <CartesianGrid stroke={colors.grid} />
        <XAxis dataKey="mean_predicted" type="number" domain={[0, 1]} tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} label={{ value: "Mean predicted probability", position: "insideBottom", offset: -10, fontSize: 11, fill: colors.ink2 }} />
        <YAxis dataKey="observed_fraction" type="number" domain={[0, 1]} tick={{ ...AXIS_TICK, fill: colors.ink3 }} stroke={colors.axis} width={40} label={{ value: "Observed fraction", angle: -90, position: "insideLeft", fontSize: 11, fill: colors.ink2 }} />
        <ZAxis dataKey="count" range={[60, 260]} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={colors.axis} strokeDasharray="4 4" />
        <Tooltip content={({ active, payload }) => active && payload?.length ? <TooltipCard title="Calibration bin" lines={[["Mean predicted", formatNumber(Number(payload[0].payload.mean_predicted), 3)], ["Observed", formatNumber(Number(payload[0].payload.observed_fraction), 3)], ["Rows", formatCount(Number(payload[0].payload.count))]]} /> : null} />
        <Scatter data={bins} fill={colors.series[0]} stroke={colors.surface} strokeWidth={2} isAnimationActive={false} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

/** Confusion matrix as an ordinal-intensity grid with the counts printed in every cell. */
export function ConfusionMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const colors = useChartColors();
  const max = Math.max(1, ...matrix.flat());
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-0.5 text-xs tabular">
        <thead>
          <tr>
            <th className="p-1 text-left font-medium text-ink-3">True ↓ / Pred →</th>
            {labels.map((label) => <th key={label} className="p-1 font-medium text-ink-2">{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, rowIndex) => (
            <tr key={labels[rowIndex]}>
              <th scope="row" className="p-1 text-left font-medium text-ink-2">{labels[rowIndex]}</th>
              {row.map((count, columnIndex) => {
                const step = Math.min(colors.ramp.length - 1, Math.floor((count / max) * (colors.ramp.length - 1)));
                const dark = step >= 2;
                return (
                  <td key={columnIndex} className="h-11 min-w-16 rounded-md text-center font-medium" style={{ background: colors.ramp[step], color: dark ? "#ffffff" : "#0b0b0b" }} title={`${count} rows`}>
                    {formatCount(count)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
